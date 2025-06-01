"""All vehicle sensors from the accessible by the API"""
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.fordpass import FordPassEntity, FordPassDataUpdateCoordinator
from custom_components.fordpass.const import DOMAIN, SENSORS, COORDINATOR, ExtSensorEntityDescription
from custom_components.fordpass.fordpass_handler import UNSUPPORTED

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Add the Entities from the config."""
    _LOGGER.debug("SENSOR async_setup_entry")
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    sensors = []

    for a_entity_description in SENSORS:
        a_entity_description: ExtSensorEntityDescription

        if coordinator.tag_not_supported_by_vehicle(a_entity_description.tag):
            _LOGGER.debug(f"SENSOR '{a_entity_description.tag}' not supported for this vehicle")
            continue

        sensor = CarSensor(coordinator, a_entity_description)

        if a_entity_description.skip_existence_check:
            sensors.append(sensor)
        else:
            # calling the state reading function to check if the sensor should be added (if there is any data)
            value = a_entity_description.tag.state_fn(coordinator.data)
            if value is not None and ((isinstance(value, (int, float, str)) and str(value) != UNSUPPORTED) or \
                                      (isinstance(value, (dict, list)) and len(value) != 0) ):
                sensors.append(sensor)
            else:
                _LOGGER.debug(f"SENSOR Skipping '{a_entity_description.tag}' - {type(value)} - {value}")

    async_add_entities(sensors, True)


class CarSensor(FordPassEntity, SensorEntity):

    def __init__(self, coordinator:FordPassDataUpdateCoordinator, entity_description:ExtSensorEntityDescription):
        super().__init__(a_tag=entity_description.tag, coordinator=coordinator, description=entity_description)

    @property
    def extra_state_attributes(self):
        """Return sensor attributes"""
        return self._tag.get_attributes(self.coordinator.data, self.coordinator.units)

    @property
    def native_value(self):
        """Return Native Value"""
        return self._tag.get_state(self.coordinator.data)

