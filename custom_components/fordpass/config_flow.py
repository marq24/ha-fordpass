"""Config flow for FordPass integration."""
import asyncio
import hashlib
import logging
import random
import re
import string
from base64 import urlsafe_b64encode
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import aiohttp
import voluptuous as vol
from homeassistant import config_entries, exceptions
from homeassistant.config_entries import ConfigError
from homeassistant.const import CONF_URL, CONF_USERNAME, CONF_REGION
from homeassistant.core import callback, HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.storage import STORAGE_DIR

from custom_components.fordpass.const import (  # pylint:disable=unused-import
    CONF_PRESSURE_UNIT,
    CONF_VIN,
    CONF_LOG_TO_FILESYSTEM,
    DEFAULT_PRESSURE_UNIT,
    DOMAIN,
    PRESSURE_UNITS,
    REGION_OPTIONS,
    DEFAULT_REGION,
    REGIONS,
    UPDATE_INTERVAL,
    UPDATE_INTERVAL_DEFAULT
)
from custom_components.fordpass.fordpass_bridge import ConnectedFordPassVehicle

_LOGGER = logging.getLogger(__name__)

VIN_SCHEME = vol.Schema(
    {
        vol.Required(CONF_VIN, default=""): str,
    }
)

CONF_TOKEN_STR: Final = "tokenstr"
CONF_SETUP_TYPE: Final = "setup_type"
CONF_ACCOUNT: Final = "account"

NEW_ACCOUNT: Final = "new_account"
ADD_VEHICLE: Final = "add_vehicle"

class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidToken(exceptions.HomeAssistantError):
    """Error to indicate there is invalid token."""


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""


class InvalidVin(exceptions.HomeAssistantError):
    """Error to indicate the wrong vin"""


class InvalidMobile(exceptions.HomeAssistantError):
    """Error to no mobile specified for South African Account"""


class FordPassConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for FordPass."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL
    region_key = DEFAULT_REGION
    username = None
    code_verifier = None
    cached_login_input = {}
    _accounts = None
    _vehicles = None
    _vehicle_name = None
    _can_not_connect_reason = None
    _session: aiohttp.ClientSession | None = None


    @callback
    def configured_vehicles(self, hass: HomeAssistant) -> set[str]:
        """Return a list of configured vehicles"""
        return {
            entry.data[CONF_VIN]
            for entry in hass.config_entries.async_entries(DOMAIN)
        }

    @callback
    def configured_accounts(self, hass: HomeAssistant):
        """Return a dict of configured accounts and their entry data"""
        accounts = {}
        for entry in hass.config_entries.async_entries(DOMAIN):
            a_username = entry.data.get(CONF_USERNAME)
            a_region = entry.data.get(CONF_REGION)
            if a_username is not None and a_region is not None:
                a_key = f"{a_username}µ@µ{a_region}"
                if a_key not in accounts:
                    accounts[a_key] = []

                accounts[a_key].append({
                    "username": a_username,
                    "region": a_region,
                    "vehicle_id": entry.data.get(CONF_VIN),
                })
        return accounts

    async def validate_token(self, data, token:str, code_verifier:str):
        _LOGGER.debug(f"validate_token(): {data}")
        if self._session is None:
            self._session = async_create_clientsession(self.hass)

        bridge = ConnectedFordPassVehicle(self._session, data[CONF_USERNAME], "", data[CONF_REGION],
                                           coordinator=None,
                                           storage_path=Path(self.hass.config.config_dir).joinpath(STORAGE_DIR))
        results = await bridge.generate_tokens(token, code_verifier)

        if results:
            _LOGGER.debug(f"validate_token(): request Vehicles")
            vehicles = await bridge.req_vehicles()
            _LOGGER.debug(f"validate_token(): got Vehicles -> {vehicles}")
            return vehicles
        else:
            _LOGGER.debug(f"validate_token(): failed - {results}")
            self._can_not_connect_reason = bridge.login_fail_reason
            raise CannotConnect

    async def validate_token_only(self, data, token:str, code_verifier:str) -> bool:
        _LOGGER.debug(f"validate_token_only(): {data}")
        if self._session is None:
            self._session = async_create_clientsession(self.hass)

        bridge = ConnectedFordPassVehicle(self._session, data[CONF_USERNAME], "", data[CONF_REGION],
                                           coordinator=None,
                                           storage_path=Path(self.hass.config.config_dir).joinpath(STORAGE_DIR))
        results = await bridge.generate_tokens(token, code_verifier)

        if not results:
            _LOGGER.debug(f"validate_token_only(): failed - {results}")
            self._can_not_connect_reason = bridge.login_fail_reason
            raise CannotConnect
        else:
            return True

    async def get_vehicles_from_existing_account(self, hass: HomeAssistant, data):
        _LOGGER.debug(f"get_vehicles_from_existing_account(): {data}")
        if self._session is None:
            self._session = async_create_clientsession(self.hass)

        bridge = ConnectedFordPassVehicle(self._session, data[CONF_USERNAME],
                                           "", data[CONF_REGION],
                                           coordinator=None,
                                           storage_path=Path(hass.config.config_dir).joinpath(STORAGE_DIR))
        _LOGGER.debug(f"get_vehicles_from_existing_account(): request Vehicles")
        vehicles = await bridge.req_vehicles()
        _LOGGER.debug(f"get_vehicles_from_existing_account(): got Vehicles -> {vehicles}")
        if vehicles is not None:
            return vehicles
        else:
            self._can_not_connect_reason = bridge.login_fail_reason
            raise CannotConnect

    async def validate_vin(self, data):
        _LOGGER.debug(f"validate_vin(): {data}")
        if self._session is None:
            self._session = async_create_clientsession(self.hass)

        bridge = ConnectedFordPassVehicle(self._session, data[CONF_USERNAME], data[CONF_VIN], data[CONF_REGION],
                                           coordinator=None,
                                           storage_path=Path(self.hass.config.config_dir).joinpath(STORAGE_DIR))
        test = await bridge.get_status()
        _LOGGER.debug(f"GOT SOMETHING BACK? {test}")
        if test and test.status_code == 200:
            _LOGGER.debug("200 Code")
            return True
        if not test:
            raise InvalidVin
        return False


    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        # lookup if there are already configured accounts?!
        self._accounts = self.configured_accounts(self.hass)

        if user_input is not None:
            if user_input.get(CONF_SETUP_TYPE) == NEW_ACCOUNT:
                return await self.async_step_new_account()
            elif user_input.get(CONF_SETUP_TYPE) == ADD_VEHICLE:
                return await self.async_step_select_account()

        # Show different options based on existing accounts
        if len(self._accounts) > 0:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({
                    vol.Required(CONF_SETUP_TYPE):
                        selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=[ADD_VEHICLE, NEW_ACCOUNT],
                                mode=selector.SelectSelectorMode.LIST,
                                translation_key=CONF_SETUP_TYPE,
                            )
                        )
                }),
                errors=errors
            )
        else:
            # No existing accounts, go directly to new account setup
            return await self.async_step_new_account()


    async def async_step_select_account(self, user_input=None):
        """Handle adding a vehicle to an existing account."""
        errors = {}

        if user_input is not None:
            parts = user_input[CONF_ACCOUNT].split("µ@µ")
            self.username = parts[0]
            self.region_key = parts[1]
            self.cached_login_input = {
                CONF_USERNAME: self.username,
                CONF_REGION: self.region_key,
            }
            try:
                info = await self.get_vehicles_from_existing_account(self.hass, data=self.cached_login_input)
                return await self.extract_vehicle_info_and_proceed_with_next_step(info)

            except CannotConnect:
                if self._can_not_connect_reason is not None:
                    errors["base"] = f"cannot_connect - '{self._can_not_connect_reason}'"
                else:
                    errors["base"] = "cannot_connect - UNKNOWN REASON"
            except Exception as ex:
                _LOGGER.error(f"Error validating existing account: {ex}")
                errors["base"] = "unknown"

        # Create account selection options (when there are multiple accounts...)
        if len(self._accounts) > 1:
            account_options = {}
            for a_key, entries in self._accounts.items():
                configured_vehicles = len(entries)
                parts = a_key.split("µ@µ")
                account_options[a_key] = f"{parts[0]} [{parts[1].upper()}]"

            return self.async_show_form(
                step_id="select_account",
                data_schema=vol.Schema({
                    vol.Required(CONF_ACCOUNT): vol.In(account_options)
                }),
                errors=errors
            )
        else:
            # when there is only one account configured, we can directly jump into the vehicle selection
            # Get the first account key and split it to get username and region...
            parts = next(iter(self._accounts)).split("µ@µ")
            self.username = parts[0]
            self.region_key = parts[1]
            self.cached_login_input = {
                CONF_USERNAME: self.username,
                CONF_REGION: self.region_key,
            }
            info = await self.get_vehicles_from_existing_account(self.hass, data=self.cached_login_input)
            return await self.extract_vehicle_info_and_proceed_with_next_step(info)


    async def async_step_new_account(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                self.region_key = user_input[CONF_REGION]
                self.username = user_input[CONF_USERNAME]

                return await self.async_step_token(None)
            except CannotConnect as ex:
                _LOGGER.debug(f"async_step_user {type(ex).__name__} - {ex}")
                if self._can_not_connect_reason is not None:
                    errors["base"] = f"cannot_connect - '{self._can_not_connect_reason}'"
                else:
                    errors["base"] = "cannot_connect - UNKNOWN REASON"
        else:
            user_input = {}
            user_input[CONF_REGION] = DEFAULT_REGION
            user_input[CONF_USERNAME] = ""

        has_fs_write_access = await asyncio.get_running_loop().run_in_executor(None,
                                                                               ConnectedFordPassVehicle.check_general_fs_access,
                                                                               Path(self.hass.config.config_dir).joinpath(STORAGE_DIR))
        if not has_fs_write_access:
            return self.async_abort(reason="no_filesystem_access")
        else:
            return self.async_show_form(
                step_id="new_account",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_USERNAME, default=""): str,
                        vol.Required(CONF_REGION, default=DEFAULT_REGION):
                            selector.SelectSelector(
                                selector.SelectSelectorConfig(
                                    options=REGION_OPTIONS,
                                    mode=selector.SelectSelectorMode.DROPDOWN,
                                    translation_key=CONF_REGION,
                                )
                            )
                    }
                ), errors=errors
            )

    async def async_step_token(self, user_input=None):
        errors = {}

        if user_input is not None:
            try:
                token_fragment = user_input[CONF_TOKEN_STR]
                # we should not save our user-captured 'code' url...
                del user_input[CONF_TOKEN_STR]

                if self.check_token(token_fragment):
                    # we don't need our generated URL either...
                    del user_input[CONF_URL]

                    user_input[CONF_REGION] = self.region_key
                    user_input[CONF_USERNAME] = self.username
                    _LOGGER.debug(f"user_input {user_input}")

                    info = await self.validate_token(user_input, token_fragment, self.code_verifier)
                    self.cached_login_input = user_input

                    return await self.extract_vehicle_info_and_proceed_with_next_step(info)

                else:
                    errors["base"] = "invalid_token"

            except CannotConnect as ex:
                _LOGGER.debug(f"async_step_token {ex}")
                if self._can_not_connect_reason is not None:
                    errors["base"] = f"cannot_connect - '{self._can_not_connect_reason}'"
                else:
                    errors["base"] = "cannot_connect - UNKNOWN REASON"

        if self.region_key is not None:
            _LOGGER.debug(f"self.region_key {self.region_key}")
            return self.async_show_form(
                step_id="token", data_schema=vol.Schema(
                    {
                        vol.Optional(CONF_URL, default=self.generate_url(self.region_key)): str,
                        vol.Required(CONF_TOKEN_STR): str,
                    }
                ), errors=errors
            )
        else:
            _LOGGER.error("No region_key set - FATAL ERROR")
            raise ConfigError(f"No region_key set - FATAL ERROR")

    async def extract_vehicle_info_and_proceed_with_next_step(self, info):
        if info is not None and "userVehicles" in info and "vehicleDetails" in info["userVehicles"]:
            self._vehicles = info["userVehicles"]["vehicleDetails"]
            self._vehicle_name = {}
            if "vehicleProfile" in info:
                for a_vehicle in info["vehicleProfile"]:
                    if "VIN" in a_vehicle and "year" in a_vehicle and "model" in a_vehicle:
                        self._vehicle_name[a_vehicle["VIN"]] = f"{a_vehicle['year']} {a_vehicle['model']}"

            _LOGGER.debug(f"Extracted vehicle names:  {self._vehicle_name}")
            return await self.async_step_vehicle()
        else:
            _LOGGER.debug(f"NO VEHICLES FOUND in info {info}")
            self._vehicles = None
            return await self.async_step_vin()

    @staticmethod
    def check_token(token):
        if "fordapp://userauthorized/?code=" in token:
            return True
        return False

    def generate_url(self, region_key):
        if region_key not in REGIONS:
            _LOGGER.error(f"generate_url(): Invalid region_key: {region_key}")
            region_key = DEFAULT_REGION
        _LOGGER.debug(f"selected REGIONS object: {REGIONS[region_key]}")
        self.code_verifier = ''.join(random.choice(string.ascii_lowercase) for i in range(43))
        hashed_code_verifier = self.generate_hash(self.code_verifier)
        url = f"{REGIONS[region_key]['locale_url']}/4566605f-43a7-400a-946e-89cc9fdb0bd7/B2C_1A_SignInSignUp_{REGIONS[region_key]['locale']}/oauth2/v2.0/authorize?redirect_uri=fordapp://userauthorized&response_type=code&max_age=3600&code_challenge={hashed_code_verifier}&code_challenge_method=S256&scope=%2009852200-05fd-41f6-8c21-d36d3497dc64%20openid&client_id=09852200-05fd-41f6-8c21-d36d3497dc64&ui_locales={REGIONS[region_key]['locale']}&language_code={REGIONS[region_key]['locale']}&ford_application_id={REGIONS[region_key]['app_id']}&country_code={REGIONS[region_key]['countrycode']}"
        return url

    @staticmethod
    def base64_url_encode(data):
        """Encode string to base64"""
        return urlsafe_b64encode(data).rstrip(b'=')

    def generate_hash(self, code):
        """Generate hash for login"""
        hashengine = hashlib.sha256()
        hashengine.update(code.encode('utf-8'))
        return self.base64_url_encode(hashengine.digest()).decode('utf-8')

    @staticmethod
    def valid_number(phone_number):
        pattern = re.compile(r'^([+]\d{2})?\d{10}$', re.IGNORECASE)
        pattern2 = re.compile(r'^([+]\d{2})?\d{9}$', re.IGNORECASE)
        return pattern.match(phone_number) is not None or pattern2.match(phone_number) is not None


    async def async_step_vin(self, user_input=None):
        """Handle manual VIN entry"""
        errors = {}
        if user_input is not None:
            _LOGGER.debug(f"cached_login_input: {self.cached_login_input} vin_input: {user_input}")

            # add the vin to the cached_login_input (so we store this in the config entry)
            self.cached_login_input["vin"] = user_input["vin"]
            vehicle = None
            try:
                vehicle = await self.validate_vin(self.cached_login_input)
            except InvalidVin:
                errors["base"] = "invalid_vin"
            except Exception:
                errors["base"] = "unknown"

            if vehicle:
                # create the config entry without the vehicle type/name...
                return self.async_create_entry(title=f"VIN: {user_input[CONF_VIN]}", data=self.cached_login_input)

        _LOGGER.debug(f"{self.cached_login_input}")
        return self.async_show_form(step_id="vin", data_schema=VIN_SCHEME, errors=errors)


    async def async_step_vehicle(self, user_input=None):
        if user_input is not None:
            _LOGGER.debug("Checking Vehicle is accessible")
            self.cached_login_input[CONF_VIN] = user_input[CONF_VIN]
            _LOGGER.debug(f"{self.cached_login_input}")

            if user_input[CONF_VIN] in self._vehicle_name:
                a_title = f"{self._vehicle_name[user_input[CONF_VIN]]} [VIN: {user_input[CONF_VIN]}]"
            else:
                a_title = f"VIN: {user_input[CONF_VIN]}"

            return self.async_create_entry(title=a_title, data=self.cached_login_input)

        _LOGGER.debug(f"async_step_vehicle with vehicles: {self._vehicles}")

        configured = self.configured_vehicles(self.hass)
        _LOGGER.debug(f"configured: {configured}")
        available_vehicles = {}
        for a_vehicle in self._vehicles:
            _LOGGER.debug(f"a vehicle: {a_vehicle}")
            a_veh_vin = a_vehicle["VIN"]
            if a_veh_vin not in configured:
                if a_veh_vin in self._vehicle_name:
                    available_vehicles[a_veh_vin] = f"{self._vehicle_name[a_veh_vin]} - {a_veh_vin}"
                elif "nickName" in a_vehicle:
                    self._vehicle_name[a_veh_vin] = a_vehicle["nickName"]
                    available_vehicles[a_veh_vin] = f"{a_vehicle['nickName']} - {a_veh_vin}"
                else:
                    available_vehicles[a_veh_vin] = f"'({a_veh_vin})"

        if not available_vehicles:
            _LOGGER.debug("No Vehicles?")
            return self.async_abort(reason="no_vehicles")
        return self.async_show_form(
            step_id="vehicle",
            data_schema=vol.Schema(
                {vol.Required(CONF_VIN): vol.In(available_vehicles)}
            ),
            errors={}
        )


    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> FlowResult:
        """Handle re-authentication"""
        self.entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_token()


    async def async_step_reauth_token(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Dialog that informs the user that reauth is required."""

        errors: dict[str, str] = {}
        assert self.entry is not None

        if user_input is not None:
            try:
                token_fragment = user_input[CONF_TOKEN_STR]
                # we should not save our user-captured 'code' url...
                del user_input[CONF_TOKEN_STR]

                if self.check_token(token_fragment):
                    # we don't need our generated URL either...
                    del user_input[CONF_URL]

                    # ok we have already the username and region, this must be stored
                    # in the config entry, so we can get it from there...
                    user_input[CONF_REGION] = self.entry.data[CONF_REGION]
                    user_input[CONF_USERNAME] = self.entry.data[CONF_USERNAME]
                    _LOGGER.debug(f"async_step_reauth_token: user_input -> {user_input}")

                    info = await self.validate_token_only(user_input, token_fragment, self.code_verifier)
                    if info:
                        # do we want to check, if the VIN is still accessible?!
                        # for now we just will reload the config entry...
                        await self.hass.config_entries.async_reload(self.entry.entry_id)
                        return self.async_abort(reason="reauth_successful")
                    else:
                        # what we need to do, if user did not re-authenticate successfully?
                        _LOGGER.warning(f"Re-Authorization failed - fordpass integration can't provide data for VIN: {self.entry.data[CONF_VIN]}")
                        return self.async_abort(reason="reauth_unsuccessful")
                        pass
                else:
                    errors["base"] = "invalid_token"

            except CannotConnect as ex:
                _LOGGER.debug(f"async_step_reauth_token {ex}")
                if self._can_not_connect_reason is not None:
                    errors["base"] = f"cannot_connect - '{self._can_not_connect_reason}'"
                else:
                    errors["base"] = "cannot_connect - UNKNOWN REASON"



            # try:
            #     info = await self._async_get_info(host)
            # except (DeviceConnectionError, InvalidAuthError, FirmwareUnsupported):
            #     return self.async_abort(reason="reauth_unsuccessful")
            #
            # if self.entry.data.get("gen", 1) != 1:
            #     user_input[CONF_USERNAME] = "admin"
            # try:
            #     await validate_input(self.hass, host, info, user_input)
            # except (DeviceConnectionError, InvalidAuthError, FirmwareUnsupported):
            #     return self.async_abort(reason="reauth_unsuccessful")
            # else:
            #     self.hass.config_entries.async_update_entry(
            #         self.entry, data={**self.entry.data, **user_input}
            #     )
            #     await self.hass.config_entries.async_reload(self.entry.entry_id)
            #     return self.async_abort(reason="reauth_successful")

        # then we generate again the fordpass-login-url and show it to the
        # user...
        return self.async_show_form(
            step_id="reauth_token", data_schema=vol.Schema(
                {
                    vol.Optional(CONF_URL, default=self.generate_url(self.entry.data[CONF_REGION])): str,
                    vol.Required(CONF_TOKEN_STR): str,
                }
            ), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options' flow for this handler."""
        return FordPassOptionsFlowHandler(config_entry)


class FordPassOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry):
        """Initialize options flow."""
        if len(dict(config_entry.options)) == 0:
            self._options = dict(config_entry.data)
        else:
            self._options = dict(config_entry.options)

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = {
            vol.Optional(CONF_PRESSURE_UNIT,
                         default=self._options.get(CONF_PRESSURE_UNIT, DEFAULT_PRESSURE_UNIT),): vol.In(PRESSURE_UNITS),
            vol.Optional(CONF_LOG_TO_FILESYSTEM,
                         default=self._options.get(CONF_LOG_TO_FILESYSTEM, False),): bool,
            vol.Optional(UPDATE_INTERVAL,
                         default=self._options.get(UPDATE_INTERVAL, UPDATE_INTERVAL_DEFAULT),): int,
        }
        return self.async_show_form(step_id="init", data_schema=vol.Schema(options))