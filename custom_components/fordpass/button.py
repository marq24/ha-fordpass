import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FordPassDataUpdateCoordinator, FordPassEntity
from .const import BUTTONS, DOMAIN, COORDINATOR

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, add_entity_cb: AddEntitiesCallback):
    _LOGGER.debug("BUTTON async_setup_entry")
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    entities = []
    for key, value in BUTTONS.items():
        entity = FordpassButton(coordinator=coordinator, button_key=key, options=config_entry.options)
        entities.append(entity)

    add_entity_cb(entities)


class FordpassButton(FordPassEntity, ButtonEntity):
    def __init__(self, coordinator, button_key:str, options):
        super().__init__(internal_key=button_key, coordinator=coordinator)

    async def async_press(self, **kwargs):
        try:
            if self._internal_key == "update_data":
                await self.coordinator.async_request_refresh()
            elif self._internal_key == "request_refresh":
                _LOGGER.debug("BUTTON PRESSED called...")
                await self.coordinator.async_vehicle_update_request_init()
            #await self.coordinator.async_press_tag(self._internal_key)
        except ValueError:
            return "unavailable"

    @property
    def icon(self):
        """Return sensor icon"""
        return BUTTONS[self._internal_key]["icon"]
