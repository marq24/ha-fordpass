"""The FordPass integration."""
import asyncio
import logging
from datetime import timedelta
from typing import Final

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
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator, UpdateFailed
from homeassistant.util.unit_system import UnitSystem

from custom_components.fordpass.const import (
    CONF_PRESSURE_UNIT,
    CONF_VIN,
    DEFAULT_PRESSURE_UNIT,
    DEFAULT_REGION,
    DOMAIN,
    MANUFACTURER,
    UPDATE_INTERVAL,
    UPDATE_INTERVAL_DEFAULT,
    COORDINATOR_KEY,
    Tag, EV_ONLY_TAGS, FUEL_OR_PEV_ONLY_TAGS, PRESSURE_UNITS,
    LEGACY_REGION_KEYS
)
from custom_components.fordpass.fordpass_bridge import ConnectedFordPassVehicle
from custom_components.fordpass.fordpass_handler import ROOT_METRICS, ROOT_MESSAGES, ROOT_VEHICLES, FordpassDataHandler

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)
PLATFORMS = ["button", "lock", "sensor", "switch", "device_tracker"]
WEBSOCKET_WATCHDOG_INTERVAL: Final = timedelta(seconds=64)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the FordPass component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Set up FordPass from a config entry."""
    user = config_entry.data[CONF_USERNAME]
    vin = config_entry.data[CONF_VIN]
    if UPDATE_INTERVAL in config_entry.options:
        update_interval = config_entry.options[UPDATE_INTERVAL]
    else:
        update_interval = UPDATE_INTERVAL_DEFAULT
    _LOGGER.debug(f"[@{vin}] Update interval: {update_interval}")

    for config_emtry_data in config_entry.data:
        _LOGGER.debug(f"[@{vin}] config_entry.data: {config_emtry_data}")

    if CONF_REGION in config_entry.data.keys():
        _LOGGER.debug(f"[@{vin}] Region: {config_entry.data[CONF_REGION]}")
        region_key = config_entry.data[CONF_REGION]
    else:
        _LOGGER.debug(f"[@{vin}] cant get region for key: {CONF_REGION} in {config_entry.data.keys()} using default: '{DEFAULT_REGION}'")
        region_key = DEFAULT_REGION

    # this should not be required... but to be as compatible as possible with existing installations
    # if there is a user out there who has initially set the region to "UK&Europe", we must patch the region key
    # to the new format!
    region_key = check_for_deprecated_region_keys(region_key)

    coordinator = FordPassDataUpdateCoordinator(hass, config_entry, user, vin, region_key, update_interval, True)
    await coordinator.bridge._rename_token_file_if_needed(user)
    await coordinator.async_refresh()  # Get initial data
    if not coordinator.last_update_success or coordinator.data is None:
        raise ConfigEntryNotReady
    else:
        await coordinator.read_config_on_startup(hass)

    # ws watchdog...
    if hass.state is CoreState.running:
        await coordinator.start_watchdog()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, coordinator.start_watchdog)

    fordpass_options_listener = config_entry.add_update_listener(options_update_listener)

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
        await hass.async_add_executor_job(service_refresh_status, hass, call, coordinator)
        await asyncio.sleep(15)
        await coordinator.async_refresh()

    async def async_clear_tokens_service(call: ServiceCall):
        await hass.async_add_executor_job(service_clear_tokens, hass, call, coordinator)
        await asyncio.sleep(5)
        await coordinator.async_request_refresh()

    async def poll_api_service(call: ServiceCall):
        await coordinator.async_request_refresh()

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

    return True


def check_for_deprecated_region_keys(region_key):
    if region_key in LEGACY_REGION_KEYS:
        _LOGGER.info(f"current configuration contains LEGACY region-key: {region_key} -> please create a new ha-config entry to avoid this message in the future!")
    return region_key


async def async_update_options(hass, config_entry):
    """Update options entries on change"""
    options = {
        CONF_PRESSURE_UNIT: config_entry.data.get(CONF_PRESSURE_UNIT, DEFAULT_PRESSURE_UNIT),
    }
    hass.config_entries.async_update_entry(config_entry, options=options)


async def options_update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Options listener to refresh config entries on option change"""
    _LOGGER.debug(f"OPTIONS CHANGE")
    await hass.config_entries.async_reload(entry.entry_id)


def service_refresh_status(hass, service, coordinator):
    """Get the latest vehicle status from vehicle, actively polls the car"""
    _LOGGER.debug(f"Running Service 'refresh_status'")
    vin = service.data.get("vin", None)
    status = coordinator.bridge.request_update(vin)
    if status == 401:
        _LOGGER.debug(f"[@{vin}] refresh_status: Invalid VIN?! (status 401)")
    elif status == 200:
        _LOGGER.debug(f"[@{vin}] refresh_status: Refresh sent")


def service_clear_tokens(hass, service, coordinator):
    """Clear the token file in config directory, only use in emergency"""
    _LOGGER.debug(f"Running Service 'clear_tokens'")
    coordinator.bridge.clear_token()


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
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

_session_cache = {}

@staticmethod
def get_cached_session(hass: HomeAssistant, user: str, region_key: str, vli:str) -> aiohttp.ClientSession:
    """Get a cached aiohttp session for the user & region."""
    global _session_cache
    a_key = f"{user}µ@µ{region_key}"
    if a_key not in _session_cache:
        _session_cache[a_key] = async_create_clientsession(hass)
    else:
        _LOGGER.debug(f"{vli}Using cached aiohttp.ClientSession (so we share cookies) for user: {user}, region: {region_key}")
    return _session_cache[a_key]

