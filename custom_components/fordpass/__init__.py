import asyncio
import logging
import time
from datetime import timedelta
from pathlib import Path
from typing import Final, Any

import aiohttp
import voluptuous as vol
from asyncio import timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_REGION, CONF_USERNAME, UnitOfPressure, EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import HomeAssistant, ServiceCall, CoreState
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as the_entity_registry
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.icon import icon_for_battery_level
from homeassistant.helpers.storage import STORAGE_DIR
from homeassistant.helpers.typing import UNDEFINED, UndefinedType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.loader import async_get_integration
from homeassistant.util.unit_system import UnitSystem

from .const import (
    DOMAIN,
    CONFIG_VERSION,
    CONFIG_MINOR_VERSION,
    CONF_IS_SUPPORTED,
    CONF_VIN,
    CONF_FORCE_REMOTE_CLIMATE_CONTROL,
    DEFAULT_REGION_FORD,
    REGION_OPTIONS_LINCOLN,
    UPDATE_INTERVAL,
    UPDATE_INTERVAL_DEFAULT,
    REGIONS,
    REGIONS_STRICT,
    LEGACY_REGION_KEYS,
    TRANSLATIONS
)
from .const_shared import (
    STARTUP_MESSAGE,
    CONF_PRESSURE_UNIT,
    CONF_LOG_TO_FILESYSTEM,
    DEFAULT_PRESSURE_UNIT,
    MANUFACTURER_FORD,
    MANUFACTURER_LINCOLN,
    COORDINATOR_KEY,
    PRESSURE_UNITS,
    RCC_SEAT_MODE_NONE,
    RCC_SEAT_MODE_HEAT_ONLY,
    RCC_SEAT_MODE_HEAT_AND_COOL,
    DAYS_MAP,
)
from .const_tags import Tag, EV_ONLY_TAGS, FUEL_OR_PEV_ONLY_TAGS, RCC_TAGS
from .entity import CustomFriendlyNameEntity
from .fordpass_bridge import ConnectedFordPassVehicle
from .fordpass_handler import (
    UNSUPPORTED,
    ROOT_METRICS,
    ROOT_MESSAGES,
    ROOT_VEHICLES,
    FordpassDataHandler
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)
PLATFORMS:Final = [Platform.BUTTON, Platform.LOCK, Platform.NUMBER, Platform.SENSOR, Platform.SWITCH, Platform.SELECT, Platform.DEVICE_TRACKER]
WEBSOCKET_WATCHDOG_INTERVAL: Final = timedelta(seconds=64)

