"""The FordPass integration."""
import asyncio
import logging
from datetime import timedelta
from re import sub

import async_timeout
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    CONF_DISTANCE_UNIT,
    CONF_PRESSURE_UNIT,
    DEFAULT_DISTANCE_UNIT,
    DEFAULT_PRESSURE_UNIT,
    DEFAULT_REGION,
    DOMAIN,
    MANUFACTURER,
    REGION,
    VIN,
    UPDATE_INTERVAL,
    UPDATE_INTERVAL_DEFAULT,
    COORDINATOR
)
from .fordpass_new import Vehicle

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)

PLATFORMS = ["lock", "sensor", "switch", "device_tracker"]

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the FordPass component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up FordPass from a config entry."""
    user = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    vin = entry.data[VIN]
    if UPDATE_INTERVAL in entry.options:
        update_interval = entry.options[UPDATE_INTERVAL]
    else:
        update_interval = UPDATE_INTERVAL_DEFAULT
    _LOGGER.debug(update_interval)
    for ar_entry in entry.data:
        _LOGGER.debug(ar_entry)
    if REGION in entry.data.keys():
        _LOGGER.debug(entry.data[REGION])
        region = entry.data[REGION]
    else:
        _LOGGER.debug("CANT GET REGION")
        region = DEFAULT_REGION
    coordinator = FordPassDataUpdateCoordinator(hass, user, password, vin, region, update_interval, 1)

    await coordinator.async_refresh()  # Get initial data

    fordpass_options_listener = entry.add_update_listener(options_update_listener)

    if not entry.options:
        await async_update_options(hass, entry)

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady

    hass.data[DOMAIN][entry.entry_id] = {
        COORDINATOR: coordinator,
        "fordpass_options_listener": fordpass_options_listener
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def async_refresh_status_service(service_call):
        await hass.async_add_executor_job(
            refresh_status, hass, service_call, coordinator
        )

    async def async_clear_tokens_service(service_call):
        await hass.async_add_executor_job(clear_tokens, hass, service_call, coordinator)

    async def poll_api_service(service_call):
        await coordinator.async_request_refresh()

    async def handle_reload(service):
        """Handle reload service call."""
        _LOGGER.debug("Reloading Integration")

        current_entries = hass.config_entries.async_entries(DOMAIN)
        reload_tasks = [
            hass.config_entries.async_reload(entry.entry_id)
            for entry in current_entries
        ]

        await asyncio.gather(*reload_tasks)

    hass.services.async_register(
        DOMAIN,
        "refresh_status",
        async_refresh_status_service,
    )
    hass.services.async_register(
        DOMAIN,
        "clear_tokens",
        async_clear_tokens_service,
    )

    hass.services.async_register(
        DOMAIN,
        "reload",
        handle_reload
    )

    hass.services.async_register(
        DOMAIN,
        "poll_api",
        poll_api_service
    )

    return True


async def async_update_options(hass, config_entry):
    """Update options entries on change"""
    options = {
        CONF_PRESSURE_UNIT: config_entry.data.get(
            CONF_PRESSURE_UNIT, DEFAULT_PRESSURE_UNIT
        )
    }
    options[CONF_DISTANCE_UNIT] = config_entry.data.get(
        CONF_DISTANCE_UNIT, DEFAULT_DISTANCE_UNIT
    )
    hass.config_entries.async_update_entry(config_entry, options=options)


async def options_update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Options listener to refresh config entries on option change"""
    _LOGGER.debug("OPTIONS CHANGE")
    await hass.config_entries.async_reload(entry.entry_id)


def refresh_status(hass, service, coordinator):
    """Get latest vehicle status from vehicle, actively polls the car"""
    _LOGGER.debug("Running Service")
    vin = service.data.get("vin", "")
    status = coordinator.vehicle.request_update(vin)
    if status == 401:
        _LOGGER.debug("Invalid VIN")
    elif status == 200:
        _LOGGER.debug("Refresh Sent")


