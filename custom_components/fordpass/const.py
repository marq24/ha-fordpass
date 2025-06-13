"""Constants for the FordPass integration."""
import logging
from typing import Final

from homeassistant.components.sensor import SensorStateClass, SensorDeviceClass, SensorEntityDescription
from homeassistant.const import UnitOfSpeed, UnitOfLength, UnitOfTemperature, PERCENTAGE, EntityCategory

_LOGGER = logging.getLogger(__name__)

DOMAIN: Final = "fordpass"

MANUFACTURER: Final = "Ford Motor Company"

CONF_VIN: Final = "vin"
CONF_PRESSURE_UNIT: Final = "pressure_unit"
COORDINATOR_KEY: Final = "coordinator"

UPDATE_INTERVAL: Final = "update_interval"
UPDATE_INTERVAL_DEFAULT: Final = 290 # it looks like that the default auto-access_token expires after 5 minutes (300 seconds)

DEFAULT_PRESSURE_UNIT: Final = "kPa"
PRESSURE_UNITS: Final = ["PSI", "kPa", "BAR"]

# https://en.wikipedia.org/wiki/ISO_3166-1_alpha-3
DEFAULT_REGION: Final = "rest_of_world"
REGION_OPTIONS: Final = ["fra", "deu", "ita", "nld", "esp", "gbr", "rest_of_europe", "can", "mex", "usa", "rest_of_world"]
LEGACY_REGION_KEYS: Final = ["USA", "Canada", "Australia", "UK&Europe", "Netherlands"]

REGION_APP_IDS: Final = {
    "africa":           "71AA9ED7-B26B-4C15-835E-9F35CC238561", # South Africa, ...
    # 'asia_pacific' seams to be broken right now - not working with original FordPass App
    "asia_pacific":     "39CD6590-B1B9-42CB-BEF9-0DC1FDB96260", # Australia, Thailand, New Zealand, ...
    "europe":           "667D773E-1BDC-4139-8AD0-2B16474E8DC7", # used for germany, france, italy, netherlands, uk, rest_of_europe
    "north_america":    "BFE8C5ED-D687-4C19-A5DD-F92CDFC4503A", # used for canada, usa, mexico
    "south_america":    "C1DFFEF5-5BA5-486A-9054-8B39A9DF9AFC", # Argentina, Brazil, ...
}

