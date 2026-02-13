"""Constants for the FordPass integration."""
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Final, NamedTuple, Callable, Any

from homeassistant.components.button import ButtonEntityDescription
from homeassistant.components.number import NumberEntityDescription, NumberMode, NumberDeviceClass
from homeassistant.components.select import SelectEntityDescription
from homeassistant.components.sensor import SensorStateClass, SensorDeviceClass, SensorEntityDescription
from homeassistant.const import (
    PERCENTAGE,
    UnitOfTime,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfSpeed,
    UnitOfLength,
    UnitOfTemperature,
    UnitOfElectricCurrent,
    EntityCategory
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.unit_system import UnitSystem

from .const_shared import (
    ZONE_LIGHTS_OPTIONS,
    RCC_SEAT_OPTIONS_FULL,
    RCC_TEMPERATURES_CELSIUS,
    ELVEH_TARGET_CHARGE_OPTIONS
)
from .fordpass_handler import FordpassDataHandler, UNSUPPORTED

_LOGGER = logging.getLogger(__name__)

class ApiKey(NamedTuple):
    key: str
    state_fn: Callable[[dict, Any], Any] = None
    attrs_fn: Callable[[dict, UnitSystem], Any] = None
    # asynchronous functions
    on_off_fn: Callable[[dict, Any, bool], Any] = None
    select_fn: Callable[[dict, Any, str, str], Any] = None
    press_fn: Callable[[DataUpdateCoordinator, Any], Any] = None

class Tag(ApiKey, Enum):

    def __hash__(self) -> int:
        return hash(self.key)

    def __str__(self):
        return self.key

    def get_state(self, data, prev_state=None):
        if self.state_fn:
            return self.state_fn(data, prev_state)
        return None

    def get_attributes(self, data, units: UnitSystem):
        if self.attrs_fn:
            return self.attrs_fn(data, units)
        return None

    async def turn_on_off(self, data, vehicle, turn_on:bool) -> bool:
        if self.on_off_fn:
            return await self.on_off_fn(data, vehicle, turn_on)
        else:
            _LOGGER.warning(f"Tag {self.key} does not support turning ON.")
            return False

    async def async_select_option(self, data, vehicle, new_value: Any) -> bool:
        if self.select_fn:
            current_value = self.get_state(data)
            if current_value is not UNSUPPORTED:
                return await self.select_fn(data, vehicle, new_value, current_value)
        return None

    async def async_set_value(self, data, vehicle, new_value: str) -> bool:
        if self.select_fn:
            current_value = self.get_state(data)
            if current_value is not UNSUPPORTED:
                return await self.select_fn(data, vehicle, new_value, current_value)
        return None

    async def async_push(self, coordinator, vehicle) -> bool:
        if self.press_fn:
            return await self.press_fn(coordinator, vehicle)
        return None

    ##################################################
    ##################################################

    # DEVICE_TRACKER
    ##################################################
    TRACKER             = ApiKey(key="tracker",
                                 attrs_fn=FordpassDataHandler.get_gps_tracker_attr)

    # BUTTON
    ##################################################
    UPDATE_DATA         = ApiKey(key="update_data",
                                 press_fn=FordpassDataHandler.reload_data)
    REQUEST_REFRESH     = ApiKey(key="request_refresh",
                                 press_fn=FordpassDataHandler.request_update_and_reload)
    DOOR_UNLOCK         = ApiKey(key="doorunlock",
                                 press_fn=FordpassDataHandler.unlock_vehicle)
    EV_START            = ApiKey(key="evstart",
                                 press_fn=FordpassDataHandler.start_charge_vehicle)
    EV_CANCEL           = ApiKey(key="evcancel",
                                 press_fn=FordpassDataHandler.cancel_charge_vehicle)
    EV_PAUSE            = ApiKey(key="evpause",
                                 press_fn=FordpassDataHandler.pause_charge_vehicle)
    HAF_SHORT           = ApiKey(key="hafshort",
                                 press_fn=FordpassDataHandler.honk_and_light_short)
    HAF_DEFAULT         = ApiKey(key="hafdefault",
                                 press_fn=FordpassDataHandler.honk_and_light)
    HAF_LONG            = ApiKey(key="haflong",
                                 press_fn=FordpassDataHandler.honk_and_light_long)
    EXTEND_REMOTE_START = ApiKey(key="extendRemoteStart",
                                 press_fn=FordpassDataHandler.extend_remote_start)
    MESSAGES_DELETE_LAST= ApiKey(key="msgdeletelast",
                                 press_fn=FordpassDataHandler.messages_delete_last)
    MESSAGES_DELETE_ALL= ApiKey(key="msgdeleteall",
                                press_fn=FordpassDataHandler.messages_delete_all)
    # LOCKS
    ##################################################
    DOOR_LOCK           = ApiKey(key="doorlock",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_door_lock_state(data, None),
                                 attrs_fn=FordpassDataHandler.get_door_lock_attrs,
                                 press_fn=FordpassDataHandler.lock_vehicle)
    # SWITCHES
    ##################################################
    # for historic reasons the key is "ignition" (even if it's the remote_start switch)
    REMOTE_START        = ApiKey(key="ignition",
                                 state_fn=FordpassDataHandler.get_remote_start_state,
                                 on_off_fn=FordpassDataHandler.on_off_remote_start)
    GUARD_MODE          = ApiKey(key="guardmode",
                                 state_fn=FordpassDataHandler.get_guard_mode_state,
                                 on_off_fn=FordpassDataHandler.on_off_guard_mode)

    ELVEH_CHARGE        = ApiKey(key="elVehCharge",
                                 state_fn=FordpassDataHandler.get_cancel_pause_charge_switch_state,
                                 on_off_fn=FordpassDataHandler.on_off_cancel_pause_charge)

    AUTO_UPDATES        = ApiKey(key="autoSoftwareUpdates",
                                 state_fn=FordpassDataHandler.get_auto_updates_state,
                                 on_off_fn=FordpassDataHandler.on_off_auto_updates)

    RCC_DEFROST_REAR    = ApiKey(key="rccDefrostRear",
                                state_fn=lambda data, prev_state: FordpassDataHandler.get_rcc_state(data, rcc_key="RccRearDefrost_Rq"),
                                on_off_fn=FordpassDataHandler.on_off_rcc_RccRearDefrost_Rq)
    RCC_DEFROST_FRONT   = ApiKey(key="rccDefrostFront",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_rcc_state(data, rcc_key="RccHeatedWindshield_Rq"),
                                 on_off_fn=FordpassDataHandler.on_off_rcc_RccHeatedWindshield_Rq)
    RCC_STEERING_WHEEL  = ApiKey(key="rccSteeringWheel",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_rcc_state(data, rcc_key="RccHeatedSteeringWheel_Rq"),
                                 on_off_fn=FordpassDataHandler.on_off_rcc_RccHeatedSteeringWheel_Rq)


    # SELECTS
    ZONE_LIGHTING       = ApiKey(key="zoneLighting",
                                 state_fn=FordpassDataHandler.get_zone_lighting_state,
                                 attrs_fn=FordpassDataHandler.get_zone_lighting_attrs,
                                 select_fn=FordpassDataHandler.set_zone_lighting)

    RCC_SEAT_REAR_LEFT  = ApiKey(key="rccSeatRearLeft",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_rcc_state(data, rcc_key="RccLeftRearClimateSeat_Rq"),
                                 select_fn=FordpassDataHandler.set_rcc_RccLeftRearClimateSeat_Rq)
    RCC_SEAT_REAR_RIGHT = ApiKey(key="rccSeatRearRight",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_rcc_state(data, rcc_key="RccRightRearClimateSeat_Rq"),
                                 select_fn=FordpassDataHandler.set_rcc_RccRightRearClimateSeat_Rq)
    RCC_SEAT_FRONT_LEFT = ApiKey(key="rccSeatFrontLeft",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_rcc_state(data, rcc_key="RccLeftFrontClimateSeat_Rq"),
                                 select_fn=FordpassDataHandler.set_rcc_RccLeftFrontClimateSeat_Rq)
    RCC_SEAT_FRONT_RIGHT= ApiKey(key="rccSeatFrontRight",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_rcc_state(data, rcc_key="RccRightFrontClimateSeat_Rq"),
                                 select_fn=FordpassDataHandler.set_rcc_RccRightFrontClimateSeat_Rq)


    ELVEH_TARGET_CHARGE = ApiKey(key="elVehTargetCharge",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_elev_target_charge_state(data, 0),
                                 select_fn=FordpassDataHandler.set_elev_target_charge)
    ELVEH_TARGET_CHARGE_ALT1 = ApiKey(key="elVehTargetChargeAlt1",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_elev_target_charge_state(data, 1),
                                 select_fn=FordpassDataHandler.set_elev_target_charge_alt1)
    ELVEH_TARGET_CHARGE_ALT2 = ApiKey(key="elVehTargetChargeAlt2",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_elev_target_charge_state(data, 2),
                                 select_fn=FordpassDataHandler.set_elev_target_charge_alt2)

    GLOBAL_TARGET_SOC = ApiKey(key="globalTargetSoc",
                               state_fn=FordpassDataHandler.get_global_target_soc_state,
                               select_fn=FordpassDataHandler.set_global_target_soc)

    # NUMBERS
    RCC_TEMPERATURE = ApiKey(key="rccTemperature",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_rcc_state(data, rcc_key="SetPointTemp_Rq"),
                                 select_fn=FordpassDataHandler.set_rcc_SetPointTemp_Rq)

    GLOBAL_AC_CURRENT_LIMIT = ApiKey(key="globalAcCurrentLimit",
                                state_fn=FordpassDataHandler.get_global_ac_current_limit_state,
                                select_fn=FordpassDataHandler.set_global_ac_current_limit)

    GLOBAL_DC_POWER_LIMIT = ApiKey(key="globalDcPowerLimit",
                                     state_fn=FordpassDataHandler.get_global_dc_power_limit_state,
                                     select_fn=FordpassDataHandler.set_global_dc_power_limit)

    # SENSORS
    ##################################################
    ODOMETER            = ApiKey(key="odometer",
                                 state_fn=FordpassDataHandler.get_odometer_state,
                                 attrs_fn=lambda data, units: FordpassDataHandler.get_metrics_dict(data, "odometer"))
    FUEL                = ApiKey(key="fuel",
                                 state_fn=FordpassDataHandler.get_fuel_state,
                                 attrs_fn=FordpassDataHandler.get_fuel_attrs)
    BATTERY             = ApiKey(key="battery",
                                 state_fn=FordpassDataHandler.get_battery_state,
                                 attrs_fn=FordpassDataHandler.get_battery_attrs)
    OIL                 = ApiKey(key="oil",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_value_for_metrics_key(data, "oilLifeRemaining", None),
                                 attrs_fn=lambda data, units: FordpassDataHandler.get_metrics_dict(data, "oilLifeRemaining"))
    SEATBELT            = ApiKey(key="seatbelt",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_value_at_index_for_metrics_key(data, "seatBeltStatus", 0),
                                 attrs_fn=FordpassDataHandler.get_seatbelt_attrs)
    TIRE_PRESSURE       = ApiKey(key="tirePressure",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_value_at_index_for_metrics_key(data, "tirePressureSystemStatus", 0),
                                 attrs_fn=FordpassDataHandler.get_tire_pressure_attrs)
    GPS                 = ApiKey(key="gps",
                                 state_fn=FordpassDataHandler.get_gps_state,
                                 attrs_fn=FordpassDataHandler.get_gps_attr)
    ALARM               = ApiKey(key="alarm",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_value_for_metrics_key(data, "alarmStatus"),
                                 attrs_fn=FordpassDataHandler.get_alarm_attr)
    IGNITION_STATUS     = ApiKey(key="ignitionStatus",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_value_for_metrics_key(data, "ignitionStatus"),
                                 attrs_fn=lambda data, units: FordpassDataHandler.get_metrics_dict(data, "ignitionStatus"))
    DOOR_STATUS         = ApiKey(key="doorStatus",
                                 state_fn=FordpassDataHandler.get_door_status_state,
                                 attrs_fn=FordpassDataHandler.get_door_status_attrs)
    WINDOW_POSITION     = ApiKey(key="windowPosition",
                                 state_fn=FordpassDataHandler.get_window_position_state,
                                 attrs_fn=FordpassDataHandler.get_window_position_attrs)
    LAST_REFRESH        = ApiKey(key="lastRefresh",
                                 state_fn=FordpassDataHandler.get_last_refresh_state)
    ELVEH               = ApiKey(key="elVeh",
                                 state_fn=FordpassDataHandler.get_elveh_state,
                                 attrs_fn=FordpassDataHandler.get_elveh_attrs)
    ELVEH_CHARGING      = ApiKey(key="elVehCharging",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_value_for_metrics_key(data, "xevBatteryChargeDisplayStatus"),
                                 attrs_fn=FordpassDataHandler.get_elveh_charging_attrs)
    ELVEH_CHARGING_POWER   = ApiKey(key="elVehChargingPower",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_elveh_charging_power_state(data))
    ELVEH_PLUG          = ApiKey(key="elVehPlug",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_value_for_metrics_key(data, "xevPlugChargerStatus"),
                                 attrs_fn=FordpassDataHandler.get_elveh_plug_attrs)
    EVCC_STATUS         = ApiKey(key="evccStatus",
                                 state_fn=FordpassDataHandler.get_evcc_status_state)
    DEEPSLEEP           = ApiKey(key="deepSleep",
                                 state_fn=FordpassDataHandler.get_deepsleep_state)
    REMOTE_START_STATUS = ApiKey(key="remoteStartStatus",
                                 state_fn=FordpassDataHandler.get_remote_start_status_state,
                                 attrs_fn=FordpassDataHandler.get_remote_start_status_attrs)
    REMOTE_START_COUNTDOWN = ApiKey(key="remoteStartCountdown",
                                 state_fn=FordpassDataHandler.get_remote_start_countdown_state)
    MESSAGES            = ApiKey(key="messages",
                                 state_fn=FordpassDataHandler.get_messages_state,
                                 attrs_fn=FordpassDataHandler.get_messages_attrs)
    DIESEL_SYSTEM_STATUS= ApiKey(key="dieselSystemStatus",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_value_for_metrics_key(data, "dieselExhaustFilterStatus"),
                                 attrs_fn=FordpassDataHandler.get_diesel_system_status_attrs)
    EXHAUST_FLUID_LEVEL = ApiKey(key="exhaustFluidLevel",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_value_for_metrics_key(data, "dieselExhaustFluidLevel", None),
                                 attrs_fn=FordpassDataHandler.get_exhaust_fluid_level_attrs)
    SPEED               = ApiKey(key="speed",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_value_for_metrics_key(data, "speed", None),
                                 attrs_fn=FordpassDataHandler.get_speed_attrs)
    ENGINESPEED         = ApiKey(key="engineSpeed",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_value_for_metrics_key(data, "engineSpeed", None))
    GEARLEVERPOSITION   = ApiKey(key="gearLeverPosition",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_value_for_metrics_key(data, "gearLeverPosition"))
    INDICATORS          = ApiKey(key="indicators",
                                 state_fn=FordpassDataHandler.get_indicators_state,
                                 attrs_fn=FordpassDataHandler.get_indicators_attrs)
    COOLANT_TEMP        = ApiKey(key="coolantTemp",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_value_for_metrics_key(data, "engineCoolantTemp", None))
    OUTSIDE_TEMP        = ApiKey(key="outsideTemp",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_value_for_metrics_key(data, "outsideTemperature", None),
                                 attrs_fn=FordpassDataHandler.get_outside_temp_attrs)
    ENGINE_OIL_TEMP     = ApiKey(key="engineOilTemp",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_value_for_metrics_key(data, "engineOilTemp", None))
    SOC                 = ApiKey(key="soc",
                                 state_fn=FordpassDataHandler.get_soc_state,
                                 attrs_fn=FordpassDataHandler.get_soc_attrs)
    YAW_RATE            = ApiKey(key="yawRate",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_value_for_metrics_key(data, "yawRate", None))
    ACCELERATION        = ApiKey(key="acceleration",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_attr_of_metrics_value_dict(data, "acceleration", "x", None),
                                 attrs_fn=lambda data, units: FordpassDataHandler.get_value_for_metrics_key(data, "acceleration", None))
    BRAKE_PEDAL_STATUS  = ApiKey(key="brakePedalStatus",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_value_for_metrics_key(data, "brakePedalStatus"))
    BRAKE_TORQUE        = ApiKey(key="brakeTorque",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_value_for_metrics_key(data, "brakeTorque", None))
    ACCELERATOR_PEDAL   = ApiKey(key="acceleratorPedalPosition",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_value_for_metrics_key(data, "acceleratorPedalPosition", None))
    PARKING_BRAKE       = ApiKey(key="parkingBrakeStatus",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_value_for_metrics_key(data, "parkingBrakeStatus"))
    TORQUE_TRANSMISSION = ApiKey(key="torqueAtTransmission",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_value_for_metrics_key(data, "torqueAtTransmission", None))
    WHEEL_TORQUE        = ApiKey(key="wheelTorqueStatus",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_value_for_metrics_key(data, "wheelTorqueStatus"))
    CABIN_TEMP          = ApiKey(key="cabinTemperature",
                                 state_fn=FordpassDataHandler.get_cabin_temperature_state,
                                 attrs_fn=FordpassDataHandler.get_cabin_temperature_attrs)

    DEVICECONNECTIVITY  = ApiKey(key="deviceConnectivity",
                                 state_fn=FordpassDataHandler.get_device_connectivity_state)

    DEEPSLEEP_IN_PROGRESS   = ApiKey(key="deepSleepInProgress",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_value_for_metrics_key(data, "deepSleepInProgress"))
    FIRMWAREUPG_IN_PROGRESS = ApiKey(key="firmwareUpgInProgress",
                                 state_fn=lambda data, prev_state: FordpassDataHandler.get_value_for_metrics_key(data, "firmwareUpgradeInProgress"),
                                 attrs_fn=lambda data, units: FordpassDataHandler.get_metrics_dict(data, "firmwareUpgradeInProgress"))


    LAST_ENERGY_CONSUMED= ApiKey(key="lastEnergyConsumed",
                                 state_fn=FordpassDataHandler.get_last_energy_consumed_state,
                                 attrs_fn=FordpassDataHandler.get_last_energy_consumed_attrs)

    LAST_ENERGY_TRANSFER_LOG_ENTRY  = ApiKey(key="energyTransferLogEntry",
                                 state_fn=FordpassDataHandler.get_energy_transfer_log_state,
                                 attrs_fn=FordpassDataHandler.get_energy_transfer_log_attrs)


    # Debug Sensors (Disabled by default)
    EVENTS = ApiKey(key="events",
                    state_fn=lambda data, prev_state: len(FordpassDataHandler.get_events(data)),
                    attrs_fn=lambda data, units: FordpassDataHandler.get_events(data))
    METRICS = ApiKey(key="metrics",
                     state_fn=lambda data, prev_state: len(FordpassDataHandler.get_metrics(data)),
                     attrs_fn=lambda data, units: FordpassDataHandler.get_metrics(data))
    STATES = ApiKey(key="states",
                    state_fn=lambda data, prev_state: len(FordpassDataHandler.get_states(data)),
                    attrs_fn=lambda data, units: FordpassDataHandler.get_states(data))
    VEHICLES = ApiKey(key="vehicles",
                      state_fn=lambda data, prev_state: len(FordpassDataHandler.get_vehicles(data)),
                      attrs_fn=lambda data, units: FordpassDataHandler.get_vehicles(data))

# tags that are only available for gas/diesel/plugin-hybrid (PHEV) vehicles...
FUEL_OR_PEV_ONLY_TAGS: Final = [
    Tag.FUEL,
    Tag.ENGINE_OIL_TEMP,
    Tag.DIESEL_SYSTEM_STATUS,
    Tag.EXHAUST_FLUID_LEVEL,
]

# tags that are only available for electric vehicles...
EV_ONLY_TAGS: Final = [
    Tag.SOC,
    Tag.EVCC_STATUS,
    Tag.ELVEH,
    Tag.ELVEH_PLUG,
    Tag.ELVEH_CHARGING,
    Tag.ELVEH_CHARGING_POWER,
    Tag.ELVEH_CHARGE,
    Tag.EV_START,
    Tag.EV_CANCEL,
    Tag.EV_PAUSE,
    Tag.ELVEH_TARGET_CHARGE,
    Tag.ELVEH_TARGET_CHARGE_ALT1,
    Tag.ELVEH_TARGET_CHARGE_ALT1,
    Tag.LAST_ENERGY_CONSUMED,
    Tag.LAST_ENERGY_TRANSFER_LOG_ENTRY
]

RCC_TAGS: Final = [
    Tag.RCC_DEFROST_REAR,
    Tag.RCC_DEFROST_FRONT,
    Tag.RCC_STEERING_WHEEL,
    Tag.RCC_SEAT_REAR_LEFT,
    Tag.RCC_SEAT_REAR_RIGHT,
    Tag.RCC_SEAT_FRONT_LEFT,
    Tag.RCC_SEAT_FRONT_RIGHT,
    Tag.RCC_TEMPERATURE,
]

@dataclass(frozen=True)
class ExtButtonEntityDescription(ButtonEntityDescription):
    tag: Tag | None = None
    name_addon: str | None = None

@dataclass(frozen=True)
class ExtSensorEntityDescription(SensorEntityDescription):
    tag: Tag | None = None
    skip_existence_check: bool | None = None
    name_addon: str | None = None

@dataclass(frozen=True)
class ExtSelectEntityDescription(SelectEntityDescription):
    tag: Tag | None = None
    skip_existence_check: bool | None = None
    name_addon: str | None = None

@dataclass(frozen=True)
class ExtNumberEntityDescription(NumberEntityDescription):
    tag: Tag | None = None
    skip_existence_check: bool | None = None
    name_addon: str | None = None


SENSORS = [
    # Tag.ODOMETER: {"icon": "mdi:counter", "state_class": "total", "device_class": "distance", "api_key": "odometer", "measurement": UnitOfLength.KILOMETERS},
    ExtSensorEntityDescription(
        tag=Tag.ODOMETER,
        key=Tag.ODOMETER.key,
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        has_entity_name=True,
    ),
    # Tag.FUEL: {"icon": "mdi:gas-station", "api_key": "fuelLevel", "measurement": PERCENTAGE},
    ExtSensorEntityDescription(
        tag=Tag.FUEL,
        key=Tag.FUEL.key,
        icon="mdi:gas-station",
        native_unit_of_measurement=PERCENTAGE,
        has_entity_name=True,
    ),
    # Tag.BATTERY: {"icon": "mdi:car-battery", "state_class": "measurement", "api_key": "batteryStateOfCharge", "measurement": PERCENTAGE},
    ExtSensorEntityDescription(
        tag=Tag.BATTERY,
        key=Tag.BATTERY.key,
        icon="mdi:car-battery",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        has_entity_name=True,
    ),
    # Tag.OIL: {"icon": "mdi:oil", "api_key": "oilLifeRemaining", "measurement": PERCENTAGE},
    ExtSensorEntityDescription(
        tag=Tag.OIL,
        key=Tag.OIL.key,
        icon="mdi:oil",
        native_unit_of_measurement=PERCENTAGE,
        has_entity_name=True,
    ),
    # Tag.TIRE_PRESSURE: {"icon": "mdi:car-tire-alert", "api_key": "tirePressure"},
    ExtSensorEntityDescription(
        tag=Tag.TIRE_PRESSURE,
        key=Tag.TIRE_PRESSURE.key,
        icon="mdi:car-tire-alert",
        has_entity_name=True,
    ),
    # Tag.GPS: {"icon": "mdi:radar", "api_key": "position"},
    ExtSensorEntityDescription(
        tag=Tag.GPS,
        key=Tag.GPS.key,
        icon="mdi:radar",
        has_entity_name=True,
    ),
    # Tag.ALARM: {"icon": "mdi:bell", "api_key": "alarmStatus"},
    ExtSensorEntityDescription(
        tag=Tag.ALARM,
        key=Tag.ALARM.key,
        icon="mdi:bell",
        has_entity_name=True,
    ),
    # Tag.IGNITION_STATUS: {"icon": "hass:power", "api_key": "ignitionStatus"},
    ExtSensorEntityDescription(
        tag=Tag.IGNITION_STATUS,
        key=Tag.IGNITION_STATUS.key,
        icon="hass:power",
        has_entity_name=True,
    ),
    # Tag.DOOR_STATUS: {"icon": "mdi:car-door", "api_key": "doorStatus"},
    ExtSensorEntityDescription(
        tag=Tag.DOOR_STATUS,
        key=Tag.DOOR_STATUS.key,
        icon="mdi:car-door",
        has_entity_name=True,
    ),
    # Tag.WINDOW_POSITION: {"icon": "mdi:car-door", "api_key": "windowStatus"},
    ExtSensorEntityDescription(
        tag=Tag.WINDOW_POSITION,
        key=Tag.WINDOW_POSITION.key,
        icon="mdi:car-door",
        has_entity_name=True,
    ),
    # Tag.LAST_REFRESH: {"icon": "mdi:clock", "device_class": "timestamp", "api_key": "lastRefresh", "skip_existence_check": True},
    ExtSensorEntityDescription(
        tag=Tag.LAST_REFRESH,
        key=Tag.LAST_REFRESH.key,
        icon="mdi:clock",
        device_class=SensorDeviceClass.TIMESTAMP,
        skip_existence_check=True,
        has_entity_name=True,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Tag.ELVEH: {"icon": "mdi:ev-station", "api_key": "xevBatteryRange", "device_class": "distance", "state_class": "measurement", "measurement": UnitOfLength.KILOMETERS},
    ExtSensorEntityDescription(
        tag=Tag.ELVEH,
        key=Tag.ELVEH.key,
        icon="mdi:ev-station",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        has_entity_name=True,
    ),
    # Tag.ELVEH_CHARGING: {"icon": "mdi:ev-station", "api_key": "xevBatteryChargeDisplayStatus"},
    ExtSensorEntityDescription(
        tag=Tag.ELVEH_CHARGING,
        key=Tag.ELVEH_CHARGING.key,
        icon="mdi:ev-station",
        has_entity_name=True,
    ),
    # Tag.ELVEH_CHARGING_POWER
    ExtSensorEntityDescription(
        tag=Tag.ELVEH_CHARGING_POWER,
        key=Tag.ELVEH_CHARGING_POWER.key,
        icon="mdi:ev-plug-ccs2",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        has_entity_name=True,
    ),
    # Tag.ELVEH_PLUG: {"icon": "mdi:connection", "api_key": "xevPlugChargerStatus"},
    ExtSensorEntityDescription(
        tag=Tag.ELVEH_PLUG,
        key=Tag.ELVEH_PLUG.key,
        icon="mdi:connection",
        has_entity_name=True,
    ),
    # Tag.SPEED: {"icon": "mdi:speedometer", "device_class": "speed", "state_class": "measurement", "api_key": "speed", "measurement": UnitOfSpeed.METERS_PER_SECOND},
    ExtSensorEntityDescription(
        tag=Tag.SPEED,
        key=Tag.SPEED.key,
        icon="mdi:speedometer",
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        has_entity_name=True,
    ),
    ExtSensorEntityDescription(
        tag=Tag.ENGINESPEED,
        key=Tag.ENGINESPEED.key,
        icon="mdi:gauge-low",
        state_class=SensorStateClass.MEASUREMENT,
        has_entity_name=True,
    ),
    ExtSensorEntityDescription(
        tag=Tag.GEARLEVERPOSITION,
        key=Tag.GEARLEVERPOSITION.key,
        icon="mdi:car-shift-pattern",
        has_entity_name=True,
    ),
    # Tag.INDICATORS: {"icon": "mdi:engine-outline", "api_key": "indicators"},
    ExtSensorEntityDescription(
        tag=Tag.INDICATORS,
        key=Tag.INDICATORS.key,
        icon="mdi:engine-outline",
        has_entity_name=True,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Tag.COOLANT_TEMP: {"icon": "mdi:coolant-temperature", "api_key": "engineCoolantTemp", "state_class": "measurement", "device_class": "temperature", "measurement": UnitOfTemperature.CELSIUS},
    ExtSensorEntityDescription(
        tag=Tag.COOLANT_TEMP,
        key=Tag.COOLANT_TEMP.key,
        icon="mdi:coolant-temperature",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        has_entity_name=True,
    ),
    # Tag.OUTSIDE_TEMP: {"icon": "mdi:thermometer", "state_class": "measurement", "device_class": "temperature", "api_key": "outsideTemperature", "measurement": UnitOfTemperature.CELSIUS},
    ExtSensorEntityDescription(
        tag=Tag.OUTSIDE_TEMP,
        key=Tag.OUTSIDE_TEMP.key,
        icon="mdi:thermometer",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        has_entity_name=True,
    ),
    # Tag.ENGINE_OIL_TEMP: {"icon": "mdi:oil-temperature", "state_class": "measurement", "device_class": "temperature", "api_key": "engineOilTemp", "measurement": UnitOfTemperature.CELSIUS},
    ExtSensorEntityDescription(
        tag=Tag.ENGINE_OIL_TEMP,
        key=Tag.ENGINE_OIL_TEMP.key,
        icon="mdi:oil-temperature",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        has_entity_name=True,
    ),
    ExtSensorEntityDescription(
        tag=Tag.YAW_RATE,
        key=Tag.YAW_RATE.key,
        icon="mdi:axis-y-rotate-clockwise",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=4,
        has_entity_name=True,
    ),
    ExtSensorEntityDescription(
        tag=Tag.ACCELERATION,
        key=Tag.ACCELERATION.key,
        icon="mdi:axis-arrow",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        has_entity_name=True,
    ),
    ExtSensorEntityDescription(
        tag=Tag.BRAKE_PEDAL_STATUS,
        key=Tag.BRAKE_PEDAL_STATUS.key,
        icon="mdi:car-brake-alert",
        has_entity_name=True,
    ),
    ExtSensorEntityDescription(
        tag=Tag.BRAKE_TORQUE,
        key=Tag.BRAKE_TORQUE.key,
        icon="mdi:car-brake-hold",
        state_class=SensorStateClass.MEASUREMENT,
        has_entity_name=True,
    ),
    ExtSensorEntityDescription(
        tag=Tag.ACCELERATOR_PEDAL,
        key=Tag.ACCELERATOR_PEDAL.key,
        icon="mdi:arrow-up-bold-outline",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        has_entity_name=True,
    ),
    ExtSensorEntityDescription(
        tag=Tag.PARKING_BRAKE,
        key=Tag.PARKING_BRAKE.key,
        icon="mdi:car-brake-parking",
        has_entity_name=True,
    ),
    ExtSensorEntityDescription(
        tag=Tag.TORQUE_TRANSMISSION,
        key=Tag.TORQUE_TRANSMISSION.key,
        icon="mdi:arrow-up-bold-box",
        state_class=SensorStateClass.MEASUREMENT,
        has_entity_name=True,
    ),
    ExtSensorEntityDescription(
        tag=Tag.WHEEL_TORQUE,
        key=Tag.WHEEL_TORQUE.key,
        icon="mdi:tire",
        has_entity_name=True,
    ),
    ExtSensorEntityDescription(
        tag=Tag.CABIN_TEMP,
        key=Tag.CABIN_TEMP.key,
        icon="mdi:home-thermometer",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        has_entity_name=True,
    ),
    # Tag.DEEPSLEEP: {"icon": "mdi:power-sleep", "name": "Deep Sleep Mode Active", "api_key": "commandPreclusion", "api_class": "states"},
    ExtSensorEntityDescription(
        tag=Tag.DEEPSLEEP,
        key=Tag.DEEPSLEEP.key,
        icon="mdi:power-sleep",
        name="Deep Sleep Mode Active",
        has_entity_name=True,
    ),
    # Tag.REMOTE_START_STATUS: {"icon": "mdi:remote", "api_key": "remoteStartCountdownTimer"},
    ExtSensorEntityDescription(
        tag=Tag.REMOTE_START_STATUS,
        key=Tag.REMOTE_START_STATUS.key,
        icon="mdi:remote",
        has_entity_name=True,
    ),
    ExtSensorEntityDescription(
        tag=Tag.REMOTE_START_COUNTDOWN,
        key=Tag.REMOTE_START_COUNTDOWN.key,
        icon="mdi:counter",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        suggested_display_precision=0,
        has_entity_name=True,
    ),
    # Tag.MESSAGES: {"icon": "mdi:message-text", "api_key": "messages", "measurement": "messages", "skip_existence_check": True},
    ExtSensorEntityDescription(
        tag=Tag.MESSAGES,
        key=Tag.MESSAGES.key,
        icon="mdi:message-text",
        native_unit_of_measurement="messages",
        skip_existence_check=True,
        has_entity_name=True,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Tag.DIESEL_SYSTEM_STATUS: {"icon": "mdi:smoking-pipe", "api_key": "dieselExhaustFilterStatus"},
    ExtSensorEntityDescription(
        tag=Tag.DIESEL_SYSTEM_STATUS,
        key=Tag.DIESEL_SYSTEM_STATUS.key,
        icon="mdi:smoking-pipe",
        has_entity_name=True,
    ),
    # Tag.EXHAUST_FLUID_LEVEL: {"icon": "mdi:barrel", "api_key": "dieselExhaustFluidLevel", "measurement": PERCENTAGE},
    ExtSensorEntityDescription(
        tag=Tag.EXHAUST_FLUID_LEVEL,
        key=Tag.EXHAUST_FLUID_LEVEL.key,
        icon="mdi:barrel",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        has_entity_name=True,
    ),
    # Tag.SOC: {"icon": "mdi:battery-high", "api_key": "xevBatteryStateOfCharge", "state_class": "measurement", "measurement": PERCENTAGE},
    ExtSensorEntityDescription(
        tag=Tag.SOC,
        key=Tag.SOC.key,
        icon="mdi:battery-high",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        has_entity_name=True,
    ),
    # Tag.EVCC_STATUS: {"icon": "mdi:state-machine", "api_key": "CAN_BE_IGNORED_IF_TYPE_IS_SINGLE", "skip_existence_check": True},
    ExtSensorEntityDescription(
        tag=Tag.EVCC_STATUS,
        key=Tag.EVCC_STATUS.key,
        icon="mdi:state-machine",
        skip_existence_check=True,
        has_entity_name=True,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ExtSensorEntityDescription(
        tag=Tag.SEATBELT,
        key=Tag.SEATBELT.key,
        icon="mdi:seatbelt",
        has_entity_name=True,
    ),
    ExtSensorEntityDescription(
        tag=Tag.DEVICECONNECTIVITY,
        key=Tag.DEVICECONNECTIVITY.key,
        icon="mdi:connection",
        has_entity_name=True,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ExtSensorEntityDescription(
        tag=Tag.LAST_ENERGY_CONSUMED,
        key=Tag.LAST_ENERGY_CONSUMED.key,
        icon="mdi:counter",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        has_entity_name=True,
    ),
    ExtSensorEntityDescription(
        tag=Tag.LAST_ENERGY_TRANSFER_LOG_ENTRY,
        key=Tag.LAST_ENERGY_TRANSFER_LOG_ENTRY.key,
        skip_existence_check=True,
        icon="mdi:ev-station",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        has_entity_name=True,
    ),


    # Debug sensors (disabled by default)
    # Tag.EVENTS: {"icon": "mdi:calendar", "api_key": "events", "skip_existence_check": True, "debug": True},
    ExtSensorEntityDescription(
        tag=Tag.EVENTS,
        key=Tag.EVENTS.key,
        icon="mdi:calendar",
        entity_registry_enabled_default=False,
        skip_existence_check=True,
        has_entity_name=True,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Tag.METRICS: {"icon": "mdi:chart-line", "api_key": "metrics", "skip_existence_check": True, "debug": True},
    ExtSensorEntityDescription(
        tag=Tag.METRICS,
        key=Tag.METRICS.key,
        icon="mdi:chart-line",
        entity_registry_enabled_default=False,
        skip_existence_check=True,
        has_entity_name=True,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Tag.STATES: {"icon": "mdi:car", "api_key": "states", "skip_existence_check": True, "debug": True},
    ExtSensorEntityDescription(
        tag=Tag.STATES,
        key=Tag.STATES.key,
        icon="mdi:car",
        entity_registry_enabled_default=False,
        skip_existence_check=True,
        has_entity_name=True,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Tag.VEHICLES: {"icon": "mdi:car-multiple", "api_key": "vehicles", "skip_existence_check": True, "debug": True},
    ExtSensorEntityDescription(
        tag=Tag.VEHICLES,
        key=Tag.VEHICLES.key,
        icon="mdi:car-multiple",
        entity_registry_enabled_default=False,
        skip_existence_check=True,
        has_entity_name=True,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ExtSensorEntityDescription(
        tag=Tag.DOOR_LOCK,
        key=Tag.DOOR_LOCK.key,
        icon="mdi:car-door-lock",
        has_entity_name=True,
        entity_registry_enabled_default=True
    ),
]

# UNHANDLED_METTRICS:
# hybridVehicleModeStatus
# seatBeltStatus
# configurations
# vehicleLifeCycleMode
# displaySystemOfMeasure


SENSORSX = {
    # Tag.FIRMWAREUPGINPROGRESS: {"icon": "mdi:one-up", "name": "Firmware Update In Progress"},
}

SWITCHES = {
    Tag.REMOTE_START: {"icon": "mdi:air-conditioner"},
    Tag.ELVEH_CHARGE: {"icon": "mdi:ev-station"},
    #Tag.GUARDMODE: {"icon": "mdi:shield-key"}
    Tag.AUTO_UPDATES: {"icon": "mdi:cloud-arrow-down-outline"},

    Tag.RCC_STEERING_WHEEL: {"icon": "mdi:steering"},
    Tag.RCC_DEFROST_FRONT: {"icon": "mdi:car-defrost-front"},
    Tag.RCC_DEFROST_REAR: {"icon": "mdi:car-defrost-rear"},
}

BUTTONS = [
    ExtButtonEntityDescription(
        tag=Tag.UPDATE_DATA,
        key=Tag.UPDATE_DATA.key,
        icon="mdi:refresh",
        has_entity_name=True,
    ),
    ExtButtonEntityDescription(
        tag=Tag.REQUEST_REFRESH,
        key=Tag.REQUEST_REFRESH.key,
        icon="mdi:car-connected",
        has_entity_name=True,
    ),
    ExtButtonEntityDescription(
        tag=Tag.DOOR_LOCK,
        key=Tag.DOOR_LOCK.key,
        icon="mdi:car-door-lock",
        has_entity_name=True,
        entity_registry_enabled_default=False
    ),
    ExtButtonEntityDescription(
        tag=Tag.DOOR_UNLOCK,
        key=Tag.DOOR_UNLOCK.key,
        icon="mdi:car-door-lock-open",
        has_entity_name=True,
        entity_registry_enabled_default=False
    ),
    ExtButtonEntityDescription(
        tag=Tag.EV_START,
        key=Tag.EV_START.key,
        icon="mdi:play-circle",
        has_entity_name=True
    ),
    ExtButtonEntityDescription(
        tag=Tag.EV_CANCEL,
        key=Tag.EV_CANCEL.key,
        icon="mdi:eject-circle",
        has_entity_name=True,
        entity_registry_enabled_default=False
    ),
    ExtButtonEntityDescription(
        tag=Tag.EV_PAUSE,
        key=Tag.EV_PAUSE.key,
        icon="mdi:pause-circle",
        has_entity_name=True,
        entity_registry_enabled_default=False
    ),
    ExtButtonEntityDescription(
        tag=Tag.HAF_SHORT,
        key=Tag.HAF_SHORT.key,
        icon="mdi:car-search-outline",
        has_entity_name=True,
    ),
    ExtButtonEntityDescription(
        tag=Tag.HAF_DEFAULT,
        key=Tag.HAF_DEFAULT.key,
        icon="mdi:car-search",
        has_entity_name=True,
    ),
    ExtButtonEntityDescription(
        tag=Tag.HAF_LONG,
        key=Tag.HAF_LONG.key,
        icon="mdi:bugle",
        has_entity_name=True,
        entity_registry_enabled_default=False
    ),
    ExtButtonEntityDescription(
        tag=Tag.EXTEND_REMOTE_START,
        key=Tag.EXTEND_REMOTE_START.key,
        icon="mdi:air-conditioner",
        has_entity_name=True,
    ),
    ExtButtonEntityDescription(
        tag=Tag.MESSAGES_DELETE_LAST,
        key=Tag.MESSAGES_DELETE_LAST.key,
        icon="mdi:delete",
        has_entity_name=True,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ExtButtonEntityDescription(
        tag=Tag.MESSAGES_DELETE_ALL,
        key=Tag.MESSAGES_DELETE_ALL.key,
        icon="mdi:delete-alert",
        has_entity_name=True,
        entity_category=EntityCategory.DIAGNOSTIC,
    )
]

SELECTS = [
    ExtSelectEntityDescription(
        tag=Tag.ZONE_LIGHTING,
        key=Tag.ZONE_LIGHTING.key,
        icon="mdi:car-parking-lights", # mdi:spotlight-beam
        options=ZONE_LIGHTS_OPTIONS,
        has_entity_name=True,
    ),
    ExtSelectEntityDescription(
        tag=Tag.RCC_SEAT_FRONT_LEFT,
        key=Tag.RCC_SEAT_FRONT_LEFT.key,
        icon="mdi:car-seat", # mdi:car-seat-cooler | mdi:car-seat-heater
        options=RCC_SEAT_OPTIONS_FULL,
        has_entity_name=True,
    ),
    ExtSelectEntityDescription(
        tag=Tag.RCC_SEAT_FRONT_RIGHT,
        key=Tag.RCC_SEAT_FRONT_RIGHT.key,
        icon="mdi:car-seat", # mdi:car-seat-cooler | mdi:car-seat-heater
        options=RCC_SEAT_OPTIONS_FULL,
        has_entity_name=True,
    ),
    ExtSelectEntityDescription(
        tag=Tag.RCC_SEAT_REAR_LEFT,
        key=Tag.RCC_SEAT_REAR_LEFT.key,
        icon="mdi:car-seat", # mdi:car-seat-cooler | mdi:car-seat-heater
        options=RCC_SEAT_OPTIONS_FULL,
        has_entity_name=True,
    ),
    ExtSelectEntityDescription(
        tag=Tag.RCC_SEAT_REAR_RIGHT,
        key=Tag.RCC_SEAT_REAR_RIGHT.key,
        icon="mdi:car-seat", # mdi:car-seat-cooler | mdi:car-seat-heater
        options=RCC_SEAT_OPTIONS_FULL,
        has_entity_name=True,
    ),
    ExtSelectEntityDescription(
        tag=Tag.ELVEH_TARGET_CHARGE,
        key=Tag.ELVEH_TARGET_CHARGE.key,
        icon="mdi:battery-charging-high",
        options=ELVEH_TARGET_CHARGE_OPTIONS,
        has_entity_name=True,
    ),
    ExtSelectEntityDescription(
        tag=Tag.ELVEH_TARGET_CHARGE_ALT1,
        key=Tag.ELVEH_TARGET_CHARGE_ALT1.key,
        icon="mdi:battery-charging-high",
        options=ELVEH_TARGET_CHARGE_OPTIONS,
        has_entity_name=True,
        entity_registry_enabled_default=False,
    ),
    ExtSelectEntityDescription(
        tag=Tag.ELVEH_TARGET_CHARGE_ALT2,
        key=Tag.ELVEH_TARGET_CHARGE_ALT2.key,
        icon="mdi:battery-charging-high",
        options=ELVEH_TARGET_CHARGE_OPTIONS,
        has_entity_name=True,
        entity_registry_enabled_default=False,
    ),
    ExtSelectEntityDescription(
        tag=Tag.RCC_TEMPERATURE,
        key=Tag.RCC_TEMPERATURE.key,
        device_class=NumberDeviceClass.TEMPERATURE,
        icon="mdi:thermometer",
        options=RCC_TEMPERATURES_CELSIUS,
        has_entity_name=True
    ),
    ExtSelectEntityDescription(
        tag=Tag.GLOBAL_TARGET_SOC,
        key=Tag.GLOBAL_TARGET_SOC.key,
        icon="mdi:battery-charging-high",
        options=ELVEH_TARGET_CHARGE_OPTIONS,
        has_entity_name=True,
    )
]

NUMBERS = [
    ExtNumberEntityDescription(
        tag=Tag.RCC_TEMPERATURE,
        key=Tag.RCC_TEMPERATURE.key,
        skip_existence_check=True,
        icon="mdi:thermometer",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=15.5,
        native_max_value=30.5,
        native_step=0.5,
        mode=NumberMode.BOX,
        has_entity_name=True,
        entity_registry_enabled_default=False
    ),
    ExtNumberEntityDescription(
        tag=Tag.GLOBAL_AC_CURRENT_LIMIT,
        key=Tag.GLOBAL_AC_CURRENT_LIMIT.key,
        icon="mdi:current-ac",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        native_min_value=5,
        native_max_value=48,
        native_step=1,
        mode=NumberMode.BOX,
        has_entity_name=True,
    ),
    # IS NOW A SELECT cause values are 50, 60, 70, 80, 85, 90, 95 & 100
    # ExtNumberEntityDescription(
    #     tag=Tag.GLOBAL_DC_POWER_LIMIT,
    #     key=Tag.GLOBAL_DC_POWER_LIMIT.key,
    #     icon="mdi:current-dc",
    #     native_unit_of_measurement=UnitOfPower.WATT,
    #     native_min_value=10,
    #     native_max_value=160,
    #     native_step=1,
    #     mode=NumberMode.BOX,
    #     has_entity_name=True,
    #     entity_registry_enabled_default=False
    # )
]
