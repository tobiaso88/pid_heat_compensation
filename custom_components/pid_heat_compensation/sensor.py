import logging
from homeassistant.helpers import entity_registry as er
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import UnitOfTemperature, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, ATTR_COMPENSATED_TEMP

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Set up the PID Compensated Sensor from a config entry."""

    # The Climate Entity ID is often derived from the Config Entry's unique ID
    # or the integration's domain setup, depending on the HA version.
    # We construct a likely ID based on the domain setup, and use the friendly name.
    
    # We rely on the naming convention (domain + entry_id or the name given in config flow)
    # The easiest way is to assume the climate entity is named after the integration domain
    # or the name given in the config flow.
    # 1. Definiera det unika ID:t som Climate Entity använder
    CLIMATE_UNIQUE_ID = f"{config_entry.entry_id}_pid_climate"

    # 2. Använd registret för att hitta det faktiska Entitets-ID:t (t.ex. climate.pid_heat_compensation)
    entity_registry = er.async_get(hass)
    climate_entity_id = entity_registry.async_get_entity_id("climate", DOMAIN, CLIMATE_UNIQUE_ID)

    if climate_entity_id is None:
        _LOGGER.error(f"Could not find climate entity with unique ID: {CLIMATE_UNIQUE_ID}. Sensor creation aborted.")
        return False # Avbryt om Climate Entity inte hittas

    # Attempt to use the friendly name from the Config Entry
    climate_name = config_entry.title if config_entry.title else "PID Heat Compensation"

    async_add_entities([PIDCompensatedTempSensor(hass, config_entry, climate_entity_id, climate_name)], True)
    return True

class PIDCompensatedTempSensor(SensorEntity):
    """Represents the Compensated Outdoor Temperature as a sensor."""

    # Define properties for the sensor
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:thermometer-lines"

    # Set the state class for long-term statistics (optional but recommended for temps)
    _attr_state_class = "measurement" 

    def __init__(self, hass, config_entry, climate_entity_id, climate_name):
        """Initialize the sensor."""
        self.hass = hass
        self._config_entry = config_entry
        self._climate_entity_id = climate_entity_id
        self._config_entry_id = config_entry.entry_id

        # Set a unique ID to avoid conflicts in the entity registry
        self._attr_unique_id = f"pid_comp_temp_{climate_entity_id}"

        # Set a descriptive friendly name
        self._attr_name = f"{climate_name} Compensated Outdoor Temp"
        self._attr_native_value = None

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._attr_native_value

    @property
    def device_info(self):
        """Kopplar entiteten till en gemensam enhet."""
        return {
            "identifiers": {(DOMAIN, self._config_entry_id)},
            "name": self._config_entry.title,
            "manufacturer": "tobiaso88",
            "model": "PID Heat Compensation",
        }

    async def async_added_to_hass(self):
        """Register callbacks when entity is added."""

        # Listen for state changes (including attribute changes) on the Climate Entity
        @callback
        def async_climate_state_listener(event):
            """Handles state changes from the Climate Entity."""
            if isinstance(event, dict):

                new_state = event.get("new_state")
            else:
                new_state = event.data.get("new_state")

            if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                return

            # Get the value from the attribute exposed in climate.py
            compensated_temp = new_state.attributes.get(ATTR_COMPENSATED_TEMP)

            if compensated_temp is not None and compensated_temp != 'N/A':
                try:
                    self._attr_native_value = float(compensated_temp)
                    self.async_write_ha_state()
                except (ValueError, TypeError):
                    _LOGGER.warning(f"Failed to convert compensated temp attribute '{compensated_temp}' to float.")

        # Use the modern and correct method to track state changes
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._climate_entity_id], async_climate_state_listener
            )
        )

        initial_event_data = {
            'data': {
                'entity_id': self._climate_entity_id,
                'new_state': self.hass.states.get(self._climate_entity_id)
            }
        }

        # Perform an initial update
        self.hass.async_add_executor_job(
            async_climate_state_listener,
            initial_event_data
        )
