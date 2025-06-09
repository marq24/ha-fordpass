import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.fordpass import FordPassEntity
from custom_components.fordpass.const import BUTTONS, DOMAIN, COORDINATOR_KEY, Tag

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, add_entity_cb: AddEntitiesCallback):
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR_KEY]
    _LOGGER.debug(f"{coordinator.vli}BUTTON async_setup_entry")
    entities = []
    for a_tag, value in BUTTONS.items():
        entity = FordpassButton(coordinator=coordinator, a_tag=a_tag)
        entities.append(entity)

    add_entity_cb(entities)


class FordpassButton(FordPassEntity, ButtonEntity):
    def __init__(self, coordinator, a_tag:Tag):
        super().__init__(a_tag=a_tag, coordinator=coordinator)

    async def async_press(self, **kwargs):
        try:
            if self._tag == Tag.UPDATE_DATA:
                await self.coordinator.async_request_refresh_force_classic_requests()
            elif self._tag == Tag.REQUEST_REFRESH:
                await self.coordinator.bridge.request_update()
                await self.coordinator.async_request_refresh_force_classic_requests()
        except ValueError:
            return "unavailable"

    @property
    def icon(self):
        """Return sensor icon"""
        return BUTTONS[self._tag]["icon"]
