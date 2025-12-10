import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform
from .const import DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)

# Change the typing to be general, or remove it.
# Home Assistant recommends not using ConfigType here in Config Flow components.
async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set PID Heat Compensation from a Config Entry."""

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Relieves PID Heat Compensation Config Entry."""

    # If this was called by an Input Number change, trigger a reload of the Climate entity.
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS) 
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