REGIONS: Final = {
    # checked 2025/06/08 - working fine...
    "deu": {
        "app_id": REGION_APP_IDS["europe"],
        "locale": "de-DE",
        "locale_url": "https://login.ford.de",
        "countrycode": "DEU"
    },
    # checked 2025/06/08 - working fine...
    "fra": {
        "app_id": REGION_APP_IDS["europe"],
        "locale": "fr-FR",
        "locale_url": "https://login.ford.com",
        "countrycode": "FRA"
    },
    # checked 2025/06/08 - working fine...
    "ita": {
        "app_id": REGION_APP_IDS["europe"],
        "locale": "it-IT",
        "locale_url": "https://login.ford.com",
        "countrycode": "ITA"
    },
    # checked 2025/06/09 - working fine...
    "esp": {
        "app_id": REGION_APP_IDS["europe"],
        "locale": "es-ES",
        "locale_url": "https://login.ford.com",
        "countrycode": "ESP"
    },
    # checked 2025/06/08 - working fine...
    "nld": {
        "app_id": REGION_APP_IDS["europe"], # 1E8C7794-FF5F-49BC-9596-A1E0C86C5B19
        "locale": "nl-NL",
        "locale_url": "https://login.ford.com",
        "countrycode": "NLD"
    },
    # checked 2025/06/08 - working fine...
    "gbr": {
        "app_id": REGION_APP_IDS["europe"], # 1E8C7794-FF5F-49BC-9596-A1E0C86C5B19",
        "locale": "en-GB",
        "locale_url": "https://login.ford.co.uk",
        "countrycode": "GBR"
    },
    # using GBR as our default for the rest of europe...
    "rest_of_europe": {
        "app_id": REGION_APP_IDS["europe"],
        "locale": "en-GB",
        "locale_url": "https://login.ford.com",
        "countrycode": "GBR"
    },


    # checked 2025/06/08 - working fine...
    "can": {
        "app_id": REGION_APP_IDS["north_america"],
        "locale": "en-CA",
        "locale_url": "https://login.ford.com",
        "countrycode": "CAN"
    },
    # checked 2025/06/08 - working fine...
    "mex": {
        "app_id": REGION_APP_IDS["north_america"],
        "locale": "es-MX",
        "locale_url": "https://login.ford.com",
        "countrycode": "MEX"
    },
    # checked 2025/06/08 - working fine...
    "usa": {
        "app_id": REGION_APP_IDS["north_america"], # 71A3AD0A-CF46-4CCF-B473-FC7FE5BC4592
        "locale": "en-US",
        "locale_url": "https://login.ford.com",
        "countrycode": "USA"
    },

    # DOES NOT WORK... checked 2025/06/09
    "bra": {
        "app_id": REGION_APP_IDS["south_america"],
        "locale": "pt-BR",
        "locale_url": "https://login.ford.com",
        "countrycode": "BRA"
    },
    # DOES NOT WORK... checked 2025/06/09
    "arg": {
        "app_id": REGION_APP_IDS["south_america"],
        "locale": "es-AR",
        "locale_url": "https://login.ford.com",
        "countrycode": "ARG"
    },

    # DOES NOT WORK... checked 2025/06/09
    "aus": {
        "app_id": REGION_APP_IDS["asia_pacific"], # "39CD6590-B1B9-42CB-BEF9-0DC1FDB96260",
        "locale": "en-AU",
        "locale_url": "https://login.ford.com",
        "countrycode": "AUS"
    },
    # DOES NOT WORK... checked 2025/06/09
    "nzl": {
        "app_id": REGION_APP_IDS["asia_pacific"], # "39CD6590-B1B9-42CB-BEF9-0DC1FDB96260",
        "locale": "en-NZ",
        "locale_url": "https://login.ford.com",
        "countrycode": "NZL"
    },

    # we use the 'usa' as the default region...,
    "rest_of_world": {
        "app_id": REGION_APP_IDS["north_america"],
        "locale": "en-US",
        "locale_url": "https://login.ford.com",
        "countrycode": "USA"
    },


    # for compatibility, we MUST KEEP the old region keys with the OLD App-IDs!!! - this really sucks!
    "Netherlands":  {"app_id": "1E8C7794-FF5F-49BC-9596-A1E0C86C5B19", "locale": "nl-NL", "locale_url": "https://login.ford.nl", "countrycode": "NLD"},
    "UK&Europe":    {"app_id": "1E8C7794-FF5F-49BC-9596-A1E0C86C5B19", "locale": "en-GB", "locale_url": "https://login.ford.co.uk", "countrycode": "GBR"},
    "Australia":    {"app_id": "5C80A6BB-CF0D-4A30-BDBF-FC804B5C1A98", "locale": "en-AU", "locale_url": "https://login.ford.com", "countrycode": "AUS"},
    "USA":          {"app_id": "71A3AD0A-CF46-4CCF-B473-FC7FE5BC4592", "locale": "en-US", "locale_url": "https://login.ford.com", "countrycode": "USA"},
    "Canada":       {"app_id": "71A3AD0A-CF46-4CCF-B473-FC7FE5BC4592", "locale": "en-CA", "locale_url": "https://login.ford.com", "countrycode": "USA"}
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

ZONE_LIGHTS_VALUE_ALL_ON = "0"
ZONE_LIGHTS_VALUE_FRONT = "1"
ZONE_LIGHTS_VALUE_REAR = "2"
ZONE_LIGHTS_VALUE_DRIVER = "3"
ZONE_LIGHTS_VALUE_PASSENGER = "4"
ZONE_LIGHTS_VALUE_OFF = "off"
ZONE_LIGHTS_OPTIONS: Final = [ZONE_LIGHTS_VALUE_ALL_ON, ZONE_LIGHTS_VALUE_FRONT, ZONE_LIGHTS_VALUE_REAR,
                              ZONE_LIGHTS_VALUE_DRIVER, ZONE_LIGHTS_VALUE_PASSENGER, ZONE_LIGHTS_VALUE_OFF]