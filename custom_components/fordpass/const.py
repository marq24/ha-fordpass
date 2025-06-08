"""Constants for the FordPass integration."""
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Final, NamedTuple, Callable, Any

from homeassistant.components.sensor import SensorStateClass, SensorDeviceClass, SensorEntityDescription
from homeassistant.const import UnitOfSpeed, UnitOfLength, UnitOfTemperature, PERCENTAGE, EntityCategory
from homeassistant.util.unit_system import UnitSystem

from custom_components.fordpass.fordpass_handler import FordpassDataHandler

_LOGGER = logging.getLogger(__name__)

DOMAIN: Final = "fordpass"

VIN: Final = "vin"

MANUFACTURER: Final = "Ford Motor Company"

CONF_PRESSURE_UNIT: Final = "pressure_unit"
DEFAULT_PRESSURE_UNIT: Final = "kPa"
PRESSURE_UNITS: Final = ["PSI", "kPa", "BAR"]

UPDATE_INTERVAL: Final = "update_interval"
UPDATE_INTERVAL_DEFAULT: Final = 290 # it looks like that the default auto-access_token expires after 5 minutes (300 seconds)

COORDINATOR: Final = "coordinator"

REGION_OPTIONS: Final = ["germany", "france", "italy", "netherlands", "uk_europe", "canada", "usa", "rdw"]
REGION_OPTIONS_BROKEN: Final = ["australia"]
DEFAULT_REGION: Final = "rdw"

REGIONS: Final = {
    # checked 2025/06/08 - working fine...
    "germany": {
        "app_id": "667D773E-1BDC-4139-8AD0-2B16474E8DC7",
        "locale": "de-DE",
        "locale_url": "https://login.ford.de",
        "countrycode": "DEU"
    },
    # checked 2025/06/08 - working fine...
    "france": {
        "app_id": "667D773E-1BDC-4139-8AD0-2B16474E8DC7",
        "locale": "fr-FR",
        "locale_url": "https://login.ford.com",
        "countrycode": "FRA"
    },
    # checked 2025/06/08 - working fine...
    "italy": {
        "app_id": "667D773E-1BDC-4139-8AD0-2B16474E8DC7",
        "locale": "it-IT",
        "locale_url": "https://login.ford.com",
        "countrycode": "ITA"
    },
    # checked 2025/06/08 - working fine...
    "netherlands": {
        "app_id": "667D773E-1BDC-4139-8AD0-2B16474E8DC7", # 1E8C7794-FF5F-49BC-9596-A1E0C86C5B19
        "locale": "nl-NL",
        "locale_url": "https://login.ford.com",
        "countrycode": "NLD"
    },
    # checked 2025/06/08 - working fine...
    "uk_europe": {
        "app_id": "667D773E-1BDC-4139-8AD0-2B16474E8DC7", # 1E8C7794-FF5F-49BC-9596-A1E0C86C5B19",
        "locale": "en-GB",
        "locale_url": "https://login.ford.co.uk",
        "countrycode": "GBR"
    },
    # checked 2025/06/08 - working fine...
    "canada": {
        "app_id": "BFE8C5ED-D687-4C19-A5DD-F92CDFC4503A",
        "locale": "en-CA",
        "locale_url": "https://login.ford.com",
        "countrycode": "CAN"
    },
    # checked 2025/06/08 - working fine...
    "usa": {
        "app_id": "BFE8C5ED-D687-4C19-A5DD-F92CDFC4503A", # 71A3AD0A-CF46-4CCF-B473-FC7FE5BC4592
        "locale": "en-US",
        "locale_url": "https://login.ford.com",
        "countrycode": "USA"
    },
    # we use the 'usa' as the default region...
    "rdw": {
        "app_id": "BFE8C5ED-D687-4C19-A5DD-F92CDFC4503A",
        "locale": "en-US",
        "locale_url": "https://login.ford.com",
        "countrycode": "USA"
    },

    # DOES NOT WORK... checked 2025/06/08
    "australia": {
        "app_id": "39CD6590-B1B9-42CB-BEF9-0DC1FDB96260",
        "locale": "en-AU",
        "locale_url": "https://login.ford.com",
        "countrycode": "AUS"
    },
}

