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

    IGNITION = ApiKey(key="ignition")
    GUARDMODE = ApiKey(key="guardmode")

    UPDATE_DATA = ApiKey(key="update_data")
    REQUEST_REFRESH = ApiKey(key="request_refresh")

    ODOMETER = ApiKey(key="odometer")
    FUEL = ApiKey(key="fuel")
    BATTERY = ApiKey(key="battery")
    OIL = ApiKey(key="oil")
    TIREPRESSURE = ApiKey(key="tirePressure")
    GPS = ApiKey(key="gps")
    ALARM = ApiKey(key="alarm")
    IGNITIONSTATUS = ApiKey(key="ignitionStatus")
    DOORSTATUS = ApiKey(key="doorStatus")
    WINDOWPOSITION = ApiKey(key="windowPosition")
    LASTREFRESH = ApiKey(key="lastRefresh")
    ELVEH = ApiKey(key="elVeh")
    ELVEHCHARGING = ApiKey(key="elVehCharging")
    SPEED = ApiKey(key="speed")
    INDICATORS = ApiKey(key="indicators")
    COOLANTTEMP = ApiKey(key="coolantTemp")
    OUTSIDETEMP = ApiKey(key="outsideTemp")
    ENGINEOILTEMP = ApiKey(key="engineOilTemp")
    DEEPSLEEP = ApiKey(key="deepSleep")
    FIRMWAREUPGINPROGRESS = ApiKey(key="firmwareUpgInProgress")
    REMOTESTARTSTATUS = ApiKey(key="remoteStartStatus")
    ZONELIGHTING = ApiKey(key="zoneLighting")
    MESSAGES = ApiKey(key="messages")
    DIESELSYSTEMSTATUS = ApiKey(key="dieselSystemStatus")
    EXHAUSTFLUIDLEVEL = ApiKey(key="exhaustFluidLevel")
    # Debug Sensors (Disabled by default)
    EVENTS = ApiKey(key="events")
    METRICS = ApiKey(key="metrics")
    STATES = ApiKey(key="states")
    VEHICLES = ApiKey(key="vehicles")

SENSORS = {
    Tag.ODOMETER.key:           {"icon": "mdi:counter", "state_class": "total", "device_class": "distance", "api_key": "odometer", "measurement": "km"},
    Tag.FUEL.key:               {"icon": "mdi:gas-station", "api_key": ["fuelLevel", "xevBatteryStateOfCharge"], "measurement": "%"},
    Tag.BATTERY.key:            {"icon": "mdi:car-battery", "device_class": "battery", "state_class": "measurement", "api_key": "batteryStateOfCharge", "measurement": "%"},
    Tag.OIL.key:                {"icon": "mdi:oil", "api_key": "oilLifeRemaining", "measurement": "%"},
    Tag.TIREPRESSURE.key:       {"icon": "mdi:car-tire-alert", "api_key": "tirePressure"},
    Tag.GPS.key:                {"icon": "mdi:radar", "api_key": "position"},
    Tag.ALARM.key:              {"icon": "mdi:bell", "api_key": "alarmStatus"},
    Tag.IGNITIONSTATUS.key:     {"icon": "hass:power", "api_key": "ignitionStatus"},
    Tag.DOORSTATUS.key:         {"icon": "mdi:car-door", "api_key": "doorStatus"},
    Tag.WINDOWPOSITION.key:     {"icon": "mdi:car-door", "api_key": "windowStatus"},
    Tag.LASTREFRESH.key:        {"icon": "mdi:clock", "device_class": "timestamp", "api_key": "lastRefresh", "sensor_type": "single"},
    Tag.ELVEH.key:              {"icon": "mdi:ev-station", "api_key": "xevBatteryRange", "device_class": "distance", "state_class": "measurement", "measurement": "km"},
    Tag.ELVEHCHARGING.key:      {"icon": "mdi:ev-station", "api_key": "xevBatteryChargeDisplayStatus"},
    Tag.SPEED.key:              {"icon": "mdi:speedometer", "device_class": "speed", "state_class": "measurement", "api_key": "speed", "measurement": "km/h"},
    Tag.INDICATORS.key:         {"icon": "mdi:engine-outline", "api_key": "indicators"},
    Tag.COOLANTTEMP.key:        {"icon": "mdi:coolant-temperature", "api_key": "engineCoolantTemp", "state_class": "measurement", "device_class": "temperature", "measurement": "°C"},
    Tag.OUTSIDETEMP.key:        {"icon": "mdi:thermometer", "state_class": "measurement", "device_class": "temperature", "api_key": "outsideTemperature", "measurement": "°C"},
    Tag.ENGINEOILTEMP.key:      {"icon": "mdi:oil-temperature", "state_class": "measurement", "device_class": "temperature", "api_key": "engineOilTemp", "measurement": "°C"},
    Tag.DEEPSLEEP.key:          {"icon": "mdi:power-sleep", "name": "Deep Sleep Mode Active", "api_key": "commandPreclusion", "api_class": "states"},
    # Tag.FIRMWAREUPGINPROGRESS.key: {"icon": "mdi:one-up", "name": "Firmware Update In Progress"},
    Tag.REMOTESTARTSTATUS.key:  {"icon": "mdi:remote", "api_key": "remoteStartCountdownTimer"},
    # Tag.ZONELIGHTING.key:     {"icon": "mdi:spotlight-beam"},
    Tag.MESSAGES.key:           {"icon": "mdi:message-text", "api_key": "messages", "measurement": "messages", "sensor_type": "single"},
    Tag.DIESELSYSTEMSTATUS.key: {"icon": "mdi:smoking-pipe", "api_key": "dieselExhaustFilterStatus"},
    Tag.EXHAUSTFLUIDLEVEL.key:  {"icon": "mdi:barrel", "api_key": "dieselExhaustFluidLevel", "measurement": "%"},
    # Debug Sensors (Disabled by default)
    Tag.EVENTS.key:     {"icon": "mdi:calendar", "api_key": "events", "sensor_type": "single", "debug": True},
    Tag.METRICS.key:    {"icon": "mdi:chart-line", "api_key": "metrics", "sensor_type": "single", "debug": True},
    Tag.STATES.key:     {"icon": "mdi:car", "api_key": "states", "sensor_type": "single", "debug": True},
    Tag.VEHICLES.key:   {"icon": "mdi:car-multiple", "api_key": "vehicles", "sensor_type": "single", "debug": True}
}

SWITCHES = {
    Tag.IGNITION.key: {"icon": "hass:power"},
    #Tag.GUARDMODE.key: {"icon": "mdi:shield-key"}
}

BUTTONS = {
    Tag.UPDATE_DATA.key:        {"icon": "mdi:refresh"},
    Tag.REQUEST_REFRESH.key:    {"icon": "mdi:car-connected"}
}