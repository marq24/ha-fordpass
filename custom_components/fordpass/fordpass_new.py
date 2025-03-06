"""Fordpass API Library"""
import json
import logging
import os
import time

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

LOG_DATA = False

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
        #self.password = password # password is not used anymore...
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

        self._is_reauth_required = False
        _LOGGER.info(f"init vehicle object for vin: '{self.vin}' - using token from: {tokens_location}")


    def generate_tokens(self, urlstring, code_verifier):
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
        response = requests.post(
            f"{FORD_LOGIN_URL}/4566605f-43a7-400a-946e-89cc9fdb0bd7/B2C_1A_SignInSignUp_{self.country_code}/oauth2/v2.0/token",
            headers=headers,
            data=data,
            verify=False
        )

        # do not check the status code here - since it's not always return http 200!
        token_data = response.json()
        if "access_token" in token_data:
            _LOGGER.debug(f"generate_tokens 'OK'- http status: {response.status_code} - JSON: {token_data}")
            return self.generate_tokens_part2(token_data)
        else:
            _LOGGER.warning(f"generate_tokens 'FAILED'- http status: {response.status_code} - cause no 'access_token' in response: {token_data}")
            return False


    def generate_tokens_part2(self, token):
        headers = {**apiHeaders, "Application-Id": self.region}
        data = {"idpToken": token["access_token"]}
        response = requests.post(
            f"{GUARD_URL}/token/v2/cat-with-b2c-access-token",
            data=json.dumps(data),
            headers=headers,
            verify=False
        )

        # do not check the status code here - since it's not always return http 200!
        final_access_token = response.json()
        if "expires_in" in final_access_token:
            final_access_token["expiry_date"] = time.time() + final_access_token["expires_in"]
            del final_access_token["expires_in"]

        if "refresh_expires_in" in final_access_token:
            final_access_token["refresh_expiry_date"] = time.time() + final_access_token["refresh_expires_in"]
            del final_access_token["refresh_expires_in"]

        _LOGGER.debug(f"generate_tokens_part2 'OK' - http status: {response.status_code} - JSON: {final_access_token}")
        if self.save_token:
            self._write_token_to_storage(final_access_token)

        return True

    @property
    def require_reauth(self) -> bool:
        return self._is_reauth_required

    def mark_re_auth_required(self):
        self._is_reauth_required = True

    # def base64_url_encode(self, data):
    #     """Encode string to base64"""
    #     return urlsafe_b64encode(data).rstrip(b'=')
    #
    # def generate_hash(self, code):
    #     """Generate hash for login"""
    #     hashengine = hashlib.sha256()
    #     hashengine.update(code.encode('utf-8'))
    #     return self.base64_url_encode(hashengine.digest()).decode('utf-8')
    #
    # # IMHO (marq24) this can't work - since with the latest (1.7x versions we do not have the password from the user...
    # # so there is IMHO no wqy to get access again (if our tokens are invalidated)...
    # def re_auth(self):
    #     """New Authentication System """
    #     _LOGGER.debug("auth: New System")
    #
    #     # Auth Step1
    #     # ----------------
    #     headers1 = {
    #         **defaultHeaders,
    #         'Content-Type': 'application/json',
    #     }
    #     code1 = ''.join(random.choice(string.ascii_lowercase) for i in range(43))
    #     code_verifier1 = self.generate_hash(code1)
    #     url1 = f"{SSO_URL}/v1.0/endpoint/default/authorize?redirect_uri=fordapp://userauthorized&response_type=code&scope=openid&max_age=3600&client_id=9fb503e0-715b-47e8-adfd-ad4b7770f73b&code_challenge={code_verifier1}&code_challenge_method=S256"
    #     response1 = session.get(
    #         url1,
    #         headers=headers1,
    #     )
    #
    #     test2 = re.findall('data-ibm-login-url="(.*)"\s', response1.text)[0]
    #     url2 = SSO_URL + test2
    #
    #     # Auth Step2
    #     # ----------------
    #     headers2 = {
    #         **defaultHeaders,
    #         "Content-Type": "application/x-www-form-urlencoded",
    #     }
    #     data2 = {
    #         "operation": "verify",
    #         "login-form-type": "password",
    #         "username": self.username,
    #         "password": self.password
    #     }
    #     response2 = session.post(
    #         url2,
    #         headers=headers2,
    #         data=data2,
    #         allow_redirects=False
    #     )
    #
    #     if response2.status_code == 302:
    #         url3 = response2.headers["Location"]
    #     else:
    #         response2.raise_for_status()
    #
    #     # Auth Step3
    #     # ----------------
    #     headers3 = {
    #         **defaultHeaders,
    #         'Content-Type': 'application/json',
    #     }
    #     response3 = session.get(
    #         url3,
    #         headers=headers3,
    #         allow_redirects=False
    #     )
    #
    #     if response3.status_code == 302:
    #         url4 = response3.headers["Location"]
    #         query4 = requests.utils.urlparse(url4).query
    #         params4 = dict(x.split('=') for x in query4.split('&'))
    #         code4 = params4["code"]
    #         grant_id4 = params4["grant_id"]
    #     else:
    #         response3.raise_for_status()
    #
    #     # Auth Step4
    #     # ----------------
    #     headers4 = {
    #         **defaultHeaders,
    #         "Content-Type": "application/x-www-form-urlencoded",
    #     }
    #     data4 = {
    #         "client_id": "9fb503e0-715b-47e8-adfd-ad4b7770f73b",
    #         "grant_type": "authorization_code",
    #         "redirect_uri": 'fordapp://userauthorized',
    #         "grant_id": grant_id4,
    #         "code": code4,
    #         "code_verifier": code1
    #     }
    #     response4 = session.post(
    #         f"{SSO_URL}/oidc/endpoint/default/token",
    #         headers=headers4,
    #         data=data4
    #     )
    #
    #     if response4.status_code == 200:
    #         result4 = response4.json()
    #         if result4["access_token"]:
    #             access_token5 = result4["access_token"]
    #     else:
    #         response4.raise_for_status()
    #
    #     # Auth Step5
    #     # ----------------
    #     headers5 = {
    #         **apiHeaders,
    #         "Application-Id": self.region
    #     }
    #     data5 = {
    #         "ciToken": access_token5
    #     }
    #     response5 = session.post(
    #         f"{GUARD_URL}/token/v2/cat-with-ci-access-token",
    #         data=json.dumps(data5),
    #         headers=headers5,
    #     )
    #
    #     if response5.status_code == 200:
    #         result5 = response5.json()
    #
    #         # we have finally our access token that allows to request ford API's
    #         self.access_token = result5["access_token"]
    #         self.refresh_token = result5["refresh_token"]
    #         if "expires_in" in result5:
    #             result5["expiry_date"] = time.time() + result5["expires_in"]
    #             del result5["expires_in"]
    #             self.expires_at = result5["expiry_date"]
    #
    #         if "refresh_expires_in" in result5:
    #             result5["refresh_expiry_date"] = time.time() + result5["refresh_expires_in"]
    #             del result5["refresh_expires_in"]
    #
    #         auto_token = self._request_auto_token()
    #         self.auto_access_token = auto_token["access_token"]
    #         self.auto_refresh_token = auto_token["refresh_token"]
    #         if "expires_in" in auto_token:
    #             self.auto_expires_at = time.time() + auto_token["expires_in"]
    #             del auto_token["expires_in"]
    #
    #         if "refresh_expires_in" in auto_token:
    #             auto_token["refresh_expiry_date"] = time.time() + auto_token["refresh_expires_in"]
    #             del auto_token["refresh_expires_in"]
    #
    #         if self.save_token:
    #             # we want to store also the 'auto' token data...
    #             result5["auto_token"] = self.auto_access_token
    #             result5["auto_refresh_token"] = self.auto_refresh_token
    #             if self.auto_expires_at is not None:
    #                 result5["auto_expiry_date"] = self.auto_expires_at
    #
    #             self._write_token_to_storage(result5)
    #
    #         session.cookies.clear()
    #         return True
    #
    #     response5.raise_for_status()
    #     return False

    def __ensure_valid_tokens(self):
        # Fetch and refresh token as needed
        _LOGGER.debug("__ensure_valid_tokens()")
        # If file exists read in token file and check it's valid
        if self.save_token:
            # do not access every time the file system - since we are the only one
            # using the vehicle object, we can keep the token in memory (and
            # invalidate it if needed)
            if (not self.use_token_data_from_memory) and os.path.isfile(self.stored_tokens_location):
                prev_token_data = self._read_token_from_storage()
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
                prev_token_data = {}
                prev_token_data["access_token"] = self.access_token
                prev_token_data["refresh_token"] = self.refresh_token
                prev_token_data["expiry_date"] = self.expires_at
                prev_token_data["auto_token"] = self.auto_access_token
                prev_token_data["auto_refresh_token"] = self.auto_refresh_token
                prev_token_data["auto_expiry_date"] = self.auto_expires_at
        else:
            prev_token_data = {}
            prev_token_data["access_token"] = self.access_token
            prev_token_data["refresh_token"] = self.refresh_token
            prev_token_data["expiry_date"] = self.expires_at
            prev_token_data["auto_token"] = self.auto_access_token
            prev_token_data["auto_refresh_token"] = self.auto_refresh_token
            prev_token_data["auto_expiry_date"] = self.auto_expires_at

        # checking token data (and refreshing if needed)
        now_time = time.time()
        if self.expires_at and now_time > self.expires_at:
            _LOGGER.debug(f"__ensure_valid_tokens: token's expires_at {self.expires_at} has expired time-delta: {now_time - self.expires_at} -> requesting new token")
            refreshed_token = self.refresh_token_func(prev_token_data)
            _LOGGER.debug(f"__ensure_valid_tokens: result for new token: {len(refreshed_token)}")
            self.refresh_auto_token_func(refreshed_token)

        if self.auto_access_token is None or self.auto_expires_at is None:
            _LOGGER.debug(f"__ensure_valid_tokens: auto_access_token: '{self.auto_access_token}' or auto_expires_at: '{self.auto_expires_at}' is None -> requesting new auto-token")
            self.refresh_auto_token_func(prev_token_data)

        if self.auto_expires_at and now_time > self.auto_expires_at:
            _LOGGER.debug(f"__ensure_valid_tokens: auto-token's auto_expires_at {self.auto_expires_at} has expired time-delta: {now_time - self.auto_expires_at} -> requesting new auto-token")
            self.refresh_auto_token_func(prev_token_data)

        if self.access_token is None:
            _LOGGER.warning("__ensure_valid_tokens: self.access_token is None -> re_auth() this will probably fail")
            # No existing token exists so refreshing library
            self.mark_re_auth_required()
        else:
            _LOGGER.debug("__ensure_valid_tokens: Tokens are valid")

    def refresh_token_func(self, prev_token_data):
        """Refresh token if still valid"""
        _LOGGER.debug(f"refresh_token_func()")

        token_data = self._request_token(prev_token_data)
        if token_data is not False:

            # re-write the 'expires_in' to 'expiry_date'...
            if "expires_in" in token_data:
                token_data["expiry_date"] = time.time() + token_data["expires_in"]
                del token_data["expires_in"]

            if "refresh_expires_in" in token_data:
                token_data["refresh_expiry_date"] = time.time() + token_data["refresh_expires_in"]
                del token_data["refresh_expires_in"]

            if self.save_token:
                self._write_token_to_storage(token_data)

            self.access_token = token_data["access_token"]
            self.refresh_token = token_data["refresh_token"]
            self.expires_at = token_data["expiry_date"]

            _LOGGER.debug("refresh_token_func: OK")
            return token_data

        else:
            self.access_token = None
            self.refresh_token = None
            self.expires_at = None

            # also invalidating the auto-tokens...
            self.auto_access_token = None
            self.auto_refresh_token = None
            self.auto_expires_at = None
            _LOGGER.debug(f"refresh_token_func: FAILED!")

    def _request_token(self, prev_token_data):
        _LOGGER.debug("_request_token()")

        headers = {
            **apiHeaders,
            "Application-Id": self.region
        }
        data = {
            "refresh_token": prev_token_data["refresh_token"]
        }
        response = session.post(
            f"{GUARD_URL}/token/v2/cat-with-refresh-token",
            data=json.dumps(data),
            headers=headers,
        )

        if response.status_code == 200:
            result = response.json()
            _LOGGER.debug(f"_request_token: status OK")
            return result
        elif response.status_code == 401:
            _LOGGER.warning(f"_request_token: status: {response.status_code} - start re_auth() - this will probably fail")
            self.mark_re_auth_required()
            return False
        else:
            _LOGGER.warning(f"_request_token: status: {response.status_code} - no data read? {response.text}")
            response.raise_for_status()
            return False

    def refresh_auto_token_func(self, cur_token_data):
        _LOGGER.debug(f"refresh_auto_token_func()")
        auto_token = self._request_auto_token()
        if auto_token is not False:
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

                self._write_token_to_storage(cur_token_data)

            # finally setting our internal values...
            self.auto_access_token = auto_token["access_token"]
            self.auto_refresh_token = auto_token["refresh_token"]
            self.auto_expires_at = auto_token["expiry_date"]

            _LOGGER.debug("refresh_auto_token_func: OK")
        else:
            self.auto_access_token = None
            self.auto_refresh_token = None
            self.auto_expires_at = None
            _LOGGER.debug(f"refresh_auto_token_func: FAILED!")

    def _request_auto_token(self):
        """Get token from new autonomic API"""
        _LOGGER.debug("_request_auto_token()")
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
        response = session.post(
            f"{AUTONOMIC_ACCOUNT_URL}/auth/oidc/token",
            data=data,
            headers=headers
        )

        if response.status_code == 200:
            result = response.json()
            _LOGGER.debug(f"_request_auto_token: status OK")
            return result
        elif response.status_code == 401:
            _LOGGER.warning(f"_request_auto_token: status: {response.status_code} - start re_auth() - this will probably fail")
            self.mark_re_auth_required()
            return False
        else:
            _LOGGER.warning(f"_request_auto_token: status: {response.status_code} - no data read? {response.text}")
            response.raise_for_status()
            return False

    def _write_token_to_storage(self, token):
        """Save token to file for reuse"""
        _LOGGER.debug(f"_write_token_to_storage()")
        # check if parent exists...
        if not os.path.exists(os.path.dirname(self.stored_tokens_location)):
            try:
                os.makedirs(os.path.dirname(self.stored_tokens_location))
            except OSError as exc:  # Guard
                _LOGGER.debug(f"_write_token_to_storage: create dir caused {exc}")

        with open(self.stored_tokens_location, "w", encoding="utf-8") as outfile:
            json.dump(token, outfile)

        # make sure that we will read the token data next time...
        self.use_token_data_from_memory = False

    def _read_token_from_storage(self):
        """Read saved token from file"""
        _LOGGER.debug(f"_read_token_from_storage()")
        try:
            with open(self.stored_tokens_location, encoding="utf-8") as token_file:
                token = json.load(token_file)
                return token
        except ValueError:
            _LOGGER.debug("_read_token_from_storage: Fixing malformed token")
            self.mark_re_auth_required()
            with open(self.stored_tokens_location, encoding="utf-8") as token_file:
                token = json.load(token_file)
                return token

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


    # fetching the main data...
    def status(self):
        """Get Vehicle status from API"""

        # API-Reference?!
        # https://www.high-mobility.com/car-api/ford-data-api
        # https://github.com/mlaanderson/fordpass-api-doc

        self.__ensure_valid_tokens()
        #_LOGGER.debug(f"status: using token: {self.auto_token}")
        _LOGGER.debug(f"status() - auto_access_token exist? {self.auto_access_token is not None}")

        headers_state = {
            **apiHeaders,
            "authorization": f"Bearer {self.auto_access_token}",
            "Application-Id": self.region,
        }
        params_state = {
            "lrdt": "01-01-1970 00:00:00"
        }
        response_state = session.get(
            f"{AUTONOMIC_URL}/telemetry/sources/fordpass/vehicles/{self.vin}",
            params=params_state,
            headers=headers_state
        )

        if response_state.status_code == 200:
            result_state = response_state.json()
            if LOG_DATA:
                _LOGGER.debug(f"status: JSON: {result_state}")
            return result_state
        elif response_state.status_code == 401:
            _LOGGER.debug(f"status: 401")
            self.mark_re_auth_required()
            return None
        else:
            _LOGGER.debug(f"status: (not 200 or 401) {response_state.status_code} {response_state.text}")
            response_state.raise_for_status()
            return None

    def messages(self):
        """Get Vehicle messages from API"""
        self.__ensure_valid_tokens()
        _LOGGER.debug(f"messages() - access_token exist? {self.access_token is not None}")

        headers_msg = {
            **apiHeaders,
            "Auth-Token": self.access_token,
            "Application-Id": self.region,
        }
        response_msg = session.get(f"{GUARD_URL}/messagecenter/v3/messages?", headers=headers_msg)
        if response_msg.status_code == 200:
            result_msg = response_msg.json()
            if LOG_DATA:
                _LOGGER.debug(f"messages: JSON: {result_msg}")
            return result_msg["result"]["messages"]
        elif response_msg.status_code == 401:
            _LOGGER.debug(f"messages: 401")
            self.mark_re_auth_required()
            return None
        else:
            _LOGGER.debug(f"messages: (not 200 or 401) {response_msg.status_code} {response_msg.text}")
            response_msg.raise_for_status()
            return None

    def vehicles(self):
        """Get vehicle list from account"""
        self.__ensure_valid_tokens()
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
        response_veh = session.post(
            f"{GUARD_URL}/expdashboard/v1/details/",
            headers=headers_veh,
            data=json.dumps(data_veh)
        )
        if response_veh.status_code == 207 or response_veh.status_code == 200:
            result_veh = response_veh.json()
            if LOG_DATA:
                _LOGGER.debug(f"vehicles: JSON: {result_veh}")
            return result_veh
        elif response_veh.status_code == 401:
            _LOGGER.debug(f"vehicles: 401")
            self.mark_re_auth_required()
            return None
        else:
            _LOGGER.debug(f"vehicles: (not 200, 207 or 401) {response_veh.status_code} {response_veh.text}")
            response_veh.raise_for_status()
            return None

    def guard_status(self):
        """Retrieve guard status from API"""
        self.__ensure_valid_tokens()
        _LOGGER.debug(f"guard_status() - access_token exist? {self.access_token is not None}")

        headers_gs = {
            **apiHeaders,
            "auth-token": self.access_token,
            "Application-Id": self.region,
        }
        params_gs = {"lrdt": "01-01-1970 00:00:00"}

        response_gs = session.get(
            f"{GUARD_URL}/guardmode/v1/{self.vin}/session",
            params=params_gs,
            headers=headers_gs,
        )
        return response_gs.json()


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
        self.__ensure_valid_tokens()

        response = self.__make_request(
            "PUT", f"{GUARD_URL}/guardmode/v1/{self.vin}/session", None, None
        )
        _LOGGER.debug(f"enable_guard: {response.text}")
        return response

    def disable_guard(self):
        """
        Disable Guard mode on supported models
        """
        self.__ensure_valid_tokens()
        response = self.__make_request(
            "DELETE", f"{GUARD_URL}/guardmode/v1/{self.vin}/session", None, None
        )
        _LOGGER.debug(f"disable_guard: {response.text}")
        return response

    def request_update(self, vin=None):
        """Send request to vehicle for update"""
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
        self.__ensure_valid_tokens()
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