class NonNullDict(dict):
    def none_null_get(self, key, default=None):
        val = super().get(key, default)
        return default if val is None else val

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the FordPass component."""
    # hass.data.setdefault(DOMAIN, {})
    return True

async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    if config_entry.version == 1:
        if config_entry.data is not None and len(config_entry.data) > 0:
            a_config_region = config_entry.data.get(CONF_REGION, UNDEFINED)
            if a_config_region in REGIONS_STRICT:
                _LOGGER.debug(f"async_migrate_entry(): Migrating configuration from version {config_entry.version}.{config_entry.minor_version}")
                # we mark the configuration entry as 'marq24' version
                # so the config_flow can check for 'our' config entries only
                new_config_entry_data = {**config_entry.data, **{CONF_IS_SUPPORTED: True}}
                hass.config_entries.async_update_entry(config_entry, data=new_config_entry_data, options=config_entry.options, version=CONFIG_VERSION, minor_version=CONFIG_MINOR_VERSION)
                _LOGGER.debug(f"async_migrate_entry(): Migration to configuration version {config_entry.version}.{config_entry.minor_version} successful")
            elif a_config_region in LEGACY_REGION_KEYS:
                # _LOGGER.info(f"async_migrate_entry(): LEGACY_REGION entry found '{a_config_region}' will not migrate config entry")
                # we will ignore 'legacy' region keys during migration [and keep them as they are]
                pass
            else:
                _LOGGER.warning(f"async_migrate_entry(): Incompatible config_entry found - this configuration should be removed from your HA - will not migrate {config_entry}")

    # ensure that all our 'unique_id's are lower-case!
    save_config_entry = config_entry.version == 2 and config_entry.minor_version == 0
    if save_config_entry or config_entry.version == 1:
        if save_config_entry:
            _LOGGER.info(f"async_migrate_entry(): Migrating configuration from version {config_entry.version}.{config_entry.minor_version}")

        registry = the_entity_registry.async_get(hass)
        entities = the_entity_registry.async_entries_for_config_entry(registry, config_entry.entry_id)

        for entity in entities:
            # 'entity' is an instance of RegistryEntry
            if entity.unique_id != entity.unique_id.lower():
                new_unique_id = entity.unique_id.lower()
                _LOGGER.info(f"Entity ID: {entity.entity_id}, Unique ID: {entity.unique_id} updated!")
                for already_existing_entity in entities:
                    if already_existing_entity.unique_id == new_unique_id:
                        _LOGGER.info(f"Entity ID: {entity.entity_id}, Unique ID: {new_unique_id} already exists! - Will PURGE previous {already_existing_entity.entity_id}")
                        registry.async_remove(already_existing_entity.entity_id)

                registry.async_update_entity(entity.entity_id, new_unique_id=new_unique_id)

        if save_config_entry:
            hass.config_entries.async_update_entry(config_entry, version=CONFIG_VERSION, minor_version=CONFIG_MINOR_VERSION)
            _LOGGER.info(f"async_migrate_entry(): Migration to configuration version {config_entry.version}.{config_entry.minor_version} successful")

    return True

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Set up FordPass from a config entry."""
    if CONF_IS_SUPPORTED not in config_entry.data:
        a_config_region = config_entry.data.get(CONF_REGION, UNDEFINED)
        if a_config_region in REGIONS_STRICT:
            _LOGGER.warning(f"async_setup_entry(): config_entry.data '{CONF_IS_SUPPORTED}' not specified in configuration entry {config_entry} - but {a_config_region} is a supported region?!")

        elif a_config_region in LEGACY_REGION_KEYS:
            # we must/want check, if there are other config_entries with the same VIN but with a NONE LEGACY region-key
            # if this is the case, we are going to ignore this LEGACY_REGION key
            this_config_entry_vin = config_entry.data.get(CONF_VIN, None)
            if this_config_entry_vin is not None:
                for entry in hass.config_entries.async_entries(DOMAIN):
                    if entry.entry_id != config_entry.entry_id:
                        if CONF_IS_SUPPORTED in entry.data:
                            other_config_entry_vin = entry.data[CONF_VIN]
                            if other_config_entry_vin.lower() == this_config_entry_vin.lower():
                                _LOGGER.warning(f"async_setup_entry(): current configuration contains a LEGACY region-key: {a_config_region} -> Remove this configuration entry {config_entry} since there is another valid config-entry with the same VIN.")
                                raise ConfigEntryNotReady(f"The configuration entry contains a LEGACY region-key: {a_config_region} and another entry exist for this VIN {this_config_entry_vin}. -> Remove this configuration entry, since it is obsolete.")

            # if we reach this point in the code, then this is a LEGACY region-key, but we don't find any other
            # config entry that have this vin too - so we can/should use this configuration entry
            _LOGGER.info(f"async_setup_entry(): current configuration contains LEGACY region-key: {a_config_region} -> please create a new ha-config entry to avoid this message in the future! See https://github.com/marq24/ha-fordpass/discussions/144 for further details.")

        else:
            _LOGGER.warning(f"async_setup_entry(): current configuration contains UNKNOWN region-key: {a_config_region} -> Remove this configuration entry {config_entry} and setup this integration again for your vehicle.")
            raise ConfigEntryNotReady(f"The configuration entry is NOT SUPPORTED by this Integration. -> Remove this configuration entry and setup this integration again for your vehicle.")

    if DOMAIN not in hass.data:
        the_integration = await async_get_integration(hass, DOMAIN)
        intg_version = the_integration.version if the_integration is not None else "UNKNOWN"
        _LOGGER.info(STARTUP_MESSAGE % intg_version)
        hass.data.setdefault(DOMAIN, {"manifest_version": intg_version})

    user = config_entry.data[CONF_USERNAME]
    vin = config_entry.data[CONF_VIN]
    if UPDATE_INTERVAL in config_entry.options:
        update_interval_as_int = config_entry.options[UPDATE_INTERVAL]
    else:
        update_interval_as_int = UPDATE_INTERVAL_DEFAULT
    _LOGGER.debug(f"[@{vin}] Update interval: {update_interval_as_int}")

    for config_entry_key, config_entry_data in config_entry.data.items():
        _LOGGER.debug(f"[@{vin}] config_entry.data: {config_entry_key}={config_entry_data}")

    if CONF_REGION in config_entry.data.keys():
        _LOGGER.debug(f"[@{vin}] Region: {config_entry.data[CONF_REGION]}")
        region_key = config_entry.data[CONF_REGION]
    else:
        _LOGGER.debug(f"[@{vin}] cant get region for key: {CONF_REGION} in {config_entry.data.keys()} using default: '{DEFAULT_REGION_FORD}'")
        region_key = DEFAULT_REGION_FORD

    coordinator = FordPassDataUpdateCoordinator(hass, config_entry, user, vin, region_key, update_interval_as_int=update_interval_as_int, save_token=True)
    await coordinator.bridge._rename_token_file_if_needed(user)

    # ok starting the init sequence...
    lang = hass.config.language.lower()
    if lang in TRANSLATIONS:
        lang_map = TRANSLATIONS[lang]
    else:
        lang_map = TRANSLATIONS["en"]

    user_garage_data = await coordinator.bridge.update_users_garage_info()
    if user_garage_data is None or len(user_garage_data) == 0:
        _LOGGER.warning(f"Could not get any garage data for user: {user}/{region_key} - so we can't continue with the init sequence")
        await coordinator._check_for_reauth()
        raise ConfigEntryNotReady(lang_map["coord_null_data"])

    # We have successfully requested the garage data for the user (with all available vehicles)
    vehicle_is_active = False
    for a_vehicle in user_garage_data:
        if vin == a_vehicle.get("vin", "vin-unknown"):
            _LOGGER.debug(f"Found the vehicle with VIN: {vin} in the initial requested garage data - so let's continue with the init sequence")
            vehicle_is_active = True
            break

    if not vehicle_is_active:
        raise ConfigEntryNotReady(lang_map["coord_no_vehicle_data"])

    # so VIN is still available in our initial garage data... so we should start the websocket connection...
    # and once that is established, we do the rest!
    try:
        if not await coordinator.start_websocket_and_wait_for_first_data():
            _LOGGER.warning(f"The coordinator.start_websocket_and_wait_for_first_data() as returned FALSE")
            raise ConfigEntryNotReady(lang_map["coord_no_vehicle_data"])

    except BaseException as exc:
        _LOGGER.error(f"Error starting websocket connection: {type(exc).__name__} - {exc}")
        raise ConfigEntryNotReady(lang_map["websocket_start_failed"])

    # init our vehicle and the supported features...
    await coordinator.read_config_on_startup(hass)

    # start the websocket watchdog...
    if hass.state is CoreState.running:
        await coordinator.start_watchdog()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, coordinator.start_watchdog)

    if not config_entry.options:
        await async_update_options(hass, config_entry)

    hass.data[DOMAIN][config_entry.entry_id] = {
        COORDINATOR_KEY: coordinator
    }

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    # SERVICES from here...
    # simple service implementations (might be moved to separate service.py)
    async def async_refresh_status_service(call: ServiceCall):
        _LOGGER.debug(f"Running Service 'refresh_status'")
        status = await coordinator.bridge.request_update()
        if status == 401:
            _LOGGER.debug(f"[@{coordinator.vli}] refresh_status: Invalid VIN?! (status 401)")
        elif status in [200, 201, 202]:
            _LOGGER.debug(f"[@{coordinator.vli}] refresh_status: Refresh sent")

        await asyncio.sleep(10)
        await coordinator.async_request_refresh_force_classic_requests()

    async def async_clear_tokens_service(call: ServiceCall):
        #await hass.async_add_executor_job(service_clear_tokens, hass, call, coordinator)
        """Clear the token file in config directory, only use in emergency"""
        _LOGGER.debug(f"Running Service 'clear_tokens'")
        await coordinator.bridge.clear_token()
        await asyncio.sleep(5)
        await coordinator.async_request_refresh_force_classic_requests()

    async def poll_api_service(call: ServiceCall):
        await coordinator.async_request_refresh_force_classic_requests()

    async def handle_reload_service(call: ServiceCall):
        """Handle reload service call."""
        _LOGGER.debug(f"Reloading Integration")

        current_entries = hass.config_entries.async_entries(DOMAIN)
        reload_tasks = [
            hass.config_entries.async_reload(entry.entry_id)
            for entry in current_entries
        ]

        await asyncio.gather(*reload_tasks)

    async def async_delete_message_service(call: ServiceCall):
        _LOGGER.debug(f"Running Service 'delete_message'")
        msg_id = call.data.get('msgid', None)
        if msg_id is not None:
            try:
                return await FordpassDataHandler.messages_delete_with_id_called_from_service(coordinator, int(msg_id))
            except ValueError:
                _LOGGER.warning(f"async_delete_message_service: provided 'msgid' can not be convert to a number: {type(msg_id).__name__} - {msg_id}")
                return False
        else:
            _LOGGER.warning(f"async_delete_message_service: No 'msgid' was provided!")
            return False

    async def async_update_departure_schedule_service(call: ServiceCall):
        _LOGGER.debug(f"Running Service 'update_departure_schedule'")

        hour = call.data.get("hour", None)
        minute = call.data.get("minute", None)
        precon_temperature = str(call.data.get("precondition_temperature", "OFF")).upper()
        days = call.data.get("schedule_days", [])

        if hour is None or minute is None:
            _LOGGER.warning("async_update_departure_schedule_service(): 'hour' and 'minute' are required")
            return False

        if isinstance(days, str):
            days = [days]
        elif not isinstance(days, list):
            _LOGGER.warning(f"async_update_departure_schedule_service(): invalid 'days' format: {type(days).__name__}")
            return False

        validated_days = []
        for day in days:
            day_name = str(day).upper()
            if day_name in DAYS_MAP:
                validated_days.append(day_name)

        if len(validated_days) == 0:
            _LOGGER.warning("async_update_departure_schedule_service(): No valid days were provided")
            return False

        if precon_temperature not in ["LOW", "MEDIUM", "HIGH", "OFF"]:
            _LOGGER.warning(f"async_update_departure_schedule_service(): invalid precon_temperature '{precon_temperature}' - fallback to OFF")
            precon_temperature = "OFF"

        try:
            await FordpassDataHandler.update_departure_schedule(coordinator.data, coordinator.bridge,
                validated_days, int(hour), int(minute), precon_temperature
            )
        except ValueError:
            _LOGGER.warning(f"async_update_departure_schedule_service(): invalid hour/minute values: hour={hour}, minute={minute}")
            return False

        #await asyncio.sleep(2)
        #await coordinator.async_request_refresh_force_classic_requests()
        return True

    async def async_delete_departure_schedule_by_days_service(call: ServiceCall):
        _LOGGER.debug(f"Running Service 'delete_departure_schedule_by_days'")

        days = call.data.get("schedule_days", [])
        if isinstance(days, str):
            days = [days]
        elif not isinstance(days, list):
            _LOGGER.warning(f"async_delete_departure_schedule_by_days_service(): invalid 'schedule_days' format: {type(days).__name__}")
            return False

        validated_days = []
        for day in days:
            day_name = str(day).upper()
            if day_name in DAYS_MAP:
                validated_days.append(day_name)

        if len(validated_days) == 0:
            _LOGGER.warning("async_delete_departure_schedule_by_days_service(): No valid days were provided")
            return False

        try:
            await FordpassDataHandler.delete_departure_schedule_by_days(coordinator.data, coordinator.bridge,
                validated_days
            )
        except ValueError:
            _LOGGER.warning(f"async_delete_departure_schedule_by_days_service(): invalid values: validated_days={validated_days}")
            return False

        return True

    async def async_delete_departure_schedule_by_ids_service(call: ServiceCall):
        _LOGGER.debug(f"Running Service 'delete_departure_schedule_by_ids'")

        raw_ids = call.data.get("schedule_ids", [])
        if isinstance(raw_ids, int):
            schedule_ids = [raw_ids]
        elif isinstance(raw_ids, str):
            parts = [p.strip() for p in raw_ids.split(",") if p.strip()]
            try:
                schedule_ids = [int(p) for p in parts]
            except ValueError:
                _LOGGER.warning(f"async_delete_departure_schedule_by_ids_service(): invalid 'schedule_ids' string: {raw_ids}")
                return False
        elif isinstance(raw_ids, list):
            schedule_ids = []
            for value in raw_ids:
                try:
                    schedule_ids.append(int(value))
                except (TypeError, ValueError):
                    _LOGGER.warning(f"async_delete_departure_schedule_by_ids_service(): invalid schedule id value: {value}")
                    return False
        else:
            _LOGGER.warning(f"async_delete_departure_schedule_by_ids_service(): invalid 'schedule_ids' format: {type(raw_ids).__name__}")
            return False

        if len(schedule_ids) == 0:
            _LOGGER.warning("async_delete_departure_schedule_by_ids_service(): No schedule IDs were provided")
            return False

        try:
            await FordpassDataHandler.delete_departure_schedule_by_schedule_ids(coordinator.data, coordinator.bridge,
                schedule_ids
            )
        except ValueError:
            _LOGGER.warning(f"async_delete_departure_schedule_by_ids_service(): invalid values: schedule_ids={schedule_ids}")
            return False

        return True

    hass.services.async_register(DOMAIN, "refresh_status", async_refresh_status_service)
    hass.services.async_register(DOMAIN, "clear_tokens", async_clear_tokens_service)
    hass.services.async_register(DOMAIN, "poll_api", poll_api_service)
    hass.services.async_register(DOMAIN, "reload", handle_reload_service)
    hass.services.async_register(DOMAIN, "delete_message", async_delete_message_service)
    if coordinator.tag_supported_by_vehicle(Tag.DEPARTURE_SCHEDULES):
        hass.services.async_register(DOMAIN, "update_departure_schedule", async_update_departure_schedule_service)
        hass.services.async_register(DOMAIN, "delete_departure_schedule_by_days", async_delete_departure_schedule_by_days_service)
        hass.services.async_register(DOMAIN, "delete_departure_schedule_by_ids", async_delete_departure_schedule_by_ids_service)
    else:
        _LOGGER.debug(f"{coordinator.vli}Service 'departure_schedule services' will NOT be registered since this vehicle does not support departure schedules")

    config_entry.async_on_unload(config_entry.add_update_listener(entry_update_listener))
    return True