def clear_tokens(hass, service, coordinator):
    """Clear the token file in config directory, only use in emergency"""
    _LOGGER.debug("Clearing Tokens")
    coordinator.vehicle.clear_token()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        return True
    return False


class FordPassDataUpdateCoordinator(DataUpdateCoordinator):
    """DataUpdateCoordinator to handle fetching new data about the vehicle."""

    def __init__(self, hass, user, password, vin, region, update_interval, save_token=False):
        """Initialize the coordinator and set up the Vehicle object."""
        self._hass = hass
        self._vin = vin
        config_path = hass.config.path(f".storage/fordpass/{user}_access_token.txt")
        self.vehicle = Vehicle(user, password, vin, region, save_token, config_path)
        self._available = True

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )

    async def _async_update_data(self):
        """Fetch data from FordPass."""
        try:
            async with async_timeout.timeout(30):
                data = await self._hass.async_add_executor_job(
                    self.vehicle.status  # Fetch new status
                )

                # Temporarily removed due to Ford backend API changes
                # data["guardstatus"] = await self._hass.async_add_executor_job(
                #    self.vehicle.guardStatus  # Fetch new status
                # )

                data["messages"] = await self._hass.async_add_executor_job(
                    self.vehicle.messages
                )
                data["vehicles"] = await self._hass.async_add_executor_job(
                    self.vehicle.vehicles
                )
                _LOGGER.debug(data)
                # If data has now been fetched but was previously unavailable, log and reset
                if not self._available:
                    _LOGGER.info("Restored connection to FordPass for %s", self._vin)
                    self._available = True

                return data
        except Exception as ex:
            self._available = False  # Mark as unavailable
            _LOGGER.warning(str(ex))
            _LOGGER.warning("Error communicating with FordPass for %s", self._vin)
            raise UpdateFailed(
                f"Error communicating with FordPass for {self._vin}"
            ) from ex


class FordPassEntity(CoordinatorEntity):
    """Defines a base FordPass entity."""
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, internal_key: str, coordinator: FordPassDataUpdateCoordinator):
        """Initialize the entity."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.coordinator_context = object()
        self.data = coordinator.data.get("metrics", {})

        self.entity_id = f"{DOMAIN}.fordpass_{self.coordinator._vin.lower()}_{internal_key}"
        self._internal_key = internal_key
        self._name = internal_key

        # ok setting the internal translation key attr (so we can make use of the translation key in the entity)
        self._attr_translation_key = internal_key.lower()

    @property
    def device_id(self):
        return f"fordpass_did_{self.self.coordinator._vin.lower()}"

    @property
    def should_poll(self) -> bool:
        return False

    @property
    def unique_id(self):
        """Return the unique ID of the entity."""
        return f"fordpass_uid_{self.coordinator._vin.lower()}_{self._internal_key}"

    @property
    def device_info(self):
        """Return device information about this device."""
        if self._internal_key is None:
            return None

        model = "unknown"
        if self.coordinator.data["vehicles"] is not None:
            for vehicle in self.coordinator.data["vehicles"]["vehicleProfile"]:
                if vehicle["VIN"] == self.coordinator._vin:
                    model = f"{vehicle['year']} {vehicle['model']}"

        return {
            "identifiers": {(DOMAIN, self.coordinator._vin)},
            "name": f"VIN {self.coordinator._vin}",
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
        #elif self.coordinator.include_fordpass_prefix:
        #    return f"[fordpass] {name}"
        else:
            return name

    @staticmethod
    def camel_case(s):
        # Use regular expression substitution to replace underscores and hyphens with spaces,
        # then title case the string (capitalize the first letter of each word), and remove spaces
        s = sub(r"(_|-)+", " ", s).title().replace(" ", "")

        # Join the string, ensuring the first letter is lowercase
        return ''.join([s[0].lower(), s[1:]])