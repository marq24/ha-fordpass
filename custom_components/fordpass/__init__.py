import asyncio
import logging
from datetime import timedelta
from pathlib import Path
from typing import Final, Any

import aiohttp
import async_timeout
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_REGION, CONF_USERNAME, UnitOfPressure, EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant, ServiceCall, CoreState
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import STORAGE_DIR
from homeassistant.helpers.typing import UNDEFINED, UndefinedType
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator, UpdateFailed
from homeassistant.loader import async_get_integration
from homeassistant.util.unit_system import UnitSystem

from custom_components.fordpass.const import (
    DOMAIN,
    TRANSLATIONS,
    STARTUP_MESSAGE,
    CONFIG_VERSION,
    CONFIG_MINOR_VERSION,
    CONF_IS_SUPPORTED,
    CONF_PRESSURE_UNIT,
    CONF_VIN,
    CONF_LOG_TO_FILESYSTEM,
    CONF_FORCE_REMOTE_CLIMATE_CONTROL,
    DEFAULT_PRESSURE_UNIT,
    DEFAULT_REGION_FORD,
    MANUFACTURER_FORD,
    MANUFACTURER_LINCOLN,
    REGION_OPTIONS_LINCOLN,
    UPDATE_INTERVAL,
    UPDATE_INTERVAL_DEFAULT,
    COORDINATOR_KEY,
    PRESSURE_UNITS,
    REGIONS,
    REGIONS_STRICT,
    LEGACY_REGION_KEYS,
    RCC_SEAT_MODE_NONE, RCC_SEAT_MODE_HEAT_ONLY, RCC_SEAT_MODE_HEAT_AND_COOL
)
from custom_components.fordpass.const_tags import Tag, EV_ONLY_TAGS, FUEL_OR_PEV_ONLY_TAGS, RCC_TAGS
from custom_components.fordpass.fordpass_bridge import ConnectedFordPassVehicle
from custom_components.fordpass.fordpass_handler import (
    UNSUPPORTED,
    ROOT_METRICS,
    ROOT_MESSAGES,
    ROOT_VEHICLES,
    FordpassDataHandler
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)
PLATFORMS = ["button", "lock", "number", "sensor", "switch", "select", "device_tracker"]
WEBSOCKET_WATCHDOG_INTERVAL: Final = timedelta(seconds=64)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the FordPass component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    if config_entry.version < CONFIG_VERSION:
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

    for config_entry_data in config_entry.data:
        _LOGGER.debug(f"[@{vin}] config_entry.data: {config_entry_data}")

    if CONF_REGION in config_entry.data.keys():
        _LOGGER.debug(f"[@{vin}] Region: {config_entry.data[CONF_REGION]}")
        region_key = config_entry.data[CONF_REGION]
    else:
        _LOGGER.debug(f"[@{vin}] cant get region for key: {CONF_REGION} in {config_entry.data.keys()} using default: '{DEFAULT_REGION_FORD}'")
        region_key = DEFAULT_REGION_FORD

    coordinator = FordPassDataUpdateCoordinator(hass, config_entry, user, vin, region_key, update_interval_as_int=update_interval_as_int, save_token=True)
    await coordinator.bridge._rename_token_file_if_needed(user)

    # HA can check if we can make an initial data refresh and report the state
    # back to HA (we don't have to code this by ourselves, HA will do this for us)
    # await coordinator.async_config_entry_first_refresh()

    # well 'coordinator.async_config_entry_first_refresh()' does not work for our fordpass integration
    # I must debug later why this is the case
    await coordinator.async_refresh()  # Get initial data
    if not coordinator.last_update_success or coordinator.data is None:
        # we should check, if 'reauth' is required... and trigger it when
        # it's needed...
        await coordinator._check_for_reauth()
        raise ConfigEntryNotReady
    else:
        await coordinator.read_config_on_startup(hass)

    # ws watchdog...
    if hass.state is CoreState.running:
        await coordinator.start_watchdog()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, coordinator.start_watchdog)

    fordpass_options_listener = config_entry.add_update_listener(entry_update_listener)

    if not config_entry.options:
        await async_update_options(hass, config_entry)

    hass.data[DOMAIN][config_entry.entry_id] = {
        COORDINATOR_KEY: coordinator,
        "fordpass_options_listener": fordpass_options_listener
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

    hass.services.async_register(DOMAIN, "refresh_status", async_refresh_status_service)
    hass.services.async_register(DOMAIN, "clear_tokens", async_clear_tokens_service)
    hass.services.async_register(DOMAIN, "poll_api", poll_api_service)
    hass.services.async_register(DOMAIN, "reload", handle_reload_service)

    config_entry.async_on_unload(config_entry.add_update_listener(entry_update_listener))
    return True


# def check_for_deprecated_region_keys(region_key):
#     if region_key in LEGACY_REGION_KEYS:
#         _LOGGER.info(f"current configuration contains LEGACY region-key: {region_key} -> please create a new ha-config entry to avoid this message in the future!")
#     return region_key


async def async_update_options(hass, config_entry):
    """Update options entries on change"""
    options = {
        CONF_PRESSURE_UNIT: config_entry.data.get(CONF_PRESSURE_UNIT, DEFAULT_PRESSURE_UNIT),
    }
    hass.config_entries.async_update_entry(config_entry, options=options)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug(f"async_unload_entry() called for entry: {config_entry.entry_id}")
    unload_ok = await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)

    if unload_ok:
        if DOMAIN in hass.data and config_entry.entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR_KEY]
            coordinator.stop_watchdog()
            await coordinator.clear_data()
            hass.data[DOMAIN].pop(config_entry.entry_id)

        hass.services.async_remove(DOMAIN, "refresh_status")
        hass.services.async_remove(DOMAIN, "clear_tokens")
        hass.services.async_remove(DOMAIN, "poll_api")
        hass.services.async_remove(DOMAIN, "reload")

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

        self.bridge = ConnectedFordPassVehicle(get_none_closed_cached_session(hass, vin, self.vli), user,
                                               vin, region_key, coordinator=self, storage_path=Path(hass.config.config_dir).joinpath(STORAGE_DIR),
                                               local_logging=config_entry.options.get(CONF_LOG_TO_FILESYSTEM, False))

        self._available = True
        self._reauth_requested = False
        self._is_brand_lincoln = region_key in REGION_OPTIONS_LINCOLN
        self._engine_type = None
        self._number_of_lighting_zones = 0
        self._supports_GUARD_MODE = None
        self._supports_REMOTE_START = None
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
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=update_interval_as_int))

    async def get_new_client_session(self, vin: str) -> aiohttp.ClientSession:
        """Get a new aiohttp ClientSession for the vehicle."""
        if self.hass is None:
            raise ValueError(f"{self.vli}Home Assistant instance is not available")
        return get_none_closed_cached_session(self.hass, vin, self.vli)

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

    def tag_not_supported_by_vehicle(self, a_tag: Tag) -> bool:
        if a_tag in FUEL_OR_PEV_ONLY_TAGS:
            return self.supportFuel is False

        if a_tag in EV_ONLY_TAGS:
            return self.supportPureEvOrPluginEv is False

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
            return ret_val is False

        # other vehicle dependant tags...
        if a_tag in [Tag.REMOTE_START_STATUS,
                     Tag.REMOTE_START_COUNTDOWN,
                     Tag.REMOTE_START,
                     Tag.EXTEND_REMOTE_START,
                     Tag.GUARD_MODE,
                     Tag.ZONE_LIGHTING,
                     Tag.ALARM,
                     Tag.GEARLEVERPOSITION,
                     Tag.AUTO_UPDATES,
                     Tag.HAF_SHORT, Tag.HAF_DEFAULT, Tag.HAF_LONG]:
            # just handling the unpleasant fact, that for 'Tag.REMOTE_START_STATUS' and 'Tag.REMOTE_START' we just
            # share the same 'support_ATTR_NAME'...
            if a_tag == Tag.REMOTE_START_STATUS or a_tag == Tag.REMOTE_START_COUNTDOWN or a_tag == Tag.EXTEND_REMOTE_START:
                support_ATTR_NAME = f"_supports_{Tag.REMOTE_START.name}"
            elif a_tag in [Tag.HAF_SHORT, Tag.HAF_DEFAULT, Tag.HAF_LONG]:
                support_ATTR_NAME = f"_supports_HAF"
            else:
                support_ATTR_NAME = f"_supports_{a_tag.name}"

            return getattr(self, support_ATTR_NAME, None) is None or getattr(self, support_ATTR_NAME) is False

        return False

    async def clear_data(self):
        _LOGGER.debug(f"{self.vli}clear_data called...")
        self._check_for_ws_task_and_cancel_if_running()
        self.bridge.clear_data()
        self.data.clear()

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
                veh_data = self.data[ROOT_VEHICLES]

                # getting the engineType...
                if "vehicleProfile" in veh_data:
                    for a_vehicle_profile in veh_data["vehicleProfile"]:
                        if a_vehicle_profile["VIN"] == self._vin:
                            if "model" in a_vehicle_profile:
                                self.vli = f"[{a_vehicle_profile['model']}] "

                            if "engineType" in a_vehicle_profile:
                                self._engine_type = a_vehicle_profile["engineType"]
                                _LOGGER.debug(f"{self.vli}EngineType is: {self._engine_type}")

                            if "numberOfLightingZones" in a_vehicle_profile:
                                self._number_of_lighting_zones = int(a_vehicle_profile["numberOfLightingZones"])
                                _LOGGER.debug(f"{self.vli}NumberOfLightingZones is: {self._number_of_lighting_zones}")

                            if "transmissionIndicator" in a_vehicle_profile:
                                self._supports_GEARLEVERPOSITION = a_vehicle_profile["transmissionIndicator"] == "A"
                                _LOGGER.debug(f"{self.vli}GearLeverPosition support: {self._supports_GEARLEVERPOSITION}")

                            # remote climate control stuff...
                            if self._force_REMOTE_CLIMATE_CONTROL:
                                self._supports_REMOTE_CLIMATE_CONTROL = True
                                _LOGGER.debug(f"{self.vli}RemoteClimateControl FORCED: {self._supports_REMOTE_CLIMATE_CONTROL}")
                            else:
                                if "remoteClimateControl" in a_vehicle_profile:
                                    self._supports_REMOTE_CLIMATE_CONTROL = a_vehicle_profile["remoteClimateControl"]
                                    _LOGGER.debug(f"{self.vli}RemoteClimateControl support: {self._supports_REMOTE_CLIMATE_CONTROL}")

                                if not self._supports_REMOTE_CLIMATE_CONTROL and "remoteHeatingCooling" in a_vehicle_profile:
                                    self._supports_REMOTE_CLIMATE_CONTROL = a_vehicle_profile["remoteHeatingCooling"]
                                    _LOGGER.debug(f"{self.vli}RemoteClimateControl/remoteHeatingCooling support: {self._supports_REMOTE_CLIMATE_CONTROL}")


                            if "heatedSteeringWheel" in a_vehicle_profile:
                                self._supports_HEATED_STEERING_WHEEL = a_vehicle_profile["heatedSteeringWheel"]
                                _LOGGER.debug(f"{self.vli}HeatedSteeringWheel support: {self._supports_HEATED_STEERING_WHEEL}")

                            self._supports_HEATED_HEATED_SEAT_MODE = RCC_SEAT_MODE_NONE
                            if "driverHeatedSeat" in a_vehicle_profile:
                                # possible values: 'None', 'Heat Only', 'Heat with Vent'
                                heated_seat = a_vehicle_profile["driverHeatedSeat"].upper()
                                if heated_seat == "HEAT WITH VENT":
                                    self._supports_HEATED_HEATED_SEAT_MODE = RCC_SEAT_MODE_HEAT_AND_COOL
                                elif "HEAT" in heated_seat:
                                    self._supports_HEATED_HEATED_SEAT_MODE = RCC_SEAT_MODE_HEAT_ONLY
                            _LOGGER.debug(f"{self.vli}DriverHeatedSeat support mode: {self._supports_HEATED_HEATED_SEAT_MODE}")
                            break
                else:
                    _LOGGER.warning(f"{self.vli}No vehicleProfile in 'vehicles' found in coordinator data - no 'engineType' available! {self.data['vehicles']}")

                # check, if RemoteStart is supported
                if "vehicleCapabilities" in veh_data:
                    for capability_obj in veh_data["vehicleCapabilities"]:
                        if capability_obj["VIN"] == self._vin:
                            self._supports_ALARM = Tag.ALARM.get_state(self.data).upper() != "UNSUPPORTED"
                            self._supports_REMOTE_START = self._check_if_veh_capability_supported("remoteStart", capability_obj)
                            self._supports_GUARD_MODE = self._check_if_veh_capability_supported("guardMode", capability_obj)
                            self._supports_ZONE_LIGHTING = self._check_if_veh_capability_supported("zoneLighting", capability_obj) and self._number_of_lighting_zones > 0
                            self._supports_HAF = self._check_if_veh_capability_supported("remotePanicAlarm", capability_obj)
                            break
                else:
                    _LOGGER.warning(f"{self.vli}No vehicleCapabilities in 'vehicles' found in coordinator data - no 'support_remote_start' available! {self.data['vehicles']}")

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

    def _check_if_veh_capability_supported(self, a_capability: str, capabilities: dict) -> bool:
        """Check if a specific vehicle capability is supported."""
        is_supported = False
        if a_capability in capabilities and capabilities[a_capability] is not None:
            val = capabilities[a_capability]
            if (isinstance(val, bool) and val) or val.upper() == "DISPLAY":
                is_supported = True
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
        if self.bridge.require_reauth:
            self._available = False  # Mark as unavailable
            if not self._reauth_requested:
                self._reauth_requested = True
                _LOGGER.warning(f"{self.vli}_async_update_data: VIN {self._vin} requires re-authentication")
                self.hass.add_job(self._config_entry.async_start_reauth, self.hass)

            raise UpdateFailed(f"Error VIN: {self._vin} requires re-authentication")

        else:
            if self.bridge.ws_connected and self._force_classic_requests is False:
                try:
                    _LOGGER.debug(f"{self.vli}_async_update_data called (but websocket is active - no data will be requested!)")
                    return self.bridge._data_container

                except UpdateFailed as exception:
                    _LOGGER.warning(f"{self.vli}UpdateFailed: {type(exception).__name__} - {exception}")
                    raise UpdateFailed() from exception
                except BaseException as other:
                    _LOGGER.warning(f"{self.vli}UpdateFailed unexpected: {type(other).__name__} - {other}")
                    raise UpdateFailed() from other

            else:
                try:
                    async with async_timeout.timeout(60):
                        if self.bridge.status_updates_allowed:
                            data = await self.bridge.update_all()
                            if data is not None:
                                try:
                                    _LOGGER.debug(f"{self.vli}_async_update_data: total number of items: {len(data[ROOT_METRICS])} metrics, {len(data[ROOT_MESSAGES])} messages, {len(data[ROOT_VEHICLES]['vehicleProfile'])} vehicles for {self._vin}")
                                except BaseException:
                                    pass

                                # only for private debugging
                                # self.write_data_debug(data)

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
                        else:
                            _LOGGER.info(f"{self.vli}_async_update_data: Updates not allowed for {self._vin} - since '__request_and_poll_command' is running, returning old data")
                            data = self.data
                        return data

                except TimeoutError as ti_err:
                    # Mark as unavailable - but let the coordinator deal with the rest...
                    self._available = False
                    raise ti_err

                except BaseException as ex:
                    self._available = False  # Mark as unavailable
                    _LOGGER.warning(f"{self.vli}_async_update_data: Error communicating with FordPass for {self._vin} {type(ex).__name__} -> {str(ex)}")
                    raise UpdateFailed(f"Error communicating with FordPass for {self._vin} cause of {type(ex).__name__}") from ex

    # def write_data_debug(self, data):
    #     import time
    #     with open(f"data/fordpass_data_{time.time()}.json", "w", encoding="utf-8") as outfile:
    #         import json
    #         json.dump(data, outfile)


