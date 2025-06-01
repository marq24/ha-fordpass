"""The FordPass integration."""
import asyncio
import logging
from datetime import timedelta

import async_timeout
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME, UnitOfPressure
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator, UpdateFailed
from homeassistant.util.unit_system import UnitSystem

from custom_components.fordpass.const import (
    CONF_PRESSURE_UNIT,
    DEFAULT_PRESSURE_UNIT,
    DEFAULT_REGION,
    DOMAIN,
    MANUFACTURER,
    REGION,
    VIN,
    UPDATE_INTERVAL,
    UPDATE_INTERVAL_DEFAULT,
    COORDINATOR, Tag, EV_ONLY_TAGS, FUEL_OR_PEV_ONLY_TAGS, PRESSURE_UNITS
)
from custom_components.fordpass.fordpass_bridge import Vehicle

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)

PLATFORMS = ["button", "lock", "sensor", "switch", "device_tracker"]

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the FordPass component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Set up FordPass from a config entry."""
    user = config_entry.data[CONF_USERNAME]
    vin = config_entry.data[VIN]
    if UPDATE_INTERVAL in config_entry.options:
        update_interval = config_entry.options[UPDATE_INTERVAL]
    else:
        update_interval = UPDATE_INTERVAL_DEFAULT
    _LOGGER.debug(f"Update interval: {update_interval}")

    for config_emtry_data in config_entry.data:
        _LOGGER.debug(f"config_entry.data: {config_emtry_data}")

    if REGION in config_entry.data.keys():
        _LOGGER.debug(f"Region: {config_entry.data[REGION]}")
        region = config_entry.data[REGION]
    else:
        _LOGGER.debug("CANT GET REGION")
        region = DEFAULT_REGION

    coordinator = FordPassDataUpdateCoordinator(hass, config_entry, user, vin, region, update_interval, True)
    await coordinator.async_refresh()  # Get initial data
    if not coordinator.last_update_success or coordinator.data is None:
        raise ConfigEntryNotReady
    else:
        await coordinator.read_config_on_startup(hass)

    fordpass_options_listener = config_entry.add_update_listener(options_update_listener)

    if not config_entry.options:
        await async_update_options(hass, config_entry)

    hass.data[DOMAIN][config_entry.entry_id] = {
        COORDINATOR: coordinator,
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
        _LOGGER.debug("Reloading Integration")

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


async def async_update_options(hass, config_entry):
    """Update options entries on change"""
    options = {
        CONF_PRESSURE_UNIT: config_entry.data.get(CONF_PRESSURE_UNIT, DEFAULT_PRESSURE_UNIT),
    }
    hass.config_entries.async_update_entry(config_entry, options=options)


async def options_update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Options listener to refresh config entries on option change"""
    _LOGGER.debug("OPTIONS CHANGE")
    await hass.config_entries.async_reload(entry.entry_id)


def service_refresh_status(hass, service, coordinator):
    """Get latest vehicle status from vehicle, actively polls the car"""
    _LOGGER.debug("Running Service 'refresh_status'")
    vin = service.data.get("vin", None)
    status = coordinator.vehicle.request_update(vin)
    if status == 401:
        _LOGGER.debug("refresh_status: Invalid VIN?! (status 401)")
    elif status == 200:
        _LOGGER.debug("refresh_status: Refresh sent")


def service_clear_tokens(hass, service, coordinator):
    """Clear the token file in config directory, only use in emergency"""
    _LOGGER.debug("Running Service 'clear_tokens'")
    coordinator.vehicle.clear_token()


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    if await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS):
        hass.data[DOMAIN].pop(config_entry.entry_id)
        return True

    return False


