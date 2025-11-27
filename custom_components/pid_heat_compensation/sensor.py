import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import UnitOfTemperature, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import async_track_state_change

from .const import DOMAIN, HA_DATA_KEY, CONF_INDOOR_SENSOR, ATTR_COMPENSATED_TEMP

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Sets the sensor platform."""

    # Retrieves the climate entity that will store the data
    climate_entity_id = f"climate.{config_entry.data['name'].lower().replace(' ', '_')}" 

    async_add_entities([
        PIDCompensationSensor(hass, config_entry.data, climate_entity_id)
    ], True)

class PIDCompensationSensor(SensorEntity):
    """Sensor that exposes the fake outdoor temperature."""

    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:thermometer-lines"
    _attr_device_class = "temperature"
    _attr_state_class = "measurement"

    def __init__(self, hass, config, climate_entity_id):
        self.hass = hass
        self._attr_name = f"{config.get('name')} Kompenserad UteTemp"
        self._attr_unique_id = f"pid_comp_{config['name'].lower()}_temp"
        self._climate_entity_id = climate_entity_id
        self._T_komp = None

    async def async_added_to_hass(self):
        """Listen for changes in the Climate Entity's attributes."""

        self.async_on_remove(
            async_track_state_change(
                self.hass, self._climate_entity_id, self._async_update_from_climate
            )
        )

    async def _async_update_from_climate(self, entity_id, old_state, new_state):
        """Updates the sensor value from the Climate Entity's attribute."""

        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        # Read the attribute ATTR_COMPENSATED_TEMP from the Climate Entity
        compensated_temp = new_state.attributes.get(ATTR_COMPENSATED_TEMP)

        if compensated_temp not in (None, 'N/A'):
            self._T_komp = compensated_temp
            self.async_write_ha_state()

    @property
    def native_value(self):
        """Returns the calculated fake temperature."""
        return self._T_komp
