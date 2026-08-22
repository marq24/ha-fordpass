from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import CONF_VIN, DOMAIN
from .const_shared import COORDINATOR_KEY

TO_REDACT = {
    CONF_USERNAME,
    CONF_VIN,
    "VIN",
    "vehicleId",
    "deviceId",
    "vehicleImage",
    "address"
}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, config_entry: ConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data.get(DOMAIN,{}).get(config_entry.entry_id, {}).get(COORDINATOR_KEY, {})

    return {
        "config_entry": {
            "data": async_redact_data(dict(config_entry.data), TO_REDACT),
            "options": async_redact_data(dict(config_entry.options), TO_REDACT),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
            "data": async_redact_data(coordinator.data, TO_REDACT) if coordinator.data else None,
        },
        "api_trace": async_redact_data(coordinator.bridge.api_response_data, TO_REDACT) if coordinator.bridge else None
    }