# def check_for_deprecated_region_keys(region_key):
#     if region_key in LEGACY_REGION_KEYS:
#         _LOGGER.info(f"current configuration contains LEGACY region-key: {region_key} -> please create a new ha-config entry to avoid this message in the future!")
#     return region_key


async def async_update_options(hass, config_entry):
    """Update options entries on change"""
    _LOGGER.debug(f"async_update_options(): called for entry: {config_entry.entry_id}")
    options = {
        CONF_PRESSURE_UNIT: config_entry.data.get(CONF_PRESSURE_UNIT, DEFAULT_PRESSURE_UNIT),
    }
    hass.config_entries.async_update_entry(config_entry, options=options)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug(f"async_unload_entry(): called for entry: {config_entry.entry_id}")
    unload_ok = await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)

    if unload_ok:
        if DOMAIN in hass.data and config_entry.entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR_KEY]
            coordinator.stop_watchdog()
            await coordinator.clear_data()
            coordinator.detach_http_session()

            hass.data[DOMAIN].pop(config_entry.entry_id)
            if coordinator.tag_supported_by_vehicle(Tag.DEPARTURE_SCHEDULES):
                hass.services.async_remove(DOMAIN, "update_departure_schedule")
                hass.services.async_remove(DOMAIN, "delete_departure_schedule_by_days")
                hass.services.async_remove(DOMAIN, "delete_departure_schedule_by_ids")

        hass.services.async_remove(DOMAIN, "refresh_status")
        hass.services.async_remove(DOMAIN, "clear_tokens")
        hass.services.async_remove(DOMAIN, "poll_api")
        hass.services.async_remove(DOMAIN, "reload")
        hass.services.async_remove(DOMAIN, "delete_message")

    return unload_ok