WINDOW_POSITIONS: Final = {
    "CLOSED": {
        "Fully_Closed": "Closed",
        "Fully_closed_position": "Closed",
        "Fully closed position": "Closed",
    },
    "OPEN": {
        "Fully open position": "Open",
        "Fully_Open": "Open",
        "Btwn 10% and 60% open": "Open-Partial",
    },
}


class ApiKey(NamedTuple):
    key: str
    state_fn: Callable[[dict], Any] = None
    attrs_fn: Callable[[dict, UnitSystem], Any] = None
    on_off_fn: Callable[[Any, bool], Any] = None


class Tag(ApiKey, Enum):

    def __hash__(self) -> int:
        return hash(self.key)

    def __str__(self):
        return self.key

    def get_state(self, data):
        if self.state_fn:
            return self.state_fn(data)
        return None

    def get_attributes(self, data, units: UnitSystem):
        if self.attrs_fn:
            return self.attrs_fn(data, units)
        return None

    def turn_on_off(self, vehicle, turn_on:bool) -> bool:
        if self.on_off_fn:
            return self.on_off_fn(vehicle, turn_on)
        else:
            _LOGGER.warning(f"Tag {self.key} does not support turning ON.")
            return False

    ##################################################
    ##################################################

    # DEVIVE_TRACKER
    ##################################################
    TRACKER             = ApiKey(key="tracker",
                                 attrs_fn=FordpassDataHandler.get_gps_tracker_attr)

    # LOCKS
    ##################################################
    DOOR_LOCK           = ApiKey(key="doorlock",
                                 state_fn=lambda data: FordpassDataHandler.get_value_at_index_for_metrics_key(data, "doorLockStatus", 0))

    # SWITCHES
    ##################################################
    # for historic reasons the key is "ignition" (even if it's the remote_start switch)
    REMOTE_START        = ApiKey(key="ignition",
                                 state_fn=FordpassDataHandler.get_remote_start_state,
                                 on_off_fn=FordpassDataHandler.remote_start_on_off)
    GUARD_MODE          = ApiKey(key="guardmode",
                                 state_fn=FordpassDataHandler.get_guard_mode_state,
                                 on_off_fn=FordpassDataHandler.guardmode_on_off)

    ELVEH_CHARGE        = ApiKey(key="elVehCharge",
                                 state_fn=lambda data: FordpassDataHandler.get_value_for_metrics_key(data, "xevBatteryChargeDisplayStatus"),
                                 on_off_fn=FordpassDataHandler.get_elveh_on_off)


