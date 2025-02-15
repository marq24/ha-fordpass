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
    "Accept-Language": "en-us",
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

    def __init__(
        self, username, password, vin, region, save_token=False, config_location=""
    ):
        self.username = username
        self.password = password
        self.save_token = save_token
        self.region = REGIONS[region]["region"]
        self.country_code = REGIONS[region]["locale"]
        self.short_code = REGIONS[region]["locale_short"]
        self.countrycode = REGIONS[region]["countrycode"]
        self.vin = vin
        self.token = None
        self.expires = None
        self.expires_at = None
        self.refresh_token = None
        self.auto_token = None
        self.auto_expires_at = None
        retry = Retry(connect=3, backoff_factor=0.5)
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        if config_location == "":
            self.token_location = f".storage/fordpass/{username}_access_token.txt"
        else:
            _LOGGER.debug(config_location)
            self.token_location = config_location

    def base64_url_encode(self, data):
        """Encode string to base64"""
        return urlsafe_b64encode(data).rstrip(b'=')

    def generate_tokens(self, urlstring, code_verifier):
        code_new = urlstring.replace("fordapp://userauthorized/?code=", "")
        print(code_new)
        print(self.country_code)
        print(code_verifier)
        data = {
            "client_id": "09852200-05fd-41f6-8c21-d36d3497dc64",
            "grant_type": "authorization_code",
            "code_verifier": code_verifier,
            "code": code_new,
            "redirect_uri": "fordapp://userauthorized"

        }

        _LOGGER.debug(data)
        headers = {
            **loginHeaders,
        }
        req = requests.post(
            f"{FORD_LOGIN_URL}/4566605f-43a7-400a-946e-89cc9fdb0bd7/B2C_1A_SignInSignUp_{self.country_code}/oauth2/v2.0/token",
            headers=headers,
            data=data,
            verify=False
        )
        print(req.status_code)
        print(req.text)
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
        print(response.status_code)
        print(response.text)
        final_tokens = response.json()
        final_tokens["expiry_date"] = time.time() + final_tokens["expires_in"]

        self.write_token(final_tokens)
        return True

    def generate_hash(self, code):
        """Generate hash for login"""
        hashengine = hashlib.sha256()
        hashengine.update(code.encode('utf-8'))
        return self.base64_url_encode(hashengine.digest()).decode('utf-8')

    def auth(self):
        """New Authentication System """
        _LOGGER.debug("New System")
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

            self.token = result["access_token"]
            self.refresh_token = result["refresh_token"]
            self.expires_at = time.time() + result["expires_in"]
            auto_token = self.get_auto_token()
            self.auto_token = auto_token["access_token"]
            self.auto_expires_at = time.time() + result["expires_in"]
            if self.save_token:
                result["expiry_date"] = time.time() + result["expires_in"]
                result["auto_token"] = auto_token["access_token"]
                result["auto_refresh"] = auto_token["refresh_token"]
                result["auto_expiry"] = time.time() + auto_token["expires_in"]

                self.write_token(result)
            session.cookies.clear()
            return True
        response.raise_for_status()
        return False

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
            if self.save_token:
                result["expiry_date"] = time.time() + result["expires_in"]
                self.write_token(result)
            self.token = result["access_token"]
            self.refresh_token = result["refresh_token"]
            self.expires_at = time.time() + result["expires_in"]
            _LOGGER.debug("WRITING REFRESH TOKEN")
            return result
        if response.status_code == 401:
            _LOGGER.debug("401 response stage 2: refresh stage 1 token")
            self.auth()

    def __acquire_token(self):
        # Fetch and refresh token as needed
        # If file exists read in token file and check it's valid
        _LOGGER.debug("Fetching token")
        if self.save_token:
            if os.path.isfile(self.token_location):
                data = self.read_token()
                _LOGGER.debug(data)
                self.token = data["access_token"]
                self.refresh_token = data["refresh_token"]
                self.expires_at = data["expiry_date"]
                if "auto_token" in data and "auto_expiry" in data:
                    self.auto_token = data["auto_token"]
                    self.auto_expires_at = data["auto_expiry"]
                else:
                    _LOGGER.debug("AUTO token not set in file")
                    self.auto_token = None
                    self.auto_expires_at = None
            else:
                data = {}
                data["access_token"] = self.token
                data["refresh_token"] = self.refresh_token
                data["expiry_date"] = self.expires_at
                data["auto_token"] = self.auto_token
                data["auto_expiry"] = self.auto_expires_at
        else:
            data = {}
            data["access_token"] = self.token
            data["refresh_token"] = self.refresh_token
            data["expiry_date"] = self.expires_at
            data["auto_token"] = self.auto_token
            data["auto_expiry"] = self.auto_expires_at
        _LOGGER.debug(self.auto_token)
        _LOGGER.debug(self.auto_expires_at)
        if self.auto_token is None or self.auto_expires_at is None:
            result = self.refresh_token_func(data)
            _LOGGER.debug("Result Above for new TOKEN")
            self.refresh_auto_token(result)
        # self.auto_token = data["auto_token"]
        # self.auto_expires_at = data["auto_expiry"]
        if self.expires_at:
            if time.time() >= self.expires_at:
                _LOGGER.debug("No token, or has expired, requesting new token")
                self.refresh_token_func(data)
                # self.auth()
        if self.auto_expires_at:
            if time.time() >= self.auto_expires_at:
                _LOGGER.debug("Autonomic token expired")
                result = self.refresh_token_func(data)
                _LOGGER.debug("Result Above for new TOKEN")
                self.refresh_auto_token(result)
        if self.token is None:
            _LOGGER.debug("Fetching token4")
            # No existing token exists so refreshing library
            self.auth()
        else:
            _LOGGER.debug("Token is valid, continuing")

    def write_token(self, token):
        # check if parent exists...
        if not os.path.exists(os.path.dirname(self.token_location)):
            try:
                os.makedirs(os.path.dirname(self.token_location))
            except OSError as exc:  # Guard
                _LOGGER.debug(exc)

        """Save token to file for reuse"""
        with open(self.token_location, "w", encoding="utf-8") as outfile:
            token["expiry_date"] = time.time() + token["expires_in"]
            _LOGGER.debug(token)
            json.dump(token, outfile)

    def read_token(self):
        """Read saved token from file"""
        try:
            with open(self.token_location, encoding="utf-8") as token_file:
                token = json.load(token_file)
                return token
        except ValueError:
            _LOGGER.debug("Fixing malformed token")
            self.auth()
            with open(self.token_location, encoding="utf-8") as token_file:
                token = json.load(token_file)
                return token

    def clear_token(self):
        """Clear tokens from config directory"""
        if os.path.isfile("/tmp/fordpass_token.txt"):
            os.remove("/tmp/fordpass_token.txt")
        if os.path.isfile("/tmp/token.txt"):
            os.remove("/tmp/token.txt")
        if os.path.isfile(self.token_location):
            os.remove(self.token_location)

    def refresh_auto_token(self, result):
        auto_token = self.get_auto_token()
        _LOGGER.debug("AUTO Refresh")
        self.auto_token = auto_token["access_token"]
        self.auto_token_refresh = auto_token["refresh_token"]
        self.auto_expires_at = time.time() + auto_token["expires_in"]
        if self.save_token:
            # result["expiry_date"] = time.time() + result["expires_in"]
            result["auto_token"] = auto_token["access_token"]
            result["auto_refresh"] = auto_token["refresh_token"]
            result["auto_expiry"] = time.time() + auto_token["expires_in"]

            self.write_token(result)

    def get_auto_token(self):
        """Get token from new autonomic API"""
        _LOGGER.debug("Getting Auto Token")
        headers = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded"
        }

        data = {
            "subject_token": self.token,
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
            _LOGGER.debug(r.status_code)
            _LOGGER.debug(r.text)
            self.auto_token = result["access_token"]
            return result
        return False

    def status(self):
        """Get Vehicle status from API"""

        self.__acquire_token()

        params = {"lrdt": "01-01-1970 00:00:00"}

        headers = {
            **apiHeaders,
            "auth-token": self.token,
            "Application-Id": self.region,
        }
        _LOGGER.debug(self.auto_token)

        if NEW_API:
            headers = {
                **apiHeaders,
                "authorization": f"Bearer {self.auto_token}",
                "Application-Id": self.region,
            }
            r = session.get(
                f"{AUTONOMIC_URL}/telemetry/sources/fordpass/vehicles/{self.vin}", params=params, headers=headers
            )
            if r.status_code == 200:
                _LOGGER.debug(r.text)
                result = r.json()
                return result
        else:
            response = session.get(
                f"{BASE_URL}/vehicles/v5/{self.vin}/status", params=params, headers=headers
            )
            if response.status_code == 200:
                result = response.json()
                if result["status"] == 402:
                    response.raise_for_status()
                return result["vehiclestatus"]
            if response.status_code == 401:
                _LOGGER.debug("401 with status request: start token refresh")
                data = {}
                data["access_token"] = self.token
                data["refresh_token"] = self.refresh_token
                data["expiry_date"] = self.expires_at
                self.refresh_token_func(data)
                self.__acquire_token()
                headers = {
                    **apiHeaders,
                    "auth-token": self.token,
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
        self.__acquire_token()
        headers = {
            **apiHeaders,
            "Auth-Token": self.token,
            "Application-Id": self.region,
        }
        response = session.get(f"{GUARD_URL}/messagecenter/v3/messages?", headers=headers)
        if response.status_code == 200:
            result = response.json()
            return result["result"]["messages"]
            # _LOGGER.debug(result)
        _LOGGER.debug(response.text)
        if response.status_code == 401:
            self.auth()
        response.raise_for_status()
        return None

    def vehicles(self):
        """Get vehicle list from account"""
        self.__acquire_token()

        headers = {
            **apiHeaders,
            "Auth-Token": self.token,
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
        if response.status_code == 207:
            result = response.json()

            _LOGGER.debug(result)
            return result
        _LOGGER.debug(response.text)
        if response.status_code == 401:
            self.auth()
        response.raise_for_status()
        return None

    def guard_status(self):
        """Retrieve guard status from API"""
        self.__acquire_token()

        params = {"lrdt": "01-01-1970 00:00:00"}

        headers = {
            **apiHeaders,
            "auth-token": self.token,
            "Application-Id": self.region,
        }

        response = session.get(
            f"{GUARD_URL}/guardmode/v1/{self.vin}/session",
            params=params,
            headers=headers,
        )
        return response.json()

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
        self.__acquire_token()

        response = self.__make_request(
            "PUT", f"{GUARD_URL}/guardmode/v1/{self.vin}/session", None, None
        )
        _LOGGER.debug(response.text)
        return response

    def disable_guard(self):
        """
        Disable Guard mode on supported models
        """
        self.__acquire_token()
        response = self.__make_request(
            "DELETE", f"{GUARD_URL}/guardmode/v1/{self.vin}/session", None, None
        )
        _LOGGER.debug(response.text)
        return response

    def request_update(self, vin=""):
        """Send request to vehicle for update"""
        self.__acquire_token()
        if vin:
            vinnum = vin
        else:
            vinnum = self.vin
        status = self.__request_and_poll_command("statusRefresh", vinnum)
        return status

    def __make_request(self, method, url, data, params):
        """
        Make a request to the given URL, passing data/params as needed
        """

        headers = {
            **apiHeaders,
            "auth-token": self.token,
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
            _LOGGER.debug("Command is pending")
            time.sleep(5)
            return self.__poll_status(url, command_id)  # retry after 5s
        if result["status"] == 200:
            _LOGGER.debug("Command completed succesfully")
            return True
        _LOGGER.debug("Command failed")
        return False

    def __request_and_poll_command(self, command, vin=None):
        """Send command to the new Command endpoint"""
        self.__acquire_token()
        headers = {
            **apiHeaders,
            "Application-Id": self.region,
            "authorization": f"Bearer {self.auto_token}"
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

        _LOGGER.debug("Testing command")
        _LOGGER.debug(r.status_code)
        _LOGGER.debug(r.text)
        if r.status_code == 201:
            # New code to hanble checking states table from vehicle data
            response = r.json()
            command_id = response["id"]
            i = 1
            while i < 14:
                # Check status every 10 seconds for 90 seconds until command completes or time expires
                status = self.status()
                _LOGGER.debug("STATUS")
                _LOGGER.debug(status)

                if "states" in status:
                    _LOGGER.debug("States located")
                    if f"{command}Command" in status["states"]:
                        _LOGGER.debug("Found command")
                        _LOGGER.debug(status["states"][f"{command}Command"]["commandId"])
                        if status["states"][f"{command}Command"]["commandId"] == command_id:
                            _LOGGER.debug("Making progress")
                            _LOGGER.debug(status["states"][f"{command}Command"])
                            if status["states"][f"{command}Command"]["value"]["toState"] == "success":
                                _LOGGER.debug("Command succeeded")
                                return True
                            if status["states"][f"{command}Command"]["value"]["toState"] == "expired":
                                _LOGGER.debug("Command expired")
                                return False
                i += 1
                _LOGGER.debug("Looping again")
                time.sleep(10)
            # time.sleep(90)
            return False
        return False

    def __request_and_poll(self, method, url):
        """Poll API until status code is reached, locking + remote start"""
        self.__acquire_token()
        command = self.__make_request(method, url, None, None)

        if command.status_code == 200:
            result = command.json()
            if "commandId" in result:
                return self.__poll_status(url, result["commandId"])
            return False
        return False
