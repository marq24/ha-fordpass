"""Fordpass API Library"""
import asyncio
import json
import logging
import os
import random
import time
import traceback
from asyncio import CancelledError
from numbers import Number
from typing import Final

import aiohttp
from aiohttp import ClientConnectorError, ClientConnectionError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.fordpass.const import REGIONS
from custom_components.fordpass.fordpass_handler import (
    ROOT_STATES,
    ROOT_EVENTS,
    ROOT_METRICS,
    ROOT_MESSAGES,
    ROOT_VEHICLES,
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

BASE_URL: Final = "https://usapi.cv.ford.com/api"
GUARD_URL: Final = "https://api.mps.ford.com/api"
SSO_URL: Final = "https://sso.ci.ford.com"
AUTONOMIC_URL: Final = "https://api.autonomic.ai/v1"
AUTONOMIC_WS_URL: Final = "wss://api.autonomic.ai/v1beta"
AUTONOMIC_ACCOUNT_URL: Final = "https://accounts.autonomic.ai/v1"
FORD_LOGIN_URL: Final = "https://login.ford.com"
FORD_VEHICLE_API: Final = "https://api.vehicle.ford.com/api"
ERROR: Final = "ERROR"

#session = None #requests.Session()

# we need global variables to keep track of the number of 401 responses per user account(=token file)
_FOUR_NULL_ONE_COUNTER: dict = {}
_AUTO_FOUR_NULL_ONE_COUNTER: dict = {}

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
    __ws_debounced_full_refresh_task: asyncio.Task | None = None

    def __init__(self, web_session, username, vin, region_key, coordinator: DataUpdateCoordinator = None,
                 save_token=False, tokens_location=None):
        self.session = web_session
        self.timeout = aiohttp.ClientTimeout(
            total=45,      # Total request timeout
            connect=30,    # Connection timeout
            sock_connect=30,
            sock_read=120   # Socket read timeout
        )
        self.username = username
        self.save_token = save_token
        self.app_id = REGIONS[region_key]["app_id"]
        self.locale_code = REGIONS[region_key]["locale"]
        self.countrycode = REGIONS[region_key]["countrycode"]
        self.vin = vin

        self._HAS_COM_ERROR = False
        global _FOUR_NULL_ONE_COUNTER
        _FOUR_NULL_ONE_COUNTER[self.username] = 0
        self.access_token = None
        self.refresh_token = None
        self.expires_at = None

        global _AUTO_FOUR_NULL_ONE_COUNTER
        _AUTO_FOUR_NULL_ONE_COUNTER[self.username] = 0
        self.auto_access_token = None
        self.auto_refresh_token = None
        self.auto_expires_at = None

        # by default, we try to read the token from the file system
        self.use_token_data_from_memory = False

        if tokens_location is None:
            self.stored_tokens_location = f".storage/fordpass/{username}_access_token.txt"
        else:
            self.stored_tokens_location = tokens_location

        self._is_reauth_required = False
        self.status_updates_allowed = True

        # our main data container that holds all data that have been fetched from the vehicle
        self._data_container = {}
        self._cached_vehicles_data = {}
        self.coordinator = coordinator

        # websocket connection related variables
        self._ws_debounced_update_task = None
        self._ws_debounced_full_refresh_task = None
        self._ws_in_use_access_token = None
        self.ws_connected = False
        self._ws_LAST_UPDATE = 0
        self._last_ignition_state = INTEGRATION_INIT

        _LOGGER.info(f"init vehicle object for vin: '{self.vin}' - using token from: {tokens_location}")

    def clear_data(self):
        self._cached_vehicles_data = {}
        self._data_container = {}

    async def generate_tokens(self, urlstring, code_verifier):
        _LOGGER.debug(f"generate_tokens() for country_code: {self.locale_code}")
        code_new = urlstring.replace("fordapp://userauthorized/?code=", "")
        headers = {
            **loginHeaders,
        }
        data = {
            "client_id": "09852200-05fd-41f6-8c21-d36d3497dc64",
            "grant_type": "authorization_code",
            "code_verifier": code_verifier,
            "code": code_new,
            "redirect_uri": "fordapp://userauthorized"
        }
        response = await self.session.post(
            f"{FORD_LOGIN_URL}/4566605f-43a7-400a-946e-89cc9fdb0bd7/B2C_1A_SignInSignUp_{self.locale_code}/oauth2/v2.0/token",
            headers=headers,
            data=data,
            ssl=True
        )

        # do not check the status code here - since it's not always return http 200!
        token_data = await response.json()
        if "access_token" in token_data:
            _LOGGER.debug(f"generate_tokens 'OK'- http status: {response.status} - JSON: {token_data}")
            return await self.generate_tokens_part2(token_data)
        else:
            _LOGGER.warning(f"generate_tokens 'FAILED'- http status: {response.status} - cause no 'access_token' in response: {token_data}")
            return False

    async def generate_tokens_part2(self, token):
        headers = {**apiHeaders, "Application-Id": self.app_id}
        data = {"idpToken": token["access_token"]}
        response = await self.session.post(
            f"{GUARD_URL}/token/v2/cat-with-b2c-access-token",
            data=json.dumps(data),
            headers=headers,
            ssl=True
        )

        # do not check the status code here - since it's not always return http 200!
        final_access_token = await response.json()
        if "expires_in" in final_access_token:
            final_access_token["expiry_date"] = time.time() + final_access_token["expires_in"]
            del final_access_token["expires_in"]

        if "refresh_expires_in" in final_access_token:
            final_access_token["refresh_expiry_date"] = time.time() + final_access_token["refresh_expires_in"]
            del final_access_token["refresh_expires_in"]

        _LOGGER.debug(f"generate_tokens_part2 'OK' - http status: {response.status} - JSON: {final_access_token}")
        if self.save_token:
            await self._write_token_to_storage(final_access_token)

        return True

    @property
    def require_reauth(self) -> bool:
        return self._is_reauth_required

    def mark_re_auth_required(self, ws=None):
        stack_trace = traceback.format_stack()
        stack_trace_str = ''.join(stack_trace[:-1])  # Exclude the call to this function
        _LOGGER.warning(f"mark_re_auth_required() called!!! -> stack trace:\n{stack_trace_str}")
        self.ws_close(ws)
        self._is_reauth_required = True

    async def __ensure_valid_tokens(self, now_time:float=None):
        # Fetch and refresh token as needed
        _LOGGER.debug("__ensure_valid_tokens()")
        self._HAS_COM_ERROR = False
        # If a file exists, read in the token file and check it's valid
        if self.save_token:
            # do not access every time the file system - since we are the only one
            # using the vehicle object, we can keep the token in memory (and
            # invalidate it if needed)
            if (not self.use_token_data_from_memory) and os.path.isfile(self.stored_tokens_location):
                prev_token_data = await self._read_token_from_storage()
                if prev_token_data is None:
                    # no token data could be read!
                    _LOGGER.info("__ensure_valid_tokens: Tokens are INVALID!!! - mark_re_auth_required() should have occurred?")
                    return

                self.use_token_data_from_memory = True
                _LOGGER.debug(f"__ensure_valid_tokens: token data read from fs - size: {len(prev_token_data)}")

                self.access_token = prev_token_data["access_token"]
                self.refresh_token = prev_token_data["refresh_token"]
                self.expires_at = prev_token_data["expiry_date"]

                if "auto_token" in prev_token_data and "auto_refresh_token" in prev_token_data and "auto_expiry_date" in prev_token_data:
                    self.auto_access_token = prev_token_data["auto_token"]
                    self.auto_refresh_token = prev_token_data["auto_refresh_token"]
                    self.auto_expires_at = prev_token_data["auto_expiry_date"]
                else:
                    _LOGGER.debug("__ensure_valid_tokens: auto-token not set (or incomplete) in file")
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
        else:
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
            _LOGGER.debug(f"__ensure_valid_tokens: token's expires_at {self.expires_at} has expired time-delta: {int(now_time - self.expires_at)} sec -> requesting new token")
            refreshed_token = await self.refresh_token_func(prev_token_data)
            if self._HAS_COM_ERROR:
                _LOGGER.warning(f"__ensure_valid_tokens: skipping 'auto_token_refresh' - COMM ERROR")
            else:
                if refreshed_token is not None and refreshed_token is not False and refreshed_token != ERROR:
                    _LOGGER.debug(f"__ensure_valid_tokens: result for new token: {len(refreshed_token)}")
                    await self.refresh_auto_token_func(refreshed_token)
                else:
                    _LOGGER.warning(f"__ensure_valid_tokens: result for new token: ERROR, None or False")

        if self.auto_access_token is None or self.auto_expires_at is None:
            _LOGGER.debug(f"__ensure_valid_tokens: auto_access_token: '{self.auto_access_token}' or auto_expires_at: '{self.auto_expires_at}' is None -> requesting new auto-token")
            await self.refresh_auto_token_func(prev_token_data)

        if self.auto_expires_at and now_time > self.auto_expires_at:
            _LOGGER.debug(f"__ensure_valid_tokens: auto-token's auto_expires_at {self.auto_expires_at} has expired time-delta: {int(now_time - self.auto_expires_at)} sec -> requesting new auto-token")
            await self.refresh_auto_token_func(prev_token_data)

        # it could be that there has been 'exceptions' when trying to update the tokens
        if self._HAS_COM_ERROR:
            _LOGGER.warning("__ensure_valid_tokens: COMM ERROR")
        else:
            if self.access_token is None:
                _LOGGER.warning("__ensure_valid_tokens: self.access_token is None! - but we don't do anything now [the '_request_token()' or '_request_auto_token()' will trigger mark_re_auth_required() when this is required!]")
            else:
                _LOGGER.debug("__ensure_valid_tokens: Tokens are valid")

    async def refresh_token_func(self, prev_token_data):
        """Refresh token if still valid"""
        _LOGGER.debug(f"refresh_token_func()")

        token_data = await self._request_token(prev_token_data)
        if token_data is None or token_data is False:
            self.access_token = None
            self.refresh_token = None
            self.expires_at = None

            # also invalidating the auto-tokens...
            self.auto_access_token = None
            self.auto_refresh_token = None
            self.auto_expires_at = None
            _LOGGER.warning(f"refresh_token_func: FAILED!")

        elif token_data == ERROR:
            _LOGGER.warning(f"refresh_token_func: COMM ERROR")
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

            if self.save_token:
                await self._write_token_to_storage(token_data)

            self.access_token = token_data["access_token"]
            self.refresh_token = token_data["refresh_token"]
            self.expires_at = token_data["expiry_date"]

            _LOGGER.debug("refresh_token_func: OK")
            return token_data

    async def _request_token(self, prev_token_data):
        global _FOUR_NULL_ONE_COUNTER
        if self._HAS_COM_ERROR:
            return ERROR
        else:
            try:
                _LOGGER.debug(f"_request_token() - {_FOUR_NULL_ONE_COUNTER[self.username]}")

                headers = {
                    **apiHeaders,
                    "Application-Id": self.app_id
                }
                data = {
                    "refresh_token": prev_token_data["refresh_token"]
                }
                response = await self.session.post(
                    f"{GUARD_URL}/token/v2/cat-with-refresh-token",
                    data=json.dumps(data),
                    headers=headers,
                    timeout=self.timeout
                )

                if response.status == 200:
                    # ok first resetting the counter for 401 errors (if we had any)
                    _FOUR_NULL_ONE_COUNTER[self.username] = 0
                    result = await response.json()
                    _LOGGER.debug(f"_request_token: status OK")
                    return result
                elif response.status == 401 or response.status == 400:
                    _FOUR_NULL_ONE_COUNTER[self.username] += 1
                    if _FOUR_NULL_ONE_COUNTER[self.username] > MAX_401_RESPONSE_COUNT:
                        _LOGGER.error(f"_request_token: status_code: {response.status} - mark_re_auth_required()")
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
                                _LOGGER.warning(f"_request_token: status_code: {response.status} - TOKEN HAS BEEN INVALIDATED")
                                _FOUR_NULL_ONE_COUNTER[self.username] = MAX_401_RESPONSE_COUNT + 1
                        except BaseException as e:
                            _LOGGER.debug(f"_request_token: status_code: {response.status} - could not read from response - {type(e)} - {e}")

                        _LOGGER.warning(f"_request_token: status_code: {response.status} - counter: {_FOUR_NULL_ONE_COUNTER}")
                        await asyncio.sleep(5)
                    return False
                else:
                    _LOGGER.info(f"_request_token: status_code: {response.status} - Received response: {await response.text()}")
                    self._HAS_COM_ERROR = True
                    return ERROR

            except BaseException as e:
                _LOGGER.warning(f"Error while '_request_token' for vehicle {self.vin} - {type(e)} - {e}")
                self._HAS_COM_ERROR = True
                return ERROR

    async def refresh_auto_token_func(self, cur_token_data):
        _LOGGER.debug(f"refresh_auto_token_func()")
        auto_token = await self._request_auto_token()
        if auto_token is None or auto_token is False:
            self.auto_access_token = None
            self.auto_refresh_token = None
            self.auto_expires_at = None
            _LOGGER.warning(f"refresh_auto_token_func: FAILED!")

        elif auto_token == ERROR:
            _LOGGER.warning(f"refresh_auto_token_func: COMM ERROR")
        else:
            # it looks like that the auto token could be requested successfully...
            if "expires_in" in auto_token:
                # re-write the 'expires_in' to 'expiry_date'...
                auto_token["expiry_date"] = time.time() + auto_token["expires_in"]
                del auto_token["expires_in"]

            if "refresh_expires_in" in auto_token:
                auto_token["refresh_expiry_date"] = time.time() + auto_token["refresh_expires_in"]
                del auto_token["refresh_expires_in"]

            if self.save_token:
                cur_token_data["auto_token"] = auto_token["access_token"]
                cur_token_data["auto_refresh_token"] = auto_token["refresh_token"]
                cur_token_data["auto_expiry_date"] = auto_token["expiry_date"]

                await self._write_token_to_storage(cur_token_data)

            # finally, setting our internal values...
            self.auto_access_token = auto_token["access_token"]
            self.auto_refresh_token = auto_token["refresh_token"]
            self.auto_expires_at = auto_token["expiry_date"]

            _LOGGER.debug("refresh_auto_token_func: OK")

    async def _request_auto_token(self):
        """Get token from new autonomic API"""
        global _AUTO_FOUR_NULL_ONE_COUNTER
        if self._HAS_COM_ERROR:
            return ERROR
        else:
            try:
                _LOGGER.debug("_request_auto_token()")
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
                    _AUTO_FOUR_NULL_ONE_COUNTER[self.username] = 0

                    result = await response.json()
                    _LOGGER.debug(f"_request_auto_token: status OK")
                    return result
                elif response.status == 401:
                    _AUTO_FOUR_NULL_ONE_COUNTER[self.username] += 1
                    if _AUTO_FOUR_NULL_ONE_COUNTER[self.username] > MAX_401_RESPONSE_COUNT:
                        _LOGGER.error(f"_request_auto_token: status_code: 401 - mark_re_auth_required()")
                        self.mark_re_auth_required()
                    else:
                        _LOGGER.warning(f"_request_auto_token: status_code: 401 - AUTO counter: {_AUTO_FOUR_NULL_ONE_COUNTER}")
                        await asyncio.sleep(5)

                    return False
                else:
                    _LOGGER.info(f"_request_auto_token: status_code: {response.status} - Received response: {await response.text()}")
                    self._HAS_COM_ERROR = True
                    return ERROR

            except BaseException as e:
                _LOGGER.warning(f"Error while '_request_auto_token' for vehicle {self.vin} - {type(e)} - {e}")
                self._HAS_COM_ERROR = True
                return ERROR

    async def _write_token_to_storage(self, token):
        """Save token to file for reuse"""
        _LOGGER.debug(f"_write_token_to_storage()")

        # Check if the parent directory exists
        directory = os.path.dirname(self.stored_tokens_location)
        if not os.path.exists(directory):
            try:
                await asyncio.get_running_loop().run_in_executor(None, lambda: os.makedirs(directory))
            except OSError as exc:
                # Handle exception as before
                pass

        # Write the file in executor
        await asyncio.get_running_loop().run_in_executor(None, lambda: self.__write_token_int(token))

        # Make sure that we will read the token data next time
        self.use_token_data_from_memory = False

    def __write_token_int(self, token):
        """Synchronous method to write token file, called from executor."""
        with open(self.stored_tokens_location, "w", encoding="utf-8") as outfile:
            json.dump(token, outfile)

    async def _read_token_from_storage(self):
        """Read saved token from a file"""
        _LOGGER.debug(f"_read_token_from_storage()")
        try:
            # Run blocking file operation in executor
            token_data = await asyncio.get_running_loop().run_in_executor(None, self.__read_token_int)
            return token_data
        except ValueError:
            _LOGGER.warning("_read_token_from_storage: 'ValueError' invalidate TOKEN FILE -> mark_re_auth_required()")
            self.mark_re_auth_required()
        return None

    def __read_token_int(self):
        """Synchronous method to read the token file, called from executor."""
        with open(self.stored_tokens_location, encoding="utf-8") as token_file:
            return json.load(token_file)

    def clear_token(self):
        _LOGGER.debug(f"clear_token()")
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
        _LOGGER.debug(f"ws_connect() STARTED...")
        self.ws_connected = False
        await self.__ensure_valid_tokens()
        if self._HAS_COM_ERROR:
            _LOGGER.debug(f"ws_connect() - COMM ERROR - skipping WebSocket connection")
            return None
        else:
            _LOGGER.debug(f"ws_connect() - auto_access_token exist? {self.auto_access_token is not None}")

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

                _LOGGER.info(f"connected to websocket: {web_socket_url}")
                async for msg in ws:
                    # store the last time we heard from the websocket
                    self._ws_LAST_UPDATE = time.time()

                    new_data_arrived = False
                    do_housekeeping_checks = False
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            ws_data = msg.json()
                            if ws_data is None or len(ws_data) == 0:
                                _LOGGER.debug(f"ws_connect(): received empty 'data': '{ws_data}'")
                                do_housekeeping_checks = True
                            else:
                                if "_httpStatus" in ws_data:
                                    status = int(ws_data["_httpStatus"])
                                    if 200 <= status < 300:
                                        if status == 202:
                                            # it looks like we have sent a new access token... and the backend just
                                            # replied with an HTTP status code...
                                            self._ws_in_use_access_token = self.auto_access_token
                                            _LOGGER.debug(f"ws_connect(): received HTTP status 202 - auto token update accepted")
                                        else:
                                            _LOGGER.debug(f"ws_connect(): received HTTP status: {status} - OK")

                                elif "_error" in ws_data:
                                    # in case of any error, we simply close the websocket connection
                                    _LOGGER.info(f"ws_connect(): error object read: {ws_data["_error"]}")
                                    break

                                    # err_obj = ws_data["_error"]
                                    # err_handled = False
                                    # if "code" in err_obj and err_obj["code"] == 401:
                                    #     if "message" in err_obj:
                                    #         lower_msg = err_obj['message'].lower()
                                    #         if 'provided token was expired' in lower_msg:
                                    #             _LOGGER.debug(f"ws_connect(): 'provided token was expired' expired - going to auto-reconnect-loop")
                                    #             self.ws_do_reconnect = True
                                    #             err_handled = True
                                    #         if 'websocket session expired' in lower_msg:
                                    #             _LOGGER.debug(f"ws_connect(): 'websocket session expired' - going to auto-reconnect-loop")
                                    #             self.ws_do_reconnect = True
                                    #             err_handled = True
                                    #
                                    # if not err_handled:
                                    #     _LOGGER.error(f"ws_connect(): unknown error object read: {err_obj}")

                                elif "_data" in ws_data:
                                    data_obj = ws_data["_data"]
                                    new_data_arrived = self._ws_handle_data(data_obj)
                                    if new_data_arrived is False:
                                        _LOGGER.debug(f"ws_connect(): received unknown 'data': {data_obj}")
                                    else:
                                        _LOGGER.debug(f"ws_connect(): received vehicle 'data'")
                                else:
                                    _LOGGER.info(f"ws_connect(): unknown 'content': {ws_data}")

                        except Exception as e:
                            _LOGGER.debug(f"Could not read JSON from: {msg} - caused {e}")

                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        _LOGGER.debug(f"received CLOSED or ERROR - will terminate websocket session: {msg}")
                        break

                    else:
                        _LOGGER.error(f"Unknown Message Type from: {msg}")

                    # do we need to push new data event to the coordinator?
                    if new_data_arrived:
                        self._ws_notify_for_new_data()

                    if do_housekeeping_checks:
                        # check if we need to update the messages...
                        await self._ws_check_for_message_update_required()

                        # check if we need to refresh the auto token...
                        await self._ws_check_for_auth_token_refresh(ws)

        except ClientConnectorError as con:
            _LOGGER.error(f"ws_connect(): Could not connect to websocket: {type(con)} - {con}")
        except ClientConnectionError as err:
            _LOGGER.error(f"ws_connect(): ??? {type(err)} - {err}")
        except asyncio.TimeoutError as time_exc:
            _LOGGER.debug(f"ws_connect(): TimeoutError: No WebSocket message received within timeout period")
        except CancelledError as canceled:
            _LOGGER.info(f"ws_connect(): Terminated? - {type(canceled)} - {canceled}")
        except BaseException as x:
            _LOGGER.error(f"ws_connect(): !!! {type(x)} - {x}")

        _LOGGER.debug(f"ws_connect() ENDED")
        try:
            await self.ws_close(ws)
        except UnboundLocalError as is_unbound:
            _LOGGER.debug(f"ws_connect(): skipping ws_close() (since ws is unbound)")
        except BaseException as e:
            _LOGGER.error(f"ws_connect(): Error while calling ws_close(): {type(e)} - {e}")

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

            #_LOGGER.info(f"ws(): NEW ignition state '{new_ignition_state}' | LAST ignition state: '{self._last_ignition_state}'")
            if self._last_ignition_state != INTEGRATION_INIT:
                if "OFF" == new_ignition_state and new_ignition_state != self._last_ignition_state:
                    if self._ws_debounced_full_refresh_task is not None and not self._ws_debounced_full_refresh_task.done():
                        self._ws_debounced_full_refresh_task.cancel()
                    _LOGGER.debug(f"ws(): ignition state changed to 'OFF' -> triggering full data update (will be started in 30sec)")
                    self._ws_debounced_full_refresh_task = asyncio.create_task(self._ws_debounce_full_data_refresh())

                elif "ON" == new_ignition_state:
                    # cancel any running the full refresh task if the new state is 'ON'...
                    if self._ws_debounced_full_refresh_task is not None and not self._ws_debounced_full_refresh_task.done():
                        _LOGGER.debug(f"ws(): ignition state changed to 'ON' -> canceling any running full refresh task")
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
                    if "value" in a_state_obj:
                        a_value_obj = a_state_obj["value"]
                        if "toState" in a_value_obj:
                            _LOGGER.debug(f"ws(): new state '{a_state_name}' arrived -> toState: {a_value_obj["toState"]}")
                            if a_value_obj["toState"].lower() == "success":
                                if ROOT_METRICS in a_value_obj:
                                    self._ws_update_key(a_value_obj, ROOT_METRICS, collected_keys)
                                    _LOGGER.debug(f"ws(): extracted '{ROOT_METRICS}' update from new 'success' state: {a_value_obj[ROOT_METRICS]}")
                        else:
                            _LOGGER.debug(f"ws(): new state (without toState) '{a_state_name}' arrived: {a_value_obj}")
                    else:
                        _LOGGER.debug(f"ws(): new state (without value) '{a_state_name}' arrived")

            # If we don't have states yet in the existing data, initialize it
            if a_root_key not in self._data_container:
                self._data_container[a_root_key] = {}

            # Update only the specific keys (e.g. if only one state is present) that are in the new data
            if hasattr(data_obj[a_root_key], "items"):
                for a_key_name, a_key_value in data_obj[a_root_key].items():
                    # for 'ROOT_METRICS' we must merge 'customMetrics'
                    # and for 'ROOT_EVENTS' we must merge 'customEvents'
                    if (a_root_key == ROOT_METRICS and a_key_name == "customMetrics") or (
                            a_root_key == ROOT_EVENTS and a_key_name == "customEvents"):
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
                _LOGGER.info(f"ws(): this is a 'heartbeat': {data_obj[a_root_key]} {collected_keys}")

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
    #                     _LOGGER.debug(f"ws(): new state '{a_state_name}' arrived -> toState: {a_value_obj["toState"]}")
    #                     if a_value_obj["toState"].lower() == "success":
    #                         if ROOT_METRICS in a_value_obj:
    #                             self._ws_update_key(a_value_obj, ROOT_METRICS, collected_keys)
    #                             _LOGGER.debug(f"ws(): extracted '{ROOT_METRICS}' update from new 'success' state: {a_value_obj[ROOT_METRICS]}")
    #                 else:
    #                     _LOGGER.debug(f"ws(): new state (without toState) '{a_state_name}' arrived: {a_value_obj}")
    #             else:
    #                 _LOGGER.debug(f"ws(): new state (without value) '{a_state_name}' arrived")
    #
    #         # core - merge recursive the dicts
    #         if a_root_key in self._data_container:
    #             self._ws_merge_dict_recursive(self._data_container[a_root_key], data_obj[a_root_key], collected_keys, prefix=None)
    #         else:
    #             self._data_container[a_root_key] = data_obj[a_root_key]
    #
    #         # just some post-processing (logging)
    #         if a_root_key == ROOT_UPDTIME:
    #             _LOGGER.info(f"ws(): this is a 'heartbeat': {data_obj[a_root_key]} {collected_keys}")
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
                _LOGGER.debug(f"_ws_check_for_auth_token_refresh(): auto token expires in less than 45 seconds - try to refresh")

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
                    _LOGGER.debug(f"_ws_check_for_auth_token_refresh(): auto token has been refreshed -> update websocket")
                    await ws.send_json({"accessToken": self.auto_access_token})
            else:
                _LOGGER.info(f"_ws_check_for_auth_token_refresh(): 'self.auto_access_token' is None (might be cause of 401 error), we will close the websocket connection and wait for the watchdog to reconnect")
                await self.ws_close(ws)
                # if self.save_token:
                #     stored_token = await self._read_token_from_storage()
                #     if stored_token is not None and "auto_token" in stored_token:
                #         self.auto_access_token = stored_token["auto_token"]
                #         self.auto_refresh_token = stored_token["auto_refresh_token"]
                #         self.auto_expires_at = stored_token["auto_expiry_date"]
                #         _LOGGER.debug(f"_ws_check_for_auth_token_refresh(): auto token re-read from storage")

        except BaseException as e:
            _LOGGER.error(f"_ws_check_for_auth_token_refresh(): Error while refreshing auto token - {type(e)} - {e}")

    async def _ws_check_for_message_update_required(self):
        update_interval = 0
        if self.coordinator is not None:
            update_interval = int(self.coordinator.update_interval.total_seconds())

        to_wait_till = self._LAST_MESSAGES_UPDATE + max(update_interval, 15 * 60)
        if to_wait_till < time.time():
            _LOGGER.debug(f"_ws_check_for_message_update_required(): a update of the messages is required [last update was: {round((time.time() - self._LAST_MESSAGES_UPDATE) / 60, 1)} min ago]")
            # we need to update the messages...
            msg_data = await self.messages()
            if msg_data is not None:
                self._data_container[ROOT_MESSAGES] = msg_data
                self._ws_notify_for_new_data()
        else:
            _LOGGER.debug(f"_ws_check_for_message_update_required(): no update required [wait for: {round((to_wait_till - time.time())/60, 1)} min]")

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
            _LOGGER.debug(f"_ws_debounce_full_data_refresh(): started")
            await asyncio.sleep(30)
            count = 0
            while not self.status_updates_allowed and count < 11:
                _LOGGER.debug(f"_ws_debounce_full_data_refresh(): waiting for status updates to be allowed... retry: {count}")
                count += 1
                await asyncio.sleep(random.uniform(2, 30))

            _LOGGER.debug(f"_ws_debounce_full_data_refresh(): starting the full update now")
            updated_data = await self.update_all()
            if updated_data is not None and self.coordinator is not None:
                self.coordinator.async_set_updated_data(self._data_container)
        except CancelledError:
            _LOGGER.debug(f"_ws_debounce_full_data_refresh(): was canceled - all good")
        except BaseException as ex:
            _LOGGER.warning(f"_ws_debounce_full_data_refresh(): Error during full data refresh - {type(ex)} - {ex}")

    async def ws_close(self, ws):
        """Close the WebSocket connection cleanly."""
        _LOGGER.debug(f"ws_close(): for {self.vin} called")
        self.ws_connected = False
        if ws is not None:
            try:
                await ws.close()
                _LOGGER.debug("ws_close(): connection closed successfully")
            except BaseException as e:
                _LOGGER.info(f"ws_close(): Error closing WebSocket connection: {type(e)} - {e}")
            finally:
                ws = None
        else:
            _LOGGER.debug("ws_close(): No active WebSocket connection to close (ws is None)")

    def ws_check_last_update(self) -> bool:
        if self._ws_LAST_UPDATE + 50 > time.time():
            _LOGGER.debug(f"ws_check_last_update(): all good! [last update: {int(time.time()-self._ws_LAST_UPDATE)} sec ago]")
            return True
        else:
            _LOGGER.info(f"ws_check_last_update(): force reconnect...")
            return False


    # fetching the main data via classic requests...
    async def update_all(self):
        data = await self.status()
        if data is not None:
            # Temporarily removed due to Ford backend API changes
            # data["guardstatus"] = await self.hass.async_add_executor_job(self.vehicle.guardStatus)
            msg_data = await self.messages()
            if msg_data is not None:
                data[ROOT_MESSAGES] = msg_data

            # only update vehicle data if not present yet
            if self._cached_vehicles_data is None or len(self._cached_vehicles_data) == 0:
                _LOGGER.debug("update_all: request vehicle data...")
                self._cached_vehicles_data = await self.vehicles()

            if self._cached_vehicles_data is not None and len(self._cached_vehicles_data) > 0:
                data[ROOT_VEHICLES] = self._cached_vehicles_data

            # ok finally store the data in our main data container...
            self._data_container = data

        return data

    async def status(self):
        """Get Vehicle status from API"""
        global _AUTO_FOUR_NULL_ONE_COUNTER
        try:
            # API-Reference?!
            # https://www.high-mobility.com/car-api/ford-data-api
            # https://github.com/mlaanderson/fordpass-api-doc

            await self.__ensure_valid_tokens()
            if self._HAS_COM_ERROR:
                _LOGGER.debug(f"status() - COMM ERROR")
                return None
            else:
                _LOGGER.debug(f"status() - auto_access_token exist? {self.auto_access_token is not None}")

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
                _AUTO_FOUR_NULL_ONE_COUNTER[self.username] = 0

                result_state = await response_state.json()
                if LOG_DATA:
                    _LOGGER.debug(f"status: JSON: {result_state}")
                return result_state
            elif response_state.status == 401:
                _AUTO_FOUR_NULL_ONE_COUNTER[self.username] += 1
                if _AUTO_FOUR_NULL_ONE_COUNTER[self.username] > MAX_401_RESPONSE_COUNT:
                    _LOGGER.error(f"status: status_code: 401 - mark_re_auth_required()")
                    self.mark_re_auth_required()
                else:
                    _LOGGER.warning(f"status: status_code: 401 - AUTO counter: {_AUTO_FOUR_NULL_ONE_COUNTER}")
                    await asyncio.sleep(5)

                return None
            else:
                _LOGGER.info(f"status: status_code : {response_state.status} - Received response: {await response_state.text()}")
                self._HAS_COM_ERROR = True
                return None

        except BaseException as e:
            _LOGGER.warning(f"Error while fetching status for vehicle {self.vin} - {type(e)} - {e}")
            self._HAS_COM_ERROR = True
            return None

    async def messages(self):
        """Get Vehicle messages from API"""
        global _FOUR_NULL_ONE_COUNTER
        try:
            await self.__ensure_valid_tokens()
            if self._HAS_COM_ERROR:
                _LOGGER.debug(f"messages() - COMM ERROR")
                return None
            else:
                _LOGGER.debug(f"messages() - access_token exist? {self.access_token is not None}")

            headers_msg = {
                **apiHeaders,
                "auth-token": self.access_token,
                "Application-Id": self.app_id,
            }
            response_msg = await self.session.get(f"{GUARD_URL}/messagecenter/v3/messages?", headers=headers_msg, timeout=self.timeout)
            if response_msg.status == 200:
                # ok first resetting the counter for 401 errors (if we had any)
                _FOUR_NULL_ONE_COUNTER[self.username] = 0

                result_msg = await response_msg.json()
                if LOG_DATA:
                    _LOGGER.debug(f"messages: JSON: {result_msg}")

                self._LAST_MESSAGES_UPDATE = time.time()
                return result_msg["result"]["messages"]
            elif response_msg.status == 401:
                _FOUR_NULL_ONE_COUNTER[self.username] += 1
                if _FOUR_NULL_ONE_COUNTER[self.username] > MAX_401_RESPONSE_COUNT:
                    _LOGGER.error(f"messages: status_code: 401 - mark_re_auth_required()")
                    self.mark_re_auth_required()
                else:
                    _LOGGER.warning(f"messages: status_code: 401 - counter: {_FOUR_NULL_ONE_COUNTER}")
                    await asyncio.sleep(5)

                return None
            else:
                _LOGGER.info(f"messages: status_code: {response_msg.status} - Received response: {await response_msg.text()}")
                self._HAS_COM_ERROR = True
                return None

        except BaseException as e:
            _LOGGER.warning(f"Error while fetching message for vehicle {self.vin} - {type(e)} - {e}")
            self._HAS_COM_ERROR = True
            return None

    async def vehicles(self):
        """Get the vehicle list from the ford account"""
        global _FOUR_NULL_ONE_COUNTER
        try:
            await self.__ensure_valid_tokens()
            if self._HAS_COM_ERROR:
                _LOGGER.debug(f"vehicles() - COMM ERROR")
                return None
            else:
                _LOGGER.debug(f"vehicles() - access_token exist? {self.access_token is not None}")

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
                f"{GUARD_URL}/expdashboard/v1/details/",
                headers=headers_veh,
                data=json.dumps(data_veh),
                timeout=self.timeout
            )
            if response_veh.status == 207 or response_veh.status == 200:
                # ok first resetting the counter for 401 errors (if we had any)
                _FOUR_NULL_ONE_COUNTER[self.username] = 0

                result_veh = await response_veh.json()
                if LOG_DATA:
                    _LOGGER.debug(f"vehicles: JSON: {result_veh}")
                return result_veh
            elif response_veh.status == 401:
                _FOUR_NULL_ONE_COUNTER[self.username] += 1
                if _FOUR_NULL_ONE_COUNTER[self.username] > MAX_401_RESPONSE_COUNT:
                    _LOGGER.error(f"vehicles: status_code: 401 - mark_re_auth_required()")
                    self.mark_re_auth_required()
                else:
                    _LOGGER.warning(f"vehicles: status_code: 401 - counter: {_FOUR_NULL_ONE_COUNTER}")
                    await asyncio.sleep(5)

                return None
            else:
                _LOGGER.info(f"vehicles: status_code: {response_veh.status} - Received response: {await response_veh.text()}")
                self._HAS_COM_ERROR = True
                return None

        except BaseException as e:
            _LOGGER.warning(f"Error while fetching vehicle - {type(e)} - {e}")
            self._HAS_COM_ERROR = True
            return None

    async def guard_status(self):
        """Retrieve guard status from API"""
        await self.__ensure_valid_tokens()
        if self._HAS_COM_ERROR:
            _LOGGER.debug(f"guard_status() - COMM ERROR")
            return None
        else:
            _LOGGER.debug(f"guard_status() - access_token exist? {self.access_token is not None}")

        headers_gs = {
            **apiHeaders,
            "auth-token": self.access_token,
            "Application-Id": self.app_id,
        }
        params_gs = {"lrdt": "01-01-1970 00:00:00"}

        response_gs = await self.session.get(
            f"{GUARD_URL}/guardmode/v1/{self.vin}/session",
            params=params_gs,
            headers=headers_gs,
            timeout=self.timeout
        )
        return await response_gs.json()

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

    # operations
    async def remote_start(self):
        return await self.__request_and_poll_command_autonomic(command="remoteStart")

    async def cancel_remote_start(self):
        return await self.__request_and_poll_command_autonomic(command="cancelRemoteStart")

    async def start_charge(self):
        # VALUE_CHARGE, CHARGE_NOW, CHARGE_DT, CHARGE_DT_COND, CHARGE_SOLD, HOME_CHARGE_NOW, HOME_STORE_CHARGE, HOME_CHARGE_DISCHARGE
        # START_GLOBAL_CHARGE
        return await self.__request_and_poll_command_ford(command="startGlobalCharge")

    async def stop_charge(self):
        # CANCEL_GLOBAL_CHARGE
        return await self.__request_and_poll_command_ford(command="cancelGlobalCharge")

    # NOT USED YET
    # def start_engine(self):
    #     return self.__request_and_poll_command(command="startEngine")
    #
    # def stop(self):
    #     return self.__request_and_poll_command(command="stop")

    async def lock(self):
        """
        Issue a lock command to the doors
        """
        return await self.__request_and_poll_command_autonomic(command="lock")

    async def unlock(self):
        """
        Issue an unlock command to the doors
        """
        return await self.__request_and_poll_command_autonomic(command="unlock")

    async def enable_guard(self):
        """
        Enable Guard mode on supported models
        """
        await self.__ensure_valid_tokens()
        if self._HAS_COM_ERROR:
            return None

        response = self.__make_request(
            "PUT", f"{GUARD_URL}/guardmode/v1/{self.vin}/session", None, None
        )
        _LOGGER.debug(f"enable_guard: {await response.text()}")
        return response

    async def disable_guard(self):
        """
        Disable Guard mode on supported models
        """
        await self.__ensure_valid_tokens()
        if self._HAS_COM_ERROR:
            return None

        response = self.__make_request(
            "DELETE", f"{GUARD_URL}/guardmode/v1/{self.vin}/session", None, None
        )
        _LOGGER.debug(f"disable_guard: {await response.text()}")
        return response

    def request_update(self, vin=None):
        """Send request to vehicle for update"""
        if vin is None or len(vin) == 0:
            vin_to_request = self.vin
        else:
            vin_to_request = vin

        status = self.__request_and_poll_command_autonomic(command="statusRefresh", vin=vin_to_request)
        return status

    # core functions...
    # def __make_request(self, method, url, data, params):
    #     """
    #     Make a request to the given URL, passing data/params as needed
    #     """
    #     if self._HAS_COM_ERROR:
    #         return None
    #     else:
    #         try:
    #             headers = {
    #                 **apiHeaders,
    #                 "auth-token": self.access_token,
    #                 "Application-Id": self.region,
    #             }
    #             return getattr(requests, method.lower())(url, headers=headers, data=data, params=params)
    #
    #         except BaseException as e:
    #             _LOGGER.warning(f"Error while '__make_request' for vehicle {self.vin} {e}")
    #             self._HAS_COM_ERROR = True
    #             return None
    #
    # def __poll_status(self, url, command_id):
    #     """
    #     Poll the given URL with the given command ID until the command is completed
    #     """
    #     status = self.__make_request("GET", f"{url}/{command_id}", None, None)
    #     if status is not None:
    #         result = status.json()
    #         if result["status"] == 552:
    #             _LOGGER.debug("__poll_status: Command is pending")
    #             time.sleep(5)
    #             return self.__poll_status(url, command_id)  # retry after 5s
    #
    #         if result["status"] == 200:
    #             _LOGGER.debug("__poll_status: Command completed successfully")
    #             return True
    #
    #     _LOGGER.debug("__poll_status: Command failed")
    #     return False

    # def x_request_and_poll_command(self, command, properties={}, vin=None):
    #     return self.__request_and_poll_command(command, properties, vin)

    async def __request_and_poll_command_autonomic(self, command, properties={}, vin=None):
        """Send command to the new Command endpoint"""
        try:
            await self.__ensure_valid_tokens()
            if self._HAS_COM_ERROR:
                _LOGGER.debug(f"__request_and_poll_command_autonomic() - COMM ERROR")
                return False
            else:
                _LOGGER.debug(f"__request_and_poll_command_autonomic(): auto_access_token exist? {self.auto_access_token is not None}")

            headers = {
                **apiHeaders,
                "authorization": f"Bearer {self.auto_access_token}",
                "Application-Id": self.app_id # a bit unusual, that Application-id will be provided for an autonomic endpoint?!
            }
            # do we want to overwrite the vin?!
            if vin is None:
                vin = self.vin

            data = {
                "properties": properties,
                "tags": {},
                "type": command,
                "wakeUp": True
            }
            post_req = await self.session.post(f"{AUTONOMIC_URL}/command/vehicles/{vin}/commands",
                                    data=json.dumps(data),
                                    headers=headers,
                                    timeout=self.timeout
                                    )

            return await self.__check_command_status(req=post_req, req_command=command, use_websocket=self.ws_connected, properties=properties)

        except BaseException as e:
            _LOGGER.warning(f"Error while '__request_and_poll_command_autonomic' for vehicle '{self.vin}' command: '{command}' props:'{properties}' -> {type(e)} - {e}")
            self._HAS_COM_ERROR = True
            return False

    async def __request_and_poll_command_ford(self, command:str, post_data=None, vin=None):
        try:
            await self.__ensure_valid_tokens()
            if self._HAS_COM_ERROR:
                _LOGGER.debug(f"__request_and_poll_command_ford() - COMM ERROR")
                return False
            else:
                _LOGGER.debug(f"__request_and_poll_command_ford(): auto_access_token exist? {self.auto_access_token is not None}")

            headers = {
                **apiHeaders,
                "auth-token": self.access_token,
                "Application-Id": self.app_id,
            }
            # do we want to overwrite the vin?!
            if vin is None:
                vin = self.vin

            command_url_part = None
            if command == "cancelGlobalCharge":
                command_url_part = f"/electrification/experiences/v1/vehicles/{vin}/global-charge-command/CANCEL"
            elif command == "startGlobalCharge":
                command_url_part = f"/electrification/experiences/v1/vehicles/{vin}/global-charge-command/START"

            if command_url_part is None:
                _LOGGER.warning(f"__request_and_poll_command_ford() - command '{command}' is not supported by the integration")
                return False

            if post_data is not None:
                json_post_data = json.dumps(post_data)
            else:
                json_post_data = None

            post_req = await self.session.post(f"{FORD_VEHICLE_API}/{command_url_part}",
                                               data=json_post_data,
                                               headers=headers,
                                               timeout=self.timeout)

            return await self.__check_command_status(req=post_req, req_command=command, use_websocket=self.ws_connected)

        except BaseException as e:
            _LOGGER.warning(f"Error while '__request_and_poll_command_ford' for vehicle '{self.vin}' command: '{command}' post_data: '{post_data}' -> {type(e)} - {e}")
            self._HAS_COM_ERROR = True
            return False

    async def __request_and_poll_url_command(self, url_command, vin=None):
        try:
            await self.__ensure_valid_tokens()
            if self._HAS_COM_ERROR:
                _LOGGER.debug(f"__request_and_poll_url_command() - COMM ERROR")
                return False
            else:
                _LOGGER.debug(f"__request_and_poll_url_command(): access_token exist? {self.access_token is not None}")

            headers = {
                **apiHeaders,
                "auth-token": self.access_token,
                "Application-Id": self.app_id,
            }
            # do we want to overwrite the vin?!
            if vin is None:
                vin = self.vin

            # URL commands wil be posted to ANOTHER endpoint!
            r = await self.session.post(
                f"{GUARD_URL}/fordconnect/v1/vehicles/{vin}/{url_command}",
                headers=headers,
                timeout=self.timeout
            )
            return await self.__check_command_status(req=r, req_command=url_command, use_websocket=self.ws_connected)

        except BaseException as e:
            _LOGGER.warning(f"Error while '__request_and_poll_url_command' for vehicle '{self.vin}' command: '{url_command}' -> {e}")
            self._HAS_COM_ERROR = True
            return False

    async def __check_command_status(self, req, req_command, use_websocket, properties={}):
        _LOGGER.debug(f"__check_command_status: Testing command status: {req.status} (check by {'WebSocket' if use_websocket else 'polling'})")

        if not (200 <= req.status <= 205):
            if req.status in (401, 403):
                _LOGGER.info(f"__check_command_status(): '{req_command}' props:'{properties}' returned '{req.status}' status code - wtf!")
            else:
                _LOGGER.warning(f"__check_command_status(): '{req_command}' props:'{properties}' returned unknown status code: {req.status}!")
            return False

        # Extract command ID from response
        command_id = None
        response = await req.json()

        for id_key in ["id", "commandId", "correlationId"]:
            if id_key in response:
                command_id = response[id_key]
                break

        if command_id is None:
            _LOGGER.warning(f"__check_command_status(): No command ID found in response: {response}")
            return False

        # Wait for backend to process command
        await asyncio.sleep(2)

        # Only set status updates flag when polling
        if not use_websocket:
            self.status_updates_allowed = False

        try:
            i = 0
            while i < 15:
                if i > 0:
                    _LOGGER.debug(f"__check_command_status(): retry again [count: {i}] - COMM ERRORS: {self._HAS_COM_ERROR}")

                # Get data based on method
                if use_websocket:
                    updated_data = self._data_container
                else:
                    updated_data = await self.status()

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
                    command_key = f"{req_command}Command"
                    if command_key in states:
                        resp_command_obj = states[command_key]
                        #_LOGGER.debug(f"__check_command_status(): Found command object")

                        if "commandId" in resp_command_obj and resp_command_obj["commandId"] == command_id:
                            #_LOGGER.debug(f"__check_command_status(): Found the commandId")

                            if "value" in resp_command_obj and "toState" in resp_command_obj["value"]:
                                to_state = resp_command_obj["value"]["toState"].upper()

                                if to_state == "SUCCESS":
                                    _LOGGER.debug("__check_command_status(): EXCELLENT! Command succeeded")
                                    if not use_websocket:
                                        self.status_updates_allowed = True
                                    return True

                                if to_state == "EXPIRED":
                                    _LOGGER.info("__check_command_status(): Command EXPIRED")
                                    if not use_websocket:
                                        self.status_updates_allowed = True
                                    return False

                                if to_state == "REQUEST_QUEUED" or "IN_PROGRESS" in to_state:
                                    _LOGGER.debug(f"__check_command_status(): toState: '{to_state}'")
                                else:
                                    _LOGGER.info(f"__check_command_status(): UNKNOWN 'toState': {to_state}")
                            else:
                                _LOGGER.debug(f"__check_command_status(): no 'value' or 'toState' in command object")
                        else:
                            cmd_id = resp_command_obj.get("commandId", "missing")
                            _LOGGER.info(f"__check_command_status(): Command ID mismatch: {command_id} vs {cmd_id}")

                i += 1
                a_delay = i * 5
                if self._HAS_COM_ERROR:
                    a_delay = a_delay + 60

                # finally, wait in our loop
                await asyncio.sleep(a_delay)

            # end of while loop reached...
            _LOGGER.info(f"__check_command_status(): CHECK for '{req_command}' unsuccessful after 15 attempts")

        except BaseException as exc:
            _LOGGER.warning(f"__check_command_status(): Error during status checking - {type(exc)} - {exc}")

        if not use_websocket:
            self.status_updates_allowed = True

        return False