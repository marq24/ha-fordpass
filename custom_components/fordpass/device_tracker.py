"""Vehicle Tracker Sensor"""
import logging

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity

from . import FordPassEntity
from .const import DOMAIN, COORDINATOR

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add the Entities from the config."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]

    # Added a check to see if the car supports GPS
    if "position" in coordinator.data["metrics"] and coordinator.data["metrics"]["position"] is not None:
        async_add_entities([CarTracker(coordinator, "gps")], True)
    else:
        _LOGGER.debug("Vehicle does not support GPS")


class CarTracker(FordPassEntity, TrackerEntity):
    def __init__(self, coordinator, sensor):
        super().__init__(internal_key="tracker", coordinator=coordinator)

    @property
    def latitude(self):
        """Return latitude"""
        return float(self.coordinator.data["metrics"]["position"]["value"]["location"]["lat"])

    @property
    def longitude(self):
        """Return longtitude"""
        return float(self.coordinator.data["metrics"]["position"]["value"]["location"]["lon"])

    @property
    def source_type(self):
        """Set source type to GPS"""
        return SourceType.GPS

    @property
    def extra_state_attributes(self):
        atts = {}
        if "alt" in self.coordinator.data["metrics"]["position"]["value"]["location"]:
            atts["Altitude"] = self.coordinator.data["metrics"]["position"]["value"]["location"]["alt"]
        if "gpsCoordinateMethod" in self.coordinator.data["metrics"]["position"]["value"]:
            atts["gpsCoordinateMethod"] = self.coordinator.data["metrics"]["position"]["value"]["gpsCoordinateMethod"]
        if "gpsDimension" in self.coordinator.data["metrics"]["position"]["value"]:
            atts["gpsDimension"] = self.coordinator.data["metrics"]["position"]["value"]["gpsDimension"]
        return atts

    @property
    def icon(self):
        """Return device tracker icon"""
        return "mdi:radar"