class FordPassEntity(CoordinatorEntity):
    """Defines a base FordPass entity."""
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name_addon = None

    def __init__(self, a_tag: Tag, coordinator: FordPassDataUpdateCoordinator, description: EntityDescription | None = None):
        """Initialize the entity."""
        super().__init__(coordinator, description)

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
        self.entity_id = f"{DOMAIN}.fordpass_{self.coordinator._vin.lower()}_{a_tag.key}"
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
    def should_poll(self) -> bool:
        return False

    @property
    def unique_id(self):
        """Return the unique ID of the entity."""
        return f"fordpass_uid_{self.coordinator._vin.lower()}_{self._tag.key}"

    @property
    def device_info(self):
        """Return device information about this device."""
        if self._tag is None:
            return None

        ## messages are login/user bound... so we create an own device for the user objects
        #if not self._tag in [Tag.MESSAGES, Tag.MESSAGES_DELETE_LAST, Tag.MESSAGES_DELETE_ALL]:
        model = "unknown"
        if "vehicles" in self.coordinator.data and self.coordinator.data["vehicles"] is not None:
            if "vehicleProfile" in self.coordinator.data["vehicles"] and self.coordinator.data["vehicles"]["vehicleProfile"] is not None:
                for vehicle in self.coordinator.data["vehicles"]["vehicleProfile"]:
                    if vehicle["VIN"] == self.coordinator._vin:
                        model = f"{vehicle['year']} {vehicle['model']}"

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
        if name is None and self.use_device_name:
            return device_name

        # we overwrite the default impl here and just return our 'name'
        # return f"{device_name} {name}" if device_name else name
        if device_entry.name_by_user is not None:
            return f"{device_entry.name_by_user} {name}" if device_name else name
        # elif self.coordinator.include_fordpass_prefix:
        #    return f"[fordpass] {name}"
        else:
            return name