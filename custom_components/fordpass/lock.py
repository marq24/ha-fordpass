"""Represents the primary lock of the vehicle."""
import logging

from homeassistant.components.lock import LockEntity

from custom_components.fordpass import FordPassEntity
from custom_components.fordpass.const import DOMAIN, COORDINATOR, Tag

_LOGGER = logging.getLogger(__name__)

def has_door_lock_value(coordinator) -> bool:
    if (coordinator.data is None or
            coordinator.data["metrics"] is None or
            coordinator.data["metrics"]["doorLockStatus"] is None or
            len(coordinator.data["metrics"]["doorLockStatus"]) == 0 or
            coordinator.data["metrics"]["doorLockStatus"][0]["value"] is None
    ) :
        return False
    else:
        return True

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add the lock from the config."""
    _LOGGER.debug("LOCK async_setup_entry")
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    if has_door_lock_value(coordinator) and coordinator.data["metrics"]["doorLockStatus"][0]["value"].upper() != "ERROR":
        async_add_entities([Lock(coordinator)], False)
    else:
        _LOGGER.debug("Ford model doesn't support remote locking")


class Lock(FordPassEntity, LockEntity):
    """Defines the vehicle's lock."""
    def __init__(self, coordinator):
        super().__init__(a_tag=Tag.DOOR_LOCK, coordinator=coordinator)

    async def async_lock(self, **kwargs):
        """Locks the vehicle."""
        self._attr_is_locking = True
        self.async_write_ha_state()
        status = await self.coordinator.hass.async_add_executor_job(self.coordinator.vehicle.lock)
        _LOGGER.debug(f"async_lock status: {status}")
        await self.coordinator.async_request_refresh()
        self._attr_is_locking = False
        self.async_write_ha_state()

    async def async_unlock(self, **kwargs):
        """Unlocks the vehicle."""
        self._attr_is_unlocking = True
        self.async_write_ha_state()
        status = await self.coordinator.hass.async_add_executor_job(self.coordinator.vehicle.unlock)
        _LOGGER.debug(f"async_unlock status: {status}")
        await self.coordinator.async_request_refresh()
        self._attr_is_unlocking = False
        self.async_write_ha_state()

    @property
    def is_locked(self):
        """Determine if the lock is locked."""
        if has_door_lock_value(self.coordinator):
            return self.coordinator.data["metrics"]["doorLockStatus"][0]["value"].upper() == "LOCKED"

        return None

    @property
    def icon(self):
        """Return MDI Icon"""
        return "mdi:car-door-lock"