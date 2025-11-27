import logging

from simple_pid import PID
from homeassistant.core import HomeAssistant, State
from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.const import ATTR_TEMPERATURE, STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfTemperature
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    DOMAIN, CONF_INDOOR_SENSOR, CONF_OUTDOOR_SENSOR,
    ATTR_COMPENSATED_TEMP, MAX_TEMP_DIFFERENCE,
    CONF_KP_ENTITY, CONF_KI_ENTITY, CONF_KD_ENTITY
)

_LOGGER = logging.getLogger(__name__)
TEMP_CELSIUS = UnitOfTemperature.CELSIUS

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Sets the climate platform from a Config Entry (UI)."""

    config = config_entry.data 
    pid_climate = PIDClimateController(hass, config)

    async_add_entities([pid_climate])

class PIDClimateController(ClimateEntity, RestoreEntity):
    """Represents a PID-based Climate entity for heat compensation."""

    _attr_hvac_mode = HVACMode.HEAT
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = TEMP_CELSIUS

    def __init__(self, hass, config):
        self.hass = hass

        self._kp_entity_id = config.get(CONF_KP_ENTITY)
        self._ki_entity_id = config.get(CONF_KI_ENTITY)
        self._kd_entity_id = config.get(CONF_KD_ENTITY)

        # Configuration
        self._attr_name = config.get("name")
        self._indoor_sensor = config[CONF_INDOOR_SENSOR]
        self._outdoor_sensor = config[CONF_OUTDOOR_SENSOR]

        # State variables
        self._attr_target_temperature = 20.0
        self._attr_current_temperature = None
        self._is_on = True
        self._compensated_temp_value = None
        self._real_outdoor_temp_value = None

        # PID-instans
        self.pid = PID(Kp=0, Ki=0, Kd=0, output_limits=(-15, 15))
        self._LOGGER = logging.getLogger(f"{__name__}.{self._attr_name}")

    # Default setpoint (if none is saved)
    DEFAULT_TARGET_TEMP = 20.0

    async def async_added_to_hass(self) -> None:
        """Called when the entity is added to HA and used to restore state."""

        last_state: State | None = await self.async_get_last_state()

        if last_state:
            # Try resetting the last set target temperature
            if last_state.attributes.get(ATTR_TEMPERATURE) is not None:
                self._attr_target_temperature = float(last_state.attributes[ATTR_TEMPERATURE])
            else:
                self._attr_target_temperature = self.DEFAULT_TARGET_TEMP

            # Reset HVAC mode (e.g. HEAT/OFF)
            if last_state.state in (HVACMode.HEAT, HVACMode.OFF):
                self._attr_hvac_mode = last_state.state
                self._is_on = self._attr_hvac_mode == HVACMode.HEAT
            else:
                self._attr_hvac_mode = HVACMode.OFF
                self._is_on = False

        # If no previous state was found, use the default value:
        if self._attr_target_temperature is None:
             self._attr_target_temperature = self.DEFAULT_TARGET_TEMP

        # Set PID setpoint
        self.pid.setpoint = self._attr_target_temperature

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, 
                [self._kp_entity_id, self._ki_entity_id, self._kd_entity_id], 
                self._update_pid_k_values
            )
        )

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._indoor_sensor, self._outdoor_sensor], self._async_update_loop
            )
        )

        self._update_pid_k_values()

        # NOTE: Make sure you call _async_update_loop manually once here
        # to initialize T_comp immediately on startup.
        await self._async_update_loop({'data': {'new_state': self.hass.states.get(self._indoor_sensor)}})

    async def _async_update_loop(self, event):
        """Main loop: Runs the PID calculation, applies limits, and updates the attributes."""

        #1. Check availability and retrieve sensor values
        T_indoor = self._get_float_state(self._indoor_sensor)
        T_outdoor_real = self._get_float_state(self._outdoor_sensor)

        if T_indoor is None or T_outdoor_real is None:
            self._LOGGER.warning("Could not retrieve valid temperature values ​​for PID calculation.")
            return

        self._attr_current_temperature = T_indoor

        #2. Manage OFF mode
        if not self._is_on:
            # When the system is OFF, T_comp should be set to T_outdoor_real (or a high value)
            # to ensure that the heat pump does not heat.
            T_comp = T_outdoor_real 
            self._compensated_temp_value = round(T_comp, 1)
            self.async_write_ha_state()
            return

        try:
            #3. Calculate the raw correction (Delta T)
            # NOTE: PID setpoint (T_bör) is already set in self.pid
            delta_T = self.pid(T_indoor) 

            #4. Calculate raw T_comp
            T_comp_raw = T_outdoor_real + delta_T

            # --- IMPLEMENTATION OF PROTECTION RULES (Clamping) ---
            # Rule A: The faked value must never be +- 10 degrees different from the actual outdoor temperature.
            min_allowed_temp = T_outdoor_real - MAX_TEMP_DIFFERENCE
            max_allowed_temp = T_outdoor_real + MAX_TEMP_DIFFERENCE

            # Limit T_comp_raw to these limits
            T_comp = max(min_allowed_temp, T_comp_raw)
            T_comp = min(max_allowed_temp, T_comp)

            # Rule B: If it's below zero outside, I never want the faked value to be above zero.
            if T_outdoor_real < 0:
                # T_comp must not be greater than 0.0
                T_comp = min(0.0, T_comp) 

            #5. Update state and attributes
            self._compensated_temp_value = round(T_comp, 1)
            self.async_write_ha_state()

            self._LOGGER.debug(
                f"PID: T_target={self._attr_target_temperature:.1f}, T_indoor={T_indoor:.1f}, "
                f"Delta_T={delta_T:.2f}, T_outdoor_real={T_outdoor_real:.1f}, T_comp={T_comp:.1f}"
            )

        except Exception as e:
            self._LOGGER.error(f"Error during PID calculation or update: {e}")

    async def async_set_temperature(self, **kwargs):
        """Sets the new target temperature."""
        target_temp = kwargs.get(ATTR_TEMPERATURE)
        if target_temp is not None:
            self._attr_target_temperature = target_temp
            self.pid.setpoint = target_temp

            self.hass.async_add_job(
                self._async_update_loop,
                {'data': {'new_state': self.hass.states.get(self._indoor_sensor)}}
            )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode):
        """Sets the operating mode (HEAT/OFF)."""
        if hvac_mode == HVACMode.HEAT:
            self._is_on = True

            self.hass.async_add_job(
                self._async_update_loop,
                {'data': {'new_state': self.hass.states.get(self._indoor_sensor)}}
            )
        else:
            self._is_on = False

        self._attr_hvac_mode = hvac_mode
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        """Exposes the calculated temperature and PID terms as attributes."""
        # Make sure the value is not None
        compensated_temp = self._compensated_temp_value if self._compensated_temp_value is not None else 'N/A'
        real_outdoor_temperature = self._get_float_state(self._outdoor_sensor)

        # Collects all attributes
        attributes = {
            ATTR_COMPENSATED_TEMP: compensated_temp, # <-- HÄR ÄR T_cOMP!
            "PID_Kp": self.pid.Kp,
            "PID_Ki": self.pid.Ki,
            "PID_Kd": self.pid.Kd,
            "PID_setpoint": self.pid.setpoint,
            "real_outdoor_temperature": real_outdoor_temperature,
        }
        return attributes

    def _get_k_value(self, entity_id):
        """Gets the current float value of an Input Number entity."""
        try:
            state = self.hass.states.get(entity_id)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                return float(state.state)
        except (ValueError, TypeError):
            self._LOGGER.error(f"Could not convert state of {entity_id} to float.")
            return None # Returnerar None vid fel

    def _update_pid_k_values(self, event=None):
        """Reads the latest K values and updates the PID instance."""

        kp = self._get_k_value(self._kp_entity_id)
        ki = self._get_k_value(self._ki_entity_id)
        kd = self._get_k_value(self._kd_entity_id)

        # Only update the PID instance if the values are valid (not None)
        if kp is not None and ki is not None and kd is not None:
            self.pid.Kp = kp
            self.pid.Ki = ki
            self.pid.Kd = kd
            self._LOGGER.debug(f"PID-parameters updated: Kp={kp}, Ki={ki}, Kd={kd}")

        # If this was called by an Input Number change, trigger a reload of the Climate entity.
        if event:
            self.async_schedule_update_ha_state(True)

    def _get_float_state(self, entity_id):
        """Gets and converts an entity's state to float."""
        from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

        state = self.hass.states.get(entity_id)
        if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
            try:
                return float(state.state)
            except ValueError:
                self._LOGGER.error(f"Could not convert state '{state.state}' for {entity_id} to float.")
        return None