class FordPassDataUpdateCoordinator(DataUpdateCoordinator):
    """DataUpdateCoordinator to handle fetching new data about the vehicle."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry,
                 user, vin, region_key, update_interval, save_token=False):
        """Initialize the coordinator and set up the Vehicle object."""
        self._config_entry = config_entry
        self._vin = vin
        self.vli = f"[@{self._vin}] "
        self.bridge = ConnectedFordPassVehicle(get_cached_session(hass, user, region_key, self.vli), user, vin, region_key,
                                               coordinator=self, save_token=save_token)

        self._available = True
        self._reauth_requested = False
        self._engineType = None
        self._supports_GUARD_MODE = None
        self._supports_REMOTE_START = None

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
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=update_interval))

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
                _LOGGER.info(f"{self.vli}Watchdog: websocket connect task cancel failed: {type(ex)} - {ex}")
            self._a_task = None

    async def _async_watchdog_check(self, *_):
        """Reconnect the websocket if it fails."""
        if self.bridge.require_reauth:
            self._available = False  # Mark as unavailable
            if not self._reauth_requested:
                self._reauth_requested = True
                _LOGGER.warning(f"{self.vli}_async_watchdog_check: VIN {self._vin} requires re-authentication")
                self.hass.add_job(self._config_entry.async_start_reauth, self.hass)

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

        if a_tag == Tag.REMOTE_START_STATUS or a_tag == Tag.REMOTE_START:
            return self._supports_REMOTE_START is None or self._supports_REMOTE_START is False

        if a_tag == Tag.GUARD_MODE:
            return self._supports_GUARD_MODE is None or self._supports_GUARD_MODE is False

        return False

    async def clear_data(self):
        _LOGGER.debug(f"{self.vli}clear_data called...")
        self._check_for_ws_task_and_cancel_if_running()
        self.bridge.clear_data()
        self.data.clear()

    @property
    def supportPureEvOrPluginEv(self) -> bool:
        return self._engineType is not None and self._engineType in ["BEV", "HEV", "PHEV"]

    @property
    def supportFuel(self) -> bool:
        return self._engineType is not None and self._engineType not in ["BEV"]

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
                            self._engineType = a_vehicle_profile["engineType"]
                            _LOGGER.debug(f"{self.vli}EngineType is: {self._engineType}")
                            break
                else:
                    _LOGGER.warning(f"{self.vli}No vehicleProfile in 'vehicles' found in coordinator data - no 'engineType' available! {self.data["vehicles"]}")

                # check, if RemoteStart is supported
                if "vehicleCapabilities" in veh_data:
                    for capability_obj in veh_data["vehicleCapabilities"]:
                        if capability_obj["VIN"] == self._vin:
                            self._supports_REMOTE_START = self._check_if_veh_capability_supported("remoteStart", capability_obj)
                            self._supports_GUARD_MODE = self._check_if_veh_capability_supported("guardMode", capability_obj)
                            break
                else:
                    _LOGGER.warning(f"{self.vli}No vehicleCapabilities in 'vehicles' found in coordinator data - no 'support_remote_start' available! {self.data["vehicles"]}")

                # check, if GuardMode is supported
                self._supports_GUARD_MODE = FordpassDataHandler.is_guard_mode_supported(self.data)

            else:
                _LOGGER.warning(f"{self.vli}No vehicles data found in coordinator data - no engineType available! {self.data}")
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
                    _LOGGER.warning(f"{self.vli}UpdateFailed: {type(exception)} - {exception}")
                    raise UpdateFailed() from exception
                except BaseException as other:
                    _LOGGER.warning(f"{self.vli}UpdateFailed unexpected: {type(other)} - {other}")
                    raise UpdateFailed() from other

            else:
                try:
                    async with async_timeout.timeout(60):
                        if self.bridge.status_updates_allowed:
                            data = await self.bridge.update_all()
                            if data is not None:
                                try:
                                    _LOGGER.debug(f"{self.vli}_async_update_data: total number of items: {len(data[ROOT_METRICS])} metrics, {len(data[ROOT_MESSAGES])} messages, {len(data[ROOT_VEHICLES]["vehicleProfile"])} vehicles for {self._vin}")
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
                    _LOGGER.warning(f"{self.vli}_async_update_data: Error communicating with FordPass for {self._vin} {type(ex)} -> {str(ex)}")
                    raise UpdateFailed(f"Error communicating with FordPass for {self._vin} cause of {type(ex)}") from ex

    # def write_data_debug(self, data):
    #     import time
    #     with open(f"data/fordpass_data_{time.time()}.json", "w", encoding="utf-8") as outfile:
    #         import json
    #         json.dump(data, outfile)


class FordPassEntity(CoordinatorEntity):
    """Defines a base FordPass entity."""
    _attr_should_poll = False
    _attr_has_entity_name = True

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

        self.coordinator: FordPassDataUpdateCoordinator = coordinator
        self.entity_id = f"{DOMAIN}.fordpass_{self.coordinator._vin.lower()}_{a_tag.key}"
        self._tag = a_tag


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
            "manufacturer": MANUFACTURER,
        }

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