"""Vehicle Tracker Sensor"""
import logging

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity

from custom_components.fordpass import FordPassEntity
from custom_components.fordpass.const import DOMAIN, COORDINATOR_KEY
from custom_components.fordpass.const_tags import Tag
from custom_components.fordpass.fordpass_handler import FordpassDataHandler, UNSUPPORTED

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add the Entities from the config."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR_KEY]
    _LOGGER.debug(f"{coordinator.vli}DEVICE_TRACKER async_setup_entry")

    # Added a check to see if the car supports GPS
    if FordpassDataHandler.get_gps_state(coordinator.data) != UNSUPPORTED:
        async_add_entities([FordPassCarTracker(coordinator)], True)
    else:
        _LOGGER.debug(f"{coordinator.vli}Vehicle does not support GPS")


class FordPassCarTracker(FordPassEntity, TrackerEntity):
    def __init__(self, coordinator):
        super().__init__(a_tag=Tag.TRACKER, coordinator=coordinator)

    @property
    def latitude(self):
        return FordpassDataHandler.get_gps_lat(self.coordinator.data)

    @property
    def longitude(self):
        return FordpassDataHandler.get_gps_lon(self.coordinator.data)

    @property
    def source_type(self):
        """Set source type to GPS"""
        return SourceType.GPS

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the tracker."""
        # we don't need units here!
        return self._tag.get_attributes(self.coordinator.data, None )

    @property
    def icon(self):
        """Return device tracker icon"""
        return "mdi:radar"
