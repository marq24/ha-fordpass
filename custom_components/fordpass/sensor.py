"""All vehicle sensors from the accessible by the API"""
import json
import logging
from dataclasses import replace
from datetime import datetime
from numbers import Number
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.restore_state import RestoreEntity, RestoredExtraData, async_get, StoredState

from . import FordPassEntity, FordPassDataUpdateCoordinator, ROOT_METRICS
from .const import DOMAIN
from .const_shared import COORDINATOR_KEY
from .const_tags import SENSORS, ExtSensorEntityDescription, Tag
from .fordpass_handler import FordpassDataHandler, UNSUPPORTED

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Add the Entities from the config."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR_KEY]
    _LOGGER.debug(f"{coordinator.vli}SENSOR async_setup_entry")
    sensors = []

    check_data_availability = coordinator.data is not None and len(coordinator.data.get(ROOT_METRICS, {})) > 0
    storage = async_get(hass)
    the_platform = entity_platform.async_get_current_platform().domain

    for a_entity_description in SENSORS:
        a_entity_description: ExtSensorEntityDescription

        if not coordinator.tag_supported_by_vehicle(a_entity_description.tag):
            _LOGGER.debug(f"{coordinator.vli}SENSOR '{a_entity_description.tag}' not supported for this engine-type/vehicle")
            continue

        if a_entity_description.tag == Tag.FIRMWARE_UPDATE_HISTORY:
            # a special sensor implementation created by TheHangMan97
            sensor = FordPassFirmwareUpdateHistorySensor(coordinator, a_entity_description)
        else:
            sensor = FordPassSensor(coordinator, a_entity_description)
            # # we want to restore the last known 'id' of the energyTransferLogs
            # if a_entity_description.tag == Tag.LAST_ENERGY_TRANSFER_LOG_ENTRY:
            #     #restored_value = storage.last_states.get(sensor.entity_id, None)
            #     restored_entity = storage.entities.get(sensor.entity_id, None)
            #     if restored_entity is not None:
            #         restored_extra_data = await restored_entity.async_get_last_extra_data()
            #         if restored_extra_data is not None and "id" in restored_extra_data and restored_extra_data["id"] is not None:
            #             coordinator._last_ENERGY_TRANSFER_LOG_ENTRY_ID = restored_extra_data["id"]
            #
            #     # if restored_value is not None or restored_value != UNSUPPORTED:
            #     #     coordinator._last_ENERGY_TRANSFER_LOG_ENTRY_ID = restored_value
            #     #     _LOGGER.debug(f"{a_entity_description.tag} -> RESTORED value {restored_value}")
            #     # else:
            #     #     coordinator._last_ENERGY_TRANSFER_LOG_ENTRY_ID = None
            #     #     _LOGGER.debug(f"{a_entity_description.tag} no VALUE to RESTORE {restored_value}")

        if a_entity_description.state_class == SensorStateClass.TOTAL_INCREASING:
            # make sure that the entity_id will have the correct domain!
            # in 'some' cases the domain was 'fordpass.' instead of the expected 'sensor.'
            entity_id = f"{the_platform}.{sensor.entity_id.split('.')[1]}".lower()
            restored_state = storage.last_states.get(entity_id, None)
            if restored_state is not None and isinstance(restored_state, StoredState) and restored_state.state is not None and restored_state.state.state is not None:
                try:
                    # the restored value MUST be number (since we use the 'total_increasing' state_class
                    a_val = restored_state.state.state
                    if (isinstance(a_val, str) and a_val.lower() not in ["unknown", "unavailable", "unsupported", "none"]) or isinstance(a_val, Number):
                        sensor._previous_state = float(a_val)
                        _LOGGER.debug(f"{coordinator.vli}SENSOR restored prev value for key '{a_entity_description.tag.key}': {a_val}")
                    else:
                        _LOGGER.debug(f"{coordinator.vli}SENSOR ignoring prev value for key {a_entity_description.tag.key}: since it's not a number {type(a_val).__name__} '{a_val}'")
                        sensor._previous_state = None

                except BaseException as exc:
                    _LOGGER.debug(f"{coordinator.vli}SENSOR ignoring prev value for key {a_entity_description.tag.key}: caused {type(exc).__name__} value is: {type(restored_state.state).__name__} {restored_state.state} - {exc}")
                    sensor._previous_state = None

        if a_entity_description.skip_existence_check or not check_data_availability:
            sensors.append(sensor)
        else:
            # calling the state reading function to check if the sensor should be added (if there is any data)
            value = a_entity_description.tag.state_fn(coordinator.data, None)
            if value is not None and ((isinstance(value, (str, Number)) and str(value) != UNSUPPORTED) or
                                      (isinstance(value, (dict, list)) and len(value) != 0) or
                                      (isinstance(value, datetime) and value) ):
                sensors.append(sensor)
            else:
                _LOGGER.debug(f"{coordinator.vli}SENSOR '{a_entity_description.tag}' skipping cause no data available: type: {type(value).__name__} - value:'{value}'")

    async_add_entities(sensors, True)