async def entry_update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    _LOGGER.debug(f"entry_update_listener() called for entry: {config_entry.entry_id}")
    await hass.config_entries.async_reload(config_entry.entry_id)


#_session_cache = {}
#_sync_lock = threading.Lock()

@staticmethod
def get_none_closed_cached_session(hass: HomeAssistant, vin:str, vli:str) -> aiohttp.ClientSession:
    """Get a ~~cached~~ aiohttp session for the user & region."""

    # 2025-06-12 for now we do not cache anything for a new vehicle... if we start to share a client session
    # across multiple vehicles (= multiple instances of this integration), then WE MUST also sync the token's!
    # When we share tokens, we must synchonize the refresh tokens and share them across multiple vehicles.
    _LOGGER.debug(f"{vli}Create new aiohttp.ClientSession for vin: {vin}")
    return async_create_clientsession(hass)

    # global _session_cache
    # a_key = f"{user}µ@µ{region_key}"
    # with _sync_lock:
    #     if a_key not in _session_cache or _session_cache[a_key].closed:
    #         _LOGGER.debug(f"{vli}Create new aiohttp.ClientSession for user: {user}, region: {region_key}")
    #         _session_cache[a_key] = async_create_clientsession(hass)
    #     else:
    #         _LOGGER.debug(f"{vli}Using cached aiohttp.ClientSession (so we share cookies) for user: {user}, region: {region_key}")
    # return _session_cache[a_key]

