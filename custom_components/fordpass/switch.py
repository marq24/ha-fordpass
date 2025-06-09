"""Fordpass Switch Entities"""
import logging

from homeassistant.components.switch import SwitchEntity

from custom_components.fordpass import FordPassEntity
from custom_components.fordpass.const import DOMAIN, SWITCHES, COORDINATOR_KEY, Tag
from custom_components.fordpass.fordpass_handler import UNSUPPORTED

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add the Switch from the config."""
    _LOGGER.debug("SWITCH async_setup_entry")
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR_KEY]
    entities = []
    for a_tag, value in SWITCHES.items():
        if coordinator.tag_not_supported_by_vehicle(a_tag):
            _LOGGER.debug(f"SWITCH '{a_tag}' not supported for this vehicle")
            continue

        sw = Switch(coordinator, a_tag)
        entities.append(sw)

    async_add_entities(entities, True)


class Switch(FordPassEntity, SwitchEntity):
    """Define the Switch for turning ignition off/on"""

    def __init__(self, coordinator, a_tag: Tag):
        """Initialize"""
        super().__init__(a_tag=a_tag, coordinator=coordinator)

    async def async_turn_on(self, **kwargs):
        """Send request to vehicle on switch status on"""
        await self._tag.turn_on_off(self.coordinator.bridge, True)
        await self.coordinator.async_request_refresh()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Send request to vehicle on switch status off"""
        await self._tag.turn_on_off(self.coordinator.bridge, False)
        await self.coordinator.async_request_refresh()
        self.async_write_ha_state()

    @property
    def is_on(self):
        """Check the status of switch"""
        state = self._tag.get_state(self.coordinator.data)
        if state is not UNSUPPORTED:
            return state.upper() == "ON"
        else:
            return None

    @property
    def icon(self):
        """Return icon for switch"""
        return SWITCHES[self._tag]["icon"]
