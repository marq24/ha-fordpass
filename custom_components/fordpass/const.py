"""Constants for the FordPass integration."""
from enum import Enum
from typing import NamedTuple

DOMAIN = "fordpass"

VIN = "vin"

MANUFACTURER = "Ford Motor Company"

DEFAULT_PRESSURE_UNIT = "kPa"
DEFAULT_DISTANCE_UNIT = "km"

CONF_PRESSURE_UNIT = "pressure_unit"
CONF_DISTANCE_UNIT = "distance_unit"

PRESSURE_UNITS = ["PSI", "kPa", "BAR"]
DISTANCE_UNITS = ["mi", "km"]
DISTANCE_CONVERSION_DISABLED = "distance_conversion"
DISTANCE_CONVERSION_DISABLED_DEFAULT = False

UPDATE_INTERVAL = "update_interval"
UPDATE_INTERVAL_DEFAULT = 290 # looks like that the default auto-access_token expires after 5 minutes (300 seconds)

COORDINATOR = "coordinator"
REGION = "region"

REGION_OPTIONS = ["USA", "Canada", "Australia", "UK&Europe", "Netherlands"]
DEFAULT_REGION = "USA"

REGIONS = {
    "Netherlands": {
        "region": "1E8C7794-FF5F-49BC-9596-A1E0C86C5B19",
        "locale": "nl-NL",
        "locale_short": "NL",
        "locale_url": "https://login.ford.nl",
        "countrycode": "NLD"
    },
    "UK&Europe": {
        "region": "1E8C7794-FF5F-49BC-9596-A1E0C86C5B19",
        "locale": "en-GB",
        "locale_short": "IE",  # Temp fix
        "locale_url": "https://login.ford.co.uk",
        "countrycode": "GBR"
    },
    "Australia": {
        "region": "5C80A6BB-CF0D-4A30-BDBF-FC804B5C1A98",
        "locale": "en-AU",
        "locale_short": "AUS",
        "locale_url": "https://login.ford.com",
        "countrycode": "AUS"
    },
    "USA": {
        "region": "71A3AD0A-CF46-4CCF-B473-FC7FE5BC4592",  # ???
        "locale": "en-US",
        "locale_short": "USA",
        "locale_url": "https://login.ford.com",  # Reverted from AU to US because it appears to be working
        "countrycode": "USA"
    },
    "Canada": {
        "region": "71A3AD0A-CF46-4CCF-B473-FC7FE5BC4592",
        "locale": "en-CA",
        "locale_short": "CAN",
        "locale_url": "https://login.ford.com",
        "countrycode": "USA"
    }
}

