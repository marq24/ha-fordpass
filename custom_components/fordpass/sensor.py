"""All vehicle sensors from the accessible by the API"""
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.restore_state import RestoreEntity  # , async_get, RestoreStateData

from custom_components.fordpass import FordPassEntity, FordPassDataUpdateCoordinator, ROOT_METRICS
from custom_components.fordpass.const import DOMAIN, SENSORS, COORDINATOR, ExtSensorEntityDescription
from custom_components.fordpass.fordpass_handler import UNSUPPORTED

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Add the Entities from the config."""
    _LOGGER.debug("SENSOR async_setup_entry")
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    sensors = []

    check_data_availability = coordinator.data is not None and len(coordinator.data.get(ROOT_METRICS, {})) > 0
    #storage = async_get(hass)

    for a_entity_description in SENSORS:
        a_entity_description: ExtSensorEntityDescription

        if coordinator.tag_not_supported_by_vehicle(a_entity_description.tag):
            _LOGGER.debug(f"SENSOR '{a_entity_description.tag}' not supported for this vehicle")
            continue

        sensor = FordPassSensor(coordinator, a_entity_description)

        if a_entity_description.skip_existence_check or not check_data_availability:
            sensors.append(sensor)
        else:
            # does_exist = check_if_previous_data_was_available(storage, sensor)
            #_LOGGER.error(f"{a_entity_description.tag} -> {does_exist}")

            # calling the state reading function to check if the sensor should be added (if there is any data)
            value = a_entity_description.tag.state_fn(coordinator.data)
            if value is not None and ((isinstance(value, (int, float, str)) and str(value) != UNSUPPORTED) or
                                      (isinstance(value, (dict, list)) and len(value) != 0) ):
                sensors.append(sensor)
            else:
                _LOGGER.debug(f"SENSOR Skipping '{a_entity_description.tag}' - {type(value)} - {value}")

    async_add_entities(sensors, True)

# def check_if_previous_data_was_available(storage: RestoreStateData, sensor: RestoreEntity) -> bool:
#     last_sensor_data = storage.last_states.get(sensor.entity_id)
#     _LOGGER.error(f"{sensor._tag} {last_sensor_data}")
#     return last_sensor_data is not None and last_sensor_data.state not in (None, UNSUPPORTED)


class FordPassSensor(FordPassEntity, SensorEntity, RestoreEntity):

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

