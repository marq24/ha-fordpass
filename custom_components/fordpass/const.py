"""Constants for the FordPass integration."""
from typing import Final

DOMAIN: Final = "fordpass"
NAME: Final = "Fordpass integration for Home Assistant [optimized for EV's & EVCC]"
ISSUE_URL: Final = "https://github.com/marq24/ha-fordpass/issues"

CONFIG_VERSION: Final = 2
CONFIG_MINOR_VERSION: Final = 0

CONF_IS_SUPPORTED: Final = "is_supported"
CONF_BRAND: Final = "brand"
CONF_VIN: Final = "vin"

CONF_FORCE_REMOTE_CLIMATE_CONTROL: Final = "force_remote_climate_control"

UPDATE_INTERVAL: Final = "update_interval"
UPDATE_INTERVAL_DEFAULT: Final = 290 # it looks like that the default auto-access_token expires after 5 minutes (300 seconds)

# https://en.wikipedia.org/wiki/ISO_3166-1_alpha-3
BRAND_OPTIONS = ["ford", "lincoln"]

DEFAULT_REGION_FORD: Final = "rest_of_world"
REGION_OPTIONS_FORD: Final = ["fra", "deu", "ita", "nld", "esp", "nor", "gbr", "rest_of_europe", "aus", "nzl", "zaf", "bra", "arg", "can", "mex", "usa", "rest_of_world"]

REGION_OPTIONS_LINCOLN: Final = ["lincoln_usa"]
DEFAULT_REGION_LINCOLN: Final = "lincoln_usa"

LEGACY_REGION_KEYS: Final = ["USA", "Canada", "Australia", "UK&Europe", "Netherlands"]
LEGACY_TO_ACTIVE_REGION_MAP: Final = {
    "USA":          "usa",
    "Canada":       "can",
    "Australia":    "aus",
    "UK&Europe":    "rest_of_europe",
    "Netherlands":  "nld"
}

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
    "nor": {
        "app_id": REGION_APP_IDS["europe"],
        "locale": "no-NB",
        "login_url": "https://login.ford.no",
        "countrycode": "NOR"
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

TRANSLATIONS: Final = {
    "de":{
        "account": "Konto",
        "deu": "Deutschland",
        "fra": "Frankreich",
        "nld": "Niederlande",
        "ita": "Italien",
        "esp": "Spanien",
        "nor": "Norwegen",
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
        "USA": "USA (LEGACY)", "Canada":"Kanada (LEGACY)", "Australia":"Australien (LEGACY)", "UK&Europe":"UK&Europa (LEGACY)", "Netherlands":"Niederlande (LEGACY)",
        "coord_null_data": "Es konnten keine Daten abgerufen werden. Bitte prüfe Dein Home Assistant System Protokoll auf mögliche Fehlermeldungen der Integration.",
        "coord_no_vehicle_data": "Es konnten keine Daten zu Deinem konfigurierten Fahrzeug abgerufen werden. Bitte prüfe Dein Home Assistant System Protokoll auf mögliche Fehlermeldungen der Integration."
    },
    "en": {
        "account": "Account",
        "deu": "Germany",
        "fra": "France",
        "nld": "Netherlands",
        "ita": "Italy",
        "esp": "Spain",
        "nor": "Norway",
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
        "USA": "USA (LEGACY)", "Canada":"Canada (LEGACY)", "Australia":"Australia (LEGACY)", "UK&Europe":"UK&Europe (LEGACY)", "Netherlands":"Netherlands (LEGACY)",
        "coord_null_data": "Coordinator could not provided any data. Please check your Home Assistant system log for possible error messages.",
        "coord_no_vehicle_data": "Coordinator could not fetch essential information from your configured vehicle. Please check your Home Assistant system log for possible error messages."
    },
    "nl": {
        "account": "Account",
        "deu": "Duitsland",
        "fra": "Frankrijk",
        "nld": "Nederland",
        "ita": "Italië",
        "esp": "Spanje",
        "nor": "Noorwegen",
        "gbr": "Verenigd Koninkrijk Groot-Brittannië en Noord-Ierland",
        "aus": "Australië",
        "nzl": "Nieuw-Zeeland",
        "zaf": "Zuid-Afrika",
        "can": "Canada",
        "mex": "Mexico",
        "usa": "Verenigde Staten van Amerika",
        "bra": "Brazilië",
        "arg": "Argentinië",
        "rest_of_europe": "Overige Europese landen",
        "rest_of_world": "Rest van de wereld",
        "lincoln_usa": "Verenigde Staten van Amerika",
        "USA": "USA (LEGACY)", "Canada":"Canada (LEGACY)", "Australia":"Australië (LEGACY)", "UK&Europe":"UK&Europa (LEGACY)", "Netherlands":"Nederland (LEGACY)",
        "coord_null_data": "Coördinator kon geen gegevens leveren. Controleer uw Home Assistant-systeemlogboek op mogelijke foutmeldingen.",
        "coord_no_vehicle_data": "Coördinator kon essentiële informatie van uw geconfigureerde voertuig niet ophalen. Controleer uw Home Assistant-systeemlogboek op mogelijke foutmeldingen."
    }
}