"""Config flow for FordPass integration."""
import hashlib
import logging
import random
import re
import string
from base64 import urlsafe_b64encode

import voluptuous as vol
from homeassistant import config_entries, core, exceptions
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import callback

from .const import (  # pylint:disable=unused-import
    CONF_DISTANCE_UNIT,
    CONF_PRESSURE_UNIT,
    DEFAULT_DISTANCE_UNIT,
    DEFAULT_PRESSURE_UNIT,
    DISTANCE_UNITS,
    DOMAIN,
    PRESSURE_UNITS,
    REGION,
    REGION_OPTIONS,
    DEFAULT_REGION,
    REGIONS,
    VIN,
    UPDATE_INTERVAL,
    UPDATE_INTERVAL_DEFAULT,
    DISTANCE_CONVERSION_DISABLED,
    DISTANCE_CONVERSION_DISABLED_DEFAULT
)
from .fordpass_new import Vehicle

_LOGGER = logging.getLogger(__name__)

VIN_SCHEME = vol.Schema(
    {
        vol.Required(VIN, default=""): str,
    }
)


@callback
def configured_vehicles(hass):
    """Return a list of configured vehicles"""
    return {
        entry.data[VIN]
        for entry in hass.config_entries.async_entries(DOMAIN)
    }


async def validate_token(hass: core.HomeAssistant, data):
    _LOGGER.debug(data)
    configPath = hass.config.path("custom_components/fordpass/" + data["username"] + "_fordpass_token.txt")
    _LOGGER.debug(configPath)
    vehicle = Vehicle(data["username"], "", "", data["region"], 1, configPath)
    results = await hass.async_add_executor_job(
        vehicle.generate_tokens,
        data["tokenstr"],
        data["code_verifier"]
    )

    if results:
        _LOGGER.debug("Getting Vehicles")
        vehicles = await(hass.async_add_executor_job(vehicle.vehicles))
        _LOGGER.debug(vehicles)
        return vehicles


async def validate_input(hass: core.HomeAssistant, data):
    """Validate the user input allows us to connect.

    Data has the keys from DATA_SCHEMA with values provided by the user.
    """
    _LOGGER.debug(data[REGION])
    configPath = hass.config.path("custom_components/fordpass/" + data[CONF_USERNAME] + "_fordpass_token.txt")
    vehicle = Vehicle(data[CONF_USERNAME], data[CONF_PASSWORD], "", data[REGION], 1, configPath)

    try:
        result = await hass.async_add_executor_job(vehicle.auth)
    except Exception as ex:
        raise InvalidAuth from ex
    try:
        if result:
            vehicles = await(hass.async_add_executor_job(vehicle.vehicles))
    except Exception:
        vehicles = None
    # except Exception as ex:
    #     raise InvalidAuth from ex

    # result3 = await hass.async_add_executor_job(vehicle.vehicles)
    # # Disabled due to API change
    # vinfound = False
    # for car in result3:
    #     if car["vin"] == data[VIN]:
    #         vinfound = True
    # if vinfound == False:
    #     _LOGGER.debug("Vin not found in account, Is your VIN valid?")
    if not result:
        _LOGGER.error("Failed to authenticate with fordpass")
        raise CannotConnect

    # Return info that you want to store in the config entry.
    return vehicles
    # return {"title": f"Vehicle ({data[VIN]})"}


