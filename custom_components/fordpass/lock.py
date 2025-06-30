"""Represents the primary lock of the vehicle."""
import asyncio
import logging

from homeassistant.components.lock import LockEntity

from custom_components.fordpass import FordPassEntity
from custom_components.fordpass.const import DOMAIN, COORDINATOR_KEY, VEHICLE_LOCK_STATE_LOCKED
from custom_components.fordpass.const_tags import Tag
from custom_components.fordpass.fordpass_handler import UNSUPPORTED

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add the lock from the config."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR_KEY]
    _LOGGER.debug(f"{coordinator.vli}LOCK async_setup_entry")
    if coordinator.data is not None:
        lock_state = Tag.DOOR_LOCK.get_state(coordinator.data)
        if lock_state != UNSUPPORTED and lock_state.upper() != "ERROR":
            async_add_entities([FordPassLock(coordinator)], False)
        else:
            _LOGGER.debug(f"{coordinator.vli}Ford model doesn't support remote locking")
    else:
        _LOGGER.debug(f"{coordinator.vli}Ford model doesn't support remote locking")



class FordPassLock(FordPassEntity, LockEntity):
    """Defines the vehicle's lock."""
    def __init__(self, coordinator):
        super().__init__(a_tag=Tag.DOOR_LOCK, coordinator=coordinator)

    async def async_lock(self, **kwargs):
        """Locks the vehicle."""
        self._attr_is_locking = True
        self.async_write_ha_state()
        status = await self.coordinator.bridge.lock()
        _LOGGER.debug(f"async_lock status: {status}")

        if self.coordinator._supports_ALARM:
            await asyncio.sleep(5)
            if Tag.ALARM.get_state(self.coordinator.data).upper() != "ARMED":
                await asyncio.sleep(25)
                if Tag.ALARM.get_state(self.coordinator.data).upper() != "ARMED":
                    await self.coordinator.bridge.request_update()

            _LOGGER.debug(f"async_lock status: {status} - after waiting for alarm 'ARMED' state")

        self._attr_is_locking = False
        self.async_write_ha_state()

    async def async_unlock(self, **kwargs):
        """Unlocks the vehicle."""
        self._attr_is_unlocking = True
        self.async_write_ha_state()
        status = await self.coordinator.bridge.unlock()
        _LOGGER.debug(f"async_unlock status: {status}")
        self._attr_is_unlocking = False
        self.async_write_ha_state()

    @property
    def is_locked(self):
        """Determine if the lock is locked."""
        lock_state = self._tag.get_state(self.coordinator.data)
        if lock_state != UNSUPPORTED:
            return lock_state == VEHICLE_LOCK_STATE_LOCKED
        return None

    @property
    def icon(self):
        if self.is_locked:
            return "mdi:car-door-lock"
        else:
            return "mdi:car-door-lock-open"