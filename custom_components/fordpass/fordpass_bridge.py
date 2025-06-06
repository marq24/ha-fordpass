"""Fordpass API Library"""
import asyncio
import json
import logging
import os
import time
import traceback
from asyncio import CancelledError
from typing import Final

import aiohttp
from aiohttp import ClientConnectorError, ClientConnectionError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.fordpass.const import REGIONS
from custom_components.fordpass.fordpass_handler import ROOT_STATES, ROOT_EVENTS, ROOT_METRICS, ROOT_MESSAGES, \
    ROOT_VEHICLES

# import requests
# from requests.adapters import HTTPAdapter
# from urllib3.util.retry import Retry

_LOGGER = logging.getLogger(__name__)
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

MAX_401_RESPONSE_COUNT: Final = 5
LOG_DATA: Final = False

BASE_URL: Final = "https://usapi.cv.ford.com/api"
GUARD_URL: Final = "https://api.mps.ford.com/api"
SSO_URL: Final = "https://sso.ci.ford.com"
AUTONOMIC_URL: Final = "https://api.autonomic.ai/v1"
AUTONOMIC_WS_URL: Final = "wss://api.autonomic.ai/v1beta"
AUTONOMIC_ACCOUNT_URL: Final = "https://accounts.autonomic.ai/v1"
FORD_LOGIN_URL: Final = "https://login.ford.com"
ERROR: Final = "ERROR"

#session = None #requests.Session()

