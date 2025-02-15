"""Represents the primary lock of the vehicle."""
import logging

from homeassistant.components.lock import LockEntity

from . import FordPassEntity
from .const import DOMAIN, COORDINATOR

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add the lock from the config."""
    entry = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]

    lock = Lock(entry)
    if lock.coordinator.data["metrics"]["doorLockStatus"] and lock.coordinator.data["metrics"]["doorLockStatus"][0]["value"] != "ERROR":
        async_add_entities([lock], False)
    else:
        _LOGGER.debug("Ford model doesn't support remote locking")


class Lock(FordPassEntity, LockEntity):
    """Defines the vehicle's lock."""
    def __init__(self, coordinator):
        super().__init__(internal_key="doorlock", coordinator=coordinator)

    async def async_lock(self, **kwargs):
        """Locks the vehicle."""
        self._attr_is_locking = True
        self.async_write_ha_state()
        status = await self.coordinator.hass.async_add_executor_job(
            self.coordinator.vehicle.lock
        )
        _LOGGER.debug(status)
        await self.coordinator.async_request_refresh()
        _LOGGER.debug("Locking here")
        self._attr_is_locking = False
        self.async_write_ha_state()

    async def async_unlock(self, **kwargs):
        """Unlocks the vehicle."""
        self._attr_is_unlocking = True
        self.async_write_ha_state()
        status = await self.coordinator.hass.async_add_executor_job(
            self.coordinator.vehicle.unlock
        )
        _LOGGER.debug(status)
        await self.coordinator.async_request_refresh()
        self._attr_is_unlocking = False
        self.async_write_ha_state()

    @property
    def is_locked(self):
        """Determine if the lock is locked."""
        if self.coordinator.data["metrics"] is None or self.coordinator.data["metrics"]["doorLockStatus"] is None:
            return None
        return self.coordinator.data["metrics"]["doorLockStatus"][0]["value"] == "LOCKED"

    @property
    def icon(self):
        """Return MDI Icon"""
        return "mdi:car-door-lock"