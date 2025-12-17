import logging
from simple_pid import PID
from homeassistant.core import HomeAssistant, State
from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.const import ATTR_TEMPERATURE, STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfTemperature
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    ATTR_COMPENSATED_TEMP,
    CONF_INDOOR_SENSOR,
    CONF_KD_ENTITY,
    CONF_KI_ENTITY,
    CONF_KP_ENTITY,
    CONF_WEATHER_FACTOR_ENTITY,
    CONF_OUTDOOR_SENSOR,
    DOMAIN,
    MAX_TEMP_DIFFERENCE
)

_LOGGER = logging.getLogger(__name__)

# Define TEMP_CELSIUS here for compatibility
TEMP_CELSIUS = UnitOfTemperature.CELSIUS

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Set up the climate platform from a Config Entry (UI)."""

    config = config_entry.data
    pid_climate = PIDClimateController(hass, config_entry)

    async_add_entities([pid_climate])

class PIDClimateController(ClimateEntity, RestoreEntity):
    """Represents a PID-based Climate entity for heating compensation."""

    MAX_TEMP_DIFFERENCE = MAX_TEMP_DIFFERENCE
    DEFAULT_TARGET_TEMP = 20.0 # Default setpoint (if none is saved)

    _attr_hvac_mode = HVACMode.HEAT
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = TEMP_CELSIUS

    def __init__(self, hass, config_entry):
        """Initialize the PID Climate entity."""
        self.hass = hass
        self._config_entry_id = config_entry.entry_id

        # Read config (prioritizes options over initial config data)
        config = config_entry.options if config_entry.options else config_entry.data

        prefix = "number." + config.get("name").lower().replace(" ", "_")

        # PID Entity IDs for dynamic tuning
        self._kp_entity_id = f"{prefix}_kp"
        self._ki_entity_id = f"{prefix}_ki"
        self._kd_entity_id = f"{prefix}_kd"
        self._weather_factor_entity_id = f"{prefix}_weather_factor"

        # Configuration
        self._attr_name = config.get("name")
        self._indoor_sensor = config[CONF_INDOOR_SENSOR]
        self._outdoor_sensor = config[CONF_OUTDOOR_SENSOR]

        # State variables
        self._attr_target_temperature = self.DEFAULT_TARGET_TEMP
        self._attr_current_temperature = None
        self._is_on = True
        self._compensated_temp_value = None
        self._real_outdoor_temp_value = None
        # weather_factor is initialized here, dynamically updated in _async_update_loop
        self._weather_factor = 1.0 

        # PID-instance (Anti-Windup limits set dynamically)
        self.pid = PID(
            Kp=0, Ki=0, Kd=0, 
            output_limits=(-self.MAX_TEMP_DIFFERENCE, self.MAX_TEMP_DIFFERENCE)
        )
        self._LOGGER = logging.getLogger(f"{__name__}.{self._attr_name}")

    @property
    def unique_id(self):
        return f"{self._config_entry_id}_pid_climate"

    async def async_added_to_hass(self) -> None:
        """Called when the entity is added to HA. Used to restore state and set up listeners."""
        
        # Retrieve the last saved state
        last_state: State | None = await self.async_get_last_state()
        
        if last_state:
            # Try to restore the last set target temperature
            if last_state.attributes.get(ATTR_TEMPERATURE) is not None:
                self._attr_target_temperature = float(last_state.attributes[ATTR_TEMPERATURE])
            else:
                self._attr_target_temperature = self.DEFAULT_TARGET_TEMP
                
            # Restore HVAC mode
            if last_state.state in (HVACMode.HEAT, HVACMode.OFF):
                self._attr_hvac_mode = last_state.state
                self._is_on = self._attr_hvac_mode == HVACMode.HEAT
            else:
                self._attr_hvac_mode = HVACMode.OFF
                self._is_on = False

        # If no previous state was found, use the default target temperature
        if self._attr_target_temperature is None:
            self._attr_target_temperature = self.DEFAULT_TARGET_TEMP
        
        # Set PID setpoint
        self.pid.setpoint = self._attr_target_temperature

        # Set up listeners for PID Input Numbers (Kp, Ki, Kd)
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, 
                [self._kp_entity_id, self._ki_entity_id, self._kd_entity_id, self._weather_factor_entity_id], 
                self._update_pid_k_values
            )
        )

        # Set up listeners for primary sensors (Indoor and Outdoor temp)
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._indoor_sensor, self._outdoor_sensor], self._async_update_loop
            )
        )

        # Initialize PID K-values from Input Numbers
        self._update_pid_k_values()

        # Manually call update loop once to initialize T_comp immediately on startup.   
        # We pass None as event since it's a manual call.
        await self._async_update_loop(None)

    async def _async_update_loop(self, event):
        """Main loop: Runs PID calculation, applies constraints, and updates attributes."""
        
        # 1. Check availability and fetch sensor values
        T_indoor = self._get_float_state(self._indoor_sensor)
        T_real_outdoor = self._get_float_state(self._outdoor_sensor)
        weather_factor = self._get_float_state(self._weather_factor_entity_id)

        self._weather_factor = weather_factor if weather_factor is not None else 1.0

        # Update real outdoor temperature attribute (for monitoring)
        self._real_outdoor_temp_value = T_real_outdoor

        # --- RESTORING LOGIC FOR NONE VALUES (Fixes startup warnings/aborts) ---

        if T_indoor is None:
            last_state = self.hass.states.get(self._indoor_sensor)
            if last_state and last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
                try:
                    T_indoor = float(last_state.state)
                except ValueError:
                    pass 

        if T_real_outdoor is None:
            last_state = self.hass.states.get(self._outdoor_sensor)
            if last_state and last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
                try:
                    T_real_outdoor = float(last_state.state)
                except ValueError:
                    pass

        # If T_indoor/T_real_outdoor are STILL None after attempted restoration, abort.
        if T_indoor is None or T_real_outdoor is None:
            self._LOGGER.warning("Could not fetch valid temperature values for PID calculation (Sensors still loading).")
            return

        self._attr_current_temperature = T_indoor

        # 2. Handle OFF mode
        if not self._is_on:
            # If system is OFF, T_comp is set to T_real_outdoor (or a high value) 
            # to ensure the heat pump does not heat.
            T_comp = T_real_outdoor
            self._compensated_temp_value = round(T_comp, 1)
            self.async_write_ha_state()
            return
        
        try:
            # 3. Calculate the raw correction (Delta T)
            delta_T = self.pid(T_indoor)
            
            # 4. Calculate raw T_comp, applying the weather factor
            T_comp = T_real_outdoor + (delta_T * self._weather_factor)

            # --- IMPLEMENTATION OF SAFETY CONSTRAINTS (Clamping) ---
            
            # Rule: If it is freezing outside, the simulated value must not be positive.
            if T_real_outdoor < 0:
                # T_comp must not be greater than 0.0
                T_comp = min(0.0, T_comp)
            
            # 5. Update state and attributes
            self._compensated_temp_value = round(T_comp, 1)
            self.async_write_ha_state()
            
            self._LOGGER.debug(
                f"PID: T_setpoint={self._attr_target_temperature:.1f}, "
                f"T_current={T_indoor:.1f}, Delta_T={delta_T:.2f}, "
                f"Factor={self._weather_factor}, "
                f"T_real_out={T_real_outdoor:.1f}, T_comp={T_comp:.1f}"
            )

        except Exception as e:
            self._LOGGER.error(f"Error during PID calculation or update: {e}")

    async def async_set_temperature(self, **kwargs):
        """Sets the new target setpoint (Target Temperature)."""
        target_temp = kwargs.get(ATTR_TEMPERATURE)
        if target_temp is not None:
            self._attr_target_temperature = target_temp
            self.pid.setpoint = target_temp

            # KORRIGERING (FUTURE-PROOF): Use async_create_task instead of async_add_job
            self.hass.async_create_task(
                self._async_update_loop(
                    {'data': {'new_state': self.hass.states.get(self._indoor_sensor)}}
                )
            )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode):
        """Sets the operating mode (HEAT/OFF)."""
        if hvac_mode == HVACMode.HEAT:
            self._is_on = True
            # KORRIGERING (FUTURE-PROOF): Use async_create_task instead of async_add_job
            self.hass.async_create_task(
                self._async_update_loop(
                    {'data': {'new_state': self.hass.states.get(self._indoor_sensor)}}
                )
            )
        else:
            self._is_on = False
        
        self._attr_hvac_mode = hvac_mode
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        """Exposes the calculated temperature and PID terms as attributes."""
        # Ensure value is not None
        compensated_temp = self._compensated_temp_value if self._compensated_temp_value is not None else 'N/A'
        real_outdoor_temperature = self._real_outdoor_temp_value if self._real_outdoor_temp_value is not None else 'N/A'
        
        # Collect all attributes
        attributes = {
            ATTR_COMPENSATED_TEMP: compensated_temp, # The compensated temperature (T_comp)
            "PID_Kp": self.pid.Kp,
            "PID_Ki": self.pid.Ki,
            "PID_Kd": self.pid.Kd,
            "PID_setpoint": self.pid.setpoint,
            "real_outdoor_temperature": real_outdoor_temperature,
            "weather_factor": self._weather_factor,
        }
        return attributes

    def _get_float_state(self, entity_id):
        """Fetches and converts an entity's state to float safely."""
        from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN 
        
        state = self.hass.states.get(entity_id)
        if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
            try:
                return float(state.state)
            except ValueError:
                self._LOGGER.error(f"Could not convert state '{state.state}' for {entity_id} to float.")
        return None # Returns None if value is invalid or missing

    def _update_pid_k_values(self, event=None):
        """Reads the latest K values from Input Numbers and updates the PID instance."""
        
        kp = self._get_k_value(self._kp_entity_id)
        ki = self._get_k_value(self._ki_entity_id)
        kd = self._get_k_value(self._kd_entity_id)
        
        # Only update PID instance if values are valid (not None)
        if kp is not None and ki is not None and kd is not None:
            self.pid.Kp = kp
            self.pid.Ki = ki
            self.pid.Kd = kd
            self._LOGGER.debug(f"PID parameters updated: Kp={kp}, Ki={ki}, Kd={kd}")
            
        # If called by an Input Number change, trigger a Climate entity update via main loop
        if event:
            # KORRIGERING (FUTURE-PROOF): Use async_create_task instead of async_add_job
            self.hass.async_create_task(
                self._async_update_loop(event) # Pass the event to trigger the main loop calculation
            )
        
    def _get_k_value(self, entity_id):
        """Fetches the current float value for an Input Number entity."""
        try:
            state = self.hass.states.get(entity_id)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                return float(state.state)
        except (ValueError, TypeError):
            self._LOGGER.error(f"Could not convert state for {entity_id} to float.")
            return None # Returns None on error