class FordPassDataUpdateCoordinator(DataUpdateCoordinator):
    """DataUpdateCoordinator to handle fetching new data about the vehicle."""
    _http_session: aiohttp.ClientSession | None = None
    _integration_start: float | None = None

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry,
                 user, vin, region_key, update_interval_as_int:int, save_token=False):
        """Initialize the coordinator and set up the Vehicle object."""
        self._config_entry = config_entry
        self._vin = vin
        self.vli = f"[@{self._vin}] "

        lang = hass.config.language.lower()
        if lang in TRANSLATIONS:
            self.lang_map = TRANSLATIONS[lang]
        else:
            self.lang_map = TRANSLATIONS["en"]

        self._http_session = get_none_closed_cached_session(hass, vin, self.vli)
        self.bridge = ConnectedFordPassVehicle(self._http_session, user,
                                               vin, region_key, coordinator=self, storage_path=Path(hass.config.config_dir).joinpath(STORAGE_DIR),
                                               local_logging=config_entry.options.get(CONF_LOG_TO_FILESYSTEM, False))

        self._available = True
        self._reauth_requested = False
        self._is_brand_lincoln = region_key in REGION_OPTIONS_LINCOLN
        self._engine_type = None
        self._number_of_lighting_zones = 0
        self._supports_GUARD_MODE = None
        self._supports_REMOTE_LOCK = None
        self._supports_REMOTE_START = None
        self._supports_TRAILER_LIGHT_CHECK = None
        self._supports_DEPARTURE_TIMES = None
        self._supports_ZONE_LIGHTING = None
        self._supports_ALARM = None
        self._supports_GEARLEVERPOSITION = None
        self._supports_AUTO_UPDATES = None
        self._supports_HAF = None
        self._force_REMOTE_CLIMATE_CONTROL = config_entry.options.get(CONF_FORCE_REMOTE_CLIMATE_CONTROL, False)
        self._supports_REMOTE_CLIMATE_CONTROL = None
        self._supports_HEATED_STEERING_WHEEL = None
        self._supports_HEATED_HEATED_SEAT_MODE = None
        #self._last_ENERGY_TRANSFER_LOG_ENTRY_ID = None

        # we need to make a clone of the unit system, so that we can change the pressure unit (for our tire types)
        self.units:UnitSystem = hass.config.units
        if CONF_PRESSURE_UNIT in config_entry.options:
            user_pressure_unit = config_entry.options.get(CONF_PRESSURE_UNIT, None)
            if user_pressure_unit is not None and user_pressure_unit in PRESSURE_UNITS:
                local_pressure_unit = UnitOfPressure.KPA
                if user_pressure_unit == "PSI":
                    local_pressure_unit = UnitOfPressure.PSI
                elif user_pressure_unit == "BAR":
                    local_pressure_unit = UnitOfPressure.BAR

                orig = hass.config.units
                self.units = UnitSystem(
                    f"{orig._name}_fordpass",
                    accumulated_precipitation=orig.accumulated_precipitation_unit,
                    area=orig.area_unit,
                    conversions=orig._conversions,
                    length=orig.length_unit,
                    mass=orig.mass_unit,
                    pressure=local_pressure_unit,
                    temperature=orig.temperature_unit,
                    volume=orig.volume_unit,
                    wind_speed=orig.wind_speed_unit,
                )

        self._watchdog = None
        self._a_task = None
        self._force_classic_requests = False
        self._ws_data_update_notify_interval_in_seconds = 5
        self._integration_start = time.time()
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=update_interval_as_int))

    async def clear_data(self):
        _LOGGER.debug(f"{self.vli}clear_data called...")
        self._check_for_ws_task_and_cancel_if_running()
        self.bridge.clear_data()
        self.data.clear()

    def detach_http_session(self):
        if self._http_session is not None:
            # try:
            #     await self._http_session.close()
            # except BaseException as ex:
            #     pass
            #
            try:
                self._http_session.detach()
            except BaseException as exc:
                pass

    def get_new_client_session(self, vin: str) -> aiohttp.ClientSession:
        """Get a new aiohttp ClientSession for the vehicle."""
        if self.hass is None:
            raise ValueError(f"{self.vli}Home Assistant instance is not available")

        # if there exist any previous _http_session - we will detach from it...
        self.detach_http_session()

        self._http_session = get_none_closed_cached_session(self.hass, vin, self.vli)
        return self._http_session

    async def start_websocket_and_wait_for_first_data(self):
        # 1. Create an event to signal when the connection is established/ready
        connected_event = asyncio.Event()

        # 2. Pass the event into your background task
        self._a_task = self._config_entry.async_create_background_task(self.hass, self.bridge.ws_connect(ready_event=connected_event), "ws_connection")

        # 3. Wait ONLY until the first message is processed (or time out)
        try:
            async with asyncio.timeout(60):  # Protect against hanging forever
                await connected_event.wait()
        except TimeoutError:
            _LOGGER.warning("Connection to websocket timed out after one minute!")
            self._a_task.cancel()
            # NOT SURE WHAT TO DO NOW ???!
            raise

        _LOGGER.debug(f"Connection to websocket established!")
        is_essential_vehicle_data_available = FordpassDataHandler.is_essential_vehicle_data_available(self.data)
        if not is_essential_vehicle_data_available:
            return False

        _LOGGER.info(f"Essential vehicle data is available after WebSocket connection has been established - that's just so GREAT! Available keys: {list(self.data.keys())} so let's move on...")
        return True

    async def start_watchdog(self, event=None):
        """Start websocket watchdog."""
        await self._async_watchdog_check()
        self._watchdog = async_track_time_interval(
            self.hass,
            self._async_watchdog_check,
            WEBSOCKET_WATCHDOG_INTERVAL,
        )

    def stop_watchdog(self):
        if hasattr(self, "_watchdog") and self._watchdog is not None:
            self._watchdog()

    def _check_for_ws_task_and_cancel_if_running(self):
        if self._a_task is not None and not self._a_task.done():
            _LOGGER.debug(f"{self.vli}Watchdog: websocket connect task is still running - canceling it...")
            try:
                canceled = self._a_task.cancel()
                _LOGGER.debug(f"{self.vli}Watchdog: websocket connect task was CANCELED? {canceled}")
            except BaseException as ex:
                _LOGGER.info(f"{self.vli}Watchdog: websocket connect task cancel failed: {type(ex).__name__} - {ex}")
            self._a_task = None

    async def _check_for_reauth(self):
        if self.bridge.require_reauth:
            self._available = False  # Mark as unavailable
            if not self._reauth_requested:
                self._reauth_requested = True
                _LOGGER.warning(f"{self.vli}_check_for_reauth: VIN {self._vin} requires re-authentication")
                self.hass.add_job(self._config_entry.async_start_reauth, self.hass)

    async def _async_watchdog_check(self, *_):
        """Reconnect the websocket if it fails."""
        await self._check_for_reauth()

        if not self.bridge.ws_connected:
            self._check_for_ws_task_and_cancel_if_running()
            _LOGGER.info(f"{self.vli}Watchdog: websocket connect required")
            self._a_task = self._config_entry.async_create_background_task(self.hass, self.bridge.ws_connect(), "ws_connection")
            if self._a_task is not None:
                _LOGGER.debug(f"{self.vli}Watchdog: task created {self._a_task.get_coro()}")
        else:
            _LOGGER.debug(f"{self.vli}Watchdog: websocket is connected")
            self._available = True
            if not self.bridge.ws_check_last_update():
                self._check_for_ws_task_and_cancel_if_running()

    def tag_supported_by_vehicle(self, a_tag: Tag) -> bool:
        if a_tag in FUEL_OR_PEV_ONLY_TAGS:
            return self.supportFuel

        if a_tag in EV_ONLY_TAGS:
            return self.supportPureEvOrPluginEv

        # handling of the remote climate control tags...
        if a_tag in RCC_TAGS:
            ret_val = self._supports_REMOTE_CLIMATE_CONTROL
            if ret_val:
                # not all vehicles do support some of the remote climate control tags, so we need to check
                if a_tag == Tag.RCC_STEERING_WHEEL:
                    ret_val = self._supports_HEATED_STEERING_WHEEL
                elif a_tag in [Tag.RCC_SEAT_FRONT_LEFT, Tag.RCC_SEAT_FRONT_RIGHT, Tag.RCC_SEAT_REAR_LEFT, Tag.RCC_SEAT_REAR_RIGHT]:
                    ret_val = self._supports_HEATED_HEATED_SEAT_MODE != RCC_SEAT_MODE_NONE

            #_LOGGER.error(f"{self.vli}Remote Climate Control support: {ret_val} - {a_tag.name}")
            return ret_val

        # other vehicle (or feature) dependent tags...
        if a_tag in [Tag.REMOTE_START_STATUS,
                     Tag.REMOTE_START_COUNTDOWN,
                     Tag.REMOTE_START,
                     Tag.EXTEND_REMOTE_START,
                     Tag.GUARD_MODE,
                     Tag.ZONE_LIGHTING,
                     Tag.ALARM,
                     Tag.DOOR_LOCK,
                     Tag.DOOR_UNLOCK,
                     Tag.GEARLEVERPOSITION,
                     Tag.AUTO_UPDATES,
                     Tag.DEPARTURE_TIMES, Tag.DEPARTURE_SCHEDULES,
                     Tag.TRAILER_LIGHT_CHECK, Tag.TRAILER_LIGHT_CHECK_ON, Tag.TRAILER_LIGHT_CHECK_OFF,
                     Tag.HAF_SHORT, Tag.HAF_DEFAULT, Tag.HAF_LONG]:

            # just handling the unpleasant fact that for 'Tag.REMOTE_START_STATUS' and 'Tag.REMOTE_START' we just
            # share the same 'support_ATTR_NAME'...
            if a_tag == Tag.REMOTE_START_STATUS or a_tag == Tag.REMOTE_START_COUNTDOWN or a_tag == Tag.EXTEND_REMOTE_START:
                support_ATTR_NAME = f"_supports_{Tag.REMOTE_START.name}"
            elif a_tag in [Tag.HAF_SHORT, Tag.HAF_DEFAULT, Tag.HAF_LONG]:
                support_ATTR_NAME = f"_supports_HAF"
            elif a_tag in [Tag.DOOR_LOCK, Tag.DOOR_UNLOCK]:
                support_ATTR_NAME = f"_supports_REMOTE_LOCK"
            elif a_tag in [Tag.TRAILER_LIGHT_CHECK, Tag.TRAILER_LIGHT_CHECK_ON, Tag.TRAILER_LIGHT_CHECK_OFF]:
                support_ATTR_NAME = f"_supports_TRAILER_LIGHT_CHECK"
            elif a_tag in [Tag.DEPARTURE_TIMES, Tag.DEPARTURE_SCHEDULES]:
                support_ATTR_NAME = f"_supports_DEPARTURE_TIMES"
            else:
                support_ATTR_NAME = f"_supports_{a_tag.name}"

            eval_result = getattr(self, support_ATTR_NAME, None)
            return  eval_result is not None and eval_result

        return True

    # async def create_energy_transfer_log_entry(self, a_entry:dict):
    #     _LOGGER.info(f"{self.vli}create_energy_transfer_log_entry called with {a_entry}")
    #     pass

    @property
    def has_ev_soc(self) -> bool:
        return self._engine_type is not None and self._engine_type in ["BEV", "PHEV"]

    @property
    def supportPureEvOrPluginEv(self) -> bool:
        # looks like that 'HEV' are just have an additional 48V battery getting energy from breaking...
        # and also looks like that there is no special EV related data present in state object (json)
        return self._engine_type is not None and self._engine_type in ["BEV", "HEV", "PHEV"]

    @property
    def supportFuel(self) -> bool:
        return self._engine_type is not None and self._engine_type not in ["BEV"]

    async def read_config_on_startup(self, hass: HomeAssistant):
        _LOGGER.debug(f"{self.vli}read_config_on_startup...")

        # we are reading here from the global coordinator data object!
        if self.data is not None:
            if ROOT_VEHICLES in self.data:
                the_veh_data = self.data[ROOT_VEHICLES]

                if isinstance(the_veh_data, list):
                    # after API-Change FordPassApp 6.20.0
                    for a_veh_obj in the_veh_data:
                        if self._vin == a_veh_obj.get("vin", "vin-unknown"):
                            tmp_pro = a_veh_obj.get("profile", None)
                            tmp_cap = a_veh_obj.get("capabilities", None)

                            if not tmp_pro or not tmp_cap:
                                _LOGGER.warning(f"{self.vli}No 'profile' or 'capabilities' found in coordinator data - no engineType available! - {a_veh_obj}")
                                continue

                            nn_profile_obj = NonNullDict(tmp_pro)
                            nn_capabilities_obj = NonNullDict(tmp_cap)

                            if "model" in nn_profile_obj:
                                fallback = f"{self._vin}(unknown-model)"
                                self.vli = f"[{nn_profile_obj.none_null_get('model', fallback)}] "

                            if "engineType" in nn_profile_obj:
                                self._engine_type = nn_profile_obj.none_null_get("engineType", "unknown")
                                # yes this check looks a bit paranoid - no clue how I can make this better!
                                if not isinstance(self._engine_type, str) or len(self._engine_type) == 0 or self._engine_type == "unknown":
                                    _LOGGER.warning(f"{self.vli}EngineType COULD NOT BE DETECTED '{self._engine_type}' using 'ICE' AS DEFAULT")
                                    self._engine_type = "ICE"
                                else:
                                    _LOGGER.debug(f"{self.vli}EngineType is: {self._engine_type}")

                            if "numberOfLightingZones" in nn_profile_obj:
                                try:
                                    self._number_of_lighting_zones = int(nn_profile_obj.none_null_get("numberOfLightingZones", "0"))
                                    _LOGGER.debug(f"{self.vli}NumberOfLightingZones is: {self._number_of_lighting_zones}")
                                except BaseException as exc:
                                    _LOGGER.debug(f"{self.vli}NumberOfLightingZones COULD NOT BE DETECTED '{self._number_of_lighting_zones}' using '0' AS DEFAULT - caused by {type(exc).__name__} - {exc}")

                            if "transmissionIndicator" in nn_profile_obj:
                                self._supports_GEARLEVERPOSITION = nn_profile_obj.none_null_get("transmissionIndicator", "Z") == "A"
                                _LOGGER.debug(f"{self.vli}GearLeverPosition support: {self._supports_GEARLEVERPOSITION}")

                            # remote climate control stuff...
                            if self._force_REMOTE_CLIMATE_CONTROL:
                                self._supports_REMOTE_CLIMATE_CONTROL = True
                                _LOGGER.debug(f"{self.vli}RemoteClimateControl FORCED: {self._supports_REMOTE_CLIMATE_CONTROL}")
                            else:
                                # in August 2026 'remoteClimateControl' is only in 'capabilities'
                                if "remoteClimateControl" in nn_capabilities_obj:
                                    self._supports_REMOTE_CLIMATE_CONTROL = self._check_if_veh_capability_supported("remoteClimateControl", nn_capabilities_obj)
                                    _LOGGER.debug(f"{self.vli}RemoteClimateControl support: {self._supports_REMOTE_CLIMATE_CONTROL}")

                                # THIS IS A BLIND GUESS!!!
                                if not self._supports_REMOTE_CLIMATE_CONTROL and "remoteHeatingCooling" in nn_capabilities_obj:
                                    self._supports_REMOTE_CLIMATE_CONTROL = self._check_if_veh_capability_supported("remoteHeatingCooling", nn_capabilities_obj)
                                    _LOGGER.debug(f"{self.vli}RemoteClimateControl/remoteHeatingCooling support: {self._supports_REMOTE_CLIMATE_CONTROL}")

                            #heating stuff...
                            if "heatedSteeringWheel" in nn_profile_obj:
                                self._supports_HEATED_STEERING_WHEEL = nn_profile_obj.none_null_get("heatedSteeringWheel", False)
                                _LOGGER.debug(f"{self.vli}HeatedSteeringWheel support: {self._supports_HEATED_STEERING_WHEEL}")

                            self._supports_HEATED_HEATED_SEAT_MODE = RCC_SEAT_MODE_NONE
                            if "driverHeatedSeat" in nn_profile_obj:
                                # possible values: 'None', 'Heat Only', 'Heat with Vent'
                                heated_seat_value = nn_profile_obj.none_null_get("driverHeatedSeat", "unknown").lower()
                                if heated_seat_value == "heat with vent":
                                    self._supports_HEATED_HEATED_SEAT_MODE = RCC_SEAT_MODE_HEAT_AND_COOL
                                elif "heat" in heated_seat_value:
                                    self._supports_HEATED_HEATED_SEAT_MODE = RCC_SEAT_MODE_HEAT_ONLY
                            _LOGGER.debug(f"{self.vli}DriverHeatedSeat support mode: {self._supports_HEATED_HEATED_SEAT_MODE}")

                            # ok now the classic 'capabilities'...
                            self._supports_ALARM = Tag.ALARM.get_state(self.data) != UNSUPPORTED
                            self._supports_REMOTE_LOCK = self._check_if_veh_capability_supported("remoteLock", nn_capabilities_obj)
                            self._supports_REMOTE_START = self._check_if_veh_capability_supported("remoteStart", nn_capabilities_obj)
                            self._supports_TRAILER_LIGHT_CHECK = self._check_if_veh_capability_supported("trailerLightCheck", nn_capabilities_obj)
                            self._supports_DEPARTURE_TIMES = self._check_if_veh_capability_supported("departureTimes", nn_capabilities_obj)
                            self._supports_GUARD_MODE = self._check_if_veh_capability_supported("guardMode", nn_capabilities_obj)
                            self._supports_ZONE_LIGHTING = self._check_if_veh_capability_supported("zoneLighting", nn_capabilities_obj) and self._number_of_lighting_zones > 0
                            self._supports_HAF = self._check_if_veh_capability_supported("remotePanicAlarm", nn_capabilities_obj)

                else:
                    _LOGGER.warning(f"{self.vli}No list object in coordinator '{ROOT_VEHICLES}' data - no engineType available! {self.the_veh_data}")

                # check, if GuardMode is supported
                # [original impl]
                self._supports_GUARD_MODE = FordpassDataHandler.is_guard_mode_supported(self.data)

            else:
                _LOGGER.warning(f"{self.vli}No vehicles data found in coordinator data - no engineType available! {self.data}")

            # other self._supports_* attribues will be checked in 'metrics' data...
            if ROOT_METRICS in self.data:
                self._supports_AUTO_UPDATES = Tag.AUTO_UPDATES.get_state(self.data) != UNSUPPORTED
                _LOGGER.debug(f"{self.vli}AutoUpdates supported: {self._supports_AUTO_UPDATES}")

        else:
            _LOGGER.warning(f"{self.vli}DATA is NONE!!! - {self.data}")

    def _check_if_veh_capability_supported(self, a_capability: str, capabilities: NonNullDict) -> bool:
        """Check if a specific vehicle capability is supported."""
        is_supported = False
        if a_capability in capabilities and capabilities.get(a_capability, None) is not None:
            val = capabilities.none_null_get(a_capability, False)
            if isinstance(val, bool):
                is_supported = val
            elif isinstance(val, str):
                lc_val = val.lower()
                is_supported = any(lc_val == a_check for a_check in ("display", "true", "yes", 'on', '1'))
            elif isinstance(val, (float, int)):
                is_supported = int(val) > 0
            else:
                _LOGGER.info(f"{self.vli}Is '{a_capability}' check failed: '{val}' is not boolean, string or number: {type(val).__name__}")

            _LOGGER.debug(f"{self.vli}Is '{a_capability}' supported?: {is_supported} - {val}")
        else:
            _LOGGER.warning(f"{self.vli}No '{a_capability}' data found for VIN {self._vin} - assuming not supported")

        return is_supported

    async def async_request_refresh_force_classic_requests(self):
        self._force_classic_requests = True
        await self.async_request_refresh()
        self._force_classic_requests = False

    async def _async_update_data(self):
        """Fetch data from FordPass."""

        # 1. check, if we are healthy...
        if self.bridge.require_reauth:
            self._available = False  # Mark as unavailable
            if not self._reauth_requested:
                self._reauth_requested = True
                _LOGGER.warning(f"{self.vli}_async_update_data(): VIN {self._vin} requires re-authentication")
                self.hass.add_job(self._config_entry.async_start_reauth, self.hass)

            raise UpdateFailed(f"Error VIN: {self._vin} requires re-authentication")

        # 2. the default should be that the websocket is connected...
        if self.bridge.ws_connected and self._force_classic_requests is False:
            try:
                _LOGGER.debug(f"{self.vli}_async_update_data(): called (but websocket is active - no data will be requested!)")
                return self.bridge._data_container

            except UpdateFailed as exception:
                _LOGGER.warning(f"{self.vli}_async_update_data(): UpdateFailed: {type(exception).__name__} - {exception}")
                raise UpdateFailed() from exception
            except BaseException as other:
                _LOGGER.warning(f"{self.vli}_async_update_data(): UpdateFailed unexpected: {type(other).__name__} - {other}")
                raise UpdateFailed() from other

        # 3. AS fallback ONLY scenario (websocket is not connected)...
        should_call_update = True
        if not self._force_classic_requests:
            # ignore all manual update requests during the first 5 minutes of the integration start...
            delta_since_start = time.time() - self._integration_start
            if delta_since_start < 300:
                should_call_update = False
                _LOGGER.info(f"{self.vli}_async_update_data(): Update skipped due to integration start phase - {delta_since_start}")

        if should_call_update:
            try:
                async with timeout(60):
                    # I hope the method name is already a hint, that this might not be so smart to call this
                    # method anylonger...
                    data = await self.bridge.update_all_manually_this_is_deprecated_and_should_not_be_called()
                    if data is not None:
                        try:
                            _LOGGER.debug(f"{self.vli}_async_update_data: total number of items: {len(data[ROOT_METRICS])} metrics, {len(data[ROOT_MESSAGES])} messages, {len(data[ROOT_VEHICLES]['vehicleProfile'])} vehicles for {self._vin}")
                        except BaseException:
                            pass

                        # If data has now been fetched but was previously unavailable, log and reset
                        if not self._available:
                            _LOGGER.info(f"{self.vli}_async_update_data: Restored connection to FordPass for {self._vin}")
                            self._available = True
                    else:
                        if self.bridge is not None and self.bridge._HAS_COM_ERROR:
                            _LOGGER.info(f"{self.vli}_async_update_data: 'data' was None for {self._vin} cause of '_HAS_COM_ERROR' (returning OLD data object)")
                        else:
                            _LOGGER.info(f"{self.vli}_async_update_data: 'data' was None for {self._vin} (returning OLD data object)")
                        data = self.data

                    return data

            except asyncio.TimeoutError as timeout_err:
                # Mark as unavailable - but let the coordinator deal with the rest...
                self._available = False
                raise timeout_err

            except BaseException as exc:
                self._available = False  # Mark as unavailable
                _LOGGER.warning(f"{self.vli}_async_update_data(): Error communicating with FordPass for {self._vin} {type(exc).__name__} -> {str(exc)}")
                raise UpdateFailed(f"Error communicating with FordPass for {self._vin} cause of {type(exc).__name__}") from exc
        else:
            if len(self.bridge._data_container) > 0:
                return self.bridge._data_container
            else:
                _LOGGER.warning(f"{self.vli}_async_update_data(): No data available - return 'None'")
                return None


