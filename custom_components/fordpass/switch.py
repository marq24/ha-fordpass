"""Fordpass Switch Entities"""
import logging

from homeassistant.components.switch import SwitchEntity

from custom_components.fordpass import FordPassEntity, RCC_TAGS
from custom_components.fordpass.const import DOMAIN, COORDINATOR_KEY
from custom_components.fordpass.const_tags import SWITCHES, Tag
from custom_components.fordpass.fordpass_handler import UNSUPPORTED

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add the Switch from the config."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR_KEY]
    _LOGGER.debug(f"{coordinator.vli}SWITCH async_setup_entry")
    entities = []
    for a_tag, value in SWITCHES.items():
        if coordinator.tag_not_supported_by_vehicle(a_tag):
            _LOGGER.debug(f"{coordinator.vli}SWITCH '{a_tag}' not supported for this vehicle")
            continue

        sw = FordPassSwitch(coordinator, a_tag)
        entities.append(sw)

    async_add_entities(entities, True)


class FordPassSwitch(FordPassEntity, SwitchEntity):
    """Define the Switch for turning ignition off/on"""

    def __init__(self, coordinator, a_tag: Tag):
        """Initialize"""
        super().__init__(a_tag=a_tag, coordinator=coordinator)

    async def async_turn_on(self, **kwargs):
        """Send request to vehicle on switch status on"""
        await self._tag.turn_on_off(self.coordinator.data, self.coordinator.bridge, True)
        await self.coordinator.async_request_refresh()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Send request to vehicle on switch status off"""
        await self._tag.turn_on_off(self.coordinator.data, self.coordinator.bridge, False)
        await self.coordinator.async_request_refresh()
        self.async_write_ha_state()

    @property
    def is_on(self):
        """Check the status of switch"""
        state = self._tag.get_state(self.coordinator.data)
        #_LOGGER.error(f"{self.coordinator.vli} SWITCH '{self._tag}' - state: {state}")
        if state is not None and state is not UNSUPPORTED:
            return state.upper() == "ON"
        else:
            return None

    @property
    def icon(self):
        """Return icon for switch"""
        return SWITCHES[self._tag]["icon"]

    @property
    def available(self):
        """Return True if entity is available."""
        state = super().available
        if self._tag == Tag.ELVEH_CHARGE:
            return state and Tag.EVCC_STATUS.get_state(self.coordinator.data) in ["B", "C"]
        elif self._tag in RCC_TAGS:
           return state #and Tag.REMOTE_START_STATUS.get_state(self.coordinator.data) == REMOTE_START_STATE_ACTIVE
        return state
