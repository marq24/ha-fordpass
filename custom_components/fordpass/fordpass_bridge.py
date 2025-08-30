"""Fordpass API Library"""
import asyncio
import json
import logging
import os
import random
import threading
import time
import traceback
from asyncio import CancelledError
from datetime import datetime, timezone
from numbers import Number
from pathlib import Path
from typing import Final

import aiohttp
from aiohttp import ClientConnectorError, ClientConnectionError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.fordpass import DOMAIN
from custom_components.fordpass.const import REGIONS, ZONE_LIGHTS_VALUE_OFF
from custom_components.fordpass.fordpass_handler import (
    ROOT_STATES,
    ROOT_EVENTS,
    ROOT_METRICS,
    ROOT_MESSAGES,
    ROOT_VEHICLES,
    ROOT_REMOTE_CLIMATE_CONTROL,
    ROOT_PREFERRED_CHARGE_TIMES,
    ROOT_UPDTIME
)

_LOGGER = logging.getLogger(__name__)

INTEGRATION_INIT: Final = "INTG_INIT"

defaultHeaders = {
    "Accept": "*/*",
    "Accept-Language": "en-US",
    "User-Agent": "FordPass/23 CFNetwork/1408.0.4 Darwin/22.5.0",
    "Accept-Encoding": "gzip, deflate, br",
}

apiHeaders = {
    **defaultHeaders,
    "Content-Type": "application/json",
}

loginHeaders = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.5",
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
    "Accept-Encoding": "gzip, deflate, br",
}

MAX_401_RESPONSE_COUNT: Final = 10
LOG_DATA: Final = False

# DEPRECATED - do not use anymore!
# BASE_URL: Final = "https://usapi.cv.ford.com/api"
# SSO_URL: Final = "https://sso.ci.ford.com"

# hopefully also not used anylonger...
# GUARD_URL: Final = "https://api.mps.ford.com/api"

AUTONOMIC_URL: Final = "https://api.autonomic.ai/v1"
AUTONOMIC_BETA_URL: Final = "https://api.autonomic.ai/v1beta"
AUTONOMIC_WS_URL: Final = "wss://api.autonomic.ai/v1beta"
AUTONOMIC_ACCOUNT_URL: Final = "https://accounts.autonomic.ai/v1"

FORD_LOGIN_URL: Final = "https://login.ford.com"
FORD_FOUNDATIONAL_API: Final = "https://api.foundational.ford.com/api"
FORD_VEHICLE_API: Final = "https://api.vehicle.ford.com/api"
ERROR: Final = "ERROR"

START_CHARGE_KEY:Final      = "START_CHARGE"
CANCEL_CHARGE_KEY:Final     = "CANCEL_CHARGE"
PAUSE_CHARGE_KEY:Final      = "PAUSE_CHARGE"
SET_CHARGE_TARGET_KEY:Final = "SET_CHARGE_TARGET"

FORD_COMMAND_URL_TEMPLATES: Final = {
    # Templates with {vin} placeholder
    START_CHARGE_KEY:       "/electrification/experiences/v1/vehicles/{url_param}/global-charge-command/START",
    CANCEL_CHARGE_KEY:      "/electrification/experiences/v1/vehicles/{url_param}/global-charge-command/CANCEL",
    PAUSE_CHARGE_KEY:       "/electrification/experiences/v1/vehicles/{url_param}/global-charge-command/PAUSE",
    SET_CHARGE_TARGET_KEY:  "/electrification/experiences/v2/vehicles/preferred-charge-times/locations/{url_param}",
}
FORD_COMMAND_MAP: Final ={
    # the code will always add 'Command' at the end!
    START_CHARGE_KEY:       "startGlobalCharge",
    CANCEL_CHARGE_KEY:      "cancelGlobalCharge",
    PAUSE_CHARGE_KEY:       "pauseGlobalCharge",
    SET_CHARGE_TARGET_KEY:  "updateChargeProfiles",
}
#session = None #requests.Session()

# we need global variables to keep track of the number of 401 responses per user account(=token file)
_FOUR_NULL_ONE_COUNTER: dict = {}
_AUTO_FOUR_NULL_ONE_COUNTER: dict = {}

_sync_lock = threading.Lock()
_sync_lock_cache = {}

def get_sync_lock_for_user_and_region(user: str, region_key: str, vli:str) -> threading.Lock:
    """Get a cached threading.Lock for the user and region."""
    global _sync_lock_cache
    a_key = f"{user}µ@µ{region_key}"
    with _sync_lock:
        if a_key not in _sync_lock_cache:
            _LOGGER.debug(f"{vli}Create new threading.Lock for user: {user}, region: {region_key}")
            _sync_lock_cache[a_key] = threading.Lock()
        else:
            pass
            #_LOGGER.debug(f"{vli}Using cached threading.Lock for user: {user}, region: {region_key}")
    return _sync_lock_cache[a_key]