class FordPassDataUpdateCoordinator(DataUpdateCoordinator):
    """DataUpdateCoordinator to handle fetching new data about the vehicle."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry,
                 user, vin, region, update_interval, save_token=False):
        """Initialize the coordinator and set up the Vehicle object."""
        self._config_entry = config_entry
        self._vin = vin
        config_path = hass.config.path(f".storage/fordpass/{user}_access_token.txt")
        self.vehicle = Vehicle(user, "", vin, region, save_token, config_path)
        self._available = True
        self._cached_vehicles_data = {}
        self._reauth_requested = False
        self._engineType = None

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

        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=update_interval))

    def tag_not_supported_by_vehicle(self, a_tag: Tag) -> bool:
        if a_tag in FUEL_OR_PEV_ONLY_TAGS:
            return self.supportFuel is False
        if a_tag in EV_ONLY_TAGS:
            return self.supportPureEvOrPluginEv is False
        return False

    @property
    def supportPureEvOrPluginEv(self) -> bool:
        return self._engineType is not None and self._engineType in ["BEV", "PHEV"]

    @property
    def supportFuel(self) -> bool:
        return self._engineType is not None and self._engineType != "BEV"

    async def read_config_on_startup(self, hass: HomeAssistant):
        _LOGGER.debug("read_config_on_startup...")
        # we are reading here from the global coordinator data object!
        if self.data is not None:
            if "vehicles" in self.data:
                veh_data = self.data["vehicles"]
                if "vehicleProfile" in veh_data:
                    for vehicle in veh_data["vehicleProfile"]:
                        if vehicle["VIN"] == self._vin:
                            self._engineType = vehicle["engineType"]
                            _LOGGER.debug(f"EngineType is: {self._engineType}")
                            break
                else:
                    _LOGGER.warning(f"No vehicleProfile in 'vehicles' found in coordinator data - no engineType available! {self.data["vehicles"]}")
            else:
                _LOGGER.warning(f"No vehicles data found in coordinator data - no engineType available! {self.data}")
        else:
            _LOGGER.warning(f"DATA is NONE!!! - {self.data}")

    async def _async_update_data(self):
        """Fetch data from FordPass."""
        if self.vehicle.require_reauth:
            self._available = False  # Mark as unavailable
            if not self._reauth_requested:
                self._reauth_requested = True
                _LOGGER.warning(f"_async_update_data: VIN {self._vin} requires re-authentication")
                self.hass.add_job(self._config_entry.async_start_reauth, self.hass)

            raise UpdateFailed(f"Error VIN: {self._vin} requires re-authentication")
        else:
            try:
                async with async_timeout.timeout(60):
                    if self.vehicle.status_updates_allowed:
                        data = await self.hass.async_add_executor_job(self.vehicle.status)
                        if data is not None:
                            # Temporarily removed due to Ford backend API changes
                            # data["guardstatus"] = await self.hass.async_add_executor_job(self.vehicle.guardStatus)

                            data["messages"] = await self.hass.async_add_executor_job(self.vehicle.messages)

                            # only update vehicle data if not present yet
                            if len(self._cached_vehicles_data) == 0:
                                _LOGGER.debug("_async_update_data: request vehicle data...")
                                self._cached_vehicles_data = await self.hass.async_add_executor_job(self.vehicle.vehicles)

                            if len(self._cached_vehicles_data) > 0:
                                data["vehicles"] = self._cached_vehicles_data

                            if "metrics" in data and data["metrics"] is not None:
                                _LOGGER.debug(f"_async_update_data: total number of items: {len(data)} metrics: {len(data["metrics"])} messages: {len(data["messages"])}")
                            else:
                                _LOGGER.debug(f"_async_update_data: total number of items: {len(data)} messages: {len(data["messages"])}")

                            # only for private debugging
                            # self.write_data_debug(data)

                            # If data has now been fetched but was previously unavailable, log and reset
                            if not self._available:
                                _LOGGER.info(f"_async_update_data: Restored connection to FordPass for {self._vin}")
                                self._available = True
                        else:
                            _LOGGER.info(f"_async_update_data: 'data' was None for {self._vin} (returning OLD data object)")
                            data = self.data
                    else:
                        _LOGGER.info(f"_async_update_data: Updates not allowed for {self._vin} - since '__request_and_poll_command' is running, returning old data")
                        data = self.data
                    return data

            except TimeoutError as ti_err:
                # Mark as unavailable - but let the coordinator deal with the rest...
                self._available = False
                raise ti_err

            except BaseException as ex:
                self._available = False  # Mark as unavailable
                _LOGGER.warning(f"_async_update_data: Error communicating with FordPass for {self._vin} {type(ex)} -> {str(ex)}")
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
        if self.coordinator.data["vehicles"] is not None:
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