async def validate_vin(hass: core.HomeAssistant, data):
    configPath = hass.config.path("custom_components/fordpass/" + data[CONF_USERNAME] + "_fordpass_token.txt")

    vehicle = Vehicle(data[CONF_USERNAME], data[CONF_PASSWORD], data[VIN], data[REGION], 1, configPath)
    test = await(hass.async_add_executor_job(vehicle.get_status))
    _LOGGER.debug("GOT SOMETHING BACK?")
    _LOGGER.debug(test)
    if test and test.status_code == 200:
        _LOGGER.debug("200 Code")
        return True
    if not test:
        raise InvalidVin
    return False


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for FordPass."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL
    region = DEFAULT_REGION
    username = None
    login_input = {}

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                self.region = user_input[REGION]
                self.username = user_input[CONF_USERNAME]

                return await self.async_step_token(None)
            except CannotConnect:
                print("EXCEPT")
                errors["base"] = "cannot_connect"
        else:
            user_input = {}
            user_input[REGION] = DEFAULT_REGION
            user_input[CONF_USERNAME] = ""

        return self.async_show_form(
            step_id="user", data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=""): str,
                    vol.Required(REGION, default=DEFAULT_REGION): vol.In(REGION_OPTIONS),
                }
            ), errors=errors
        )

    async def async_step_token(self, user_input=None):
        errors = {}

        if user_input is not None:
            try:
                token = user_input["tokenstr"]
                if self.check_token(token):
                    user_input["region"] = self.region
                    user_input["username"] = self.username
                    user_input["password"] = ""
                    user_input["code_verifier"] = self.login_input["code_verifier"]
                    _LOGGER.debug(user_input)
                    info = await validate_token(self.hass, user_input)
                    self.login_input = user_input
                    if info is None:
                        self.vehicles = None
                        _LOGGER.debug("NO VEHICLES FOUND")
                    else:
                        self.vehicles = info["userVehicles"]["vehicleDetails"]
                    if self.vehicles is None:
                        return await self.async_step_vin()
                    return await self.async_step_vehicle()

                else:
                    errors["base"] = "invalid_token"

            except CannotConnect:
                print("EXCEPT")
                errors["base"] = "cannot_connect"

        if self.region is not None:
            _LOGGER.debug(f"Region {self.region}")
            return self.async_show_form(
                step_id="token", data_schema=vol.Schema(
                    {
                        vol.Optional(CONF_URL, default=self.generate_url(self.region)): str,
                        vol.Required("tokenstr"): str,
                    }
                ), errors=errors
            )

    def check_token(self, token):
        if "fordapp://userauthorized/?code=" in token:
            return True
        return False

    def generate_url(self, region):
        _LOGGER.debug(REGIONS[region])
        code1 = ''.join(random.choice(string.ascii_lowercase) for i in range(43))
        code_verifier = self.generate_hash(code1)
        self.login_input["code_verifier"] = code1

        url = f"{REGIONS[region]['locale_url']}/4566605f-43a7-400a-946e-89cc9fdb0bd7/B2C_1A_SignInSignUp_{REGIONS[region]['locale']}/oauth2/v2.0/authorize?redirect_uri=fordapp://userauthorized&response_type=code&max_age=3600&code_challenge={code_verifier}&code_challenge_method=S256&scope=%2009852200-05fd-41f6-8c21-d36d3497dc64%20openid&client_id=09852200-05fd-41f6-8c21-d36d3497dc64&ui_locales={REGIONS[region]['locale']}&language_code={REGIONS[region]['locale']}&country_code={REGIONS[region]['locale_short']}&ford_application_id={REGIONS[region]['region']}"
        return url

    def base64_url_encode(self, data):
        """Encode string to base64"""
        return urlsafe_b64encode(data).rstrip(b'=')

    def generate_hash(self, code):
        """Generate hash for login"""
        hashengine = hashlib.sha256()
        hashengine.update(code.encode('utf-8'))
        return self.base64_url_encode(hashengine.digest()).decode('utf-8')

    def validNumber(self, phone_number):
        pattern = re.compile(r'^([+]\d{2})?\d{10}$', re.IGNORECASE)
        pattern2 = re.compile(r'^([+]\d{2})?\d{9}$', re.IGNORECASE)
        return pattern.match(phone_number) is not None or pattern2.match(phone_number) is not None

    async def async_step_vin(self, user_input=None):
        """Handle manual VIN entry"""
        errors = {}
        if user_input is not None:
            _LOGGER.debug(self.login_input)
            _LOGGER.debug(user_input)
            data = self.login_input
            data["vin"] = user_input["vin"]
            vehicle = None
            try:
                vehicle = await validate_vin(self.hass, data)
            except InvalidVin:
                errors["base"] = "invalid_vin"
            except Exception:
                errors["base"] = "unknown"

            if vehicle:
                return self.async_create_entry(title=f"Vehicle ({user_input[VIN]})", data=self.login_input)

            # return self.async_create_entry(title=f"Enter VIN", data=self.login_input)
        _LOGGER.debug(self.login_input)
        return self.async_show_form(step_id="vin", data_schema=VIN_SCHEME, errors=errors)

    async def async_step_vehicle(self, user_input=None):
        if user_input is not None:
            _LOGGER.debug("Checking Vehicle is accessible")
            self.login_input[VIN] = user_input["vin"]
            _LOGGER.debug(self.login_input)
            return self.async_create_entry(title=f"Vehicle ({user_input[VIN]})", data=self.login_input)

        _LOGGER.debug(self.vehicles)

        configured = configured_vehicles(self.hass)
        _LOGGER.debug(configured)
        avaliable_vehicles = {}
        for vehicle in self.vehicles:
            _LOGGER.debug(vehicle)
            if vehicle["VIN"] not in configured:
                if "nickName" in vehicle:
                    avaliable_vehicles[vehicle["VIN"]] = vehicle["nickName"] + f" ({vehicle['VIN']})"
                else:
                    avaliable_vehicles[vehicle["VIN"]] = f" ({vehicle['VIN']})"

        if not avaliable_vehicles:
            _LOGGER.debug("No Vehicles?")
            return self.async_abort(reason="no_vehicles")
        return self.async_show_form(
            step_id="vehicle",
            data_schema=vol.Schema(
                {vol.Required(VIN): vol.In(avaliable_vehicles)}
            ),
            errors={}
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlow(config_entry)


class OptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        options = {
            vol.Optional(
                CONF_PRESSURE_UNIT,
                default=self.config_entry.options.get(
                    CONF_PRESSURE_UNIT, DEFAULT_PRESSURE_UNIT
                ),
            ): vol.In(PRESSURE_UNITS),
            vol.Optional(
                CONF_DISTANCE_UNIT,
                default=self.config_entry.options.get(
                    CONF_DISTANCE_UNIT, DEFAULT_DISTANCE_UNIT
                ),
            ): vol.In(DISTANCE_UNITS),
            vol.Optional(
                DISTANCE_CONVERSION_DISABLED,
                default=self.config_entry.options.get(
                    DISTANCE_CONVERSION_DISABLED, DISTANCE_CONVERSION_DISABLED_DEFAULT
                ),
            ): bool,
            vol.Optional(
                UPDATE_INTERVAL,
                default=self.config_entry.options.get(
                    UPDATE_INTERVAL, UPDATE_INTERVAL_DEFAULT
                ),
            ): int,

        }

        return self.async_show_form(step_id="init", data_schema=vol.Schema(options))


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