class FordPassEntity(CustomFriendlyNameEntity):
    """Defines a base FordPass entity."""
    _attr_has_entity_name = True
    _attr_name_addon = None

    def __init__(self, entity_type:str, a_tag: Tag, coordinator: FordPassDataUpdateCoordinator, description: EntityDescription | None = None):
        """Initialize the entity."""
        super().__init__(coordinator)

        # ok setting the internal translation key attr (so we can make use of the translation key in the entity)
        self._attr_translation_key = a_tag.key.lower()
        if description is not None:
            self.entity_description = description
            # if an 'entity_description' is present and the description has a translation key - we use it!
            if hasattr(description, "translation_key") and description.translation_key is not None:
                self._attr_translation_key = description.translation_key.lower()

        if hasattr(description, "name_addon"):
            self._attr_name_addon = description.name_addon

        self.coordinator: FordPassDataUpdateCoordinator = coordinator
        self.entity_id = f"{entity_type}.fordpass_{self.coordinator._vin.lower()}_{a_tag.key}".lower()
        self._tag = a_tag

    def _name_internal(self, device_class_name: str | None, platform_translations: dict[str, Any], ) -> str | UndefinedType | None:
        tmp = super()._name_internal(device_class_name, platform_translations)
        if self._attr_name_addon is not None:
            return f"{self._attr_name_addon} {tmp}"
        else:
            return tmp

    @property
    def device_id(self):
        return f"fordpass_did_{self.self.coordinator._vin.lower()}"

    @property
    def unique_id(self):
        """Return the unique ID of the entity."""
        return f"fordpass_uid_{self.coordinator._vin}_{self._tag.key}".lower()

    @property
    def device_info(self):
        """Return device information about this device."""
        if self._tag is None:
            return None

        ## messages are login/user bound... so we create an own device for the user objects
        #if not self._tag in [Tag.MESSAGES, Tag.MESSAGES_DELETE_LAST, Tag.MESSAGES_DELETE_ALL]:
        model = "unknown"
        if ROOT_VEHICLES in self.coordinator.data and self.coordinator.data[ROOT_VEHICLES] is not None:
            vehicles_obj = self.coordinator.data[ROOT_VEHICLES]
            if isinstance(vehicles_obj, list):
                for a_vehicle in vehicles_obj:
                    if a_vehicle["vin"] == self.coordinator._vin:
                        a_profile_obj = a_vehicle.get('profile', {})
                        model = f"{a_profile_obj.get('year', '')} {a_profile_obj.get('model', 'unknown')}"

            elif isinstance(vehicles_obj, dict):
                if "vehicleProfile" in vehicles_obj and vehicles_obj["vehicleProfile"] is not None:
                    for a_vehicle in vehicles_obj["vehicleProfile"]:
                        if a_vehicle["VIN"] == self.coordinator._vin:
                            model = f"{a_vehicle['year']} {a_vehicle['model']}"

        return {
            "identifiers": {(DOMAIN, self.coordinator._vin)},
            "name": f"VIN: {self.coordinator._vin}",
            "model": f"{model}",
            "manufacturer": MANUFACTURER_LINCOLN if self.coordinator._is_brand_lincoln else MANUFACTURER_FORD
        }
        # else:
        #     a_config_entry = self.coordinator._config_entry
        #     name = a_config_entry.data.get(CONF_USERNAME, "unknown_user")
        #     region = a_config_entry.data.get(CONF_REGION, DEFAULT_REGION_FORD)
        #     return {
        #         "identifiers": {(DOMAIN, f"{name}µ@µ{region}")},
        #         "name": f"{self.coordinator.lang_map.get("account", "Account")}: {name} [{self.coordinator.lang_map.get(region, "Unknown")}]",
        #         "manufacturer": MANUFACTURER_LINCOLN if self.coordinator._is_brand_lincoln else MANUFACTURER_FORD
        #     }

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name.
        If has_entity_name is False, this returns self.name
        If has_entity_name is True, this returns device.name + self.name
        """
        name = self.name
        if name is UNDEFINED:
            name = None

        if not self.has_entity_name or not (device_entry := self.device_entry):
            return name

        device_name = device_entry.name_by_user or device_entry.name
        if name is None:
            if hasattr(self, 'use_device_name') and self.use_device_name:
                return device_name
            else:
                _LOGGER.warning(f"Missing attribute 'use_device_name' for {self._tag.key}")
                return self._tag.key

        # check if there is a user specified entity name (overwritten)
        if registry_entry := self.registry_entry:
            if registry_entry.has_entity_name and registry_entry.name is not None:
                name = registry_entry.name

        return name

    @property
    def icon(self):
        """Return the icon."""
        try:
            if self._tag == Tag.SOC and self.coordinator.has_ev_soc:
                soc_value = FordpassDataHandler.get_soc_state(self.coordinator.data)
                charge_display_status = FordpassDataHandler.get_value_for_metrics_key(self.coordinator.data, "xevBatteryChargeDisplayStatus")
                return icon_for_battery_level(battery_level=soc_value, charging=charge_display_status.upper() == "IN_PROGRESS")
        except BaseException as exc:
            _LOGGER.debug(f"Error retrieving icon for {self._tag.key}: {exc}")

        return super().icon