"""Constants for the FordPass integration."""

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
UPDATE_INTERVAL_DEFAULT = 60

COORDINATOR = "coordinator"

REGION = "region"

REGION_OPTIONS = ["USA", "Canada", "Australia", "UK&Europe", "Netherlands"]
DEFAULT_REGION = "USA"

SENSORS = {
    "odometer": {"icon": "mdi:counter", "state_class": "total", "device_class": "distance", "api_key": "odometer", "measurement": "km"},
    "fuel": {"icon": "mdi:gas-station", "api_key": ["fuelLevel", "xevBatteryStateOfCharge"], "measurement": "%"},
    "battery": {"icon": "mdi:car-battery", "device_class": "battery", "state_class": "measurement", "api_key": "batteryStateOfCharge", "measurement": "%"},
    "oil": {"icon": "mdi:oil", "api_key": "oilLifeRemaining", "measurement": "%"},
    "tirePressure": {"icon": "mdi:car-tire-alert", "api_key": "tirePressure"},
    "gps": {"icon": "mdi:radar", "api_key": "position"},
    "alarm": {"icon": "mdi:bell", "api_key": "alarmStatus"},
    "ignitionStatus": {"icon": "hass:power", "api_key": "ignitionStatus"},
    "doorStatus": {"icon": "mdi:car-door", "api_key": "doorStatus"},
    "windowPosition": {"icon": "mdi:car-door", "api_key": "windowStatus"},
    "lastRefresh": {"icon": "mdi:clock", "device_class": "timestamp", "api_key": "lastRefresh", "sensor_type": "single"},
    "elVeh": {"icon": "mdi:ev-station", "api_key": "xevBatteryRange", "device_class": "distance", "state_class": "measurement", "measurement": "km"},
    "elVehCharging": {"icon": "mdi:ev-station", "api_key": "xevBatteryChargeDisplayStatus"},
    "speed": {"icon": "mdi:speedometer", "device_class": "speed", "state_class": "measurement", "api_key": "speed", "measurement": "km/h"},
    "indicators": {"icon": "mdi:engine-outline", "api_key": "indicators"},
    "coolantTemp": {"icon": "mdi:coolant-temperature", "api_key": "engineCoolantTemp", "state_class": "measurement", "device_class": "temperature", "measurement": "°C"},
    "outsideTemp": {"icon": "mdi:thermometer", "state_class": "measurement", "device_class": "temperature", "api_key": "outsideTemperature", "measurement": "°C"},
    "engineOilTemp": {"icon": "mdi:oil-temperature", "state_class": "measurement", "device_class": "temperature", "api_key": "engineOilTemp", "measurement": "°C"},
    "deepSleep": {"icon": "mdi:power-sleep", "name": "Deep Sleep Mode Active", "api_key": "commandPreclusion", "api_class": "states"},
    # "firmwareUpgInProgress": {
    #    "icon": "mdi:one-up",
    #   "name": "Firmware Update In Progress",
    # },
    "remoteStartStatus": {"icon": "mdi:remote", "api_key": "remoteStartCountdownTimer"},
    # "zoneLighting": {"icon": "mdi:spotlight-beam"},
    "messages": {"icon": "mdi:message-text", "api_key": "messages", "measurement": "messages", "sensor_type": "single"},
    "dieselSystemStatus": {"icon": "mdi:smoking-pipe", "api_key": "dieselExhaustFilterStatus"},
    "exhaustFluidLevel": {"icon": "mdi:barrel", "api_key": "dieselExhaustFluidLevel", "measurement": "%"},
    # Debug Sensors (Disabled by default)
    "events": {"icon": "mdi:calendar", "api_key": "events", "sensor_type": "single", "debug": True},
    "metrics": {"icon": "mdi:chart-line", "api_key": "metrics", "sensor_type": "single", "debug": True},
    "states": {"icon": "mdi:car", "api_key": "states", "sensor_type": "single", "debug": True},
    "vehicles": {"icon": "mdi:car-multiple", "api_key": "vehicles", "sensor_type": "single", "debug": True}
}

SWITCHES = {
    "ignition": {"icon": "hass:power"},
    # "guardmode": {"icon": "mdi:shield-key"}
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