WINDOW_POSITIONS = {
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

class Tag(ApiKey, Enum):

    def __hash__(self) -> int:
        return hash(self.key)

    def __str__(self):
        return self.key

        # "auxPower": 1116.8,
    TRACKER = ApiKey(key="tracker")
    DOOR_LOCK = ApiKey(key="doorLock")

    IGNITION = ApiKey(key="ignition")
    GUARD_MODE = ApiKey(key="guardmode")

    UPDATE_DATA = ApiKey(key="update_data")
    REQUEST_REFRESH = ApiKey(key="request_refresh")

    ODOMETER = ApiKey(key="odometer")
    FUEL = ApiKey(key="fuel")
    BATTERY = ApiKey(key="battery")
    OIL = ApiKey(key="oil")
    TIRE_PRESSURE = ApiKey(key="tirePressure")
    GPS = ApiKey(key="gps")
    ALARM = ApiKey(key="alarm")
    IGNITION_STATUS = ApiKey(key="ignitionStatus")
    DOOR_STATUS = ApiKey(key="doorStatus")
    WINDOW_POSITION = ApiKey(key="windowPosition")
    LAST_REFRESH = ApiKey(key="lastRefresh")
    ELVEH = ApiKey(key="elVeh")
    ELVEH_CHARGING = ApiKey(key="elVehCharging")
    SPEED = ApiKey(key="speed")
    INDICATORS = ApiKey(key="indicators")
    COOLANT_TEMP = ApiKey(key="coolantTemp")
    OUTSIDE_TEMP = ApiKey(key="outsideTemp")
    ENGINE_OIL_TEMP = ApiKey(key="engineOilTemp")
    DEEPSLEEP = ApiKey(key="deepSleep")
    DEEPSLEEP_IN_PROGRESS = ApiKey(key="deepSleepInProgress")
    FIRMWAREUPG_IN_PROGRESS = ApiKey(key="firmwareUpgInProgress")
    REMOTE_START_STATUS = ApiKey(key="remoteStartStatus")
    ZONE_LIGHTING = ApiKey(key="zoneLighting")
    MESSAGES = ApiKey(key="messages")
    DIESEL_SYSTEM_STATUS = ApiKey(key="dieselSystemStatus")
    EXHAUST_FLUID_LEVEL = ApiKey(key="exhaustFluidLevel")
    # Debug Sensors (Disabled by default)
    EVENTS = ApiKey(key="events")
    METRICS = ApiKey(key="metrics")
    STATES = ApiKey(key="states")
    VEHICLES = ApiKey(key="vehicles")

    SOC = ApiKey(key="soc")
    EVCC_STATUS = ApiKey(key="evccStatus")

SENSORS = {
    Tag.ODOMETER:               {"icon": "mdi:counter", "state_class": "total", "device_class": "distance", "api_key": "odometer", "measurement": "km"},
    Tag.FUEL:                   {"icon": "mdi:gas-station", "api_key": ["fuelLevel", "xevBatteryStateOfCharge"], "measurement": "%"},
    Tag.BATTERY:                {"icon": "mdi:car-battery", "device_class": "battery", "state_class": "measurement", "api_key": "batteryStateOfCharge", "measurement": "%"},
    Tag.OIL:                    {"icon": "mdi:oil", "api_key": "oilLifeRemaining", "measurement": "%"},
    Tag.TIRE_PRESSURE:          {"icon": "mdi:car-tire-alert", "api_key": "tirePressure"},
    Tag.GPS:                    {"icon": "mdi:radar", "api_key": "position"},
    Tag.ALARM:                  {"icon": "mdi:bell", "api_key": "alarmStatus"},
    Tag.IGNITION_STATUS:        {"icon": "hass:power", "api_key": "ignitionStatus"},
    Tag.DOOR_STATUS:            {"icon": "mdi:car-door", "api_key": "doorStatus"},
    Tag.WINDOW_POSITION:        {"icon": "mdi:car-door", "api_key": "windowStatus"},
    Tag.LAST_REFRESH:           {"icon": "mdi:clock", "device_class": "timestamp", "api_key": "lastRefresh", "sensor_type": "single"},
    Tag.ELVEH:                  {"icon": "mdi:ev-station", "api_key": "xevBatteryRange", "device_class": "distance", "state_class": "measurement", "measurement": "km"},
    Tag.ELVEH_CHARGING:         {"icon": "mdi:ev-station", "api_key": "xevBatteryChargeDisplayStatus"},
    Tag.SPEED:                  {"icon": "mdi:speedometer", "device_class": "speed", "state_class": "measurement", "api_key": "speed", "measurement": "km/h"},
    Tag.INDICATORS:             {"icon": "mdi:engine-outline", "api_key": "indicators"},
    Tag.COOLANT_TEMP:           {"icon": "mdi:coolant-temperature", "api_key": "engineCoolantTemp", "state_class": "measurement", "device_class": "temperature", "measurement": "°C"},
    Tag.OUTSIDE_TEMP:           {"icon": "mdi:thermometer", "state_class": "measurement", "device_class": "temperature", "api_key": "outsideTemperature", "measurement": "°C"},
    Tag.ENGINE_OIL_TEMP:         {"icon": "mdi:oil-temperature", "state_class": "measurement", "device_class": "temperature", "api_key": "engineOilTemp", "measurement": "°C"},
    Tag.DEEPSLEEP:              {"icon": "mdi:power-sleep", "name": "Deep Sleep Mode Active", "api_key": "commandPreclusion", "api_class": "states"},
    # Tag.FIRMWAREUPGINPROGRESS: {"icon": "mdi:one-up", "name": "Firmware Update In Progress"},
    Tag.REMOTE_START_STATUS:    {"icon": "mdi:remote", "api_key": "remoteStartCountdownTimer"},
    # Tag.ZONELIGHTING:     {"icon": "mdi:spotlight-beam"},
    Tag.MESSAGES:               {"icon": "mdi:message-text", "api_key": "messages", "measurement": "messages", "sensor_type": "single"},
    Tag.DIESEL_SYSTEM_STATUS:   {"icon": "mdi:smoking-pipe", "api_key": "dieselExhaustFilterStatus"},
    Tag.EXHAUST_FLUID_LEVEL:    {"icon": "mdi:barrel", "api_key": "dieselExhaustFluidLevel", "measurement": "%"},
    # Debug Sensors (Disabled by default)
    Tag.EVENTS:                 {"icon": "mdi:calendar", "api_key": "events", "sensor_type": "single", "debug": True},
    Tag.METRICS:                {"icon": "mdi:chart-line", "api_key": "metrics", "sensor_type": "single", "debug": True},
    Tag.STATES:                 {"icon": "mdi:car", "api_key": "states", "sensor_type": "single", "debug": True},
    Tag.VEHICLES:               {"icon": "mdi:car-multiple", "api_key": "vehicles", "sensor_type": "single", "debug": True},

    Tag.SOC:                   {"icon": "mdi:battery-high", "api_key": "xevBatteryStateOfCharge", "state_class": "measurement", "measurement": "%"},
    Tag.EVCC_STATUS:           {"icon": "mdi:state-machine", "api_key": "CAN_BE_IGNORED_IF_TYPE_IS_SINGLE", "sensor_type": "single"},
}

SWITCHES = {
    Tag.IGNITION: {"icon": "hass:power"},
    #Tag.GUARDMODE: {"icon": "mdi:shield-key"}
}

BUTTONS = {
    Tag.UPDATE_DATA:        {"icon": "mdi:refresh"},
    Tag.REQUEST_REFRESH:    {"icon": "mdi:car-connected"}
}