class Vehicle:
    # Represents a Ford vehicle, with methods for status and issuing commands

    def __init__(self, web_session, username, password, vin, region, coordinator: DataUpdateCoordinator=None, save_token=False, tokens_location=None):
        self.session = web_session
        self.username = username
        #self.password = password # password is not used anymore...
        self.save_token = save_token
        self.region = REGIONS[region]["region"]
        self.country_code = REGIONS[region]["locale"]
        self.short_code = REGIONS[region]["locale_short"]
        self.countrycode = REGIONS[region]["countrycode"]
        self.vin = vin

        self._HAS_COM_ERROR = False

        self._FOUR_NULL_ONE_COUNTER = 0
        self.access_token = None
        self.refresh_token = None
        self.expires_at = None

        self._AUTO_FOUR_NULL_ONE_COUNTER = 0
        self.auto_access_token = None
        self.auto_refresh_token = None
        self.auto_expires_at = None

        # by default, we try to read the token from the file system
        self.use_token_data_from_memory = False

        #retry = Retry(connect=3, backoff_factor=0.5)
        #adapter = HTTPAdapter(max_retries=retry)
        #session.mount("http://", adapter)
        #session.mount("https://", adapter)

        if tokens_location is None:
            self.stored_tokens_location = f".storage/fordpass/{username}_access_token.txt"
        else:
            self.stored_tokens_location = tokens_location

        self._is_reauth_required = False
        self.status_updates_allowed = True

        # our main data container that holds all data that have been fetched from the vehicle
        self._data_container = {}
        self._cached_vehicles_data = {}
        self._ws_debounced_update_task = None
        self._ws_in_use_access_token = None
        self.coordinator = coordinator
        self.ws_connected = False
        self.ws_connect_in_progress = False
        self.ws_do_reconnect = True
        self.ws_terminate = False
        self._ws_LAST_UPDATE = 0
        self._ws_connection = None
        _LOGGER.info(f"init vehicle object for vin: '{self.vin}' - using token from: {tokens_location}")

    async def clear_data(self):
        self.ws_terminate = True
        self.ws_connected = False
        self.ws_do_reconnect = False
        self.ws_connect_in_progress = False
        self._cached_vehicles_data = {}
        self._data_container = {}
        if self._ws_connection is not None:
            await self._ws_connection.close()

    async def generate_tokens(self, urlstring, code_verifier):
        _LOGGER.debug(f"generate_tokens() for country_code: {self.country_code}")
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
            f"{FORD_LOGIN_URL}/4566605f-43a7-400a-946e-89cc9fdb0bd7/B2C_1A_SignInSignUp_{self.country_code}/oauth2/v2.0/token",
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
        headers = {**apiHeaders, "Application-Id": self.region}
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

    def mark_re_auth_required(self):
        stack_trace = traceback.format_stack()
        stack_trace_str = ''.join(stack_trace[:-1])  # Exclude the call to this function
        _LOGGER.warning(f"mark_re_auth_required() called!!! -> stack trace:\n{stack_trace_str}")
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
            _LOGGER.debug(f"__ensure_valid_tokens: token's expires_at {self.expires_at} has expired time-delta: {now_time - self.expires_at} -> requesting new token")
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
            _LOGGER.debug(f"__ensure_valid_tokens: auto-token's auto_expires_at {self.auto_expires_at} has expired time-delta: {now_time - self.auto_expires_at} -> requesting new auto-token")
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
        if self._HAS_COM_ERROR:
            return ERROR
        else:
            try:
                _LOGGER.debug("_request_token()")

                headers = {
                    **apiHeaders,
                    "Application-Id": self.region
                }
                data = {
                    "refresh_token": prev_token_data["refresh_token"]
                }
                response = await self.session.post(
                    f"{GUARD_URL}/token/v2/cat-with-refresh-token",
                    data=json.dumps(data),
                    headers=headers,
                )

                if response.status == 200:
                    # ok first resetting the counter for 401 errors (if we had any)
                    self._FOUR_NULL_ONE_COUNTER = 0
                    result = await response.json()
                    _LOGGER.debug(f"_request_token: status OK")
                    return result
                elif response.status == 401:
                    self._FOUR_NULL_ONE_COUNTER = self._FOUR_NULL_ONE_COUNTER + 1
                    if self._FOUR_NULL_ONE_COUNTER > MAX_401_RESPONSE_COUNT:
                        _LOGGER.error(f"_request_token: status_code: 401 - mark_re_auth_required()")
                        self.mark_re_auth_required()
                    else:
                        _LOGGER.warning(f"_request_token: status_code: 401 - counter: {self._FOUR_NULL_ONE_COUNTER}")
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
                    headers=headers
                )

                if response.status == 200:
                    # ok first resetting the counter for 401 errors (if we had any)
                    self._AUTO_FOUR_NULL_ONE_COUNTER = 0

                    result = await response.json()
                    _LOGGER.debug(f"_request_auto_token: status OK")
                    return result
                elif response.status == 401:
                    self._AUTO_FOUR_NULL_ONE_COUNTER = self._AUTO_FOUR_NULL_ONE_COUNTER + 1
                    if self._AUTO_FOUR_NULL_ONE_COUNTER > MAX_401_RESPONSE_COUNT:
                        _LOGGER.error(f"_request_auto_token: status_code: 401 - mark_re_auth_required()")
                        self.mark_re_auth_required()
                    else:
                        _LOGGER.warning(f"_request_auto_token: status_code: 401 - AUTO counter: {self._AUTO_FOUR_NULL_ONE_COUNTER}")

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
                await self.session.loop.run_in_executor(None, lambda: os.makedirs(directory))
            except OSError as exc:
                # Handle exception as before
                pass

        # Write the file in executor
        await self.session.loop.run_in_executor(None, lambda: self.__write_token_int(token))

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
            token_data = await self.session.loop.run_in_executor(None, self.__read_token_int)
            return token_data
        except ValueError:
            _LOGGER.warning("_read_token_from_storage: 'ValueError' invalidate TOKEN FILE -> mark_re_auth_required()")
            self.mark_re_auth_required()
        return None

    def __read_token_int(self):
        """Synchronous method to read token file, called from executor."""
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

    async def ws_connect(self):

        while self.ws_do_reconnect:
            self.ws_do_reconnect = False

            await self.__ensure_valid_tokens()
            if self._HAS_COM_ERROR:
                _LOGGER.debug(f"ws_connect() - COMM ERROR")
                return None
            else:
                _LOGGER.debug(f"ws_connect() - auto_access_token exist? {self.auto_access_token is not None}")

            headers_ws = {
                **apiHeaders,
                "authorization": f"Bearer {self.auto_access_token}",
                "Application-Id": self.region,
                "Connection": "Upgrade",
                "Upgrade": "websocket",
                #"Sec-WebSocket-Extensions": "permessage-deflate; client_max_window_bits",
                #"Sec-WebSocket-Key": "QOX3XLqFRFO6N+kAyrhQKA==",
                #"Sec-WebSocket-Version": "13"
            }
            web_socket_url = f"{AUTONOMIC_WS_URL}/telemetry/sources/fordpass/vehicles/{self.vin}/ws"

            self._ws_in_use_access_token = self.auto_access_token
            try:
                self.ws_connect_in_progress = True
                async with self.session.ws_connect(url=web_socket_url, headers=headers_ws) as ws:
                    self.ws_connect_in_progress = False
                    self._ws_connection = ws
                    self.ws_connected = True
                    _LOGGER.info(f"connected to websocket: {web_socket_url}")
                    #await ws.send_json({"type": "connection_init"})
                    async for msg in ws:
                        # store the last time we heard from the websocket
                        self._ws_LAST_UPDATE = time.time()

                        if self.ws_terminate:
                            _LOGGER.debug(f"ws_connect(): ws_terminate is set - closing websocket connection")
                            await ws.close()
                            break

                        new_data_arrived = False
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                ws_data = msg.json()
                                if ws_data is None or len(ws_data) == 0:
                                    _LOGGER.debug(f"ws_connect(): received empty data: '{ws_data}'")
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
                                        err_obj = ws_data["_error"]
                                        err_handled = False
                                        if "code" in err_obj and err_obj["code"] == 401:
                                            if "message" in err_obj:
                                                lower_msg = err_obj['message'].lower()
                                                if 'provided token was expired' in lower_msg:
                                                    _LOGGER.debug(f"ws_connect(): 'provided token was expired' expired - going to auto-reconnect-loop")
                                                    self.ws_do_reconnect = True
                                                    err_handled = True
                                                if 'websocket session expired' in lower_msg:
                                                    _LOGGER.debug(f"ws_connect(): 'websocket session expired' - going to auto-reconnect-loop")
                                                    self.ws_do_reconnect = True
                                                    err_handled = True

                                        if not err_handled:
                                            _LOGGER.error(f"ws_connect(): unknown error object read: {err_obj}")

                                    elif "_data" in ws_data:
                                        data_obj = ws_data["_data"]
                                        new_data_arrived = self._ws_handle_data(data_obj)
                                        if new_data_arrived is False:
                                            _LOGGER.debug(f"received: {data_obj}")
                                    else:
                                        _LOGGER.info(f"unknown content: {ws_data}")

                            except Exception as e:
                                _LOGGER.debug(f"Could not read JSON from: {msg} - caused {e}")

                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            _LOGGER.debug(f"received: {msg}")
                            break
                        else:
                            _LOGGER.error(f"xxx: {msg}")

                        # do we need to push new data event to the coordinator?
                        if new_data_arrived:
                            if self._ws_debounced_update_task is not None:
                                self._ws_debounced_update_task.cancel()
                            self._ws_debounced_update_task = asyncio.create_task(self._ws_debounce_coordinator_update())

                        # check if we need to refresh the auto token...
                        await self._ws_check_for_auth_token_refresh(ws)

            except ClientConnectorError as con:
                _LOGGER.error(f"ws_connect(): Could not connect to websocket: {type(con)} - {con}")
            except ClientConnectionError as err:
                _LOGGER.error(f"ws_connect(): ??? {type(err)} - {err}")
            except CancelledError as canceled:
                _LOGGER.info(f"Terminated ws_connect() ? - {type(canceled)} - {canceled}")
            except BaseException as x:
                _LOGGER.error(f"ws_connect(): !!! {type(x)} - {x}")

            self.ws_connect_in_progress = False
            self.ws_connected = False

        return None

    def _ws_handle_data(self, data_obj):

        new_metrics = self._ws_update_key(data_obj, ROOT_METRICS)
        new_states = self._ws_update_key(data_obj, ROOT_STATES)
        new_events = self._ws_update_key(data_obj, ROOT_EVENTS)

        return new_metrics or new_states or new_events

    def _ws_update_key(self, data_obj, a_root_key):
        if a_root_key in data_obj:
            # special handling for single state updates...
            if a_root_key == ROOT_STATES and len(data_obj[a_root_key]) == 1:
                a_state_name, a_state_obj = next(iter(data_obj[a_root_key].items()))
                if "value" in a_state_obj:
                    a_value_obj = a_state_obj["value"]
                    if "toState" in a_value_obj:
                        _LOGGER.debug(f"ws(): new state '{a_state_name}' arrived -> toState: {a_value_obj["toState"]}")
                        if a_value_obj["toState"].lower() == "success":
                            if ROOT_METRICS in a_value_obj:
                                self._ws_update_key(a_value_obj, ROOT_METRICS)
                                _LOGGER.debug(f"ws(): extracted '{ROOT_METRICS}' update from new 'success' state: {a_value_obj[ROOT_METRICS]}")
                    else:
                        _LOGGER.debug(f"ws(): new state (without toState) '{a_state_name}' arrived: {a_value_obj}")
                else:
                    _LOGGER.debug(f"ws(): new state (without value) '{a_state_name}' arrived")

            # If we don't have states yet in the existing data, initialize it
            if a_root_key not in self._data_container:
                self._data_container[a_root_key] = {}

            # Update only the specific keys (e.g. if only one state is present) that are in the new data
            for a_key_name, a_key_value in data_obj[a_root_key].items():
                self._data_container[a_root_key][a_key_name] = a_key_value

            return True

        return False

    async def _ws_check_for_auth_token_refresh(self, ws):
        # check the age of auto auth_token... and if' it's near the expiry date, we should refresh it
        try:
            if self.auto_expires_at and time.time() + 60 > self.auto_expires_at:
                _LOGGER.debug(f"_ws_check_for_auth_token_refresh: auto token expires in less than 60 seconds - try to refresh")

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
                    _LOGGER.debug(f"_ws_check_for_auth_token_refresh: auto token has been refreshed -> update websocket")
                    await ws.send_json({"accessToken": self.auto_access_token})
            else:
                _LOGGER.debug(f"_ws_check_for_auth_token_refresh: 'self.auto_access_token' is None (might be cause of 401 error)")
                if self.save_token:
                    await self._read_token_from_storage()

        except BaseException as e:
            _LOGGER.error(f"_ws_check_for_auth_token_refresh: Error while refreshing auto token - {type(e)} - {e}")

    async def _ws_debounce_coordinator_update(self):
        await asyncio.sleep(0.3)
        if self.coordinator is not None:
            self.coordinator.async_set_updated_data(self._data_container)

    async def ws_check_last_update(self):
        if self._ws_LAST_UPDATE + 120 > time.time():
            _LOGGER.debug(f"ws_check_last_update: last update is less than 120 seconds ago - no need to update")
        else:
            _LOGGER.info(f"ws_check_last_update: force reconnect... is _ws_connection object available? {self._ws_connection is not None}")
            if self._ws_connection is not None:
                await self._ws_connection.close()
                self.ws_connected = False
                self.ws_do_reconnect = True


    async def update_all(self):
        data = await self.status()
        if data is not None:
            # Temporarily removed due to Ford backend API changes
            # data["guardstatus"] = await self.hass.async_add_executor_job(self.vehicle.guardStatus)

            data[ROOT_MESSAGES] = await self.messages()

            # only update vehicle data if not present yet
            if len(self._cached_vehicles_data) == 0:
                _LOGGER.debug("update_all: request vehicle data...")
                self._cached_vehicles_data = await self.vehicles()

            if len(self._cached_vehicles_data) > 0:
                data[ROOT_VEHICLES] = self._cached_vehicles_data

            # ok finally store the data in our main data container...
            self._data_container = data

        return data

    # fetching the main data...
    async def status(self):
        """Get Vehicle status from API"""
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
                "Application-Id": self.region,
            }
            params_state = {
                "lrdt": "01-01-1970 00:00:00"
            }
            response_state = await self.session.get(
                f"{AUTONOMIC_URL}/telemetry/sources/fordpass/vehicles/{self.vin}",
                params=params_state,
                headers=headers_state
            )

            if response_state.status == 200:
                # ok first resetting the counter for 401 errors (if we had any)
                self._AUTO_FOUR_NULL_ONE_COUNTER = 0

                result_state = await response_state.json()
                if LOG_DATA:
                    _LOGGER.debug(f"status: JSON: {result_state}")
                return result_state
            elif response_state.status == 401:
                self._AUTO_FOUR_NULL_ONE_COUNTER = self._AUTO_FOUR_NULL_ONE_COUNTER + 1
                if self._AUTO_FOUR_NULL_ONE_COUNTER > MAX_401_RESPONSE_COUNT:
                    _LOGGER.error(f"status: status_code: 401 - mark_re_auth_required()")
                    self.mark_re_auth_required()
                else:
                    _LOGGER.warning(f"status: status_code: 401 - AUTO counter: {self._AUTO_FOUR_NULL_ONE_COUNTER}")

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
        try:
            await self.__ensure_valid_tokens()
            if self._HAS_COM_ERROR:
                _LOGGER.debug(f"messages() - COMM ERROR")
                return None
            else:
                _LOGGER.debug(f"messages() - access_token exist? {self.access_token is not None}")

            headers_msg = {
                **apiHeaders,
                "Auth-Token": self.access_token,
                "Application-Id": self.region,
            }
            response_msg = await self.session.get(f"{GUARD_URL}/messagecenter/v3/messages?", headers=headers_msg)
            if response_msg.status == 200:
                # ok first resetting the counter for 401 errors (if we had any)
                self._FOUR_NULL_ONE_COUNTER = 0

                result_msg = await response_msg.json()
                if LOG_DATA:
                    _LOGGER.debug(f"messages: JSON: {result_msg}")
                return result_msg["result"]["messages"]
            elif response_msg.status == 401:
                self._FOUR_NULL_ONE_COUNTER = self._FOUR_NULL_ONE_COUNTER + 1
                if self._FOUR_NULL_ONE_COUNTER > MAX_401_RESPONSE_COUNT:
                    _LOGGER.error(f"messages: status_code: 401 - mark_re_auth_required()")
                    self.mark_re_auth_required()
                else:
                    _LOGGER.warning(f"messages: status_code: 401 - counter: {self._FOUR_NULL_ONE_COUNTER}")

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
        try:
            await self.__ensure_valid_tokens()
            if self._HAS_COM_ERROR:
                _LOGGER.debug(f"vehicles() - COMM ERROR")
                return None
            else:
                _LOGGER.debug(f"vehicles() - access_token exist? {self.access_token is not None}")

            headers_veh = {
                **apiHeaders,
                "Auth-Token": self.access_token,
                "Application-Id": self.region,
                "Countrycode": self.countrycode,
                "Locale": "en-US"
            }
            data_veh = {
                "dashboardRefreshRequest": "All"
            }
            response_veh = await self.session.post(
                f"{GUARD_URL}/expdashboard/v1/details/",
                headers=headers_veh,
                data=json.dumps(data_veh)
            )
            if response_veh.status == 207 or response_veh.status == 200:
                # ok first resetting the counter for 401 errors (if we had any)
                self._FOUR_NULL_ONE_COUNTER = 0

                result_veh = await response_veh.json()
                if LOG_DATA:
                    _LOGGER.debug(f"vehicles: JSON: {result_veh}")
                return result_veh
            elif response_veh.status == 401:
                self._FOUR_NULL_ONE_COUNTER = self._FOUR_NULL_ONE_COUNTER + 1
                if self._FOUR_NULL_ONE_COUNTER > MAX_401_RESPONSE_COUNT:
                    _LOGGER.error(f"vehicles: status_code: 401 - mark_re_auth_required()")
                    self.mark_re_auth_required()
                else:
                    _LOGGER.warning(f"vehicles: status_code: 401 - counter: {self._FOUR_NULL_ONE_COUNTER}")

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
            "Application-Id": self.region,
        }
        params_gs = {"lrdt": "01-01-1970 00:00:00"}

        response_gs = await self.session.get(
            f"{GUARD_URL}/guardmode/v1/{self.vin}/session",
            params=params_gs,
            headers=headers_gs,
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
        return await self.__request_and_poll_command(command="remoteStart")

    async def cancel_remote_start(self):
        return await self.__request_and_poll_command(command="cancelRemoteStart")

    async def start_charge(self):
        # VALUE_CHARGE, CHARGE_NOW, CHARGE_DT, CHARGE_DT_COND, CHARGE_SOLD, HOME_CHARGE_NOW, HOME_STORE_CHARGE, HOME_CHARGE_DISCHARGE
        # START_GLOBAL_CHARGE
        return await self.__request_and_poll_command(url_command="startCharge")

    async def stop_charge(self):
        # CANCEL_GLOBAL_CHARGE
        return await self.__request_and_poll_command(url_command="stopCharge")

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
        return await self.__request_and_poll_command(command="lock")

    async def unlock(self):
        """
        Issue an unlock command to the doors
        """
        return await self.__request_and_poll_command(command="unlock")

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

        status = self.__request_and_poll_command(command="statusRefresh", vin=vin_to_request)
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

    async def __request_and_poll_command(self, command, properties={}, vin=None):
        """Send command to the new Command endpoint"""
        self.status_updates_allowed = False
        try:
            await self.__ensure_valid_tokens()
            if self._HAS_COM_ERROR:
                self.status_updates_allowed = True
                _LOGGER.debug(f"__request_and_poll_command() - COMM ERROR")
                return False
            else:
                _LOGGER.debug(f"__request_and_poll_command(): auto_access_token exist? {self.auto_access_token is not None}")

            headers = {
                **apiHeaders,
                "Application-Id": self.region,
                "authorization": f"Bearer {self.auto_access_token}"
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
                                    headers=headers
                                    )
            if self.ws_connected:
                return await self.__wait_ws_status_update(req=post_req, req_command=command, properties=properties)
            else:
                return await self.__poll_command_status(req=post_req, req_command=command, properties=properties)

        except BaseException as e:
            _LOGGER.warning(f"Error while '__request_and_poll_command' for vehicle '{self.vin}' command: '{command}' props:'{properties}' -> {e}")
            self._HAS_COM_ERROR = True
            self.status_updates_allowed = True
            return False

    async def __request_and_poll_url_command(self, url_command, vin=None):
        self.status_updates_allowed = False
        try:
            await self.__ensure_valid_tokens()
            if self._HAS_COM_ERROR:
                self.status_updates_allowed = True
                _LOGGER.debug(f"__request_and_poll_url_command() - COMM ERROR")
                return False
            else:
                _LOGGER.debug(f"__request_and_poll_url_command(): access_token exist? {self.access_token is not None}")

            headers = {
                **apiHeaders,
                "Auth-Token": self.access_token,
                "Application-Id": self.region,
                "Countrycode": self.countrycode,
                "Locale": "en-US"
            }
            # do we want to overwrite the vin?!
            if vin is None:
                vin = self.vin

            # URL commands wil be posted to ANOTHER endpoint!
            r = await self.session.post(
                f"{GUARD_URL}/fordconnect/v1/vehicles/{vin}/{url_command}",
                headers=headers
            )
            if self.ws_connected:
                return await self.__wait_ws_status_update(req=r, req_command=url_command)
            else:
                return await self.__poll_command_status(req=r, req_command=url_command)

        except BaseException as e:
            _LOGGER.warning(f"Error while '__request_and_poll_url_command' for vehicle '{self.vin}' command: '{url_command}' -> {e}")
            self._HAS_COM_ERROR = True
            self.status_updates_allowed = True
            return False

    async def __poll_command_status(self, req, req_command, properties={}):
        _LOGGER.debug(f"__poll_command_status: Testing command status: {req.status}")
        if req.status == 201:
            # New code to handle checking states table from vehicle data
            response = await req.json()
            command_id = response["id"]

            # at least allowing the backend 2 seconds to process the command (before we are going to check the status)
            time.sleep(2)

            i = 1
            while i < 14:
                a_delay = 5
                if i > 5:
                    a_delay = 10

                # requesting the status... [to see the process about our command that we just have sent]
                updated_data = await self.status()

                if updated_data is not None and "states" in updated_data:
                    states = updated_data["states"]
                    if LOG_DATA:
                        _LOGGER.debug(f"__poll_command_status: States located states: {states}")

                    if f"{req_command}Command" in states:
                        resp_command_obj = states[f"{req_command}Command"]
                        _LOGGER.debug(f"__poll_command_status: Found an command obj")

                        if "commandId" in resp_command_obj:
                            if resp_command_obj["commandId"] == command_id:
                                _LOGGER.debug(f"__poll_command_status: Found the commandId")

                                if "value" in resp_command_obj and "toState" in resp_command_obj["value"]:
                                    to_state = resp_command_obj["value"]["toState"]
                                    if to_state == "success":
                                        _LOGGER.debug("__poll_command_status: EXCELLENT! command succeeded")
                                        self.status_updates_allowed = True
                                        return True
                                    if to_state == "expired":
                                        _LOGGER.debug("__poll_command_status: Command expired")
                                        self.status_updates_allowed = True
                                        return False

                                    if to_state == "request_queued":
                                        a_delay = 10
                                        _LOGGER.debug(f"__poll_command_status: toState: '{to_state}' - let's wait (10sec)!")
                                    elif "in_progress" in to_state:
                                        a_delay = 5
                                        _LOGGER.debug(f"__poll_command_status: toState: '{to_state}' - let's wait (5sec)!")
                                    else:
                                        _LOGGER.info(f"__poll_command_status: Unknown 'toState': {to_state}")

                                else:
                                    _LOGGER.debug(f"__poll_command_status: no 'value' or 'toState' in command object {resp_command_obj} - waiting for next loop")
                            else:
                                _LOGGER.info(f"__poll_command_status: The {command_id} does not match {resp_command_obj['commandId']} -> object dump: {resp_command_obj}")
                        else:
                            _LOGGER.info(f"__poll_command_status: No 'commandId' found in : {resp_command_obj}")

                i += 1
                _LOGGER.debug(f"__poll_command_status: Looping again [{i}] - COMM ERRORS occurred? {self._HAS_COM_ERROR}")
                if self._HAS_COM_ERROR:
                    a_delay = 60

                time.sleep(a_delay)

            # this is after the 'while'-loop...
            self.status_updates_allowed = True
            return False

        elif req.status == 401 or req.status == 403:
            _LOGGER.info(f"__poll_command_status: '{req_command}' props:'{properties}' returned {req.status} - wft!")
            self.status_updates_allowed = True
            return False
        else:
            _LOGGER.info(f"__poll_command_status: '{req_command}' props:'{properties}' returned unknown Status code {req.status}!")
            self.status_updates_allowed = True
            return False

    async def __wait_ws_status_update(self, req, req_command:str, properties={}):
        _LOGGER.debug(f"__wait_ws_status_update: Testing command status: {req.status}")
        if req.status == 201:
            # New code to handle checking states table from vehicle data
            response = await req.json()
            command_id = response["id"]

            # at least allowing the backend 2 seconds to process the command (before we are going to check the status)
            await asyncio.sleep(2)

            i = 1
            while i < 14:
                a_delay = 5
                if i > 5:
                    a_delay = 10

                # requesting the status... [to see the process about our command that we just have sent]
                updated_data = self._data_container

                if updated_data is not None and ROOT_STATES in updated_data:
                    states = updated_data[ROOT_STATES]
                    if LOG_DATA:
                        _LOGGER.debug(f"__wait_ws_status_update: States located states: {states}")

                    if f"{req_command}Command" in states:
                        resp_command_obj = states[f"{req_command}Command"]
                        _LOGGER.debug(f"__wait_ws_status_update: Found an command obj")

                        if "commandId" in resp_command_obj:
                            if resp_command_obj["commandId"] == command_id:
                                _LOGGER.debug(f"__wait_ws_status_update: Found the commandId")

                                if "value" in resp_command_obj and "toState" in resp_command_obj["value"]:
                                    to_state = resp_command_obj["value"]["toState"]
                                    if to_state == "success":
                                        _LOGGER.debug("__wait_ws_status_update: EXCELLENT! command succeeded")
                                        self.status_updates_allowed = True
                                        return True
                                    if to_state == "expired":
                                        _LOGGER.debug("__wait_ws_status_update: Command expired")
                                        self.status_updates_allowed = True
                                        return False

                                    if to_state == "request_queued":
                                        a_delay = 10
                                        _LOGGER.debug(f"__wait_ws_status_update: toState: '{to_state}' - let's wait (10sec)!")
                                    elif "in_progress" in to_state:
                                        a_delay = 5
                                        _LOGGER.debug(f"__wait_ws_status_update: toState: '{to_state}' - let's wait (5sec)!")
                                    else:
                                        _LOGGER.info(f"__wait_ws_status_update: Unknown 'toState': {to_state}")

                                else:
                                    _LOGGER.debug(f"__wait_ws_status_update: no 'value' or 'toState' in command object {resp_command_obj} - waiting for next loop")
                            else:
                                _LOGGER.info(f"__wait_ws_status_update: The {command_id} does not match {resp_command_obj['commandId']} -> object dump: {resp_command_obj}")
                        else:
                            _LOGGER.info(f"__wait_ws_status_update: No 'commandId' found in : {resp_command_obj}")

                i += 1
                _LOGGER.debug(f"__wait_ws_status_update: Looping again [{i}] - COMM ERRORS occurred? {self._HAS_COM_ERROR}")
                if self._HAS_COM_ERROR:
                    a_delay = 60

                await asyncio.sleep(a_delay)

            # this is after the 'while'-loop...
            self.status_updates_allowed = True
            return False

        elif req.status == 401 or req.status == 403:
            _LOGGER.info(f"__wait_ws_status_update: '{req_command}' props:'{properties}' returned {req.status} - wft!")
            self.status_updates_allowed = True
            return False
        else:
            _LOGGER.info(f"__wait_ws_status_update: '{req_command}' props:'{properties}' returned unknown Status code {req.status}!")
            self.status_updates_allowed = True
            return False