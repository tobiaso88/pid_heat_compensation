import logging
from homeassistant.helpers import entity_registry as er
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import UnitOfTemperature, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.event import async_track_state_change_event, async_call_later
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, ATTR_COMPENSATED_TEMP

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Set up the PID Compensated Sensor from a config entry."""

    # Attempt to use the friendly name from the Config Entry
    climate_name = config_entry.title if config_entry.title else "PID Heat Compensation"
    climate_unique_id = f"{config_entry.entry_id}_pid_climate"

    async_add_entities(
        [PIDCompensatedTempSensor(hass, config_entry, climate_unique_id, climate_name)],
        True,
    )
    return True

class PIDCompensatedTempSensor(SensorEntity):
    """Represents the Compensated Outdoor Temperature as a sensor."""

    # Define properties for the sensor
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:thermometer-lines"

    # Set the state class for long-term statistics (optional but recommended for temps)
    _attr_state_class = "measurement" 

    def __init__(self, hass, config_entry, climate_unique_id, climate_name):
        """Initialize the sensor."""
        self.hass = hass
        self._config_entry = config_entry
        self._climate_unique_id = climate_unique_id
        self._climate_entity_id = None
        self._config_entry_id = config_entry.entry_id
        self._remove_climate_listener = None
        self._remove_retry_listener = None

        # Set a unique ID to avoid conflicts in the entity registry
        self._attr_unique_id = f"pid_comp_temp_{self._config_entry_id}"

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
        await self._async_try_start_listening()

    async def _async_try_start_listening(self) -> None:
        """Try to find the climate entity and start listening."""
        if self._remove_climate_listener is not None:
            return

        entity_registry = er.async_get(self.hass)
        self._climate_entity_id = entity_registry.async_get_entity_id(
            "climate", DOMAIN, self._climate_unique_id
        )

        if self._climate_entity_id is None:
            self._schedule_retry()
            return

        # Listen for state changes (including attribute changes) on the Climate Entity
        @callback
        def async_climate_state_listener(event):
            """Handles state changes from the Climate Entity."""
            new_state = self._extract_new_state_from_event(event)

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
        self._remove_climate_listener = async_track_state_change_event(
            self.hass, [self._climate_entity_id], async_climate_state_listener
        )
        self.async_on_remove(self._remove_climate_listener)

        initial_event_data = {
            'data': {
                'entity_id': self._climate_entity_id,
                'new_state': self.hass.states.get(self._climate_entity_id)
            }
        }

        # Perform an initial update on the event loop thread.
        async_climate_state_listener(initial_event_data)

    def _schedule_retry(self) -> None:
        """Schedule a retry when the climate entity is not yet available."""
        if self._remove_retry_listener is not None:
            return

        @callback
        def _retry(_now):
            self._remove_retry_listener = None
            self.hass.add_job(self._async_try_start_listening())

        self._remove_retry_listener = async_call_later(self.hass, 10, _retry)
        self.async_on_remove(self._remove_retry_listener)

    @staticmethod
    def _extract_new_state_from_event(event):
        """Handle HA event objects and dict-like initial payloads."""
        if isinstance(event, dict):
            return event.get("new_state") or event.get("data", {}).get("new_state")
        return event.data.get("new_state")
