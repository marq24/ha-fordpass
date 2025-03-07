"""Fordpass Switch Entities"""
import logging

from homeassistant.components.switch import SwitchEntity

from . import FordPassEntity
from .const import DOMAIN, SWITCHES, COORDINATOR, Tag

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add the Switch from the config."""
    _LOGGER.debug("SWITCH async_setup_entry")
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    entities = []
    for key, value in SWITCHES.items():
        # Only add guard entity if supported by the car
        if key == Tag.GUARDMODE.key and "guardstatus" in coordinator.data:
            if coordinator.data["guardstatus"]["returnCode"] == 200:
                sw = Switch(coordinator, key, config_entry.options)
                entities.append(sw)
            else:
                _LOGGER.debug("Guard mode not supported on this vehicle")
        else:
            sw = Switch(coordinator, key, config_entry.options)
            entities.append(sw)

    async_add_entities(entities, True)


class Switch(FordPassEntity, SwitchEntity):
    """Define the Switch for turning ignition off/on"""

    def __init__(self, coordinator, switch_key: str, options):
        """Initialize"""
        super().__init__(internal_key=switch_key, coordinator=coordinator)

    async def async_turn_on(self, **kwargs):
        """Send request to vehicle on switch status on"""
        if self._internal_key == Tag.IGNITION.key:
            await self.coordinator.hass.async_add_executor_job(self.coordinator.vehicle.start)
            await self.coordinator.async_request_refresh()
        elif self._internal_key == Tag.GUARDMODE.key:
            await self.coordinator.hass.async_add_executor_job(self.coordinator.vehicle.enableGuard)
            await self.coordinator.async_request_refresh()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Send request to vehicle on switch status off"""
        if self._internal_key == Tag.IGNITION.key:
            await self.coordinator.hass.async_add_executor_job(self.coordinator.vehicle.stop)
            await self.coordinator.async_request_refresh()
        elif self._internal_key == Tag.GUARDMODE.key:
            await self.coordinator.hass.async_add_executor_job(self.coordinator.vehicle.disableGuard)
            await self.coordinator.async_request_refresh()
        self.async_write_ha_state()

    @property
    def is_on(self):
        """Check status of switch"""
        if self._internal_key == Tag.IGNITION.key:
            if (self.coordinator.data["metrics"] is None or self.coordinator.data["metrics"]["ignitionStatus"] is None):
                return None
            if self.coordinator.data["metrics"]["ignitionStatus"]["value"] == "OFF":
                return False
        if self._internal_key == Tag.GUARDMODE.key:
            # Need to find the correct response for enabled vs disabled so this may be spotty at the moment
            guardstatus = self.coordinator.data["guardstatus"]
            _LOGGER.debug(f"is_on guardstatus: {guardstatus}")
            if guardstatus["returnCode"] == 200:
                if "gmStatus" in guardstatus:
                    if guardstatus["session"]["gmStatus"] == "enable":
                        return True
                    return False
                return False
            return False
        return False

    @property
    def icon(self):
        """Return icon for switch"""
        return SWITCHES[self._internal_key]["icon"]
