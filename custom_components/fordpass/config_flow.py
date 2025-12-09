"""Config flow for FordPass integration."""
import asyncio
import hashlib
import logging
import re
from base64 import urlsafe_b64encode
from collections.abc import Mapping
from pathlib import Path
from secrets import token_urlsafe
from typing import Any, Final

import aiohttp
import voluptuous as vol
from homeassistant import config_entries, exceptions
from homeassistant.config_entries import ConfigError, ConfigFlowResult, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_URL, CONF_USERNAME, CONF_REGION
from homeassistant.core import callback, HomeAssistant
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.storage import STORAGE_DIR

from custom_components.fordpass.const import (  # pylint:disable=unused-import
    DOMAIN,
    OAUTH_ID,
    CLIENT_ID,
    REGIONS,
    REGION_OPTIONS_FORD,
    DEFAULT_REGION_FORD,
    REGION_OPTIONS_LINCOLN,
    DEFAULT_REGION_LINCOLN,

    CONFIG_VERSION,
    CONFIG_MINOR_VERSION,
    CONF_IS_SUPPORTED,
    CONF_BRAND,
    CONF_VIN,
    CONF_PRESSURE_UNIT,
    CONF_LOG_TO_FILESYSTEM,
    CONF_FORCE_REMOTE_CLIMATE_CONTROL,
    PRESSURE_UNITS,
    DEFAULT_PRESSURE_UNIT,
    BRAND_OPTIONS,

    UPDATE_INTERVAL,
    UPDATE_INTERVAL_DEFAULT,
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


class FordPassConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for FordPass."""
    VERSION = CONFIG_VERSION
    MINOR_VERSION = CONFIG_MINOR_VERSION
    region_key = DEFAULT_REGION_FORD
    username = None
    code_verifier = None
    cached_login_input = {}
    _accounts = None
    _vehicles = None
    _vehicle_name = None
    _can_not_connect_reason = None
    _session: aiohttp.ClientSession | None = None

    # @staticmethod
    # def base64_url_encode(data):
    #     """Encode string to base64"""
    #     return urlsafe_b64encode(data).rstrip(b'=')
    #
    # def generate_hash(self, code):
    #     """Generate hash for login"""
    #     hashengine = hashlib.sha256()
    #     hashengine.update(code.encode('ascii'))
    #     return self.base64_url_encode(hashengine.digest()).decode('utf-8')

    @staticmethod
    def generate_code_challenge():
        # Create a code verifier with a length of 128 characters
        code_verifier = token_urlsafe(96)

        hashed_verifier = hashlib.sha256(code_verifier.encode("utf-8"))
        code_challenge = urlsafe_b64encode(hashed_verifier.digest())
        code_challenge_without_padding = code_challenge.rstrip(b"=")
        return {
            "code_verifier": code_verifier,
            "code_challenge_method": "S256",
            "code_challenge": code_challenge_without_padding,
        }

    @callback
    def configured_vehicles(self, hass: HomeAssistant) -> set[str]:
        """Return a list of configured vehicles"""
        # return {
        #     entry.data[CONF_VIN]
        #     for entry in hass.config_entries.async_entries(DOMAIN)
        # }
        vehicles = []
        for entry in hass.config_entries.async_entries(DOMAIN):
            if CONF_IS_SUPPORTED in entry.data:
                a_vin = entry.data[CONF_VIN]
                a_region = entry.data.get(CONF_REGION)
                if a_vin is not None and a_region is not None:
                    if a_region in REGIONS:
                        if a_vin not in vehicles:
                            vehicles.append(a_vin)
                    else:
                        _LOGGER.warning(f"configured_vehicles(): UNKNOWN REGION! vin:'{a_vin}' region:'{a_region}' from: {entry}")
            else:
                if entry.data.get(CONF_REGION) in REGIONS:
                    _LOGGER.info(f"configured_vehicles(): LEGACY REGION configuration entry {entry} found")
                else:
                    _LOGGER.warning(f"configured_vehicles(): INCOMPATIBLE CONFIG ENTRY FOUND: {entry}")
        return vehicles

    @callback
    def configured_accounts(self, hass: HomeAssistant):
        """Return a dict of configured accounts and their entry data"""
        accounts = {}
        for entry in hass.config_entries.async_entries(DOMAIN):
            if CONF_IS_SUPPORTED in entry.data:
                a_username = entry.data.get(CONF_USERNAME)
                a_region = entry.data.get(CONF_REGION)
                if a_username is not None and a_region is not None:
                    if a_region in REGIONS:
                        a_key = f"{a_username}µ@µ{a_region}"
                        if a_key not in accounts:
                            accounts[a_key] = []

                        accounts[a_key].append({
                            "username": a_username,
                            "region": a_region,
                            "vehicle_id": entry.data.get(CONF_VIN),
                        })
                    else:
                        _LOGGER.warning(f"configured_accounts(): UNKNOWN REGION! user:'{a_username}' region:'{a_region}' from: {entry}")
            else:
                if entry.data.get(CONF_REGION) in REGIONS:
                    _LOGGER.info(f"configured_accounts(): LEGACY REGION configuration entry {entry} found")
                else:
                    _LOGGER.warning(f"configured_accounts(): INCOMPATIBLE CONFIG ENTRY FOUND: {entry}")
        return accounts

    async def validate_token(self, data, token:str, code_verifier:str):
        _LOGGER.debug(f"validate_token(): {data}")
        if self._session is None:
            self._session = async_create_clientsession(self.hass)

        bridge = ConnectedFordPassVehicle(self._session, data[CONF_USERNAME], "", data[CONF_REGION],
                                           coordinator=None,
                                           storage_path=Path(self.hass.config.config_dir).joinpath(STORAGE_DIR))

        results = await bridge.generate_tokens(token, code_verifier, data[CONF_REGION])

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

        results = await bridge.generate_tokens(token, code_verifier, data[CONF_REGION])

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

        test = await bridge.req_status()
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
                return await self.async_step_brand()
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
            return await self.async_step_brand()


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


    async def async_step_brand(self, user_input=None):
        errors = {}
        if user_input is not None:
            if user_input[CONF_BRAND] == "ford":
                return await self.async_step_new_account_ford()
            else:
                return await self.async_step_new_account_lincoln()

        else:
            user_input = {}
            user_input[CONF_BRAND] = "ford"

        has_fs_write_access = await asyncio.get_running_loop().run_in_executor(None,
                                                                               ConnectedFordPassVehicle.check_general_fs_access,
                                                                               Path(self.hass.config.config_dir).joinpath(STORAGE_DIR))
        if not has_fs_write_access:
            return self.async_abort(reason="no_filesystem_access")
        else:
            return self.async_show_form(
                step_id="brand",
                data_schema=vol.Schema({
                    vol.Required(CONF_BRAND, default="ford"):
                        selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=BRAND_OPTIONS,
                                mode=selector.SelectSelectorMode.LIST,
                                translation_key=CONF_BRAND,
                            )
                        )
                }), errors=errors
            )


    async def async_step_new_account_ford(self, user_input=None):
        account_data = {"default": DEFAULT_REGION_FORD,
                        "options": REGION_OPTIONS_FORD,
                        "step_id": "new_account_ford"}
        errors = {}
        if user_input is not None:
            try:
                self.region_key = user_input[CONF_REGION]
                self.username = user_input[CONF_USERNAME]
                return await self.async_step_token(None)

            except CannotConnect as ex:
                _LOGGER.debug(f"async_step_new_account_ford {type(ex).__name__} - {ex}")
                if self._can_not_connect_reason is not None:
                    errors["base"] = f"cannot_connect - '{self._can_not_connect_reason}'"
                else:
                    errors["base"] = "cannot_connect - UNKNOWN REASON"
        else:
            user_input = {}
            user_input[CONF_REGION] = account_data["default"]
            user_input[CONF_USERNAME] = ""

        return self.async_show_form(
            step_id=account_data["step_id"],
            data_schema=vol.Schema({
                vol.Required(CONF_USERNAME, default=""): str,
                vol.Required(CONF_REGION, default=account_data["default"]):
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=account_data["options"],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key=CONF_REGION,
                        )
                    )
            }), errors=errors
        )


    async def async_step_new_account_lincoln(self, user_input=None):
        account_data = {"default": DEFAULT_REGION_LINCOLN,
                        "options": REGION_OPTIONS_LINCOLN,
                        "step_id": "new_account_lincoln"}
        errors = {}
        if user_input is not None:
            try:
                self.region_key = user_input[CONF_REGION]
                self.username = user_input[CONF_USERNAME]
                return await self.async_step_token(None)

            except CannotConnect as ex:
                _LOGGER.debug(f"async_step_new_account_lincoln {type(ex).__name__} - {ex}")
                if self._can_not_connect_reason is not None:
                    errors["base"] = f"cannot_connect - '{self._can_not_connect_reason}'"
                else:
                    errors["base"] = "cannot_connect - UNKNOWN REASON"
        else:
            user_input = {}
            user_input[CONF_REGION] = account_data["default"]
            user_input[CONF_USERNAME] = ""

        return self.async_show_form(
            step_id=account_data["step_id"],
            data_schema=vol.Schema({
                vol.Required(CONF_USERNAME, default=""): str,
                vol.Required(CONF_REGION, default=account_data["default"]):
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=account_data["options"],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key=CONF_REGION,
                        )
                    )
            }), errors=errors
        )


    async def async_step_token(self, user_input=None):
        errors = {}

        if user_input is not None:
            try:
                token_fragment = user_input[CONF_TOKEN_STR]
                # we should not save our user-captured 'code' url...
                del user_input[CONF_TOKEN_STR]

                if self.check_token(token_fragment, self.region_key):
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
    def check_token(token, region_key):
        _LOGGER.debug(f"check_token(): selected REGIONS object: {REGIONS[region_key]}")

        redirect_schema = "fordapp"
        if "redirect_schema" in REGIONS[region_key]:
            redirect_schema = REGIONS[region_key]["redirect_schema"]

        if f"{redirect_schema}://userauthorized/?code=" in token:
            return True
        return False

    def generate_url(self, region_key):
        if region_key not in REGIONS:
            _LOGGER.error(f"generate_url(): Invalid region_key: {region_key}")
            region_key = DEFAULT_REGION_FORD
        _LOGGER.debug(f"generate_url(): selected REGIONS object: {REGIONS[region_key]}")

        cc_object = self.generate_code_challenge()
        code_challenge = cc_object["code_challenge"].decode("utf-8")
        code_challenge_method = cc_object["code_challenge_method"]
        self.code_verifier = cc_object["code_verifier"]

        # LINCOLN
        # https://login.lincoln.com/4566605f-43a7-400a-946e-89cc9fdb0bd7/B2C_1A_SignInSignUp_Lincoln_en-US/oauth2/v2.0/authorize?redirect_uri=lincolnapp%3A%2F%2Fuserauthorized&response_type=code&scope=09852200-05fd-41f6-8c21-d36d3497dc64%20openid&max_age=3600&login_hint=eyJyZWFsbSI6ICJjbG91ZElkZW50aXR5UmVhbG0ifQ%3D%3D&code_challenge=K2WtKFhDWmbkkx__9U9b4LhI1z_QvEGb6VvZ1RGX45I&code_challenge_method=S256&client_id=09852200-05fd-41f6-8c21-d36d3497dc64&language_code=en-US&ford_application_id=45133B88-0671-4AAF-B8D1-99E684ED4E45&country_code=USA

        sign_up = "B2C_1A_SignInSignUp_"
        if "sign_up_addon" in REGIONS[region_key]:
            sign_up = f"{sign_up}{REGIONS[region_key]['sign_up_addon']}"

        redirect_schema = "fordapp"
        if "redirect_schema" in REGIONS[region_key]:
            redirect_schema = REGIONS[region_key]["redirect_schema"]

        url = f"{REGIONS[region_key]['login_url']}/{OAUTH_ID}/{sign_up}{REGIONS[region_key]['locale']}/oauth2/v2.0/authorize?redirect_uri={redirect_schema}://userauthorized&response_type=code&max_age=3600&code_challenge={code_challenge}&code_challenge_method={code_challenge_method}&scope=%20{CLIENT_ID}%20openid&client_id={CLIENT_ID}&ui_locales={REGIONS[region_key]['locale']}&language_code={REGIONS[region_key]['locale']}&ford_application_id={REGIONS[region_key]['app_id']}&country_code={REGIONS[region_key]['countrycode']}"
        return url

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
            self.cached_login_input[CONF_VIN] = user_input[CONF_VIN]
            vehicle = None
            try:
                vehicle = await self.validate_vin(self.cached_login_input)
            except InvalidVin:
                errors["base"] = "invalid_vin"
            except Exception:
                errors["base"] = "unknown"

            if vehicle:
                self.cached_login_input[CONF_IS_SUPPORTED] = True
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

            self.cached_login_input[CONF_IS_SUPPORTED] = True
            return self.async_create_entry(title=a_title, data=self.cached_login_input)

        _LOGGER.debug(f"async_step_vehicle(): with vehicles: {self._vehicles}")

        already_configured_vins = self.configured_vehicles(self.hass)
        _LOGGER.debug(f"async_step_vehicle(): configured VINs: {already_configured_vins}")

        available_vehicles = {}
        for a_vehicle in self._vehicles:
            _LOGGER.debug(f"async_step_vehicle(): a vehicle from backend response: {a_vehicle}")
            a_veh_vin = a_vehicle["VIN"]
            if a_veh_vin not in already_configured_vins:
                if a_veh_vin in self._vehicle_name:
                    available_vehicles[a_veh_vin] = f"{self._vehicle_name[a_veh_vin]} - {a_veh_vin}"
                elif "nickName" in a_vehicle:
                    self._vehicle_name[a_veh_vin] = a_vehicle["nickName"]
                    available_vehicles[a_veh_vin] = f"{a_vehicle['nickName']} - {a_veh_vin}"
                else:
                    available_vehicles[a_veh_vin] = f"'({a_veh_vin})"

        if not available_vehicles:
            _LOGGER.debug("async_step_vehicle(): No Vehicles (or all already configured)?")
            return self.async_abort(reason="no_vehicles")

        return self.async_show_form(
            step_id="vehicle",
            data_schema=vol.Schema(
                {vol.Required(CONF_VIN): vol.In(available_vehicles)}
            ),
            errors={}
        )


    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Handle flow upon an API authentication error."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""

        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        assert reauth_entry is not None

        if user_input is not None:
            try:
                token_fragment = user_input[CONF_TOKEN_STR]
                # we should not save our user-captured 'code' url...
                del user_input[CONF_TOKEN_STR]

                if self.check_token(token_fragment, reauth_entry.data[CONF_REGION]):
                    # we don't need our generated URL either...
                    del user_input[CONF_URL]

                    # ok we have already the username and region, this must be stored
                    # in the config entry, so we can get it from there...
                    user_input[CONF_REGION] = reauth_entry.data[CONF_REGION]
                    user_input[CONF_USERNAME] = reauth_entry.data[CONF_USERNAME]
                    _LOGGER.debug(f"async_step_reauth_token: user_input -> {user_input}")

                    info = await self.validate_token_only(user_input, token_fragment, self.code_verifier)
                    if info:
                        # do we want to check, if the VIN is still accessible?!
                        # for now, we just will reload the config entry...
                        await self.hass.config_entries.async_reload(reauth_entry.entry_id)
                        return self.async_abort(reason="reauth_successful")
                    else:
                        # what we need to do, if user did not re-authenticate successfully?
                        _LOGGER.warning(f"Re-Authorization failed - fordpass integration can't provide data for VIN: {reauth_entry.data[CONF_VIN]}")
                        return self.async_abort(reason="reauth_unsuccessful")
                else:
                    errors["base"] = "invalid_token"

            except CannotConnect as ex:
                _LOGGER.debug(f"async_step_reauth_token {ex}")
                if self._can_not_connect_reason is not None:
                    errors["base"] = f"cannot_connect - '{self._can_not_connect_reason}'"
                else:
                    errors["base"] = "cannot_connect - UNKNOWN REASON"

        # then we generate again the fordpass-login-url and show it to the
        # user...
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({
                vol.Optional(CONF_URL, default=self.generate_url(reauth_entry.data[CONF_REGION])): str,
                vol.Required(CONF_TOKEN_STR): str,
            }),
            errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options' flow for this handler."""
        return FordPassOptionsFlowHandler(config_entry)


class FordPassOptionsFlowHandler(OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry):
        """Initialize options flow."""
        if len(dict(config_entry.options)) == 0:
            self._options = dict(config_entry.data)
        else:
            self._options = dict(config_entry.options)

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = {vol.Optional(CONF_PRESSURE_UNIT, default=self._options.get(CONF_PRESSURE_UNIT, DEFAULT_PRESSURE_UNIT),): vol.In(PRESSURE_UNITS),
                   vol.Optional(CONF_FORCE_REMOTE_CLIMATE_CONTROL, default=self._options.get(CONF_FORCE_REMOTE_CLIMATE_CONTROL, False),): bool,
                   vol.Optional(CONF_LOG_TO_FILESYSTEM, default=self._options.get(CONF_LOG_TO_FILESYSTEM, False),): bool,
                   vol.Optional(UPDATE_INTERVAL, default=self._options.get(UPDATE_INTERVAL, UPDATE_INTERVAL_DEFAULT),): int}
        return self.async_show_form(step_id="init", data_schema=vol.Schema(options))