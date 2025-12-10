import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.helpers.selector import selector

from .const import (
    CONF_INDOOR_SENSOR,
    CONF_KD_ENTITY,
    CONF_KI_ENTITY,
    CONF_KP_ENTITY,
    CONF_OUTDOOR_SENSOR,
    DEFAULT_NAME,
    DOMAIN
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
    vol.Required(CONF_INDOOR_SENSOR): selector(
        {"entity": {"domain": "sensor", "device_class": "temperature"}}
    ),
    vol.Required(CONF_OUTDOOR_SENSOR): selector(
        {"entity": {"domain": "sensor", "device_class": "temperature"}}
    ),
    vol.Required(CONF_KP_ENTITY, default="input_number.pid_heat_compensation_kp"): selector({
        "entity": {"domain": "input_number"}
    }),
    vol.Required(CONF_KI_ENTITY, default="input_number.pid_heat_compensation_ki"): selector({
        "entity": {"domain": "input_number"}
    }),
    vol.Required(CONF_KD_ENTITY, default="input_number.pid_heat_compensation_kd"): selector({
        "entity": {"domain": "input_number"}
    }),
})

class PIDHeatCompensationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            title = user_input.get(CONF_NAME, DEFAULT_NAME)
            return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors={},
        )
