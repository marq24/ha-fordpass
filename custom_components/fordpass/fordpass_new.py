"""Fordpass API Library"""
import hashlib
import json
import logging
import os
import random
import re
import string
import time
from base64 import urlsafe_b64encode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .const import REGIONS

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

NEW_API = True

BASE_URL = "https://usapi.cv.ford.com/api"
GUARD_URL = "https://api.mps.ford.com/api"
SSO_URL = "https://sso.ci.ford.com"
AUTONOMIC_URL = "https://api.autonomic.ai/v1"
AUTONOMIC_ACCOUNT_URL = "https://accounts.autonomic.ai/v1"
FORD_LOGIN_URL = "https://login.ford.com"

session = requests.Session()


class Vehicle:
    # Represents a Ford vehicle, with methods for status and issuing commands

    def __init__(self, username, password, vin, region, save_token=False, tokens_location=None):
        self.username = username
        self.password = password
        self.save_token = save_token
        self.region = REGIONS[region]["region"]
        self.country_code = REGIONS[region]["locale"]
        self.short_code = REGIONS[region]["locale_short"]
        self.countrycode = REGIONS[region]["countrycode"]
        self.vin = vin

        self.access_token = None
        self.refresh_token = None
        self.expires_at = None

        self.auto_access_token = None
        self.auto_refresh_token = None
        self.auto_expires_at = None

        # by default, we try to read the token from the file system
        self.use_token_data_from_memory = False

        retry = Retry(connect=3, backoff_factor=0.5)
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        if tokens_location is None:
            self.stored_tokens_location = f".storage/fordpass/{username}_access_token.txt"
        else:
            self.stored_tokens_location = tokens_location

        _LOGGER.info(f"init vehicle object {self.vin} using token from: {tokens_location}")

    def base64_url_encode(self, data):
        """Encode string to base64"""
        return urlsafe_b64encode(data).rstrip(b'=')

    def generate_tokens(self, urlstring, code_verifier):
        code_new = urlstring.replace("fordapp://userauthorized/?code=", "")
        #_LOGGER.debug(f"generate_tokens: {code_new} country_code: {self.country_code} code_verifier: {code_verifier}")
        _LOGGER.debug(f"generate_tokens: code: {code_new} country_code: {self.country_code}")

        data = {
            "client_id": "09852200-05fd-41f6-8c21-d36d3497dc64",
            "grant_type": "authorization_code",
            "code_verifier": code_verifier,
            "code": code_new,
            "redirect_uri": "fordapp://userauthorized"
        }

        #_LOGGER.debug(f"generate_tokens post data: {data}")
        headers = {
            **loginHeaders,
        }
        req = requests.post(
            f"{FORD_LOGIN_URL}/4566605f-43a7-400a-946e-89cc9fdb0bd7/B2C_1A_SignInSignUp_{self.country_code}/oauth2/v2.0/token",
            headers=headers,
            data=data,
            verify=False
        )
        _LOGGER.debug(f"generate_tokens status: {req.status_code} content: {req.text}")
        return self.generate_fulltokens(req.json())

    def generate_fulltokens(self, token):
        data = {"idpToken": token["access_token"]}
        headers = {**apiHeaders, "Application-Id": self.region}
        response = requests.post(
            f"{GUARD_URL}/token/v2/cat-with-b2c-access-token",
            data=json.dumps(data),
            headers=headers,
            verify=False
        )
        _LOGGER.debug(f"generate_fulltokens status: {response.status_code} content: {response.text}")

        final_tokens = response.json()
        if "expires_in" in final_tokens:
            final_tokens["expiry_date"] = time.time() + final_tokens["expires_in"]
            del final_tokens["expires_in"]

        if "refresh_expires_in" in final_tokens:
            final_tokens["refresh_expiry_date"] = time.time() + final_tokens["refresh_expires_in"]
            del final_tokens["refresh_expires_in"]

        if self.save_token:
            self.write_token_to_storage(final_tokens)

        return True

    def generate_hash(self, code):
        """Generate hash for login"""
        hashengine = hashlib.sha256()
        hashengine.update(code.encode('utf-8'))
        return self.base64_url_encode(hashengine.digest()).decode('utf-8')

    def auth(self):
        """New Authentication System """
        _LOGGER.debug("auth: New System")
        # Auth Step1
        headers = {
            **defaultHeaders,
            'Content-Type': 'application/json',
        }
        code1 = ''.join(random.choice(string.ascii_lowercase) for i in range(43))
        code_verifier = self.generate_hash(code1)
        url1 = f"{SSO_URL}/v1.0/endpoint/default/authorize?redirect_uri=fordapp://userauthorized&response_type=code&scope=openid&max_age=3600&client_id=9fb503e0-715b-47e8-adfd-ad4b7770f73b&code_challenge={code_verifier}&code_challenge_method=S256"
        response = session.get(
            url1,
            headers=headers,
        )

        test = re.findall('data-ibm-login-url="(.*)"\s', response.text)[0]
        next_url = SSO_URL + test

        # Auth Step2
        headers = {
            **defaultHeaders,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "operation": "verify",
            "login-form-type": "password",
            "username": self.username,
            "password": self.password

        }
        response = session.post(
            next_url,
            headers=headers,
            data=data,
            allow_redirects=False
        )

        if response.status_code == 302:
            next_url = response.headers["Location"]
        else:
            response.raise_for_status()

        # Auth Step3
        headers = {
            **defaultHeaders,
            'Content-Type': 'application/json',
        }

        response = session.get(
            next_url,
            headers=headers,
            allow_redirects=False
        )

        if response.status_code == 302:
            next_url = response.headers["Location"]
            query = requests.utils.urlparse(next_url).query
            params = dict(x.split('=') for x in query.split('&'))
            code = params["code"]
            grant_id = params["grant_id"]
        else:
            response.raise_for_status()

        # Auth Step4
        headers = {
            **defaultHeaders,
            "Content-Type": "application/x-www-form-urlencoded",
        }

        data = {
            "client_id": "9fb503e0-715b-47e8-adfd-ad4b7770f73b",
            "grant_type": "authorization_code",
            "redirect_uri": 'fordapp://userauthorized',
            "grant_id": grant_id,
            "code": code,
            "code_verifier": code1
        }

        response = session.post(
            f"{SSO_URL}/oidc/endpoint/default/token",
            headers=headers,
            data=data

        )

        if response.status_code == 200:
            result = response.json()
            if result["access_token"]:
                access_token = result["access_token"]
        else:
            response.raise_for_status()


        # Auth Step5
        data = {"ciToken": access_token}
        headers = {**apiHeaders, "Application-Id": self.region}
        response = session.post(
            f"{GUARD_URL}/token/v2/cat-with-ci-access-token",
            data=json.dumps(data),
            headers=headers,
        )

        if response.status_code == 200:
            result = response.json()

            self.access_token = result["access_token"]
            self.refresh_token = result["refresh_token"]
            if "expires_in" in result:
                result["expiry_date"] = time.time() + result["expires_in"]
                del result["expires_in"]
                self.expires_at = result["expiry_date"]

            if "refresh_expires_in" in result:
                result["refresh_expiry_date"] = time.time() + result["refresh_expires_in"]
                del result["refresh_expires_in"]

            auto_token = self._refresh_auto_token_request()
            self.auto_access_token = auto_token["access_token"]
            self.auto_refresh_token = auto_token["refresh_token"]
            if "expires_in" in auto_token:
                self.auto_expires_at = time.time() + auto_token["expires_in"]
                del auto_token["expires_in"]

            if "refresh_expires_in" in auto_token:
                auto_token["refresh_expiry_date"] = time.time() + auto_token["refresh_expires_in"]
                del auto_token["refresh_expires_in"]

            if self.save_token:
                # we want to store also the 'auto' token data...
                result["auto_token"] = self.auto_access_token
                result["auto_refresh_token"] = self.auto_refresh_token
                if self.auto_expires_at is not None:
                    result["auto_expiry_date"] = self.auto_expires_at

                self.write_token_to_storage(result)

            session.cookies.clear()
            return True

        response.raise_for_status()
        return False

    def __acquire_tokens(self):
        # Fetch and refresh token as needed
        # If file exists read in token file and check it's valid
        _LOGGER.debug("__acquire_token: called...")
        if self.save_token:
            # do not access every time the file system - since we are the only one
            # using the vehicle object, we can keep the token in memory (and
            # invalidate it if needed)
            if (not self.use_token_data_from_memory) and os.path.isfile(self.stored_tokens_location):
                token_data = self.read_token_from_storage()
                self.use_token_data_from_memory = True
                _LOGGER.debug(f"__acquire_token: token data read from fs: {token_data}")

                self.access_token = token_data["access_token"]
                self.refresh_token = token_data["refresh_token"]
                self.expires_at = token_data["expiry_date"]

                if "auto_token" in token_data and "auto_refresh_token" in token_data and "auto_expiry_date" in token_data:
                    self.auto_access_token = token_data["auto_token"]
                    self.auto_refresh_token = token_data["auto_refresh_token"]
                    self.auto_expires_at = token_data["auto_expiry_date"]
                else:
                    _LOGGER.debug("__acquire_token: AUTO token not set (or incomplete) in file")
                    self.auto_access_token = None
                    self.auto_refresh_token = None
                    self.auto_expires_at = None
            else:
                token_data = {}
                token_data["access_token"] = self.access_token
                token_data["refresh_token"] = self.refresh_token
                token_data["expiry_date"] = self.expires_at
                token_data["auto_token"] = self.auto_access_token
                token_data["auto_refresh_token"] = self.auto_refresh_token
                token_data["auto_expiry_date"] = self.auto_expires_at
        else:
            token_data = {}
            token_data["access_token"] = self.access_token
            token_data["refresh_token"] = self.refresh_token
            token_data["expiry_date"] = self.expires_at
            token_data["auto_token"] = self.auto_access_token
            token_data["auto_refresh_token"] = self.auto_refresh_token
            token_data["auto_expiry_date"] = self.auto_expires_at

        # checking token data (and refreshing if needed)
        if self.auto_access_token is None or self.auto_expires_at is None:
            _LOGGER.debug(f"__acquire_token: auto_token or auto_expires_at is None -> requesting new token")
            result = self.refresh_token_func(token_data)
            _LOGGER.debug(f"__acquire_token: result for new token: {result}")
            self.refresh_auto_token_func(result)

        # self.auto_token = token_data["auto_token"]
        # self.auto_expires_at = token_data["auto_expiry_date"]

        if self.expires_at:
            if time.time() >= self.expires_at:
                _LOGGER.debug("__acquire_token: expires_at has expired -> requesting new token")
                result = self.refresh_token_func(token_data)
                _LOGGER.debug(f"__acquire_token: result for new token: {result}")
                self.refresh_auto_token_func(result)

        if self.auto_expires_at:
            if time.time() >= self.auto_expires_at:
                _LOGGER.debug("__acquire_token: auto_expires_at has expired -> requesting new token")
                result = self.refresh_token_func(token_data)
                _LOGGER.debug(f"__acquire_token: result for new token: {result}")
                self.refresh_auto_token_func(result)

        if self.access_token is None:
            _LOGGER.debug("__acquire_token: self.access_token is None -> requesting new token...")
            # No existing token exists so refreshing library
            self.auth()
        else:
            _LOGGER.debug("__acquire_token: Token is valid -> continuing")

    def refresh_token_func(self, token):
        """Refresh token if still valid"""
        data = {"refresh_token": token["refresh_token"]}
        headers = {**apiHeaders, "Application-Id": self.region}

        response = session.post(
            f"{GUARD_URL}/token/v2/cat-with-refresh-token",
            data=json.dumps(data),
            headers=headers,
        )

        if response.status_code == 200:
            result = response.json()

            # re-write the 'expires_in' to 'expiry_date'...
            if "expires_in" in result:
                result["expiry_date"] = time.time() + result["expires_in"]
                del result["expires_in"]

            if "refresh_expires_in" in result:
                result["refresh_expiry_date"] = time.time() + result["refresh_expires_in"]
                del result["refresh_expires_in"]

            if self.save_token:
                self.write_token_to_storage(result)

            self.access_token = result["access_token"]
            self.refresh_token = result["refresh_token"]
            self.expires_at = result["expiry_date"]

            _LOGGER.debug("refresh_token_func: read new access token -> success")
            return result

        elif response.status_code == 401:
            _LOGGER.debug(f"refresh_token_func: status: {response.status_code} - start auth()")
            self.auth()
        else:
            _LOGGER.debug(f"refresh_token_func: status: {response.status_code} - no data read!")

        return False

    def refresh_auto_token_func(self, token_data):
        _LOGGER.debug(f"refresh_auto_token_func: called...")
        auto_token = self._refresh_auto_token_request()
        if auto_token is not False:
            if "expires_in" in auto_token:
                # re-write the 'expires_in' to 'expiry_date'...
                auto_token["expiry_date"] = time.time() + auto_token["expires_in"]
                del auto_token["expires_in"]

            if "refresh_expires_in" in auto_token:
                auto_token["refresh_expiry_date"] = time.time() + auto_token["refresh_expires_in"]
                del auto_token["refresh_expires_in"]

            if self.save_token:
                token_data["auto_token"] = auto_token["access_token"]
                token_data["auto_refresh_token"] = auto_token["refresh_token"]
                token_data["auto_expiry_date"] = auto_token["expiry_date"]

                self.write_token_to_storage(token_data)

            # finally setting our internal values...
            self.auto_access_token = auto_token["access_token"]
            self.auto_refresh_token = auto_token["refresh_token"]
            self.auto_expires_at = auto_token["expiry_date"]

            _LOGGER.debug(f"refresh_auto_token_func: updated auto_token: {self.auto_access_token} auto_expires_at: {self.auto_expires_at}")
        else:
            self.auto_access_token = None
            self.auto_refresh_token = None
            self.auto_expires_at = None
            _LOGGER.debug(f"refresh_auto_token_func: FAILED!")

    def _refresh_auto_token_request(self):
        """Get token from new autonomic API"""
        _LOGGER.debug("_refresh_auto_token_request: request Auto Token")
        headers = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded"
        }

        # looks like, that the auto_refresh_token is useless here...
        # but for now I (marq24) keep this in the code...
        data = {
            "subject_token": self.access_token,
            "subject_issuer": "fordpass",
            "client_id": "fordpass-prod",
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
        }

        r = session.post(
            f"{AUTONOMIC_ACCOUNT_URL}/auth/oidc/token",
            data=data,
            headers=headers
        )

        if r.status_code == 200:
            result = r.json()
            _LOGGER.debug(f"_refresh_auto_token_request: status: {r.status_code} content: {r.text}")
            return result
        elif r.status_code == 401:
            _LOGGER.debug(f"_refresh_auto_token_request: status: {r.status_code} - start auth()")
            self.auth()
        else:
            _LOGGER.debug(f"_refresh_auto_token_request: status: {r.status_code} - no data read!")

        return False


    def write_token_to_storage(self, token):
        """Save token to file for reuse"""

        # check if parent exists...
        if not os.path.exists(os.path.dirname(self.stored_tokens_location)):
            try:
                os.makedirs(os.path.dirname(self.stored_tokens_location))
            except OSError as exc:  # Guard
                _LOGGER.debug(f"write_token_to_storage: create dir caused {exc}")

        with open(self.stored_tokens_location, "w", encoding="utf-8") as outfile:
            _LOGGER.debug(f"write_token_to_storage: {token}")
            json.dump(token, outfile)

        # make sure that we will read the token data next time...
        self.use_token_data_from_memory = False

    def read_token_from_storage(self):
        """Read saved token from file"""
        try:
            with open(self.stored_tokens_location, encoding="utf-8") as token_file:
                token = json.load(token_file)
                return token
        except ValueError:
            _LOGGER.debug("read_token_from_storage: Fixing malformed token")
            self.auth()
            with open(self.stored_tokens_location, encoding="utf-8") as token_file:
                token = json.load(token_file)
                return token

    def clear_token(self):
        """Clear tokens from config directory"""
        if os.path.isfile("/tmp/fordpass_token.txt"):
            os.remove("/tmp/fordpass_token.txt")
        if os.path.isfile("/tmp/token.txt"):
            os.remove("/tmp/token.txt")
        if os.path.isfile(self.stored_tokens_location):
            os.remove(self.stored_tokens_location)

        # make sure that we will read the token data next time...
        self.use_token_data_from_memory = False


    # fetching the main data...
    def status(self):
        """Get Vehicle status from API"""
        self.__acquire_tokens()
        #_LOGGER.debug(f"status: using token: {self.auto_token}")
        _LOGGER.debug(f"status: started... token exist? {self.auto_access_token is not None}")

        params = {"lrdt": "01-01-1970 00:00:00"}

        headers = {
            **apiHeaders,
            "auth-token": self.access_token,
            "Application-Id": self.region,
        }

        if NEW_API:
            headers = {
                **apiHeaders,
                "authorization": f"Bearer {self.auto_access_token}",
                "Application-Id": self.region,
            }
            response = session.get(
                f"{AUTONOMIC_URL}/telemetry/sources/fordpass/vehicles/{self.vin}", params=params, headers=headers
            )
            if response.status_code == 200:
                result = response.json()
                _LOGGER.debug(f"status: JSON: {result}")
                return result
            elif response.status_code == 401:
                _LOGGER.debug(f"status: 401")
                self.auth()
            else:
                _LOGGER.debug(f"status: (not 200) {response.text}")

        else:
            # we should get rid of OLD code...
            response = session.get(
                f"{BASE_URL}/vehicles/v5/{self.vin}/status", params=params, headers=headers
            )
            if response.status_code == 200:
                result = response.json()
                if result["status"] == 402:
                    response.raise_for_status()
                return result["vehiclestatus"]
            
            elif response.status_code == 401:
                _LOGGER.debug("status: 401 with status request: start token refresh")
                data = {}
                data["access_token"] = self.access_token
                data["refresh_token"] = self.refresh_token
                data["expiry_date"] = self.expires_at
                self.refresh_token_func(data)
                self.__acquire_tokens()
                headers = {
                    **apiHeaders,
                    "auth-token": self.access_token,
                    "Application-Id": self.region,
                }
                response = session.get(
                    f"{BASE_URL}/vehicles/v5/{self.vin}/status",
                    params=params,
                    headers=headers,
                )
                if response.status_code == 200:
                    result = response.json()

                return result["vehiclestatus"]
            
            response.raise_for_status()

    def messages(self):
        """Get Vehicle messages from API"""
        self.__acquire_tokens()
        _LOGGER.debug(f"messages: started... token exist? {self.auto_access_token is not None}")

        headers = {
            **apiHeaders,
            "Auth-Token": self.access_token,
            "Application-Id": self.region,
        }
        response = session.get(f"{GUARD_URL}/messagecenter/v3/messages?", headers=headers)
        if response.status_code == 200:
            result = response.json()
            _LOGGER.debug(f"messages: JSON: {result}")
            return result["result"]["messages"]
        elif response.status_code == 401:
            _LOGGER.debug(f"messages: 401")
            self.auth()
        else:
            _LOGGER.debug(f"messages: (not 200) {response.text}")

        response.raise_for_status()
        return None

    def vehicles(self):
        """Get vehicle list from account"""
        self.__acquire_tokens()
        _LOGGER.debug(f"vehicles: started... token exist? {self.auto_access_token is not None}")

        headers = {
            **apiHeaders,
            "Auth-Token": self.access_token,
            "Application-Id": self.region,
            "Countrycode": self.countrycode,
            "Locale": "EN-US"
        }

        data = {
            "dashboardRefreshRequest": "All"
        }
        response = session.post(
            f"{GUARD_URL}/expdashboard/v1/details/",
            headers=headers,
            data=json.dumps(data)
        )
        if response.status_code == 207 or response.status_code == 200:
            result = response.json()
            _LOGGER.debug(f"vehicles: JSON: {result}")
            return result
        elif response.status_code == 401:
            _LOGGER.debug(f"vehicles: 401")
            self.auth()
        else:
            _LOGGER.debug(f"vehicles: (not 200 or 207) {response.text}")

        response.raise_for_status()
        return None

    def guard_status(self):
        """Retrieve guard status from API"""
        self.__acquire_tokens()
        _LOGGER.debug(f"guard_status: started... token exist? {self.auto_access_token is not None}")

        params = {"lrdt": "01-01-1970 00:00:00"}

        headers = {
            **apiHeaders,
            "auth-token": self.access_token,
            "Application-Id": self.region,
        }

        response = session.get(
            f"{GUARD_URL}/guardmode/v1/{self.vin}/session",
            params=params,
            headers=headers,
        )
        return response.json()


    # operations
    def start(self):
        """
        Issue a start command to the engine
        """
        return self.__request_and_poll_command("remoteStart")

    def stop(self):
        """
        Issue a stop command to the engine
        """
        return self.__request_and_poll_command("cancelRemoteStart")

    def lock(self):
        """
        Issue a lock command to the doors
        """
        return self.__request_and_poll_command("lock")

    def unlock(self):
        """
        Issue an unlock command to the doors
        """
        return self.__request_and_poll_command("unlock")

    def enable_guard(self):
        """
        Enable Guard mode on supported models
        """
        self.__acquire_tokens()

        response = self.__make_request(
            "PUT", f"{GUARD_URL}/guardmode/v1/{self.vin}/session", None, None
        )
        _LOGGER.debug(f"enable_guard: {response.text}")
        return response

    def disable_guard(self):
        """
        Disable Guard mode on supported models
        """
        self.__acquire_tokens()
        response = self.__make_request(
            "DELETE", f"{GUARD_URL}/guardmode/v1/{self.vin}/session", None, None
        )
        _LOGGER.debug(f"disable_guard: {response.text}")
        return response

    def request_update(self, vin=None):
        """Send request to vehicle for update"""
        self.__acquire_tokens()
        if vin is None or len(vin) == 0:
            vin_to_requst = self.vin
        else:
            vin_to_requst = vin

        status = self.__request_and_poll_command("statusRefresh", vin_to_requst)
        return status


    # core functions...
    def __make_request(self, method, url, data, params):
        """
        Make a request to the given URL, passing data/params as needed
        """

        headers = {
            **apiHeaders,
            "auth-token": self.access_token,
            "Application-Id": self.region,
        }

        return getattr(requests, method.lower())(
            url, headers=headers, data=data, params=params
        )

    def __poll_status(self, url, command_id):
        """
        Poll the given URL with the given command ID until the command is completed
        """
        status = self.__make_request("GET", f"{url}/{command_id}", None, None)
        result = status.json()
        if result["status"] == 552:
            _LOGGER.debug("__poll_status: Command is pending")
            time.sleep(5)
            return self.__poll_status(url, command_id)  # retry after 5s
        if result["status"] == 200:
            _LOGGER.debug("__poll_status: Command completed successfully")
            return True
        _LOGGER.debug("__poll_status: Command failed")
        return False

    def __request_and_poll_command(self, command, vin=None):
        """Send command to the new Command endpoint"""
        self.__acquire_tokens()
        headers = {
            **apiHeaders,
            "Application-Id": self.region,
            "authorization": f"Bearer {self.auto_access_token}"
        }

        data = {
            "properties": {},
            "tags": {},
            "type": command,
            "wakeUp": True
        }
        if vin is None:
            r = session.post(
                f"{AUTONOMIC_URL}/command/vehicles/{self.vin}/commands",
                data=json.dumps(data),
                headers=headers
            )
        else:
            r = session.post(
                f"{AUTONOMIC_URL}/command/vehicles/{self.vin}/commands",
                data=json.dumps(data),
                headers=headers
            )

        _LOGGER.debug(f"__request_and_poll_command: Testing command status: {r.status_code} content: {r.text}")
        if r.status_code == 201:
            # New code to handle checking states table from vehicle data
            response = r.json()
            command_id = response["id"]
            i = 1
            while i < 14:
                # Check status every 10 seconds for 90 seconds until command completes or time expires
                status = self.status()
                _LOGGER.debug(f"__request_and_poll_command: STATUS {status}")

                if "states" in status:
                    _LOGGER.debug("__request_and_poll_command: States located")
                    if f"{command}Command" in status["states"]:
                        _LOGGER.debug(f"__request_and_poll_command: Found command {status["states"][f"{command}Command"]["commandId"]}")
                        if status["states"][f"{command}Command"]["commandId"] == command_id:
                            _LOGGER.debug(f"__request_and_poll_command: Making progress {status["states"][f"{command}Command"]}")
                            if status["states"][f"{command}Command"]["value"]["toState"] == "success":
                                _LOGGER.debug("__request_and_poll_command: Command succeeded")
                                return True
                            if status["states"][f"{command}Command"]["value"]["toState"] == "expired":
                                _LOGGER.debug("__request_and_poll_command: Command expired")
                                return False
                i += 1
                _LOGGER.debug("__request_and_poll_command: Looping again")
                time.sleep(10)
            # time.sleep(90)
            return False
        return False

    # def __request_and_poll(self, method, url):
    #     """Poll API until status code is reached, locking + remote start"""
    #     self.__acquire_token()
    #     command = self.__make_request(method, url, None, None)
    #
    #     if command.status_code == 200:
    #         result = command.json()
    #         if "commandId" in result:
    #             return self.__poll_status(url, result["commandId"])
    #
    #     return False