# BUTTONS
    ##################################################
    UPDATE_DATA         = ApiKey(key="update_data")
    REQUEST_REFRESH     = ApiKey(key="request_refresh")

    # SENSORS
    ##################################################
    ODOMETER            = ApiKey(key="odometer",
                                 state_fn=lambda data: FordpassDataHandler.get_value_for_metrics_key(data, "odometer"),
                                 attrs_fn=lambda data, units: FordpassDataHandler.get_metrics_dict(data, "odometer"))
    FUEL                = ApiKey(key="fuel",
                                 state_fn=FordpassDataHandler.get_fuel_state,
                                 attrs_fn=FordpassDataHandler.get_fuel_attrs)
    BATTERY             = ApiKey(key="battery",
                                 state_fn=lambda data: round(FordpassDataHandler.get_value_for_metrics_key(data, "batteryStateOfCharge", 0)),
                                 attrs_fn=FordpassDataHandler.get_battery_attrs)
    OIL                 = ApiKey(key="oil",
                                 state_fn=lambda data: FordpassDataHandler.get_value_for_metrics_key(data, "oilLifeRemaining"),
                                 attrs_fn=lambda data, units: FordpassDataHandler.get_metrics_dict(data, "oilLifeRemaining"))
    SEATBELT            = ApiKey(key="seatbelt",
                                 state_fn=lambda data: FordpassDataHandler.get_value_at_index_for_metrics_key(data, "seatBeltStatus", 0, None),
                                 attrs_fn=FordpassDataHandler.get_seatbelt_attrs)
    TIRE_PRESSURE       = ApiKey(key="tirePressure",
                                 state_fn=lambda data: FordpassDataHandler.get_value_at_index_for_metrics_key(data, "tirePressureSystemStatus", 0),
                                 attrs_fn=FordpassDataHandler.get_tire_pressure_attrs)
    GPS                 = ApiKey(key="gps",
                                 state_fn=FordpassDataHandler.get_gps_state,
                                 attrs_fn=FordpassDataHandler.get_gps_attr)
    ALARM               = ApiKey(key="alarm",
                                 state_fn=lambda data: FordpassDataHandler.get_value_for_metrics_key(data, "alarmStatus"),
                                 attrs_fn=FordpassDataHandler.get_alarm_attr)
    IGNITION_STATUS     = ApiKey(key="ignitionStatus",
                                 state_fn=lambda data: FordpassDataHandler.get_value_for_metrics_key(data, "ignitionStatus"),
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
                                 state_fn=lambda data: FordpassDataHandler.get_value_for_metrics_key(data, "xevBatteryChargeDisplayStatus"),
                                 attrs_fn=FordpassDataHandler.get_elveh_charging_attrs)
    ELVEH_PLUG          = ApiKey(key="elVehPlug",
                                 state_fn=lambda data: FordpassDataHandler.get_value_for_metrics_key(data, "xevPlugChargerStatus"),
                                 attrs_fn=FordpassDataHandler.get_elveh_plug_attrs)
    DEEPSLEEP           = ApiKey(key="deepSleep",
                                 state_fn=FordpassDataHandler.get_deepsleep_state)
    REMOTE_START_STATUS = ApiKey(key="remoteStartStatus",
                                 state_fn=FordpassDataHandler.get_remote_start_status_state,
                                 attrs_fn=FordpassDataHandler.get_remote_start_status_attrs)
    ZONE_LIGHTING       = ApiKey(key="zoneLighting",
                                 state_fn=FordpassDataHandler.get_zone_lighting_state,
                                 attrs_fn=FordpassDataHandler.get_zone_lighting_attrs)
    MESSAGES            = ApiKey(key="messages",
                                 state_fn=FordpassDataHandler.get_messages_state,
                                 attrs_fn=FordpassDataHandler.get_messages_attrs)
    DIESEL_SYSTEM_STATUS= ApiKey(key="dieselSystemStatus",
                                 state_fn=lambda data: FordpassDataHandler.get_value_for_metrics_key(data, "dieselExhaustFilterStatus"),
                                 attrs_fn=FordpassDataHandler.get_diesel_system_status_attrs)
    EXHAUST_FLUID_LEVEL = ApiKey(key="exhaustFluidLevel",
                                 state_fn=lambda data: FordpassDataHandler.get_value_for_metrics_key(data, "dieselExhaustFluidLevel"),
                                 attrs_fn=FordpassDataHandler.get_exhaust_fluid_level_attrs)
    SPEED               = ApiKey(key="speed",
                                 state_fn=lambda data: FordpassDataHandler.get_value_for_metrics_key(data, "speed"),
                                 attrs_fn=FordpassDataHandler.get_speed_attrs)
    INDICATORS          = ApiKey(key="indicators",
                                 state_fn=FordpassDataHandler.get_indicators_state,
                                 attrs_fn=FordpassDataHandler.get_indicators_attrs)
    COOLANT_TEMP        = ApiKey(key="coolantTemp",
                                 state_fn=lambda data: FordpassDataHandler.get_value_for_metrics_key(data, "engineCoolantTemp"))
    OUTSIDE_TEMP        = ApiKey(key="outsideTemp",
                                 state_fn=lambda data: FordpassDataHandler.get_value_for_metrics_key(data, "outsideTemperature"),
                                 attrs_fn=FordpassDataHandler.get_outside_temp_attrs)
    ENGINE_OIL_TEMP     = ApiKey(key="engineOilTemp",
                                 state_fn=lambda data: FordpassDataHandler.get_value_for_metrics_key(data, "engineOilTemp"))
    SOC                 = ApiKey(key="soc",
                                 state_fn=FordpassDataHandler.get_soc_state,
                                 attrs_fn=FordpassDataHandler.get_soc_attrs)
    EVCC_STATUS         = ApiKey(key="evccStatus",
                                 state_fn=FordpassDataHandler.get_evcc_status_state)

    DEEPSLEEP_IN_PROGRESS   = ApiKey(key="deepSleepInProgress",
                                     state_fn=lambda data: FordpassDataHandler.get_value_for_metrics_key(data, "deepSleepInProgress"))
    FIRMWAREUPG_IN_PROGRESS = ApiKey(key="firmwareUpgInProgress",
                                     state_fn=lambda data: FordpassDataHandler.get_value_for_metrics_key(data, "firmwareUpgradeInProgress"),
                                     attrs_fn=lambda data, units: FordpassDataHandler.get_metrics_dict(data, "firmwareUpgradeInProgress"))

    # Debug Sensors (Disabled by default)
    EVENTS = ApiKey(key="events",
                    state_fn=lambda data: len(FordpassDataHandler.get_events(data)),
                    attrs_fn=lambda data, units: FordpassDataHandler.get_events(data))
    METRICS = ApiKey(key="metrics",
                     state_fn=lambda data: len(FordpassDataHandler.get_metrics(data)),
                     attrs_fn=lambda data, units: FordpassDataHandler.get_metrics(data))
    STATES = ApiKey(key="states",
                    state_fn=lambda data: len(FordpassDataHandler.get_states(data)),
                    attrs_fn=lambda data, units: FordpassDataHandler.get_states(data))
    VEHICLES = ApiKey(key="vehicles",
                      state_fn=lambda data: len(FordpassDataHandler.get_vehicles(data)),
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
    Tag.ELVEH_CHARGE
]


