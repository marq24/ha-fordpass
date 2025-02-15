import glob
import json
import os
import re
import sys
from datetime import datetime

import requests

# Place this script in the /config/custom_components/fordpass folder on your HomeAssistant
# Add the details below
# run from a terminal in the /config/custom_components/fordpass folder: python3 autonomicData.py
# Script will automatically redact your VIN, VehicleID, and Geolocation details (lat, long) by default, but can be turned off

# USER INPUT DATA

# Required: Enter the VIN to query
fp_vin = ""

# Automatically redact json? (True or False) False is only recommended if you would like to save your json for personal use
redaction = True

# Optional: Enter your vehicle year (example: 2023)
vicYear = ""

# Optional: Enter your vehicle model (example: Lightning)
vicModel = ""

# You can turn off print statements if you want to use this script for other purposes (True or False)
verbose = True


def get_autonomic_token(ford_access_token):
    url = "https://accounts.autonomic.ai/v1/auth/oidc/token"
    headers = {
        "accept": "*/*",
        "content-type": "application/x-www-form-urlencoded"
    }
    data = {
        "subject_token": ford_access_token,
        "subject_issuer": "fordpass",
        "client_id": "fordpass-prod",
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "subject_token_type": "urn:ietf:params:oauth:token-type:jwt"
    }

    try:
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        autonomic_token_data = response.json()
        return autonomic_token_data

    except requests.exceptions.HTTPError as errh:
        print(f"HTTP Error: {errh}")
        print("Trying refresh token")
        get_autonomic_token(fpRefresh)
    except requests.exceptions.ConnectionError as errc:
        print(f"Error Connecting: {errc}")
        sys.exit()
    except requests.exceptions.Timeout as errt:
        print(f"Timeout Error: {errt}")
        sys.exit()
    except requests.exceptions.RequestException as err:
        print(f"Something went wrong: {err}")
        sys.exit()


def get_vehicle_status(vin, access_token):
    BASE_URL = "https://api.autonomic.ai/"
    endpoint = f"v1beta/telemetry/sources/fordpass/vehicles/{vin}:query"
    url = f"{BASE_URL}{endpoint}"
    headers = {
        "Authorization": f"Bearer {access_token}",  # Replace 'your_autonom_token' with the actual Autonomic API token
        "Content-Type": "application/json",
        "accept": "*/*"
    }
    redactionItems = ["lat", "lon", "vehicleId", "vin", "latitude", "longitude"]

    try:
        response = requests.post(url, headers=headers, json={})
        response.raise_for_status()  # Raise HTTPError for bad requests (4xx and 5xx status codes)

        # Parse the JSON response
        vehicle_status_data = response.json()

        # Redact sensitive information
        if redaction:
            redact_json(vehicle_status_data, redactionItems)
        return vehicle_status_data

    except requests.exceptions.HTTPError as errh:
        print(f"HTTP Error: {errh}")
    except requests.exceptions.ConnectionError as errc:
        print(f"Error Connecting: {errc}")
    except requests.exceptions.Timeout as errt:
        print(f"Timeout Error: {errt}")
    except requests.exceptions.RequestException as err:
        print(f"Something went wrong: {err}")


def redact_json(data, redaction):
    # Regular expression to match GPS coordinates
    gps_pattern = r'"gpsDegree":\s*-?\d+\.\d+,\s*"gpsFraction":\s*-?\d+\.\d+,\s*"gpsSign":\s*-?\d+\.\d+'

    if isinstance(data, dict):
        for key in list(data.keys()):
            if key in redaction:
                data[key] = 'REDACTED'
            else:
                if isinstance(data[key], str):
                    # Redact GPS coordinates in string values
                    data[key] = re.sub(gps_pattern, '"gpsDegree": "REDACTED", "gpsFraction": "REDACTED", "gpsSign": "REDACTED"', data[key])
                else:
                    redact_json(data[key], redaction)
            # Special handling for 'stringArrayValue'
            if key == 'stringArrayValue':
                for i in range(len(data[key])):
                    data[key][i] = re.sub(gps_pattern, '"gpsDegree": "REDACTED", "gpsFraction": "REDACTED", "gpsSign": "REDACTED"', data[key][i])
    elif isinstance(data, list):
        for item in data:
            redact_json(item, redaction)


if __name__ == "__main__":
    existing_ford_token = os.path.join("/config/.storage/fordpass", "*_access_token.txt")
    userToken = glob.glob(existing_ford_token)

    if userToken:
        for userTokenMatch in userToken:
            with open(userTokenMatch, 'r') as file:
                fp_token_data = json.load(file)
            fpToken = fp_token_data['access_token']
            fpRefresh = fp_token_data['refresh_token']
    else:
        print(f"Error finding FordPass token text file: {existing_ford_token}, {userToken}")
        sys.exit()

    if fp_vin == "":
        print("Please enter your VIN into the python script")
        sys.exit()

    if verbose:
        print("Starting")
    if redaction:
        redactionStatus = "_REDACTED"
        if verbose:
            print("Automatically redacting json")
    else:
        redactionStatus = ""
        if verbose:
            print("WARNING: json will contain sensitive information!")
    # Exchange Fordpass token for Autonomic Token
    autonomic_token = get_autonomic_token(fpToken)
    vehicle_status = get_vehicle_status(fp_vin, autonomic_token["access_token"])
    current_datetime = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    if vicYear != "":
        vicYear = vicYear.replace(" ", "_") + "-"
    if vicModel != "":
        vicModel = vicModel.replace(" ", "_")
    else:
        vicModel = "my"

    fileName = os.path.join(fordPassDir, f"{vicYear}{vicModel}_status_{current_datetime}{redactionStatus}.json")

    # Write the redacted JSON data to the file
    with open(fileName, 'w') as file:
        json.dump(vehicle_status, file, indent=4)
    if verbose:
        print(f"File saved: {fileName}")
        print("Note: json file will be deleted if ha-fordpass is updated")
