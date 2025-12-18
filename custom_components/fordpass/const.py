"""Constants for the FordPass integration."""
import logging
from enum import Enum
from typing import Final

_LOGGER = logging.getLogger(__name__)

DOMAIN: Final = "fordpass"
NAME: Final = "Fordpass integration for Home Assistant [optimized for EV's & EVCC]"
ISSUE_URL: Final = "https://github.com/marq24/ha-fordpass/issues"
MANUFACTURER_FORD: Final = "Ford Motor Company"
MANUFACTURER_LINCOLN: Final = "Lincoln Motor Company"

STARTUP_MESSAGE: Final = f"""
-------------------------------------------------------------------
{NAME} - v%s
This is a custom integration!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""

CONFIG_VERSION: Final = 2
CONFIG_MINOR_VERSION: Final = 0

CONF_IS_SUPPORTED: Final = "is_supported"
CONF_BRAND: Final = "brand"
CONF_VIN: Final = "vin"

CONF_PRESSURE_UNIT: Final = "pressure_unit"
CONF_LOG_TO_FILESYSTEM: Final = "log_to_filesystem"
CONF_FORCE_REMOTE_CLIMATE_CONTROL: Final = "force_remote_climate_control"
COORDINATOR_KEY: Final = "coordinator"

UPDATE_INTERVAL: Final = "update_interval"
UPDATE_INTERVAL_DEFAULT: Final = 290 # it looks like that the default auto-access_token expires after 5 minutes (300 seconds)

DEFAULT_PRESSURE_UNIT: Final = "kPa"
PRESSURE_UNITS: Final = ["PSI", "kPa", "BAR"]

# https://en.wikipedia.org/wiki/ISO_3166-1_alpha-3
BRAND_OPTIONS = ["ford", "lincoln"]

DEFAULT_REGION_FORD: Final = "rest_of_world"
REGION_OPTIONS_FORD: Final = ["fra", "deu", "ita", "nld", "esp", "gbr", "rest_of_europe", "aus", "nzl", "zaf", "bra", "arg", "can", "mex", "usa", "rest_of_world"]

REGION_OPTIONS_LINCOLN: Final = ["lincoln_usa"]
DEFAULT_REGION_LINCOLN: Final = "lincoln_usa"

LEGACY_REGION_KEYS: Final = ["USA", "Canada", "Australia", "UK&Europe", "Netherlands"]

REGION_APP_IDS: Final = {
    "africa":           "71AA9ED7-B26B-4C15-835E-9F35CC238561", # South Africa, ...
    "asia_pacific":     "39CD6590-B1B9-42CB-BEF9-0DC1FDB96260", # Australia, Thailand, New Zealand, ...
    "europe":           "667D773E-1BDC-4139-8AD0-2B16474E8DC7", # used for germany, france, italy, netherlands, uk, rest_of_europe
    "north_america":    "BFE8C5ED-D687-4C19-A5DD-F92CDFC4503A", # used for canada, usa, mexico
    "south_america":    "C1DFFEF5-5BA5-486A-9054-8B39A9DF9AFC", # Argentina, Brazil, ...
}

OAUTH_ID: Final = "4566605f-43a7-400a-946e-89cc9fdb0bd7"
CLIENT_ID: Final = "09852200-05fd-41f6-8c21-d36d3497dc64"

LINCOLN_REGION_APP_IDS: Final = {
    "north_america":    "45133B88-0671-4AAF-B8D1-99E684ED4E45"
}

REGIONS: Final = {
    "lincoln_usa": {
        "app_id": LINCOLN_REGION_APP_IDS["north_america"],
        "locale": "en-US",
        "login_url": "https://login.lincoln.com",
        "sign_up_addon": "Lincoln_",
        "redirect_schema": "lincolnapp",
        "countrycode": "USA"
    },

    # checked 2025/06/08 - working fine...
    "deu": {
        "app_id": REGION_APP_IDS["europe"],
        "locale": "de-DE",
        "login_url": "https://login.ford.de",
        "countrycode": "DEU"
    },
    # checked 2025/06/08 - working fine...
    "fra": {
        "app_id": REGION_APP_IDS["europe"],
        "locale": "fr-FR",
        "login_url": "https://login.ford.com",
        "countrycode": "FRA"
    },
    # checked 2025/06/08 - working fine...
    "ita": {
        "app_id": REGION_APP_IDS["europe"],
        "locale": "it-IT",
        "login_url": "https://login.ford.com",
        "countrycode": "ITA"
    },
    # checked 2025/06/09 - working fine...
    "esp": {
        "app_id": REGION_APP_IDS["europe"],
        "locale": "es-ES",
        "login_url": "https://login.ford.com",
        "countrycode": "ESP"
    },
    # checked 2025/06/08 - working fine...
    "nld": {
        "app_id": REGION_APP_IDS["europe"], # 1E8C7794-FF5F-49BC-9596-A1E0C86C5B19
        "locale": "nl-NL",
        "login_url": "https://login.ford.com",
        "countrycode": "NLD"
    },
    # checked 2025/06/08 - working fine...
    "gbr": {
        "app_id": REGION_APP_IDS["europe"], # 1E8C7794-FF5F-49BC-9596-A1E0C86C5B19",
        "locale": "en-GB",
        "login_url": "https://login.ford.co.uk",
        "countrycode": "GBR"
    },
    # using GBR as our default for the rest of europe...
    "rest_of_europe": {
        "app_id": REGION_APP_IDS["europe"],
        "locale": "en-GB",
        "login_url": "https://login.ford.com",
        "countrycode": "GBR"
    },
    # checked 2025/06/08 - working fine...
    "can": {
        "app_id": REGION_APP_IDS["north_america"],
        "locale": "en-CA",
        "login_url": "https://login.ford.com",
        "countrycode": "CAN"
    },
    # checked 2025/06/08 - working fine...
    "mex": {
        "app_id": REGION_APP_IDS["north_america"],
        "locale": "es-MX",
        "login_url": "https://login.ford.com",
        "countrycode": "MEX"
    },
    # checked 2025/06/08 - working fine...
    "usa": {
        "app_id": REGION_APP_IDS["north_america"],
        "locale": "en-US",
        "login_url": "https://login.ford.com",
        "countrycode": "USA"
    },

    # DOES NOT WORK... checked 2025/06/09
    "bra": {
        "app_id": REGION_APP_IDS["south_america"],
        "locale": "pt-BR",
        "login_url": "https://login.ford.com",
        "countrycode": "BRA"
    },
    # DOES NOT WORK... checked 2025/06/09
    "arg": {
        "app_id": REGION_APP_IDS["south_america"],
        "locale": "es-AR",
        "login_url": "https://login.ford.com",
        "countrycode": "ARG"
    },

    # NEED AN www.ford.com.au registered account!!!
    "aus": {
        "app_id": REGION_APP_IDS["asia_pacific"],
        "locale": "en-AU",
        "login_url": "https://login.ford.com",
        "countrycode": "AUS"
    },
    # NEED AN www.ford.com.au registered account!!!
    "nzl": {
        "app_id": REGION_APP_IDS["asia_pacific"],
        "locale": "en-NZ",
        "login_url": "https://login.ford.com",
        "countrycode": "NZL"
    },

    # NEED AN www.ford.co.za registered account!!!
    "zaf": {
        "app_id": REGION_APP_IDS["africa"],
        "locale": "en-ZA",
        "login_url": "https://login.ford.com",
        "countrycode": "ZAF"
    },

    # we use the 'usa' as the default region...,
    "rest_of_world": {
        "app_id": REGION_APP_IDS["north_america"],
        "locale": "en-US",
        "login_url": "https://login.ford.com",
        "countrycode": "USA"
    },

    # for compatibility, we MUST KEEP the old region keys with the OLD App-IDs!!! - this really sucks!
    "Netherlands":  {"app_id": "1E8C7794-FF5F-49BC-9596-A1E0C86C5B19", "locale": "nl-NL", "login_url": "https://login.ford.nl", "countrycode": "NLD"},
    "UK&Europe":    {"app_id": "1E8C7794-FF5F-49BC-9596-A1E0C86C5B19", "locale": "en-GB", "login_url": "https://login.ford.co.uk", "countrycode": "GBR"},
    "Australia":    {"app_id": "5C80A6BB-CF0D-4A30-BDBF-FC804B5C1A98", "locale": "en-AU", "login_url": "https://login.ford.com", "countrycode": "AUS"},
    "USA":          {"app_id": "71A3AD0A-CF46-4CCF-B473-FC7FE5BC4592", "locale": "en-US", "login_url": "https://login.ford.com", "countrycode": "USA"},
    "Canada":       {"app_id": "71A3AD0A-CF46-4CCF-B473-FC7FE5BC4592", "locale": "en-CA", "login_url": "https://login.ford.com", "countrycode": "USA"}
}

REGIONS_STRICT = REGIONS.copy()
for a_key in LEGACY_REGION_KEYS:
    REGIONS_STRICT.pop(a_key)

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

REMOTE_START_STATE_ACTIVE: Final      = "Active"
REMOTE_START_STATE_INACTIVE: Final    = "Inactive"

RCC_SEAT_MODE_HEAT_AND_COOL: Final = "HEAT_AND_COOL"
RCC_SEAT_MODE_HEAT_ONLY: Final = "HEAT_ONLY"
RCC_SEAT_MODE_NONE: Final = "NONE"
RCC_SEAT_OPTIONS_FULL: Final = ["off", "heated1", "heated2", "heated3", "cooled1", "cooled2", "cooled3"]
RCC_SEAT_OPTIONS_HEAT_ONLY: Final = ["off", "heated1", "heated2", "heated3"]

RCC_TEMPERATURES_CELSIUS:    Final = ["lo",
                                      "16", "16_5", "17", "17_5", "18", "18_5", "19", "19_5", "20", "20_5",
                                      "21", "21_5", "22", "22_5", "23", "23_5", "24", "24_5", "25", "25_5",
                                      "26", "26_5", "27", "27_5", "28", "28_5", "29", "30",
                                      "hi"]

ELVEH_TARGET_CHARGE_OPTIONS: Final = ["50", "60", "70", "80", "85", "90", "95", "100"]

VEHICLE_LOCK_STATE_LOCKED:      Final = "LOCKED"
VEHICLE_LOCK_STATE_PARTLY:      Final = "PARTLY_LOCKED"
VEHICLE_LOCK_STATE_UNLOCKED:    Final = "UNLOCKED"

ZONE_LIGHTS_VALUE_ALL_ON:       Final = "0"
ZONE_LIGHTS_VALUE_FRONT:        Final = "1"
ZONE_LIGHTS_VALUE_REAR:         Final = "2"
ZONE_LIGHTS_VALUE_DRIVER:       Final = "3"
ZONE_LIGHTS_VALUE_PASSENGER:    Final = "4"
ZONE_LIGHTS_VALUE_OFF:          Final = "off"
ZONE_LIGHTS_OPTIONS: Final = [ZONE_LIGHTS_VALUE_ALL_ON, ZONE_LIGHTS_VALUE_FRONT, ZONE_LIGHTS_VALUE_REAR,
                              ZONE_LIGHTS_VALUE_DRIVER, ZONE_LIGHTS_VALUE_PASSENGER, ZONE_LIGHTS_VALUE_OFF]

class HONK_AND_FLASH(Enum):
    SHORT = 1
    DEFAULT = 3
    LONG = 5

XEVPLUGCHARGER_STATE_CONNECTED:     Final = "CONNECTED"
XEVPLUGCHARGER_STATE_DISCONNECTED:  Final = "DISCONNECTED"
XEVPLUGCHARGER_STATE_CHARGING:      Final = "CHARGING"      # this is from evcc code - I have not seen this in my data yet
XEVPLUGCHARGER_STATE_CHARGINGAC:    Final = "CHARGINGAC"    # this is from evcc code - I have not seen this in my data yet
XEVPLUGCHARGER_STATES:              Final = [XEVPLUGCHARGER_STATE_CONNECTED, XEVPLUGCHARGER_STATE_DISCONNECTED,
                                             XEVPLUGCHARGER_STATE_CHARGING, XEVPLUGCHARGER_STATE_CHARGINGAC]

XEVBATTERYCHARGEDISPLAY_STATE_NOT_READY:    Final = "NOT_READY"
XEVBATTERYCHARGEDISPLAY_STATE_SCHEDULED:    Final = "SCHEDULED"
XEVBATTERYCHARGEDISPLAY_STATE_PAUSED:       Final = "PAUSED"
XEVBATTERYCHARGEDISPLAY_STATE_IN_PROGRESS:  Final = "IN_PROGRESS"
XEVBATTERYCHARGEDISPLAY_STATE_STOPPED:      Final = "STOPPED"
XEVBATTERYCHARGEDISPLAY_STATE_FAULT:        Final = "FAULT"
XEVBATTERYCHARGEDISPLAY_STATION_NOT_DETECTED: Final = "STATION_NOT_DETECTED"

XEVBATTERYCHARGEDISPLAY_STATES:             Final = [XEVBATTERYCHARGEDISPLAY_STATE_NOT_READY, XEVBATTERYCHARGEDISPLAY_STATE_SCHEDULED,
                                                     XEVBATTERYCHARGEDISPLAY_STATE_PAUSED, XEVBATTERYCHARGEDISPLAY_STATE_IN_PROGRESS,
                                                     XEVBATTERYCHARGEDISPLAY_STATE_STOPPED, XEVBATTERYCHARGEDISPLAY_STATE_FAULT,
                                                     XEVBATTERYCHARGEDISPLAY_STATION_NOT_DETECTED]

DAYS_MAP = {
    "MONDAY":   0,
    "TUESDAY":  1,
    "WEDNESDAY":2,
    "THURSDAY": 3,
    "FRIDAY":   4,
    "SATURDAY": 5,
    "SUNDAY":   6,
}

TRANSLATIONS: Final = {
    "de":{
        "account": "Konto",
        "deu": "Deutschland",
        "fra": "Frankreich",
        "nld": "Niederlande",
        "ita": "Italien",
        "esp": "Spanien",
        "gbr": "Vereinigtes Königreich Großbritannien und Irland",
        "aus": "Australien",
        "nzl": "Neuseeland",
        "zaf": "Südafrika",
        "can": "Kanada",
        "mex": "Mexiko",
        "usa": "Die Vereinigten Staaten von Amerika",
        "bra": "Brasilien",
        "arg": "Argentinien",
        "rest_of_europe": "Andere europäische Länder",
        "rest_of_world": "Rest der Welt",
        "lincoln_usa": "Vereinigten Staaten von Amerika",
        "USA": "USA (LEGACY)", "Canada":"Kanada (LEGACY)", "Australia":"Australien (LEGACY)", "UK&Europe":"UK&Europa (LEGACY)", "Netherlands":"Niederlande (LEGACY)"
    },
    "en": {
        "account": "Account",
        "deu": "Germany",
        "fra": "France",
        "nld": "Netherlands",
        "ita": "Italy",
        "esp": "Spain",
        "gbr": "United Kingdom of Great Britain and Northern Ireland",
        "aus": "Australia",
        "nzl": "New Zealand",
        "zaf": "South Africa",
        "can": "Canada",
        "mex": "Mexico",
        "usa": "The United States of America",
        "bra": "Brazil",
        "arg": "Argentina",
        "rest_of_europe": "Other European Countries",
        "rest_of_world": "Rest of the World",
        "lincoln_usa": "United States of America",
        "USA": "USA (LEGACY)", "Canada":"Canada (LEGACY)", "Australia":"Australia (LEGACY)", "UK&Europe":"UK&Europe (LEGACY)", "Netherlands":"Netherlands (LEGACY)"
    }
}
