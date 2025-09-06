"""All vehicle sensors from the accessible by the API"""
import logging
from dataclasses import replace
from numbers import Number

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.restore_state import RestoreEntity  # , async_get, RestoreStateData

from custom_components.fordpass import FordPassEntity, FordPassDataUpdateCoordinator, ROOT_METRICS
from custom_components.fordpass.const import DOMAIN, COORDINATOR_KEY
from custom_components.fordpass.const_tags import SENSORS, ExtSensorEntityDescription, Tag
from custom_components.fordpass.fordpass_handler import UNSUPPORTED

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Add the Entities from the config."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR_KEY]
    _LOGGER.debug(f"{coordinator.vli}SENSOR async_setup_entry")
    sensors = []

    check_data_availability = coordinator.data is not None and len(coordinator.data.get(ROOT_METRICS, {})) > 0
    #storage = async_get(hass)

    for a_entity_description in SENSORS:
        a_entity_description: ExtSensorEntityDescription

        if coordinator.tag_not_supported_by_vehicle(a_entity_description.tag):
            _LOGGER.debug(f"{coordinator.vli}SENSOR '{a_entity_description.tag}' not supported for this engine-type/vehicle")
            continue

        sensor = FordPassSensor(coordinator, a_entity_description)

        if a_entity_description.skip_existence_check or not check_data_availability:
            sensors.append(sensor)
        else:
            # does_exist = check_if_previous_data_was_available(storage, sensor)
            #_LOGGER.error(f"{a_entity_description.tag} -> {does_exist}")

            # calling the state reading function to check if the sensor should be added (if there is any data)
            value = a_entity_description.tag.state_fn(coordinator.data)
            if value is not None and ((isinstance(value, (str, Number)) and str(value) != UNSUPPORTED) or
                                      (isinstance(value, (dict, list)) and len(value) != 0) ):
                sensors.append(sensor)
            else:
                _LOGGER.debug(f"{coordinator.vli}SENSOR '{a_entity_description.tag}' skipping cause no data available: type: {type(value).__name__} - value:'{value}'")

    async_add_entities(sensors, True)

# def check_if_previous_data_was_available(storage: RestoreStateData, sensor: RestoreEntity) -> bool:
#     last_sensor_data = storage.last_states.get(sensor.entity_id)
#     _LOGGER.error(f"{sensor._tag} {last_sensor_data}")
#     return last_sensor_data is not None and last_sensor_data.state not in (None, UNSUPPORTED)


class FordPassSensor(FordPassEntity, SensorEntity, RestoreEntity):

    def __init__(self, coordinator:FordPassDataUpdateCoordinator, entity_description:ExtSensorEntityDescription):
        # make sure that we set the device class for battery sensors [see #89]
        if (coordinator.has_ev_soc and entity_description.tag == Tag.SOC) or (not coordinator.has_ev_soc and entity_description.tag == Tag.BATTERY):
            entity_description = replace(
                entity_description,
                device_class = SensorDeviceClass.BATTERY
            )
        super().__init__(a_tag=entity_description.tag, coordinator=coordinator, description=entity_description)

    @property
    def extra_state_attributes(self):
        """Return sensor attributes"""
        return self._tag.get_attributes(self.coordinator.data, self.coordinator.units)

    @property
    def native_value(self):
        """Return Native Value"""
        return self._tag.get_state(self.coordinator.data)