class ConnectedFordPassVehicle:
    # Represents a Ford vehicle, with methods for status and issuing commands

    session: aiohttp.ClientSession | None = None
    timeout: aiohttp.ClientTimeout | None = None
    coordinator: DataUpdateCoordinator | None = None

    use_token_data_from_memory: bool = False

    _data_container: dict = {}
    _cached_vehicles_data: dict

    ws_connected: bool = False
    _ws_debounced_update_task: asyncio.Task | None = None
    _ws_in_use_access_token: str | None = None
    _LAST_MESSAGES_UPDATE: float = 0.0
    _last_ignition_state: str | None = None
    _ws_debounced_full_refresh_task: asyncio.Task | None = None
    _ws_debounced_preferred_charge_times_refresh_task: asyncio.Task | None = None
    # when you have multiple vehicles, you need to set the vehicle log id
    # (v)ehicle (l)og (i)d
    vli: str = ""
    vin: Final[str]
    username: Final[str]
    region_key: Final[str]
    accout_key: Final[str]
    _LOCAL_LOGGING: Final[bool]

    def __init__(self, web_session, username, vin, region_key, coordinator: DataUpdateCoordinator=None,
                 storage_path:Path=None, tokens_location=None, local_logging:bool=False):
        self.session = web_session
        self.timeout = aiohttp.ClientTimeout(
            total=45,      # Total request timeout
            connect=30,    # Connection timeout
            sock_connect=30,
            sock_read=120   # Socket read timeout
        )
        self._LOCAL_LOGGING = local_logging
        self.username = username
        self.region_key = region_key
        self.account_key = f"{username}µ@µ{region_key}"
        self.app_id = REGIONS[self.region_key]["app_id"]
        self.locale_code = REGIONS[self.region_key]["locale"]
        self.countrycode = REGIONS[self.region_key]["countrycode"]
        self.vin = vin
        # this is just our initial log identifier for the vehicle... we will
        # fetch the vehicle name later and use it as vli
        self.vli = f"[@{self.vin}] "

        self.login_fail_reason = None
        self._HAS_COM_ERROR = False
        global _FOUR_NULL_ONE_COUNTER
        _FOUR_NULL_ONE_COUNTER[self.vin] = 0
        self.access_token = None
        self.refresh_token = None
        self.expires_at = None

        global _AUTO_FOUR_NULL_ONE_COUNTER
        _AUTO_FOUR_NULL_ONE_COUNTER[self.vin] = 0
        self.auto_access_token = None
        self.auto_refresh_token = None
        self.auto_expires_at = None

        # by default, we try to read the token from the file system
        self.use_token_data_from_memory = False

        if storage_path is not None and isinstance(storage_path, Path):
            self._storage_path = storage_path
        else:
            self._storage_path = Path(".storage")
        if tokens_location is None:
            if storage_path is not None:
                self.stored_tokens_location = str(storage_path.joinpath(DOMAIN, f"{username}_access_token@{region_key}.txt"))
            else:
                self.stored_tokens_location = f".storage/{DOMAIN}/{username}_access_token@{region_key}.txt"
        else:
            self.stored_tokens_location = tokens_location

        self._is_reauth_required = False
        self.status_updates_allowed = True

        # our main data container that holds all data that have been fetched from the vehicle
        self._data_container = {}
        self._cached_vehicles_data = {}
        self._remote_climate_control_supported = None
        self._cached_rcc_data = {}
        self._preferred_charge_times_supported = None
        self._cached_pct_data = {}
        self.coordinator = coordinator

        # websocket connection related variables
        self._ws_debounced_update_task = None
        self._ws_debounced_full_refresh_task = None
        self._ws_debounced_preferred_charge_times_refresh_task = None
        self._ws_in_use_access_token = None
        self.ws_connected = False
        self._ws_LAST_UPDATE = 0
        self._last_ignition_state = INTEGRATION_INIT

        _LOGGER.info(f"{self.vli}init vehicle object for vin: '{self.vin}' - using token from: '{self.stored_tokens_location}'")

    async def _local_logging(self, type, data):
        if self._LOCAL_LOGGING:
            await asyncio.get_running_loop().run_in_executor(None, lambda: self.__dump_data(type, data))

    def __dump_data(self, type:str, data:dict):
        a_datetime = datetime.now(timezone.utc)
        filename = str(self._storage_path.joinpath(DOMAIN, "data_dumps", self.username, self.region_key, self.vin,
                                                   f"{a_datetime.year}", f"{a_datetime.month:02d}",
                                                   f"{a_datetime.day:02d}", f"{a_datetime.hour:02d}",
                                                   f"{a_datetime.strftime("%Y-%m-%d_%H-%M-%S.%f")[:-3]}_{type}.json"))
        try:
            directory = os.path.dirname(filename)
            if not os.path.exists(directory):
                os.makedirs(directory)

            #file_path = os.path.join(os.getcwd(), filename)
            with open(filename, "w", encoding="utf-8") as outfile:
                json.dump(data, outfile, indent=4)
        except BaseException as e:
            _LOGGER.info(f"{self.vli}__dump_data(): Error while writing data to file '{filename}' - {type(e).__name__} - {e}")

    def clear_data(self):
        self._cached_vehicles_data = {}
        self._cached_rcc_data = {}
        self._data_container = {}

    async def __check_for_closed_session(self, e:BaseException):
        if isinstance(e, RuntimeError) and self.session is not None and self.session.closed:
            self.ws_connected = False
            _LOGGER.debug(f"{self.vli}__check_for_closed_session(): RuntimeError - session is closed - trying to create a new session")
            # this might look a bit strange - but I don't want to pass the hass object down to the vehicle object...
            if self.coordinator is not None:
                new_session = await self.coordinator.get_new_client_session(user=self.username, region_key=self.region_key)
                if new_session is not None and not new_session.closed:
                    self.session = new_session
                    return True
                else:
                    _LOGGER.info(f"{self.vli}__check_for_closed_session(): session is closed - but no new session could be created!")
        return False

    async def generate_tokens(self, urlstring, code_verifier, region_key):
        sign_up = "B2C_1A_SignInSignUp_"
        if region_key in REGIONS and "sign_up_addon" in REGIONS[region_key]:
            sign_up = f"{sign_up}{REGIONS[region_key]['sign_up_addon']}"

        redirect_schema = "fordapp"
        if region_key in REGIONS and "redirect_schema" in REGIONS[region_key]:
            redirect_schema = REGIONS[region_key]["redirect_schema"]

        _LOGGER.debug(f"{self.vli}generate_tokens() for country_code: {self.locale_code}")
        code_new = urlstring.replace(f"{redirect_schema}://userauthorized/?code=", "")

        headers = {
            **loginHeaders,
        }
        data = {
            "client_id": "09852200-05fd-41f6-8c21-d36d3497dc64",
            "grant_type": "authorization_code",
            "code_verifier": code_verifier,
            "code": code_new,
            "redirect_uri": f"{redirect_schema}://userauthorized"
        }
        response = await self.session.post(
            f"{FORD_LOGIN_URL}/4566605f-43a7-400a-946e-89cc9fdb0bd7/{sign_up}{self.locale_code}/oauth2/v2.0/token",
            headers=headers,
            data=data,
            ssl=True
        )

        # do not check the status code here - since it's not always return http 200!
        token_data = await response.json()
        if "access_token" in token_data:
            _LOGGER.debug(f"{self.vli}generate_tokens 'OK'- http status: {response.status} - JSON: {token_data}")
            return await self.generate_tokens_part2(token_data)
        else:
            if "message" in token_data:
                self.login_fail_reason = token_data["message"]
            elif "error_description" in token_data:
                self.login_fail_reason = token_data["error_description"]
            elif "error" in token_data:
                self.login_fail_reason = token_data["error"]

            _LOGGER.warning(f"{self.vli}generate_tokens 'FAILED'- http status: {response.status} - cause no 'access_token' in response: {token_data}")
            return False

    async def generate_tokens_part2(self, token):
        headers = {**apiHeaders, "Application-Id": self.app_id}
        data = {"idpToken": token["access_token"]}
        response = await self.session.post(
            f"{FORD_FOUNDATIONAL_API}/token/v2/cat-with-b2c-access-token",
            data=json.dumps(data),
            headers=headers,
            ssl=True
        )

        # do not check the status code here - since it's not always return http 200!
        final_access_token = await response.json()
        if "access_token" in final_access_token:
            if "expires_in" in final_access_token:
                final_access_token["expiry_date"] = time.time() + final_access_token["expires_in"]
                del final_access_token["expires_in"]
            if "refresh_expires_in" in final_access_token:
                final_access_token["refresh_expiry_date"] = time.time() + final_access_token["refresh_expires_in"]
                del final_access_token["refresh_expires_in"]

            _LOGGER.debug(f"{self.vli}generate_tokens_part2 'OK' - http status: {response.status} - JSON: {final_access_token}")
            await self._write_token_to_storage(final_access_token)
            return True
        else:
            if "message" in final_access_token:
                self.login_fail_reason = final_access_token["message"]
            elif "error_description" in final_access_token:
                self.login_fail_reason = final_access_token["error_description"]
            elif "error" in final_access_token:
                self.login_fail_reason = final_access_token["error"]

            _LOGGER.warning(f"{self.vli}generate_tokens_part2 'FAILED' - http status: {response.status} for '...cat-with-b2c-access-token' request - JSON: {final_access_token}")
            return False

    @property
    def require_reauth(self) -> bool:
        return self._is_reauth_required

    def mark_re_auth_required(self, ws=None):
        stack_trace = traceback.format_stack()
        stack_trace_str = ''.join(stack_trace[:-1])  # Exclude the call to this function
        _LOGGER.warning(f"{self.vli}mark_re_auth_required() called!!! -> stack trace:\n{stack_trace_str}")
        self.ws_close(ws)
        self._is_reauth_required = True

    async def __ensure_valid_tokens(self, now_time:float=None):
        # Fetch and refresh token as needed
        # with get_sync_lock_for_user_and_region(self.username, self.region_key, self.vli):

        _LOGGER.debug(f"{self.vli}__ensure_valid_tokens()")
        self._HAS_COM_ERROR = False
        # If a file exists, read in the token file and check it's valid

        # do not access every time the file system - since we are the only one
        # using the vehicle object, we can keep the token in memory (and
        # invalidate it if needed)
        if (not self.use_token_data_from_memory) and os.path.isfile(self.stored_tokens_location):
            prev_token_data = await self._read_token_from_storage()
            if prev_token_data is None:
                # no token data could be read!
                _LOGGER.info(f"{self.vli}__ensure_valid_tokens: Tokens are INVALID!!! - mark_re_auth_required() should have occurred?")
                return

            self.use_token_data_from_memory = True
            _LOGGER.debug(f"{self.vli}__ensure_valid_tokens: token data read from fs - size: {len(prev_token_data)}")

            self.access_token = prev_token_data["access_token"]
            self.refresh_token = prev_token_data["refresh_token"]
            self.expires_at = prev_token_data["expiry_date"]

            if "auto_token" in prev_token_data and "auto_refresh_token" in prev_token_data and "auto_expiry_date" in prev_token_data:
                self.auto_access_token = prev_token_data["auto_token"]
                self.auto_refresh_token = prev_token_data["auto_refresh_token"]
                self.auto_expires_at = prev_token_data["auto_expiry_date"]
            else:
                _LOGGER.debug(f"{self.vli}__ensure_valid_tokens: auto-token not set (or incomplete) in file")
                self.auto_access_token = None
                self.auto_refresh_token = None
                self.auto_expires_at = None
        else:
            # we will use the token data from memory...
            prev_token_data = {"access_token": self.access_token,
                               "refresh_token": self.refresh_token,
                               "expiry_date": self.expires_at,
                               "auto_token": self.auto_access_token,
                               "auto_refresh_token": self.auto_refresh_token,
                               "auto_expiry_date": self.auto_expires_at}

        # checking token data (and refreshing if needed)
        if now_time is None:
            now_time = time.time() + 7 # (so we will invalidate tokens if they expire in the next 7 seconds)

        if self.expires_at and now_time > self.expires_at:
            _LOGGER.debug(f"{self.vli}__ensure_valid_tokens: token's expires_at {self.expires_at} has expired time-delta: {int(now_time - self.expires_at)} sec -> requesting new token")
            refreshed_token = await self.refresh_token_func(prev_token_data)
            if self._HAS_COM_ERROR:
                _LOGGER.warning(f"{self.vli}__ensure_valid_tokens: skipping 'auto_token_refresh' - COMM ERROR")
            else:
                if refreshed_token is not None and refreshed_token is not False and refreshed_token != ERROR:
                    _LOGGER.debug(f"{self.vli}__ensure_valid_tokens: result for new token: {len(refreshed_token)}")
                    await self.refresh_auto_token_func(refreshed_token)
                else:
                    _LOGGER.warning(f"{self.vli}__ensure_valid_tokens: result for new token: ERROR, None or False")

        if self.auto_access_token is None or self.auto_expires_at is None:
            _LOGGER.debug(f"{self.vli}__ensure_valid_tokens: auto_access_token: '{self.auto_access_token}' or auto_expires_at: '{self.auto_expires_at}' is None -> requesting new auto-token")
            await self.refresh_auto_token_func(prev_token_data)

        if self.auto_expires_at and now_time > self.auto_expires_at:
            _LOGGER.debug(f"{self.vli}__ensure_valid_tokens: auto-token's auto_expires_at {self.auto_expires_at} has expired time-delta: {int(now_time - self.auto_expires_at)} sec -> requesting new auto-token")
            await self.refresh_auto_token_func(prev_token_data)

        # it could be that there has been 'exceptions' when trying to update the tokens
        if self._HAS_COM_ERROR:
            _LOGGER.warning(f"{self.vli}__ensure_valid_tokens: COMM ERROR")
        else:
            if self.access_token is None:
                _LOGGER.warning(f"{self.vli}__ensure_valid_tokens: self.access_token is None! - but we don't do anything now [the '_request_token()' or '_request_auto_token()' will trigger mark_re_auth_required() when this is required!]")
            else:
                _LOGGER.debug(f"{self.vli}__ensure_valid_tokens: Tokens are valid")

    async def refresh_token_func(self, prev_token_data):
        """Refresh token if still valid"""
        _LOGGER.debug(f"{self.vli}refresh_token_func()")

        token_data = await self._request_token(prev_token_data)
        if token_data is None or token_data is False:
            self.access_token = None
            self.refresh_token = None
            self.expires_at = None

            # also invalidating the auto-tokens...
            self.auto_access_token = None
            self.auto_refresh_token = None
            self.auto_expires_at = None
            _LOGGER.warning(f"{self.vli}refresh_token_func: FAILED!")

        elif token_data == ERROR:
            _LOGGER.warning(f"{self.vli}refresh_token_func: COMM ERROR")
            return ERROR
        else:
            # it looks like that the token could be requested successfully...

            # re-write the 'expires_in' to 'expiry_date'...
            if "expires_in" in token_data:
                token_data["expiry_date"] = time.time() + token_data["expires_in"]
                del token_data["expires_in"]

            if "refresh_expires_in" in token_data:
                token_data["refresh_expiry_date"] = time.time() + token_data["refresh_expires_in"]
                del token_data["refresh_expires_in"]

            await self._write_token_to_storage(token_data)

            self.access_token = token_data["access_token"]
            self.refresh_token = token_data["refresh_token"]
            self.expires_at = token_data["expiry_date"]

            _LOGGER.debug(f"{self.vli}refresh_token_func: OK")
            return token_data

    async def _request_token(self, prev_token_data):
        global _FOUR_NULL_ONE_COUNTER
        if self._HAS_COM_ERROR:
            return ERROR
        else:
            try:
                _LOGGER.debug(f"{self.vli}_request_token() - {_FOUR_NULL_ONE_COUNTER[self.vin]}")

                headers = {
                    **apiHeaders,
                    "Application-Id": self.app_id
                }
                data = {
                    "refresh_token": prev_token_data["refresh_token"]
                }
                response = await self.session.post(
                    f"{FORD_FOUNDATIONAL_API}/token/v2/cat-with-refresh-token",
                    data=json.dumps(data),
                    headers=headers,
                    timeout=self.timeout
                )

                if response.status == 200:
                    # ok first resetting the counter for 401 errors (if we had any)
                    _FOUR_NULL_ONE_COUNTER[self.vin] = 0
                    result = await response.json()
                    _LOGGER.debug(f"{self.vli}_request_token: status OK")
                    return result
                elif response.status == 401 or response.status == 400:
                    _FOUR_NULL_ONE_COUNTER[self.vin] += 1
                    if _FOUR_NULL_ONE_COUNTER[self.vin] > MAX_401_RESPONSE_COUNT:
                        _LOGGER.error(f"{self.vli}_request_token: status_code: {response.status} - mark_re_auth_required()")
                        self.mark_re_auth_required()
                    else:
                        # some new checking for the error message...
                        # status_code: 400 - Received response: {"message":"Invalid or Expired Token","timestamp":"2025-06-09T07:02:44.048994479Z","errorCode":"460"}
                        try:
                            msg = await response.json()
                            is_invalid_msg = False
                            if "message" in msg:
                                a_msg = msg["message"].lower()
                                if "invalid" in a_msg or "expired token" in a_msg:
                                    is_invalid_msg = True
                            if is_invalid_msg or ("errorCode" in msg and msg["errorCode"] == "460"):
                                _LOGGER.warning(f"{self.vli}_request_token: status_code: {response.status} - TOKEN HAS BEEN INVALIDATED")
                                _FOUR_NULL_ONE_COUNTER[self.vin] = MAX_401_RESPONSE_COUNT + 1
                        except BaseException as e:
                            _LOGGER.debug(f"{self.vli}_request_token: status_code: {response.status} - could not read from response - {type(e).__name__} - {e}")

                    (_LOGGER.warning if _FOUR_NULL_ONE_COUNTER[self.vin] > 2 else _LOGGER.info)(f"{self.vli}_request_token: status_code: {response.status} - counter: {_FOUR_NULL_ONE_COUNTER}")
                    await asyncio.sleep(5)
                    return False
                else:
                    _LOGGER.info(f"{self.vli}_request_token: status_code: {response.status} - {response.real_url} - Received response: {await response.text()}")
                    self._HAS_COM_ERROR = True
                    return ERROR

            except BaseException as e:
                if not await self.__check_for_closed_session(e):
                    _LOGGER.warning(f"{self.vli}_request_token(): Error while '_request_token' for vehicle {self.vin} - {type(e).__name__} - {e}")
                else:
                    _LOGGER.info(f"{self.vli}_request_token(): RuntimeError - Session was closed occurred - but a new Session could be generated")
                self._HAS_COM_ERROR = True
                return ERROR

    async def refresh_auto_token_func(self, cur_token_data):
        _LOGGER.debug(f"{self.vli}refresh_auto_token_func()")
        auto_token = await self._request_auto_token()
        if auto_token is None or auto_token is False:
            self.auto_access_token = None
            self.auto_refresh_token = None
            self.auto_expires_at = None
            (_LOGGER.warning if _AUTO_FOUR_NULL_ONE_COUNTER[self.vin] > 2 else _LOGGER.info)(f"{self.vli}refresh_auto_token_func: FAILED!")

        elif auto_token == ERROR:
            _LOGGER.warning(f"{self.vli}refresh_auto_token_func: COMM ERROR")
        else:
            # it looks like that the auto token could be requested successfully...
            if "expires_in" in auto_token:
                # re-write the 'expires_in' to 'expiry_date'...
                auto_token["expiry_date"] = time.time() + auto_token["expires_in"]
                del auto_token["expires_in"]

            if "refresh_expires_in" in auto_token:
                auto_token["refresh_expiry_date"] = time.time() + auto_token["refresh_expires_in"]
                del auto_token["refresh_expires_in"]

            cur_token_data["auto_token"] = auto_token["access_token"]
            cur_token_data["auto_refresh_token"] = auto_token["refresh_token"]
            cur_token_data["auto_expiry_date"] = auto_token["expiry_date"]

            await self._write_token_to_storage(cur_token_data)

            # finally, setting our internal values...
            self.auto_access_token = auto_token["access_token"]
            self.auto_refresh_token = auto_token["refresh_token"]
            self.auto_expires_at = auto_token["expiry_date"]

            _LOGGER.debug(f"{self.vli}refresh_auto_token_func: OK")

    async def _request_auto_token(self):
        """Get token from new autonomic API"""
        global _AUTO_FOUR_NULL_ONE_COUNTER
        if self._HAS_COM_ERROR:
            return ERROR
        else:
            try:
                _LOGGER.debug(f"{self.vli}_request_auto_token()")
                headers = {
                    "accept": "*/*",
                    "content-type": "application/x-www-form-urlencoded"
                }
                # it looks like, that the auto_refresh_token is useless here...
                # but for now I (marq24) keep this in the code...
                data = {
                    "subject_token": self.access_token,
                    "subject_issuer": "fordpass",
                    "client_id": "fordpass-prod",
                    "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                    "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
                }
                response = await self.session.post(
                    f"{AUTONOMIC_ACCOUNT_URL}/auth/oidc/token",
                    data=data,
                    headers=headers,
                    timeout=self.timeout
                )

                if response.status == 200:
                    # ok first resetting the counter for 401 errors (if we had any)
                    _AUTO_FOUR_NULL_ONE_COUNTER[self.vin] = 0

                    result = await response.json()
                    _LOGGER.debug(f"{self.vli}_request_auto_token: status OK")
                    return result
                elif response.status == 401:
                    _AUTO_FOUR_NULL_ONE_COUNTER[self.vin] += 1
                    if _AUTO_FOUR_NULL_ONE_COUNTER[self.vin] > MAX_401_RESPONSE_COUNT:
                        _LOGGER.error(f"{self.vli}_request_auto_token: status_code: 401 - mark_re_auth_required()")
                        self.mark_re_auth_required()
                    else:
                        (_LOGGER.warning if _AUTO_FOUR_NULL_ONE_COUNTER[self.vin] > 2 else _LOGGER.info)(f"{self.vli}_request_auto_token: status_code: 401 - AUTO counter: {_AUTO_FOUR_NULL_ONE_COUNTER}")
                        await asyncio.sleep(5)
                    return False
                else:
                    _LOGGER.info(f"{self.vli}_request_auto_token: status_code: {response.status} - {response.real_url} - Received response: {await response.text()}")
                    self._HAS_COM_ERROR = True
                    return ERROR

            except BaseException as e:
                if not await self.__check_for_closed_session(e):
                    _LOGGER.warning(f"{self.vli}_request_auto_token(): Error while '_request_token' for vehicle {self.vin} - {type(e).__name__} - {e}")
                else:
                    _LOGGER.info(f"{self.vli}_request_auto_token(): RuntimeError - Session was closed occurred - but a new Session could be generated")
                self._HAS_COM_ERROR = True
                return ERROR

    """Check if we can write to the file system - should be called from the setup UI"""
    @staticmethod
    def check_general_fs_access(a_storage_path:Path):
        _LOGGER.debug(f"check_general_fs_access(): storage_path is: '{a_storage_path}'")
        can_create_file = False
        if a_storage_path is not None:
            testfile = str(a_storage_path.joinpath(DOMAIN, "write_test@file.txt"))
        else:
            testfile = f".storage/{DOMAIN}/write_test@file.txt"
        # Check if the parent directory exists
        directory = os.path.dirname(testfile)
        if not os.path.exists(directory):
            try:
                os.makedirs(directory, exist_ok=True)
            except OSError as exc:
                _LOGGER.warning(f"check_general_fs_access(): could not create directory '{directory}': {type(exc).__name__} - {exc}")

        if os.path.exists(directory):
            try:
                with open(testfile, "w", encoding="utf-8") as outfile:
                    json.dump({"test": "file"}, outfile)
            except OSError as exc:
                _LOGGER.warning(f"check_general_fs_access(): could not create test file '{testfile}': {type(exc).__name__} - {exc}")

            if os.path.exists(testfile):
                can_create_file = True
                _LOGGER.debug(f"check_general_fs_access(): successfully created test file: '{testfile}'")
                os.remove(testfile)

        return can_create_file

    async def _write_token_to_storage(self, token):
        """Save token to file for reuse"""
        _LOGGER.debug(f"{self.vli}_write_token_to_storage()")

        # Check if the parent directory exists
        directory = os.path.dirname(self.stored_tokens_location)
        if not os.path.exists(directory):
            try:
                await asyncio.get_running_loop().run_in_executor(None, lambda: os.makedirs(directory, exist_ok=True))
            except OSError as exc:
                # Handle exception as before
                _LOGGER.error(f"{self.vli}_write_token_to_storage(): Failed to create directory '{directory}': {exc}")

        if os.path.exists(directory):
            # Write the file in executor
            await asyncio.get_running_loop().run_in_executor(None, lambda: self.__write_token_int(token))
        else:
            _LOGGER.wrning(f"{self.vli}_write_token_to_storage(): Directory '{directory}' does not exist, cannot write token file.")
        # Make sure that we will read the token data next time
        self.use_token_data_from_memory = False

    def __write_token_int(self, token):
        """Synchronous method to write token file, called from executor."""
        try:
            with open(self.stored_tokens_location, "w", encoding="utf-8") as outfile:
                json.dump(token, outfile)
        except OSError as exc:
            _LOGGER.error(f"{self.vli}_write_token_to_storage(): Failed to create directory '{self.stored_tokens_location}': {type(exc).__name__} - {exc}")

    async def _read_token_from_storage(self):
        """Read saved token from a file"""
        _LOGGER.debug(f"{self.vli}_read_token_from_storage()")
        try:
            # Run blocking file operation in executor
            token_data = await asyncio.get_running_loop().run_in_executor(None, self.__read_token_int)
            return token_data
        except ValueError:
            _LOGGER.warning(f"{self.vli}_read_token_from_storage: 'ValueError' invalidate TOKEN FILE -> mark_re_auth_required()")
            self.mark_re_auth_required()
        return None

    def __read_token_int(self):
        """Synchronous method to read the token file, called from executor."""
        with open(self.stored_tokens_location, encoding="utf-8") as token_file:
            return json.load(token_file)

    async def _rename_token_file_if_needed(self, username:str):
        """Move a legacy token file to new region-specific location if it exists"""
        stored_tokens_location_legacy = f".storage/fordpass/{username}_access_token.txt"
        try:
            # Check if the legacy file exists
            if os.path.isfile(stored_tokens_location_legacy):
                _LOGGER.debug(f"{self.vli}Found legacy token at {stored_tokens_location_legacy}, moving to {self.stored_tokens_location}")

                # Move the file (in executor to avoid blocking)
                await asyncio.get_running_loop().run_in_executor(None, lambda: os.rename(stored_tokens_location_legacy, self.stored_tokens_location))
                _LOGGER.debug(f"{self.vli}Successfully moved token file to new location")
            else:
                _LOGGER.debug(f"{self.vli}No legacy token file found at {stored_tokens_location_legacy}, nothing to move")

        except Exception as e:
            _LOGGER.warning(f"{self.vli}Failed to move token file: {type(e).__name__} - {e}")

    def clear_token(self):
        _LOGGER.debug(f"{self.vli}clear_token()")
        """Clear tokens from config directory"""
        if os.path.isfile("/tmp/fordpass_token.txt"):
            os.remove("/tmp/fordpass_token.txt")
        if os.path.isfile("/tmp/token.txt"):
            os.remove("/tmp/token.txt")
        if os.path.isfile(self.stored_tokens_location):
            os.remove(self.stored_tokens_location)

        # make sure that we will read the token data next time...
        self.use_token_data_from_memory = False

        # but when we cleared the tokens... we must mark us as 're-auth' required...
        self._is_reauth_required = True


    # the WebSocket related handling...
    async def ws_connect(self):
        _LOGGER.debug(f"{self.vli}ws_connect() STARTED...")
        self.ws_connected = False
        await self.__ensure_valid_tokens()
        if self._HAS_COM_ERROR:
            _LOGGER.debug(f"{self.vli}ws_connect() - COMM ERROR - skipping WebSocket connection")
            return None
        elif len(self._data_container.get(ROOT_METRICS, {})) == 0:
            _LOGGER.warning(f"{self.vli}ws_connect() - no metrics data available - skipping WebSocket connection")
            return None
        else:
            _LOGGER.debug(f"{self.vli}ws_connect() - auto_access_token exist? {self.auto_access_token is not None}")

        headers_ws = {
            **apiHeaders,
            "authorization": f"Bearer {self.auto_access_token}",
            "Application-Id": self.app_id,
            "Connection": "Upgrade",
            "Upgrade": "websocket",
            #"Sec-WebSocket-Extensions": "permessage-deflate; client_max_window_bits",
            #"Sec-WebSocket-Key": "QOX3XLqFRFO6N+kAyrhQKA==",
            #"Sec-WebSocket-Version": "13"
        }
        web_socket_url = f"{AUTONOMIC_WS_URL}/telemetry/sources/fordpass/vehicles/{self.vin}/ws"

        self._ws_in_use_access_token = self.auto_access_token
        try:
            async with self.session.ws_connect(url=web_socket_url, headers=headers_ws, timeout=self.timeout) as ws:
                self.ws_connected = True

                _LOGGER.info(f"{self.vli}connected to websocket: {web_socket_url}")
                async for msg in ws:
                    # store the last time we heard from the websocket
                    self._ws_LAST_UPDATE = time.time()

                    new_data_arrived = False
                    do_housekeeping_checks = False
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            ws_data = msg.json()
                            if ws_data is None or len(ws_data) == 0:
                                _LOGGER.debug(f"{self.vli}ws_connect(): received empty 'data': '{ws_data}'")
                                do_housekeeping_checks = True
                            else:
                                if "_httpStatus" in ws_data:
                                    status = int(ws_data["_httpStatus"])
                                    if 200 <= status < 300:
                                        if status == 202:
                                            # it looks like we have sent a new access token... and the backend just
                                            # replied with an HTTP status code...
                                            self._ws_in_use_access_token = self.auto_access_token
                                            _LOGGER.debug(f"{self.vli}ws_connect(): received HTTP status 202 - auto token update accepted")
                                        else:
                                            _LOGGER.debug(f"{self.vli}ws_connect(): received HTTP status: {status} - OK")

                                elif "_error" in ws_data:
                                    # in case of any error, we simply close the websocket connection
                                    _LOGGER.info(f"{self.vli}ws_connect(): error object read: {ws_data["_error"]}")
                                    break

                                    # err_obj = ws_data["_error"]
                                    # err_handled = False
                                    # if "code" in err_obj and err_obj["code"] == 401:
                                    #     if "message" in err_obj:
                                    #         lower_msg = err_obj['message'].lower()
                                    #         if 'provided token was expired' in lower_msg:
                                    #             _LOGGER.debug(f"{self.vli}ws_connect(): 'provided token was expired' expired - going to auto-reconnect-loop")
                                    #             self.ws_do_reconnect = True
                                    #             err_handled = True
                                    #         if 'websocket session expired' in lower_msg:
                                    #             _LOGGER.debug(f"{self.vli}ws_connect(): 'websocket session expired' - going to auto-reconnect-loop")
                                    #             self.ws_do_reconnect = True
                                    #             err_handled = True
                                    #
                                    # if not err_handled:
                                    #     _LOGGER.error(f"{self.vli}ws_connect(): unknown error object read: {err_obj}")

                                elif "_data" in ws_data:
                                    data_obj = ws_data["_data"]
                                    if self._LOCAL_LOGGING:
                                        await self._local_logging("ws", data_obj)

                                    new_data_arrived = self._ws_handle_data(data_obj)
                                    if new_data_arrived is False:
                                        _LOGGER.debug(f"{self.vli}ws_connect(): received unknown 'data': {data_obj}")
                                    else:
                                        _LOGGER.debug(f"{self.vli}ws_connect(): received vehicle 'data'")
                                else:
                                    if self._LOCAL_LOGGING:
                                        await self._local_logging("ws", ws_data)

                                    _LOGGER.info(f"{self.vli}ws_connect(): unknown 'content': {ws_data}")

                        except Exception as e:
                            _LOGGER.debug(f"{self.vli}Could not read JSON from: {msg} - caused {e}")

                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        _LOGGER.debug(f"{self.vli}received CLOSED or ERROR - will terminate websocket session: {msg}")
                        break

                    else:
                        _LOGGER.error(f"{self.vli}Unknown Message Type from: {msg}")

                    # do we need to push new data event to the coordinator?
                    if new_data_arrived:
                        self._ws_notify_for_new_data()

                    if do_housekeeping_checks:
                        # check if we need to update the messages...
                        await self._ws_check_for_message_update_required()

                        # check if we need to refresh the auto token...
                        await self._ws_check_for_auth_token_refresh(ws)

        except ClientConnectorError as con:
            _LOGGER.error(f"{self.vli}ws_connect(): Could not connect to websocket: {type(con).__name__} - {con}")
        except ClientConnectionError as err:
            _LOGGER.error(f"{self.vli}ws_connect(): ??? {type(err).__name__} - {err}")
        except asyncio.TimeoutError as time_exc:
            _LOGGER.debug(f"{self.vli}ws_connect(): TimeoutError: No WebSocket message received within timeout period")
        except CancelledError as canceled:
            _LOGGER.info(f"{self.vli}ws_connect(): Terminated? - {type(canceled).__name__} - {canceled}")
        except BaseException as x:
            _LOGGER.error(f"{self.vli}ws_connect(): !!! {type(x).__name__} - {x}")

        _LOGGER.debug(f"{self.vli}ws_connect() ENDED")
        try:
            await self.ws_close(ws)
        except UnboundLocalError as is_unbound:
            _LOGGER.debug(f"{self.vli}ws_connect(): skipping ws_close() (since ws is unbound)")
        except BaseException as e:
            _LOGGER.error(f"{self.vli}ws_connect(): Error while calling ws_close(): {type(e).__name__} - {e}")

        self.ws_connected = False
        return None

    def _ws_handle_data(self, data_obj):
        collected_keys = []
        new_states = self._ws_update_key(data_obj, ROOT_STATES, collected_keys)
        new_events = self._ws_update_key(data_obj, ROOT_EVENTS, collected_keys)
        new_msg = self._ws_update_key(data_obj, ROOT_MESSAGES, collected_keys)
        if new_msg:
            self._LAST_MESSAGES_UPDATE = time.time()

        new_metrics = self._ws_update_key(data_obj, ROOT_METRICS, collected_keys)
        if ROOT_STATES not in data_obj:
            self._ws_update_key(data_obj, ROOT_UPDTIME, collected_keys)

        # check, if the 'ignitionStatus' has changed cause of the data that was received via the websocket...
        # IF the state goes to 'OFF', we will trigger a complete integration data update
        if ROOT_METRICS not in data_obj:
            # compare 'ignitionStatus' reading with default impl in FordPassDataHandler!
            new_ignition_state = self._data_container.get(ROOT_METRICS, {}).get("ignitionStatus", {}).get("value", INTEGRATION_INIT).upper()

            #_LOGGER.info(f"{self.vli}ws(): NEW ignition state '{new_ignition_state}' | LAST ignition state: '{self._last_ignition_state}'")
            if self._last_ignition_state != INTEGRATION_INIT:
                if "OFF" == new_ignition_state and new_ignition_state != self._last_ignition_state:
                    if self._ws_debounced_full_refresh_task is not None and not self._ws_debounced_full_refresh_task.done():
                        self._ws_debounced_full_refresh_task.cancel()
                    _LOGGER.debug(f"{self.vli}ws(): ignition state changed to 'OFF' -> triggering full data update (will be started in 30sec)")
                    self._ws_debounced_full_refresh_task = asyncio.create_task(self._ws_debounce_full_data_refresh())

                elif "ON" == new_ignition_state:
                    # cancel any running the full refresh task if the new state is 'ON'...
                    if self._ws_debounced_full_refresh_task is not None and not self._ws_debounced_full_refresh_task.done():
                        _LOGGER.debug(f"{self.vli}ws(): ignition state changed to 'ON' -> canceling any running full refresh task")
                        self._ws_debounced_full_refresh_task.cancel()

            self._last_ignition_state = new_ignition_state

        return new_metrics or new_states or new_events or new_msg

    def _ws_update_key(self, data_obj, a_root_key, collected_keys):
        if a_root_key in data_obj:

            if a_root_key == ROOT_STATES:
                # moving the content of a possible 'commands' dict to the root level
                # [since this makes checking for commands easier].
                if "commands" in data_obj[a_root_key] and hasattr(data_obj[a_root_key]["commands"], "items"):
                    # Move each command to the root level
                    for cmd_key, cmd_value in data_obj[a_root_key]["commands"].items():
                        data_obj[a_root_key][cmd_key] = cmd_value

                    # Remove the original commands dictionary
                    del data_obj[a_root_key]["commands"]

                # special handling for state updates...
                for a_state_name, a_state_obj in data_obj[a_root_key].items():
                    # "timestamp": "2025-06-05T21:34:47.619487Z",
                    if "timestamp" in a_state_obj and a_state_obj["timestamp"] is not None:
                        try:
                            # Convert ISO 8601 format to Unix timestamp
                            parsed_dt = datetime.fromisoformat(a_state_obj["timestamp"].replace('Z', '+00:00'))
                            if time.time() - parsed_dt.timestamp() > 60 * 10:
                                _LOGGER.debug(f"{self.vli}ws(): skip '{a_state_name}' handling - older than 10 minutes")
                                continue
                        except BaseException as ex:
                            pass

                    if "value" in a_state_obj:
                        a_value_obj = a_state_obj["value"]
                        if "toState" in a_value_obj:
                            _LOGGER.debug(f"{self.vli}ws(): new state '{a_state_name}' arrived -> toState: {a_value_obj["toState"]}")
                            to_state_value = a_value_obj["toState"].upper()
                            if to_state_value in ["SUCCESS", "COMMAND_SUCCEEDED_ON_DEVICE"]:
                                if ROOT_METRICS in a_value_obj:
                                    self._ws_update_key(a_value_obj, ROOT_METRICS, collected_keys)
                                    _LOGGER.debug(f"{self.vli}ws(): extracted '{ROOT_METRICS}' update from new 'success' state: {a_value_obj[ROOT_METRICS]}")

                                if "updateChargeProfilesCommand" == a_state_name:
                                    # we have a special handling for the 'updateChargeProfilesCommand'
                                    # -> when we receive a 'success' state, we will update our
                                    # energy_transfer_object...
                                    if self._ws_debounced_preferred_charge_times_refresh_task is not None and not self._ws_debounced_preferred_charge_times_refresh_task.done():
                                        self._ws_debounced_preferred_charge_times_refresh_task.cancel()
                                    _LOGGER.debug(f"{self.vli}ws(): updateChargeProfilesCommand -> triggering 'preferred_charge_times' data update (will be started in 30sec)")
                                    self._ws_debounced_preferred_charge_times_refresh_task = asyncio.create_task(self._ws_debounce_update_preferred_charge_times())

                        else:
                            _LOGGER.debug(f"{self.vli}ws(): new state (without toState) '{a_state_name}' arrived: {a_value_obj}")
                    else:
                        _LOGGER.debug(f"{self.vli}ws(): new state (without value) '{a_state_name}' arrived")

            # If we don't have states yet in the existing data, initialize it
            if a_root_key not in self._data_container:
                self._data_container[a_root_key] = {}

            # Update only the specific keys (e.g. if only one state is present) that are in the new data
            if hasattr(data_obj[a_root_key], "items"):
                for a_key_name, a_key_value in data_obj[a_root_key].items():
                    # for 'ROOT_METRICS' we must merge 'customMetrics' & 'configurations'
                    # and for 'ROOT_EVENTS' we must merge 'customEvents'
                    if ((a_root_key == ROOT_METRICS and (a_key_name == "customMetrics" or a_key_name == "configurations")) or
                        (a_root_key == ROOT_EVENTS and a_key_name == "customEvents")):
                        if a_key_name not in self._data_container[a_root_key]:
                            self._data_container[a_root_key][a_key_name] = {}
                        for a_sub_key_name, a_sub_key_value in a_key_value.items():
                            self._data_container[a_root_key][a_key_name][a_sub_key_name] = a_sub_key_value
                            collected_keys.append(f"{a_key_name}[{a_sub_key_name}]")
                    # for all other keys, we simply update the value
                    else:
                        self._data_container[a_root_key][a_key_name] = a_key_value
                        collected_keys.append(a_key_name)

            elif isinstance(data_obj[a_root_key], (str, Number)):
                self._data_container[a_root_key] = data_obj[a_root_key]
                collected_keys.append(a_root_key)

            if a_root_key == ROOT_UPDTIME:
                _LOGGER.info(f"{self.vli}ws(): this is a 'heartbeat': {data_obj[a_root_key]} {collected_keys}")

            return True

        return False

    # def _ws_update_key(self, data_obj, a_root_key, collected_keys):
    #     if a_root_key in data_obj:
    #
    #         # special handling for single state updates...
    #         if a_root_key == ROOT_STATES and len(data_obj[a_root_key]) == 1:
    #             a_state_name, a_state_obj = next(iter(data_obj[a_root_key].items()))
    #             if "value" in a_state_obj:
    #                 a_value_obj = a_state_obj["value"]
    #                 if "toState" in a_value_obj:
    #                     _LOGGER.debug(f"{self.vli}ws(): new state '{a_state_name}' arrived -> toState: {a_value_obj["toState"]}")
    #                     if a_value_obj["toState"].lower() == "success":
    #                         if ROOT_METRICS in a_value_obj:
    #                             self._ws_update_key(a_value_obj, ROOT_METRICS, collected_keys)
    #                             _LOGGER.debug(f"{self.vli}ws(): extracted '{ROOT_METRICS}' update from new 'success' state: {a_value_obj[ROOT_METRICS]}")
    #                 else:
    #                     _LOGGER.debug(f"{self.vli}ws(): new state (without toState) '{a_state_name}' arrived: {a_value_obj}")
    #             else:
    #                 _LOGGER.debug(f"{self.vli}ws(): new state (without value) '{a_state_name}' arrived")
    #
    #         # core - merge recursive the dicts
    #         if a_root_key in self._data_container:
    #             self._ws_merge_dict_recursive(self._data_container[a_root_key], data_obj[a_root_key], collected_keys, prefix=None)
    #         else:
    #             self._data_container[a_root_key] = data_obj[a_root_key]
    #
    #         # just some post-processing (logging)
    #         if a_root_key == ROOT_UPDTIME:
    #             _LOGGER.info(f"{self.vli}ws(): this is a 'heartbeat': {data_obj[a_root_key]} {collected_keys}")
    #
    #         return True
    #     return False
    #
    # def _ws_merge_dict_recursive(self, target_dict, source_dict, collected_keys, prefix=""):
    #     """Recursively merge source_dict into target_dict while keeping existing keys in target_dict"""
    #     for key, value in source_dict.items():
    #         path = f"{prefix}.{key}" if prefix else key
    #         if hasattr(value, "items") and key in target_dict and hasattr(target_dict[key], "items"):
    #             # Both source and target have dict at this key - recursive merge
    #             self._ws_merge_dict_recursive(target_dict[key], value, collected_keys, path)
    #         else:
    #             # Either source or target isn't a dict, or key doesn't exist in target - overwriting
    #             target_dict[key] = value
    #             collected_keys.append(path)

    async def _ws_check_for_auth_token_refresh(self, ws):
        # check the age of auto auth_token... and if' it's near the expiry date, we should refresh it
        try:
            if self.auto_expires_at and time.time() + 45 > self.auto_expires_at:
                _LOGGER.debug(f"{self.vli}_ws_check_for_auth_token_refresh(): auto token expires in less than 45 seconds - try to refresh")

                prev_token_data = {"access_token": self.access_token,
                                   "refresh_token": self.refresh_token,
                                   "expiry_date": self.expires_at,
                                   "auto_token": self.auto_access_token,
                                   "auto_refresh_token": self.auto_refresh_token,
                                   "auto_expiry_date": self.auto_expires_at}

                await self.refresh_auto_token_func(prev_token_data)

            # could be that another process has refreshed the auto token...
            if self.auto_access_token is not None:
                if self.auto_access_token != self._ws_in_use_access_token:
                    _LOGGER.debug(f"{self.vli}_ws_check_for_auth_token_refresh(): auto token has been refreshed -> update websocket")
                    await ws.send_json({"accessToken": self.auto_access_token})
            else:
                _LOGGER.info(f"{self.vli}_ws_check_for_auth_token_refresh(): 'self.auto_access_token' is None (might be cause of 401 error), we will close the websocket connection and wait for the watchdog to reconnect")
                await self.ws_close(ws)

        except BaseException as e:
            _LOGGER.error(f"{self.vli}_ws_check_for_auth_token_refresh(): Error while refreshing auto token - {type(e).__name__} - {e}")

    async def _ws_check_for_message_update_required(self):
        update_interval = 0
        if self.coordinator is not None:
            update_interval = int(self.coordinator.update_interval.total_seconds())

        # only request every 20 minutes for new messages...
        to_wait_till = self._LAST_MESSAGES_UPDATE + max(update_interval, 20 * 60)
        if to_wait_till < time.time():
            _LOGGER.debug(f"{self.vli}_ws_check_for_message_update_required(): a update of the messages is required [last update was: {round((time.time() - self._LAST_MESSAGES_UPDATE) / 60, 1)} min ago]")
            # we need to update the messages...
            msg_data = await self.req_messages()
            if msg_data is not None:
                self._data_container[ROOT_MESSAGES] = msg_data
                self._ws_notify_for_new_data()
            elif self._HAS_COM_ERROR:
                # we have some communication issues when try to read messages - as long as the
                # websocket is connected, we should not panic...
                # we will still update the last messages update time... so that we don't hammer
                # the backend with requests...
                self._LAST_MESSAGES_UPDATE = time.time()
        else:
            _LOGGER.debug(f"{self.vli}_ws_check_for_message_update_required(): no update required [wait for: {round((to_wait_till - time.time())/60, 1)} min]")

    def _ws_notify_for_new_data(self):
        if self._ws_debounced_update_task is not None and not self._ws_debounced_update_task.done():
            self._ws_debounced_update_task.cancel()
        self._ws_debounced_update_task = asyncio.create_task(self._ws_debounce_coordinator_update())

    async def _ws_debounce_coordinator_update(self):
        await asyncio.sleep(0.3)
        if self.coordinator is not None:
            self.coordinator.async_set_updated_data(self._data_container)

    async def _ws_debounce_full_data_refresh(self):
        try:
            # if the ignition state has changed to 'OFF', we will wait 30 seconds before we trigger the full refresh
            # this is to ensure that the vehicle has enough time to send all the last data updates - and that the vehicle
            # will be started again... (in a short while)
            _LOGGER.debug(f"{self.vli}_ws_debounce_full_data_refresh(): started")
            await asyncio.sleep(30)
            count = 0
            while not self.status_updates_allowed and count < 11:
                _LOGGER.debug(f"{self.vli}_ws_debounce_full_data_refresh(): waiting for status updates to be allowed... retry: {count}")
                count += 1
                await asyncio.sleep(random.uniform(2, 30))

            _LOGGER.debug(f"{self.vli}_ws_debounce_full_data_refresh(): starting the full update now")
            updated_data = await self.update_all()
            if updated_data is not None and self.coordinator is not None:
                self.coordinator.async_set_updated_data(self._data_container)
        except CancelledError:
            _LOGGER.debug(f"{self.vli}_ws_debounce_full_data_refresh(): was canceled - all good")
        except BaseException as ex:
            _LOGGER.warning(f"{self.vli}_ws_debounce_full_data_refresh(): Error during full data refresh - {type(ex).__name__} - {ex}")

    async def ws_close(self, ws):
        """Close the WebSocket connection cleanly."""
        _LOGGER.debug(f"{self.vli}ws_close(): for {self.vin} called")
        self.ws_connected = False
        if ws is not None:
            try:
                await ws.close()
                _LOGGER.debug(f"{self.vli}ws_close(): connection closed successfully")
            except BaseException as e:
                _LOGGER.info(f"{self.vli}ws_close(): Error closing WebSocket connection: {type(e).__name__} - {e}")
            finally:
                ws = None
        else:
            _LOGGER.debug(f"{self.vli}ws_close(): No active WebSocket connection to close (ws is None)")

    def ws_check_last_update(self) -> bool:
        if self._ws_LAST_UPDATE + 50 > time.time():
            _LOGGER.debug(f"{self.vli}ws_check_last_update(): all good! [last update: {int(time.time()-self._ws_LAST_UPDATE)} sec ago]")
            return True
        else:
            _LOGGER.info(f"{self.vli}ws_check_last_update(): force reconnect...")
            return False


    # fetching the main data via classic requests...
    async def update_all(self):
        data = await self.req_status()
        if data is not None:
            # Temporarily removed due to Ford backend API changes
            # data["guardstatus"] = await self.hass.async_add_executor_job(self.guard_status)
            msg_data = await self.req_messages()
            if msg_data is not None:
                data[ROOT_MESSAGES] = msg_data

            # only update vehicle data if not present yet
            if self._cached_vehicles_data is None or len(self._cached_vehicles_data) == 0:
                _LOGGER.debug(f"{self.vli}update_all(): request vehicle data...")
                self._cached_vehicles_data = await self.req_vehicles()

            if self._cached_vehicles_data is not None and len(self._cached_vehicles_data) > 0:
                data[ROOT_VEHICLES] = self._cached_vehicles_data

                # we must check if the vehicle supports 'remote climate control'...
                if self._remote_climate_control_supported is None and "vehicleProfile" in self._cached_vehicles_data:
                    for a_vehicle_profile in self._cached_vehicles_data["vehicleProfile"]:
                        if a_vehicle_profile["VIN"] == self.vin:
                            if "remoteClimateControl" in a_vehicle_profile:
                                self._remote_climate_control_supported = a_vehicle_profile["remoteClimateControl"]

                            if "showEVBatteryLevel" in a_vehicle_profile:
                                self._preferred_charge_times_supported = a_vehicle_profile["showEVBatteryLevel"]

                            break

            # only update remote climate data if not present yet
            if self._remote_climate_control_supported:
                if self._cached_rcc_data is None or len(self._cached_rcc_data) == 0:
                    _LOGGER.debug(f"{self.vli}update_all(): request 'remote climate control' data...")
                    self._cached_rcc_data = await self.req_remote_climate()

                if self._cached_rcc_data is not None and len(self._cached_rcc_data) > 0:
                    data[ROOT_REMOTE_CLIMATE_CONTROL] = self._cached_rcc_data

            # only update energy-status if not present yet
            if self._preferred_charge_times_supported:
                if self._cached_pct_data is None or len(self._cached_pct_data) == 0:
                    _LOGGER.debug(f"{self.vli}update_all(): request 'preferred_charge_times' data...")
                    self._cached_pct_data = await self.req_preferred_charge_times()

                if self._cached_pct_data is not None and len(self._cached_pct_data) > 0:
                    data[ROOT_PREFERRED_CHARGE_TIMES] = self._cached_pct_data


            # ok finally store the data in our main data container...
            self._data_container = data

        return data


    async def update_remote_climate_int(self):
        # only update remote climate data if not present yet
        if self._remote_climate_control_supported:
            _LOGGER.debug(f"{self.vli}update_remote_climate_int(): request 'remote climate control' data...")
            self._cached_rcc_data = await self.req_remote_climate()

            if self._cached_rcc_data is not None and len(self._cached_rcc_data) > 0:
                self._data_container[ROOT_REMOTE_CLIMATE_CONTROL] = self._cached_rcc_data


    async def update_preferred_charge_times_int(self):
        # only update remote climate data if not present yet
        if self._preferred_charge_times_supported:
            _LOGGER.debug(f"{self.vli}update_preferred_charge_times_int(): request 'energy transfer status' data...")
            self._cached_pct_data = await self.req_preferred_charge_times()

            if self._cached_pct_data is not None and len(self._cached_pct_data) > 0:
                self._data_container[ROOT_PREFERRED_CHARGE_TIMES] = self._cached_pct_data
                return True

        return False

    async def _ws_debounce_update_preferred_charge_times(self):
        if self._preferred_charge_times_supported:
            try:
                _LOGGER.debug(f"{self.vli}_ws_debounce_update_preferred_charge_times(): started")
                await asyncio.sleep(30)
                _LOGGER.debug(f"{self.vli}_ws_debounce_update_preferred_charge_times(): starting the 'update_preferred_charge_times_int()' update now")
                success = await self.update_preferred_charge_times_int()
                if success and self.coordinator is not None:
                    self.coordinator.async_set_updated_data(self._data_container)

            except CancelledError:
                _LOGGER.debug(f"{self.vli}_ws_debounce_update_preferred_charge_times(): was canceled - all good")
            except BaseException as ex:
                _LOGGER.warning(f"{self.vli}_ws_debounce_update_preferred_charge_times(): Error during 'preferred_charge_times' data refresh - {type(ex).__name__} - {ex}")


    async def req_status(self):
        """Get Vehicle status from API"""
        global _AUTO_FOUR_NULL_ONE_COUNTER
        try:
            # API-Reference?!
            # https://www.high-mobility.com/car-api/ford-data-api
            # https://github.com/mlaanderson/fordpass-api-doc

            await self.__ensure_valid_tokens()
            if self._HAS_COM_ERROR:
                _LOGGER.debug(f"{self.vli}req_status(): - COMM ERROR")
                return None
            else:
                _LOGGER.debug(f"{self.vli}req_status(): - auto_access_token exist? {self.auto_access_token is not None}")

            headers_state = {
                **apiHeaders,
                "authorization": f"Bearer {self.auto_access_token}",
                "Application-Id": self.app_id,
            }
            params_state = {
                "lrdt": "01-01-1970 00:00:00"
            }
            response_state = await self.session.get(
                f"{AUTONOMIC_URL}/telemetry/sources/fordpass/vehicles/{self.vin}",
                params=params_state,
                headers=headers_state,
                timeout=self.timeout
            )

            if response_state.status == 200:
                # ok first resetting the counter for 401 errors (if we had any)
                _AUTO_FOUR_NULL_ONE_COUNTER[self.vin] = 0

                result_state = await response_state.json()
                if self._LOCAL_LOGGING:
                    await self._local_logging("state", result_state)
                return result_state
            elif response_state.status == 401:
                _AUTO_FOUR_NULL_ONE_COUNTER[self.vin] += 1
                if _AUTO_FOUR_NULL_ONE_COUNTER[self.vin] > MAX_401_RESPONSE_COUNT:
                    _LOGGER.error(f"{self.vli}req_status(): status_code: 401 - mark_re_auth_required()")
                    self.mark_re_auth_required()
                else:
                    (_LOGGER.warning if _AUTO_FOUR_NULL_ONE_COUNTER[self.vin] > 2 else _LOGGER.info)(f"{self.vli}req_status(): status_code: 401 - AUTO counter: {_AUTO_FOUR_NULL_ONE_COUNTER}")
                    await asyncio.sleep(5)
                return None
            elif response_state.status == 403:
                try:
                    msg = await response_state.json()
                    if msg is not None and "error" in msg and msg.get("error", "").upper() == "FORBIDDEN":
                        if "message" in msg and "NOT AUTHORIZED TO PERFORM" in msg.get("message", "").upper():
                            _LOGGER.error(f"{self.vli}The vehicle with the VIN '{self.vin}' is not authorized in FordPass - user action required!")
                            return {ROOT_METRICS: {}}

                    # if the message is not the 'NOT AUTHORIZED', then we at least must also return the
                    # default error
                    _LOGGER.debug(f"{self.vli}req_status():  status_code: 403 - response: '{msg}'")
                    self._HAS_COM_ERROR = True
                    return None
                except BaseException as e:
                    _LOGGER.debug(f"{self.vli}req_status():  status_code: 403 - Error while handle 'response' - {type(e).__name__} - {e}")
                    self._HAS_COM_ERROR = True
                    return None
                pass
            else:
                _LOGGER.info(f"{self.vli}req_status(): status_code : {response_state.status} - {response_state.real_url} - Received response: {await response_state.text()}")
                self._HAS_COM_ERROR = True
                return None

        except BaseException as e:
            if not await self.__check_for_closed_session(e):
                _LOGGER.warning(f"{self.vli}req_status(): Error while '_request_token' for vehicle {self.vin} - {type(e).__name__} - {e}")
            else:
                _LOGGER.info(f"{self.vli}req_status(): RuntimeError - Session was closed occurred - but a new Session could be generated")
            self._HAS_COM_ERROR = True
            return None

    async def req_messages(self):
        """Get Vehicle messages from API"""
        global _FOUR_NULL_ONE_COUNTER
        try:
            await self.__ensure_valid_tokens()
            if self._HAS_COM_ERROR:
                _LOGGER.debug(f"{self.vli}messages() - COMM ERROR")
                return None
            else:
                _LOGGER.debug(f"{self.vli}messages() - access_token exist? {self.access_token is not None}")

            headers_msg = {
                **apiHeaders,
                "auth-token": self.access_token,
                "Application-Id": self.app_id,
            }
            response_msg = await self.session.get(f"{FORD_FOUNDATIONAL_API}/messagecenter/v3/messages?", headers=headers_msg, timeout=self.timeout)
            if response_msg.status == 200:
                # ok first resetting the counter for 401 errors (if we had any)
                _FOUR_NULL_ONE_COUNTER[self.vin] = 0

                result_msg = await response_msg.json()
                if self._LOCAL_LOGGING:
                    await self._local_logging("msg", result_msg)

                self._LAST_MESSAGES_UPDATE = time.time()
                return result_msg["result"]["messages"]
            elif response_msg.status == 401:
                _FOUR_NULL_ONE_COUNTER[self.vin] += 1
                if _FOUR_NULL_ONE_COUNTER[self.vin] > MAX_401_RESPONSE_COUNT:
                    _LOGGER.error(f"{self.vli}req_messages(): status_code: 401 - mark_re_auth_required()")
                    self.mark_re_auth_required()
                else:
                    (_LOGGER.warning if _FOUR_NULL_ONE_COUNTER[self.vin] > 2 else _LOGGER.info)(f"{self.vli}req_messages(): status_code: 401 - counter: {_FOUR_NULL_ONE_COUNTER}")
                    await asyncio.sleep(5)
                return None
            else:
                _LOGGER.info(f"{self.vli}req_messages(): status_code: {response_msg.status} - {response_msg.real_url} - Received response: {await response_msg.text()}")
                self._HAS_COM_ERROR = True
                return None

        except BaseException as e:
            if not await self.__check_for_closed_session(e):
                _LOGGER.warning(f"{self.vli}req_messages(): Error while '_request_token' for vehicle {self.vin} - {type(e).__name__} - {e}")
            else:
                _LOGGER.info(f"{self.vli}req_messages(): RuntimeError - Session was closed occurred - but a new Session could be generated")
            self._HAS_COM_ERROR = True
            return None

    async def req_vehicles(self):
        """Get the vehicle list from the ford account"""
        global _FOUR_NULL_ONE_COUNTER
        try:
            await self.__ensure_valid_tokens()
            if self._HAS_COM_ERROR:
                _LOGGER.debug(f"{self.vli}req_vehicles(): - COMM ERROR")
                return None
            else:
                _LOGGER.debug(f"{self.vli}req_vehicles(): - access_token exist? {self.access_token is not None}")

            headers_veh = {
                **apiHeaders,
                "auth-token": self.access_token,
                "Application-Id": self.app_id,
                "countryCode": self.countrycode,
                "locale": self.locale_code
            }
            data_veh = {
                "dashboardRefreshRequest": "All"
            }
            response_veh = await self.session.post(
                f"{FORD_VEHICLE_API}/expdashboard/v1/details/",
                headers=headers_veh,
                data=json.dumps(data_veh),
                timeout=self.timeout
            )
            if response_veh.status == 207 or response_veh.status == 200:
                # ok first resetting the counter for 401 errors (if we had any)
                _FOUR_NULL_ONE_COUNTER[self.vin] = 0

                result_veh = await response_veh.json()
                if self._LOCAL_LOGGING:
                    await self._local_logging("veh", result_veh)

                # creating our logger id for the vehicle...
                if "@" in self.vli and result_veh is not None and "userVehicles" in result_veh and "vehicleDetails" in result_veh["userVehicles"]:
                    self._vehicles = result_veh["userVehicles"]["vehicleDetails"]
                    self._vehicle_name = {}
                    if "vehicleProfile" in result_veh:
                        for a_vehicle in result_veh["vehicleProfile"]:
                            if "VIN" in a_vehicle and "model" in a_vehicle:
                                if self.vin == a_vehicle["VIN"]:
                                    self.vli = f"[{a_vehicle['model']}] "
                                    break
                return result_veh

            elif response_veh.status == 401:
                _FOUR_NULL_ONE_COUNTER[self.vin] += 1
                if _FOUR_NULL_ONE_COUNTER[self.vin] > MAX_401_RESPONSE_COUNT:
                    _LOGGER.error(f"{self.vli}req_vehicles(): status_code: 401 - mark_re_auth_required()")
                    self.mark_re_auth_required()
                else:
                    (_LOGGER.warning if _FOUR_NULL_ONE_COUNTER[self.vin] > 2 else _LOGGER.info)(f"{self.vli}req_vehicles(): status_code: 401 - counter: {_FOUR_NULL_ONE_COUNTER}")
                    await asyncio.sleep(5)

                return None
            else:
                _LOGGER.info(f"{self.vli}req_vehicles: status_code: {response_veh.status} - {response_veh.real_url} - Received response: {await response_veh.text()}")
                self._HAS_COM_ERROR = True
                return None

        except BaseException as e:
            if not await self.__check_for_closed_session(e):
                _LOGGER.warning(f"{self.vli}req_vehicles(): Error while '_request_token' for vehicle {self.vin} - {type(e).__name__} - {e}")
            else:
                _LOGGER.info(f"{self.vli}req_vehicles(): RuntimeError - Session was closed occurred - but a new Session could be generated")
            self._HAS_COM_ERROR = True
            return None

    async def req_remote_climate(self):
        global _FOUR_NULL_ONE_COUNTER
        try:
            await self.__ensure_valid_tokens()
            if self._HAS_COM_ERROR:
                _LOGGER.debug(f"{self.vli}req_remote_climate(): - COMM ERROR")
                return None
            else:
                _LOGGER.debug(f"{self.vli}req_remote_climate(): - access_token exist? {self.access_token is not None}")

            headers_veh = {
                **apiHeaders,
                "auth-token": self.access_token,
                "Application-Id": self.app_id
            }
            data_veh = {
                "vin": self.vin
            }
            response_rcc = await self.session.post(
                f"{FORD_VEHICLE_API}/rcc/profile/status",
                headers=headers_veh,
                data=json.dumps(data_veh),
                timeout=self.timeout
            )
            if response_rcc.status == 200:
                # ok first resetting the counter for 401 errors (if we had any)
                _FOUR_NULL_ONE_COUNTER[self.vin] = 0

                result_rcc = await response_rcc.json()

                # check if there is a 'profile' in the result... and if not, we will create a default one!
                # profiles_obj = result_rcc.get("rccUserProfiles", [])
                # if len(profiles_obj) == 0:
                #     _LOGGER.info(f"{self.vli}req_remote_climate(): creating a default 'remote climate control' profile for vehicle")
                #     result_rcc["rccUserProfiles"] = [
                #         {"preferenceType": "RccHeatedWindshield_Rq", "preferenceValue": "Off"},
                #         {"preferenceType": "RccRearDefrost_Rq", "preferenceValue": "Off"},
                #         {"preferenceType": "RccHeatedSteeringWheel_Rq", "preferenceValue": "Off"},
                #         {"preferenceType": "RccLeftFrontClimateSeat_Rq", "preferenceValue": "Off"},
                #         {"preferenceType": "RccLeftRearClimateSeat_Rq", "preferenceValue": "Off"},
                #         {"preferenceType": "RccRightFrontClimateSeat_Rq", "preferenceValue": "Off"},
                #         {"preferenceType": "RccRightRearClimateSeat_Rq", "preferenceValue": "Off"},
                #         {"preferenceType": "SetPointTemp_Rq", "preferenceValue": "24_0"}
                #     ]

                if self._LOCAL_LOGGING:
                    await self._local_logging("rcc", result_rcc)

                return result_rcc

            elif response_rcc.status == 401:
                _FOUR_NULL_ONE_COUNTER[self.vin] += 1
                if _FOUR_NULL_ONE_COUNTER[self.vin] > MAX_401_RESPONSE_COUNT:
                    _LOGGER.error(f"{self.vli}req_remote_climate(): status_code: 401 - mark_re_auth_required()")
                    self.mark_re_auth_required()
                else:
                    (_LOGGER.warning if _FOUR_NULL_ONE_COUNTER[self.vin] > 2 else _LOGGER.info)(f"{self.vli}req_remote_climate(): status_code: 401 - counter: {_FOUR_NULL_ONE_COUNTER}")
                    await asyncio.sleep(5)

                return None
            else:
                _LOGGER.info(f"{self.vli}req_remote_climate(): status_code: {response_rcc.status} - {response_rcc.real_url} - Received response: {await response_rcc.text()}")
                self._HAS_COM_ERROR = True
                return None

        except BaseException as e:
            if not await self.__check_for_closed_session(e):
                _LOGGER.warning(f"{self.vli}req_remote_climate(): Error while '_request_token' for vehicle {self.vin} - {type(e).__name__} - {e}")
            else:
                _LOGGER.info(f"{self.vli}req_remote_climate(): RuntimeError - Session was closed occurred - but a new Session could be generated")
            self._HAS_COM_ERROR = True
            return None

    async def req_preferred_charge_times(self):
        global _FOUR_NULL_ONE_COUNTER
        try:
            await self.__ensure_valid_tokens()
            if self._HAS_COM_ERROR:
                _LOGGER.debug(f"{self.vli}req_preferred_charge_times(): - COMM ERROR")
                return None
            else:
                _LOGGER.debug(f"{self.vli}req_preferred_charge_times(): - access_token exist? {self.access_token is not None}")

            # and the 'preferred-charge-times' request will get a 'vin' in the header
            headers_veh = {
                **apiHeaders,
                "auth-token": self.access_token,
                "Application-Id": self.app_id,
                "vin": self.vin
            }
            response_pct = await self.session.get(
                f"{FORD_VEHICLE_API}/electrification/experiences/v2/vehicles/preferred-charge-times",
                headers=headers_veh,
                timeout=self.timeout
            )
            if response_pct.status == 200:
                # ok first resetting the counter for 401 errors (if we had any)
                _FOUR_NULL_ONE_COUNTER[self.vin] = 0

                result_pct = await response_pct.json()
                if self._LOCAL_LOGGING:
                    await self._local_logging("pct", result_pct)

                # we are going to transform our result! - we create a dict with the 'location.id' as a key
                if isinstance(result_pct, list):
                    modified_result = {}
                    for a_entry in result_pct:
                        if "vin" in a_entry:
                            if a_entry["vin"].upper() == self.vin.upper():
                                modified_result[a_entry["location"]["id"]] = a_entry
                    result_pct = modified_result
                else:
                    _LOGGER.warning(f"{self.vli}req_preferred_charge_times(): received unexpected data format: {type(result_pct).__name__} - expected a list of entries")

                #_LOGGER.error(f"--------------------------")
                #_LOGGER.error(f"--------------------------")
                #_LOGGER.error(f"{self.vli}req_preferred_charge_times(): received data: {result_pct}")
                #_LOGGER.error(f"--------------------------")
                #_LOGGER.error(f"--------------------------")
                return result_pct

            elif response_pct.status == 401:
                _FOUR_NULL_ONE_COUNTER[self.vin] += 1
                if _FOUR_NULL_ONE_COUNTER[self.vin] > MAX_401_RESPONSE_COUNT:
                    _LOGGER.error(f"{self.vli}req_preferred_charge_times(): status_code: 401 - mark_re_auth_required()")
                    self.mark_re_auth_required()
                else:
                    (_LOGGER.warning if _FOUR_NULL_ONE_COUNTER[self.vin] > 2 else _LOGGER.info)(f"{self.vli}req_preferred_charge_times(): status_code: 401 - counter: {_FOUR_NULL_ONE_COUNTER}")
                    await asyncio.sleep(5)

                return None
            else:
                _LOGGER.info(f"{self.vli}req_preferred_charge_times(): status_code: {response_pct.status} - {response_pct.real_url} - Received response: {await response_pct.text()}")
                self._HAS_COM_ERROR = True
                return None

        except BaseException as e:
            if not await self.__check_for_closed_session(e):
                _LOGGER.warning(f"{self.vli}req_preferred_charge_times(): Error while '_request_token' for vehicle {self.vin} - {type(e).__name__} - {e}")
            else:
                _LOGGER.info(f"{self.vli}req_preferred_charge_times(): RuntimeError - Session was closed occurred - but a new Session could be generated")
            self._HAS_COM_ERROR = True
            return None

    async def req_energy_transfer_status(self):
        # this function will only return a valid object if the vehicle is located at a KNOWN charging location
        global _FOUR_NULL_ONE_COUNTER
        try:
            await self.__ensure_valid_tokens()
            if self._HAS_COM_ERROR:
                _LOGGER.debug(f"{self.vli}req_energy_transfer_status(): - COMM ERROR")
                return None
            else:
                _LOGGER.debug(f"{self.vli}req_energy_transfer_status(): - access_token exist? {self.access_token is not None}")

            # quite funny the energy-transfer-status request will get a 'deviceId' in the header
            # which is actually our VIN...
            headers_veh = {
                **apiHeaders,
                "auth-token": self.access_token,
                "Application-Id": self.app_id,
                "deviceId": self.vin
            }
            response_ets = await self.session.get(
                f"{FORD_VEHICLE_API}/electrification/experiences/v2/devices/energy-transfer-status",
                headers=headers_veh,
                timeout=self.timeout
            )
            if response_ets.status == 200:
                # ok first resetting the counter for 401 errors (if we had any)
                _FOUR_NULL_ONE_COUNTER[self.vin] = 0

                result_ets = await response_ets.json()
                if self._LOCAL_LOGGING:
                    await self._local_logging("ets", result_ets)

                return result_ets

            elif response_ets.status == 401:
                _FOUR_NULL_ONE_COUNTER[self.vin] += 1
                if _FOUR_NULL_ONE_COUNTER[self.vin] > MAX_401_RESPONSE_COUNT:
                    _LOGGER.error(f"{self.vli}req_energy_transfer_status(): status_code: 401 - mark_re_auth_required()")
                    self.mark_re_auth_required()
                else:
                    (_LOGGER.warning if _FOUR_NULL_ONE_COUNTER[self.vin] > 2 else _LOGGER.info)(f"{self.vli}req_energy_transfer_status(): status_code: 401 - counter: {_FOUR_NULL_ONE_COUNTER}")
                    await asyncio.sleep(5)

                return None
            else:
                _LOGGER.info(f"{self.vli}req_energy_transfer_status(): status_code: {response_ets.status} - {response_ets.real_url} - Received response: {await response_ets.text()}")
                self._HAS_COM_ERROR = True
                return None

        except BaseException as e:
            if not await self.__check_for_closed_session(e):
                _LOGGER.warning(f"{self.vli}req_energy_transfer_status(): Error while '_request_token' for vehicle {self.vin} - {type(e).__name__} - {e}")
            else:
                _LOGGER.info(f"{self.vli}req_energy_transfer_status(): RuntimeError - Session was closed occurred - but a new Session could be generated")
            self._HAS_COM_ERROR = True
            return None

    # ***********************************************************
    # ***********************************************************
    # ***********************************************************
    # async def guard_status(self):
    #     """Retrieve guard status from API"""
    #     await self.__ensure_valid_tokens()
    #     if self._HAS_COM_ERROR:
    #         _LOGGER.debug(f"{self.vli}guard_status() - COMM ERROR")
    #         return None
    #     else:
    #         _LOGGER.debug(f"{self.vli}guard_status() - access_token exist? {self.access_token is not None}")
    #
    #     headers_gs = {
    #         **apiHeaders,
    #         "auth-token": self.access_token,
    #         "Application-Id": self.app_id,
    #     }
    #     params_gs = {"lrdt": "01-01-1970 00:00:00"}
    #
    #     response_gs = await self.session.get(
    #         f"{GUARD_URL}/guardmode/v1/{self.vin}/session",
    #         params=params_gs,
    #         headers=headers_gs,
    #         timeout=self.timeout
    #     )
    #     return await response_gs.json()
    #
    # async def enable_guard(self):
    #     """
    #     Enable Guard mode on supported models
    #     """
    #     await self.__ensure_valid_tokens()
    #     if self._HAS_COM_ERROR:
    #         return None
    #
    #     response = self.__make_request(
    #         "PUT", f"{GUARD_URL}/guardmode/v1/{self.vin}/session", None, None
    #     )
    #     _LOGGER.debug(f"{self.vli}enable_guard: {await response.text()}")
    #     return response
    #
    # async def disable_guard(self):
    #     """
    #     Disable Guard mode on supported models
    #     """
    #     await self.__ensure_valid_tokens()
    #     if self._HAS_COM_ERROR:
    #         return None
    #
    #     response = self.__make_request(
    #         "DELETE", f"{GUARD_URL}/guardmode/v1/{self.vin}/session", None, None
    #     )
    #     _LOGGER.debug(f"{self.vli}disable_guard: {await response.text()}")
    #     return response



    # public final GenericCommand<CommandStateActuation> actuationCommand;
    # public final GenericCommand<CommandStateActuation> antiTheft;
    # public final GenericCommand<CommandStateActuation> cancelRemoteStartCommand;
    # public final CommandPreclusion commandPreclusion;
    # public final CustomCommands commands;
    # public final GenericCommand<CommandStateActuation> configurationUpdate;
    # public final GenericCommand<CommandStateActuation> lockCommand;
    # public final GenericCommand<CommandStateActuation> remoteStartCommand;
    # public final GenericCommand<CommandStateActuation> startPanicCue;
    # public final GenericCommand<CommandStateActuation> statusRefreshCommand;
    # public final GenericCommand<CommandStateActuation> unlockCommand;

    # public enum CellularCommand {
    #     START,
    #     EXTEND_START,
    #     STOP,
    #     LOCK,
    #     UNLOCK,
    #     LIGHTS_AND_HORN,
    #     STATUS_REFRESH,
    #     OPEN_MASTER_RESET_WINDOW,
    #     CLOSE_MASTER_RESET_WINDOW,
    #     START_ON_DEMAND_PRECONDITIONING,
    #     EXTEND_ON_DEMAND_PRECONDITIONING,
    #     STOP_ON_DEMAND_PRECONDITIONING,
    #     UPDATE_CHARGE_SETTINGS,
    #     START_GLOBAL_CHARGE,
    #     CANCEL_GLOBAL_CHARGE,
    #     START_TRAILER_LIGHT_CHECK,
    #     STOP_TRAILER_LIGHT_CHECK,
    #     ENABLE_DEPARTURE_TIMES,
    #     DISABLE_DEPARTURE_TIMES,
    #     UPDATE_DEPARTURE_TIMES,
    #     GET_ASU_SETTINGS,
    #     PUBLISH_ASU_SETTINGS,
    #     SEND_OTA_SCHEDULE,
    #     PPO_REFRESH
    # }

    @staticmethod
    def _get_command_object_ford(command_key, url_param_value):
        template = FORD_COMMAND_URL_TEMPLATES.get(command_key, None)
        if template:
            return {"url":      template.format(url_param=url_param_value),
                    "command":  FORD_COMMAND_MAP.get(command_key, None)}
        return None

    # operations
    async def start_charge(self):
        # VALUE_CHARGE, CHARGE_NOW, CHARGE_DT, CHARGE_DT_COND, CHARGE_SOLD, HOME_CHARGE_NOW, HOME_STORE_CHARGE, HOME_CHARGE_DISCHARGE
        # START_GLOBAL_CHARGE
        return await self.__request_and_poll_command_ford(command_key=START_CHARGE_KEY)

    async def cancel_charge(self):
        # CANCEL_GLOBAL_CHARGE
        return await self.__request_and_poll_command_ford(command_key=CANCEL_CHARGE_KEY)

    async def pause_charge(self):
        # PAUSE_GLOBAL_CHARGE
        return await self.__request_and_poll_command_ford(command_key=PAUSE_CHARGE_KEY)

    async def set_zone_lighting(self, target_option:str, current_option=None):
        if target_option is None or str(target_option) == ZONE_LIGHTS_VALUE_OFF:
            return await self.__request_command(command="turnZoneLightsOff")
        else:
            light_is_one = False
            if current_option is not None:
                str_current_option = str(current_option)
                if str_current_option == str(target_option):
                    _LOGGER.debug(f"{self.vli}set_zone_lighting() - target option '{target_option}' is already set, no action required")
                    return True
                elif str_current_option == ZONE_LIGHTS_VALUE_OFF:
                    _LOGGER.debug(f"{self.vli}set_zone_lighting() - target option '{target_option}' to set, but current option is OFF [we MUST turn on the lights first]")
                    light_is_one = await self.__request_command(command="turnZoneLightsOn")
                    if light_is_one:
                        # wait a bit to ensure the lights are on
                        await asyncio.sleep(5)
                else:
                    _LOGGER.debug(f"{self.vli}set_zone_lighting() - target option '{target_option}' to set, current option is '{current_option}' [we just need to switch the mode]")
                    light_is_one = True
            else:
                _LOGGER.debug(f"{self.vli}set_zone_lighting() - target option '{target_option}' to set, but current option is unknown [we assume it's on]")
                light_is_one = True

            if light_is_one:
                return await self.__request_command(command="setZoneLightsMode", post_data={"zone": str(target_option)})
            else:
                _LOGGER.debug(f"{self.vli}set_zone_lighting() - target option '{target_option}' but lights are not on, so we cannot set the option")

        return False

    async def set_charge_target(self, data:dict):
        result = await self.__request_and_poll_command_ford(command_key=SET_CHARGE_TARGET_KEY, post_data=data, include_vin_in_header=True)
        if result:
            _LOGGER.debug(f"{self.vli}set_charge_target() - target charge set successfully")
            # WE WILL NOT trigger an update here, since we have a special handling when the websocket receive a
            # SUCCESS (COMMAND_SUCCEEDED_ON_DEVICE) state update for the 'updateChargeProfilesCommand' there we will
            # trigger an 'asyncio.create_task(self.update_energy_transfer_status_int())'
            # await self.update_energy_transfer_status_int()
        else:
            _LOGGER.info(f"{self.vli}set_charge_target() - setting target charge failed: data that was sent: {data}")
        return result

    async def set_rcc(self, data:dict, result_list:dict):
        result = await self.__request_command(command="setRemoteClimateControl", post_data=data)
        if result:
            _LOGGER.debug(f"{self.vli}set_rcc() - remote_climate_control set successfully")

            if self._cached_rcc_data is not None:
                # we will also update the cached remote climate control data
                self._cached_rcc_data["rccUserProfiles"] = result_list
                if ROOT_REMOTE_CLIMATE_CONTROL not in self._data_container:
                    self._data_container[ROOT_REMOTE_CLIMATE_CONTROL] = {}

                self._data_container[ROOT_REMOTE_CLIMATE_CONTROL] = self._cached_rcc_data
        else:
            _LOGGER.info(f"{self.vli}set_rcc() - remote_climate_control failed: data that was sent: {data}")

        return result

    # NOT USED YET
    # def start_engine(self):
    #     return self.__request_and_poll_command(command="startEngine")
    #
    # def stop(self):
    #     return self.__request_and_poll_command(command="stop")

    async def auto_updates_on(self):
        return await self.__request_and_poll_command_autonomic(baseurl=AUTONOMIC_BETA_URL,
                                                               write_command="publishASUSettingsCommand",
                                                               properties={"ASUState": "ON"})

    async def auto_updates_off(self):
        return await self.__request_and_poll_command_autonomic(baseurl=AUTONOMIC_BETA_URL,
                                                               write_command="publishASUSettingsCommand",
                                                               properties={"ASUState": "OFF"})

    async def remote_start(self):
        await self.update_remote_climate_int()
        return await self.__request_and_poll_command_autonomic(baseurl=AUTONOMIC_URL, write_command="remoteStart")

    async def cancel_remote_start(self):
        return await self.__request_and_poll_command_autonomic(baseurl=AUTONOMIC_URL, write_command="cancelRemoteStart")

    async def lock(self):
        """Issue a lock command to the doors"""
        return await self.__request_and_poll_command_autonomic(baseurl=AUTONOMIC_URL, write_command="lock")

    async def unlock(self):
        """Issue an unlock command to the doors"""
        return await self.__request_and_poll_command_autonomic(baseurl=AUTONOMIC_URL, write_command="unlock")

    def request_update(self):
        """Send request to vehicle for update"""
        status = self.__request_and_poll_command_autonomic(baseurl=AUTONOMIC_URL, write_command="statusRefresh")
        return status


    async def __request_command(self, command:str, post_data=None, vin=None):
        try:
            await self.__ensure_valid_tokens()
            if self._HAS_COM_ERROR:
                _LOGGER.debug(f"{self.vli}__request_command() - COMM ERROR")
                return False
            else:
                _LOGGER.debug(f"{self.vli}__request_command(): access_token exist? {self.access_token is not None}")

            headers = {
                **apiHeaders,
                "auth-token": self.access_token,
                "Application-Id": self.app_id,
            }
            # do we want to overwrite the vin?!
            if vin is None:
                vin = self.vin

            request_type = None
            check_command = None
            if command == "turnZoneLightsOff":
                request_type = "DELETE"
                command_url = f"https://api.mps.ford.com/vehicles/vpfi/zonelightingactivation"
                post_data = {"vin": vin}

            elif command == "turnZoneLightsOn":
                request_type = "PUT"
                command_url = f"https://api.mps.ford.com/vehicles/vpfi/zonelightingactivation"
                post_data = {"vin": vin}

            elif command == "setZoneLightsMode":
                # if we can't get the target mode, we assume the default mode '0' (= ALL)
                target_zone = post_data.get("zone", "0")
                request_type = "PUT"
                command_url = f"https://api.mps.ford.com/vehicles/vpfi/{target_zone}/zonelightingzone"
                post_data = {"vin": vin}

            # remote climate control stuff...
            elif command == "setRemoteClimateControl":
                command_url = f"{FORD_VEHICLE_API}/rcc/profile/update"
                request_type = "PUT"
                # Unfortunately, the PUT request will only return an object like this:
                # {"status": 200} - so there is no id, command_id or anything else present
                # that could be used,to verify if your data update was successful.
                # But I saw in the 'states:commands:publishProfilePreferencesR2Command' - so
                # at the end of the day the request will be received by the vehicle.
                # Using a timestamp will be also not perfect, because we can/will send muliple
                # UpdateProfile requests...
                check_command = "publishProfilePreferencesR2"

            if command_url is None:
                _LOGGER.warning(f"{self.vli}__request_command() - command '{command}' is not supported by the integration")
                return False

            if post_data is not None:
                json_post_data = json.dumps(post_data)
            else:
                json_post_data = None

            if request_type is None or request_type not in ["POST", "PUT", "DELETE"]:
                _LOGGER.warning(f"{self.vli}__request_command() - Unsupported request type '{request_type}' for command '{command}'")
                return False

            req = None
            if request_type == "POST":
                req = await self.session.post(f"{command_url}",
                                              data=json_post_data,
                                              headers=headers,
                                              timeout=self.timeout)
            elif request_type == "PUT":
                req = await self.session.put(f"{command_url}",
                                             data=json_post_data,
                                             headers=headers,
                                             timeout=self.timeout)
            elif request_type == "DELETE":
                req = await self.session.delete(f"{command_url}",
                                                data=json_post_data,
                                                headers=headers,
                                                timeout=self.timeout)

            if req is not None:
                if not (200 <= req.status <= 205):
                    if req.status in (401, 402, 403, 404, 405):
                        _LOGGER.info(f"{self.vli}__request_command(): '{command}' returned '{req.status}' status code - wtf!")
                    else:
                        _LOGGER.warning(f"{self.vli}__request_command(): '{command}' returned unknown status code: {req.status}!")
                    return False

                response = await req.json()
                if self._LOCAL_LOGGING:
                    await self._local_logging("command", response)

                _LOGGER.debug(f"{self.vli}__request_command(): '{command}' response: {response}")

                # not used yet - since we do not have a command_id or similar
                # see: 'elif command == "setRemoteClimateControl":'
                #if check_command is not None:
                #    await self.__wait_for_state(command_id=None, state_command_str=check_command, use_websocket=self.ws_connected)

                return True

        except BaseException as e:
            if not await self.__check_for_closed_session(e):
                _LOGGER.warning(f"{self.vli}Error while '__request_command()' for vehicle '{self.vin}' command: '{command}' post_data: '{post_data}' -> {type(e).__name__} - {e}")
            else:
                _LOGGER.info(f"{self.vli}RuntimeError while '__request_command()' - Session was closed occurred - but a new Session could be generated")

            self._HAS_COM_ERROR = True
            return False

    async def __request_and_poll_command_autonomic(self, baseurl, write_command, properties={}):
        """Send command to the new Command endpoint"""
        try:
            await self.__ensure_valid_tokens()
            if self._HAS_COM_ERROR:
                _LOGGER.debug(f"{self.vli}__request_and_poll_command_autonomic() - COMM ERROR")
                return False
            else:
                _LOGGER.debug(f"{self.vli}__request_and_poll_command_autonomic(): auto_access_token exist? {self.auto_access_token is not None}")

            headers = {
                **apiHeaders,
                "authorization": f"Bearer {self.auto_access_token}",
                "Application-Id": self.app_id # a bit unusual, that Application-id will be provided for an autonomic endpoint?!
            }

            data = {
                "properties": properties,
                "tags": {},
                "type": write_command,
                "version": "1.0.0",
                "wakeUp": True
            }

            # currently only the beta autonomic endpoint supports/needs the version tag
            if baseurl != AUTONOMIC_BETA_URL:
                del data["version"]

            post_req = await self.session.post(f"{baseurl}/command/vehicles/{self.vin}/commands",
                                    data=json.dumps(data),
                                    headers=headers,
                                    timeout=self.timeout
                                    )

            return await self.__request_and_poll_comon(request_obj=post_req,
                                                 state_command_str=write_command,
                                                 use_websocket=self.ws_connected)

        except BaseException as e:
            if not await self.__check_for_closed_session(e):
                _LOGGER.warning(f"{self.vli}Error while '__request_and_poll_command_autonomic()' for vehicle '{self.vin}' command: '{write_command}' props:'{properties}' -> {type(e).__name__} - {e}")
            else:
                _LOGGER.info(f"{self.vli}RuntimeError while '__request_and_poll_command_autonomic()' - Session was closed occurred - but a new Session could be generated")

            self._HAS_COM_ERROR = True
            return False

    async def __request_and_poll_command_ford(self, command_key:str, post_data=None, include_vin_in_header=False):
        try:
            await self.__ensure_valid_tokens()
            if self._HAS_COM_ERROR:
                _LOGGER.debug(f"{self.vli}__request_and_poll_command_ford() - COMM ERROR")
                return False
            else:
                _LOGGER.debug(f"{self.vli}__request_and_poll_command_ford(): access_token exist? {self.access_token is not None}")

            headers = {
                **apiHeaders,
                "auth-token": self.access_token,
                "Application-Id": self.app_id,
            }
            if include_vin_in_header:
                headers["vin"] = self.vin

            if command_key == SET_CHARGE_TARGET_KEY:
                url_param_value = post_data["location"]["id"]
            else:
                url_param_value = self.vin

            a_cmd_obj = self._get_command_object_ford(command_key, url_param_value)
            command_url_part = a_cmd_obj.get("url", None)
            command = a_cmd_obj.get("command", None)

            if command_url_part is None or command is None:
                _LOGGER.warning(f"{self.vli}__request_and_poll_command_ford() - command_key '{command_key}' is not supported by the integration: '{a_cmd_obj}'")
                return False

            if post_data is not None:
                json_post_data = json.dumps(post_data)
            else:
                json_post_data = None

            post_req = await self.session.post(f"{FORD_VEHICLE_API}/{command_url_part}",
                                               data=json_post_data,
                                               headers=headers,
                                               timeout=self.timeout)

            return await self.__request_and_poll_comon(request_obj=post_req,
                                                 state_command_str=command,
                                                 use_websocket=self.ws_connected)

        except BaseException as e:
            if not await self.__check_for_closed_session(e):
                _LOGGER.warning(f"{self.vli}Error while '__request_and_poll_command_ford' for vehicle '{self.vin}' command: '{command}' post_data: '{post_data}' -> {type(e).__name__} - {e}")
            else:
                _LOGGER.info(f"{self.vli}RuntimeError while '__request_and_poll_command_ford' - Session was closed occurred - but a new Session could be generated")

            self._HAS_COM_ERROR = True
            return False

    # async def __request_and_poll_url_command(self, url_command, vin=None):
    #     try:
    #         await self.__ensure_valid_tokens()
    #         if self._HAS_COM_ERROR:
    #             _LOGGER.debug(f"{self.vli}__request_and_poll_url_command() - COMM ERROR")
    #             return False
    #         else:
    #             _LOGGER.debug(f"{self.vli}__request_and_poll_url_command(): access_token exist? {self.access_token is not None}")
    #
    #         headers = {
    #             **apiHeaders,
    #             "auth-token": self.access_token,
    #             "Application-Id": self.app_id,
    #         }
    #         # do we want to overwrite the vin?!
    #         if vin is None:
    #             vin = self.vin
    #
    #         # URL commands wil be posted to ANOTHER endpoint!
    #         req_object = await self.session.post(
    #             f"{FORD_VEHICLE_API}/fordconnect/v1/vehicles/{vin}/{url_command}",
    #             headers=headers,
    #             timeout=self.timeout
    #         )
    #         return await self.__request_and_poll_comon(request_obj=req_object,
    #                                              state_command_str=url_command,
    #                                              use_websocket=self.ws_connected)
    #
    #     except BaseException as e:
    #         if not await self.__check_for_closed_session(e):
    #             _LOGGER.warning(f"{self.vli}Error while '__request_and_poll_url_command' for vehicle '{self.vin}' command: '{url_command}' -> {e}")
    #         else:
    #             _LOGGER.info(f"{self.vli}RuntimeError while '__request_and_poll_url_command' - Session was closed occurred - but a new Session could be generated")
    #
    #         self._HAS_COM_ERROR = True
    #         return False

    async def __request_and_poll_comon(self, request_obj, state_command_str, use_websocket):
        _LOGGER.debug(f"{self.vli}__request_and_poll_comon(): Testing command status: {request_obj.status} (check by {'WebSocket' if use_websocket else 'polling'})")

        if not (200 <= request_obj.status <= 205):
            if request_obj.status in (401, 402, 403, 404, 405):
                _LOGGER.info(f"{self.vli}__request_and_poll_comon(): '{state_command_str}' returned '{request_obj.status}' status code - wtf!")
            else:
                _LOGGER.warning(f"{self.vli}__request_and_poll_comon(): '{state_command_str}' returned unknown status code: {request_obj.status}!")
            return False

        # Extract command ID from response
        command_id = None
        response = await request_obj.json()
        if self._LOCAL_LOGGING:
            await self._local_logging("command+poll", response)

        for id_key in ["id", "commandId", "correlationId"]:
            if id_key in response:
                command_id = response[id_key]
                break

        if command_id is None:
            _LOGGER.warning(f"{self.vli}__request_and_poll_comon(): No command ID found in response: {response}")
            return False

        # ok we have our command reference id, now we can/should wait for a positive state change
        return await self.__wait_for_state(command_id, state_command_str, use_websocket=use_websocket)

    async def __wait_for_state(self, command_id, state_command_str, use_websocket):
        # Wait for backend to process command
        await asyncio.sleep(2)

        # Only set status updates flag when polling
        if not use_websocket:
            self.status_updates_allowed = False

        try:
            i = 0
            while i < 15:
                if i > 0:
                    _LOGGER.debug(f"{self.vli}__wait_for_state(): retry again [count: {i}] waiting for '{state_command_str}' - COMM ERRORS: {self._HAS_COM_ERROR}")

                # Get data based on method
                if use_websocket:
                    updated_data = self._data_container
                else:
                    updated_data = await self.req_status()

                # Check states for command status
                if updated_data is not None and ROOT_STATES in updated_data:
                    states = updated_data[ROOT_STATES]

                    # doing some cleanup of the states dict moving the content of a possible existing
                    # commands dict to the root level
                    if "commands" in states and hasattr(states["commands"], "items"):
                        # Move each command to the root level
                        for cmd_key, cmd_value in states["commands"].items():
                            states[cmd_key] = cmd_value

                        # Remove the original commands dictionary
                        del states["commands"]

                    # ok now we can check if our command is in the (updated) states dict
                    command_key = state_command_str if state_command_str.endswith("Command") else f"{state_command_str}Command"
                    if command_key in states:
                        resp_command_obj = states[command_key]
                        #_LOGGER.debug(f"{self.vli}__wait_for_state(): Found command object")
                        #_LOGGER.info(f"{resp_command_obj}")

                        if command_id is None or ("commandId" in resp_command_obj and resp_command_obj["commandId"] == command_id):
                            #_LOGGER.debug(f"{self.vli}__wait_for_state(): Found the commandId")

                            if "value" in resp_command_obj and "toState" in resp_command_obj["value"]:
                                to_state = resp_command_obj["value"]["toState"].upper()

                                if to_state in ["SUCCESS", "COMMAND_SUCCEEDED_ON_DEVICE"]:
                                    _LOGGER.debug(f"{self.vli}__wait_for_state(): EXCELLENT! Command succeeded")
                                    if not use_websocket:
                                        self.status_updates_allowed = True
                                    return True

                                elif "EXPIRED" == to_state:
                                    _LOGGER.info(f"{self.vli}__wait_for_state(): Command EXPIRED - wait is OVER")
                                    if not use_websocket:
                                        self.status_updates_allowed = True
                                    return False

                                elif "REQUEST_QUEUED" == to_state or "IN_PROGRESS" in to_state:
                                    _LOGGER.debug(f"{self.vli}__wait_for_state(): toState: '{to_state}'")
                                else:
                                    _LOGGER.info(f"{self.vli}__wait_for_state(): UNKNOWN 'toState': {to_state}")
                            else:
                                _LOGGER.debug(f"{self.vli}__wait_for_state(): no 'value' or 'toState' in command object")
                        else:
                            cmd_id = resp_command_obj.get("commandId", "missing")
                            _LOGGER.debug(f"{self.vli}__wait_for_state(): Command ID mismatch: {command_id} vs {cmd_id}")

                i += 1
                a_delay = i * 5
                if self._HAS_COM_ERROR:
                    a_delay = a_delay + 60

                # finally, wait in our loop
                await asyncio.sleep(a_delay)

            # end of while loop reached...
            _LOGGER.info(f"{self.vli}__wait_for_state(): CHECK for '{state_command_str}' unsuccessful after 15 attempts")

        except BaseException as exc:
            if not await self.__check_for_closed_session(exc):
                _LOGGER.warning(f"{self.vli}__wait_for_state(): Error during status checking - {type(exc).__name__} - {exc}")
            else:
                _LOGGER.info(f"{self.vli}__wait_for_state(): RuntimeError - Session was closed occurred - but a new Session could be generated")

        if not use_websocket:
            self.status_updates_allowed = True

        return False