@dataclass
class ExtSensorEntityDescription(SensorEntityDescription, frozen_or_thawed=True):
    tag: Tag | None = None
    skip_existence_check: bool | None = None


SENSORS = [
    # Tag.ODOMETER: {"icon": "mdi:counter", "state_class": "total", "device_class": "distance", "api_key": "odometer", "measurement": UnitOfLength.KILOMETERS},
    ExtSensorEntityDescription(
        tag=Tag.ODOMETER,
        key=Tag.ODOMETER.key,
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL,
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
        skip_existence_check=True,
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
]

# UNHANDLED_METTRICS:
# hybridVehicleModeStatus
# seatBeltStatus
# configurations
# vehicleLifeCycleMode
# displaySystemOfMeasure


SENSORSX = {
    # Tag.FIRMWAREUPGINPROGRESS: {"icon": "mdi:one-up", "name": "Firmware Update In Progress"},
    # Tag.ZONELIGHTING: {"icon": "mdi:spotlight-beam"},
}

SWITCHES = {
    Tag.REMOTE_START: {"icon": "mdi:air-conditioner"},
    #Tag.ELVEH_CHARGE: {"icon": "mdi:ev-station"},
    #Tag.GUARDMODE: {"icon": "mdi:shield-key"}
}

BUTTONS = {
    Tag.UPDATE_DATA:        {"icon": "mdi:refresh"},
    Tag.REQUEST_REFRESH:    {"icon": "mdi:car-connected"}
}