# def check_if_previous_data_was_available(storage: RestoreStateData, sensor: RestoreEntity) -> bool:
#     last_sensor_data = storage.last_states.get(sensor.entity_id)
#     _LOGGER.error(f"{sensor._tag} {last_sensor_data}")
#     return last_sensor_data is not None and last_sensor_data.state not in (None, UNSUPPORTED)


class FordPassSensor(FordPassEntity, SensorEntity, RestoreEntity):
    _previous_state: Any|None = None

    def __init__(self, coordinator:FordPassDataUpdateCoordinator, entity_description:ExtSensorEntityDescription):
        # make sure that we set the device class for battery sensors [see #89]
        if (coordinator.has_ev_soc and entity_description.tag == Tag.SOC) or (not coordinator.has_ev_soc and entity_description.tag == Tag.BATTERY):
            entity_description = replace(
                entity_description,
                device_class=SensorDeviceClass.BATTERY
            )
        self._previous_state = None
        super().__init__(entity_type=Platform.SENSOR, a_tag=entity_description.tag, coordinator=coordinator, description=entity_description)

    @property
    def extra_state_attributes(self):
        """Return sensor attributes"""
        return self._tag.get_attributes(self.coordinator.data, self.coordinator.units)

    @property
    def native_value(self):
        """Return Native Value"""
        new_state = self._tag.get_state(self.coordinator.data, self._previous_state)
        if new_state is not None and new_state is not UNSUPPORTED:
            self._previous_state = new_state
        return new_state

    @property
    def available(self):
        """Return True if the entity is available."""
        state = super().available
        # the countdown sensor can be always active (does not hurt)
        # if self._tag == Tag.REMOTE_START_COUNTDOWN:
        #     return state and Tag.REMOTE_START_STATUS.get_state(self.coordinator.data) == REMOTE_START_STATE_ACTIVE
        return state


class FordPassFirmwareUpdateHistorySensor(FordPassSensor):
    """Accumulates completed firmware/ECU updates across coordinator refreshes.

    Ford does not expose a history list for this (unlike e.g. energyTransferLogs), so we build our
    own by watching events.configurationUpdateEvent for new updateTime values and persisting the
    resulting list across HA restarts via RestoreEntity.
    """
    _MAX_HISTORY_ENTRIES = 20

    def __init__(self, coordinator: FordPassDataUpdateCoordinator, entity_description: ExtSensorEntityDescription):
        self._history: list = []
        super().__init__(coordinator, entity_description)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        last_extra_data = await self.async_get_last_extra_data()
        if last_extra_data is not None:
            self._history = last_extra_data.as_dict().get("history", [])
        self._append_current_event_if_new()

    @property
    def extra_restore_state_data(self):
        return RestoredExtraData({"history": self._history})

    def _append_current_event_if_new(self):
        config_update_event = FordpassDataHandler.get_events(self.coordinator.data).get("configurationUpdateEvent", {})
        update_time = config_update_event.get("updateTime")
        if not update_time:
            return
        if self._history and self._history[-1].get("updateTime") == update_time:
            return

        oem_data = config_update_event.get("oemData", {})
        updated_ecus = []
        for entry_str in oem_data.get("ecu_configuration", {}).get("stringArrayValue", []):
            try:
                ecu = json.loads(entry_str)
            except (ValueError, TypeError):
                continue
            updated_ecus.append({"ecuId": ecu.get("ECUId"), "partNumber": ecu.get("partIIPartNumber")})

        self._history.append({
            "updateTime": update_time,
            "firmwareVersion": oem_data.get("ftcp_version", {}).get("stringValue"),
            "updatedEcus": updated_ecus,
        })
        self._history = self._history[-self._MAX_HISTORY_ENTRIES:]

    def _handle_coordinator_update(self) -> None:
        self._append_current_event_if_new()
        super()._handle_coordinator_update()

    @property
    def native_value(self):
        return len(self._history)

    @property
    def extra_state_attributes(self):
        return {"history": list(reversed(self._history))}