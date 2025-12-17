from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.entity import EntityCategory
from .const import DOMAIN

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the PID parameter numbers."""
    # Vi skapar en lista med de parametrar vi vill kunna styra
    entities = [
        PIDParameterNumber(config_entry, "Kp", -2.0, -10.0, 10.0),
        PIDParameterNumber(config_entry, "Ki", 0.0, -5.0, 5.0),
        PIDParameterNumber(config_entry, "Kd", 0.0, -5.0, 5.0),
        PIDParameterNumber(config_entry, "Weather Factor", 1.0, -2.0, 2.0),
    ]
    async_add_entities(entities)

class PIDParameterNumber(NumberEntity):
    """En entitet som ersätter input_number för PID-inställningar."""

    def __init__(self, config_entry, name, initial_value, min_val, max_val):
        self._config_entry = config_entry
        self._config_entry_id = config_entry.entry_id
        self._attr_name = f"{config_entry.title} {name}"
        self._attr_unique_id = f"{config_entry.entry_id}_{name.lower().replace(' ', '_')}"
        self._attr_native_value = initial_value
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._attr_native_step = 0.01
        self._attr_mode = NumberMode.BOX  # Gör att man kan skriva in värdet exakt
        
        # Vi kategoriserar dessa som 'config' så de inte skräpar ner vanliga vyer
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_icon = "mdi:tune"

    @property
    def device_info(self):
        """Kopplar entiteten till en gemensam enhet."""
        return {
            "identifiers": {(DOMAIN, self._config_entry_id)},
            "name": self._config_entry.title,
            "manufacturer": "tobiaso88",
            "model": "PID Heat Compensation",
        }

    async def async_set_native_value(self, value: float) -> None:
        """Uppdatera värdet när användaren ändrar i UI."""
        self._attr_native_value = value
        self.async_write_ha_state()
        # Här kan du också trigga en omräkning i din PID-controller direkt!
