"""Constants for the FordPass integration."""
import json
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from re import sub
from typing import Final, NamedTuple, Callable, Any

from homeassistant.components.sensor import SensorStateClass, SensorDeviceClass, SensorEntityDescription
from homeassistant.const import UnitOfSpeed, UnitOfLength, UnitOfTemperature, PERCENTAGE, UnitOfPressure
from homeassistant.util import dt
from homeassistant.util.unit_system import UnitSystem

DOMAIN: Final = "fordpass"

VIN: Final = "vin"

MANUFACTURER: Final = "Ford Motor Company"

CONF_PRESSURE_UNIT: Final = "pressure_unit"
DEFAULT_PRESSURE_UNIT: Final = "kPa"
PRESSURE_UNITS: Final = ["PSI", "kPa", "BAR"]

UPDATE_INTERVAL: Final = "update_interval"
UPDATE_INTERVAL_DEFAULT: Final = 290 # looks like that the default auto-access_token expires after 5 minutes (300 seconds)

COORDINATOR: Final = "coordinator"
REGION: Final = "region"

REGION_OPTIONS: Final = ["USA", "Canada", "Australia", "UK&Europe", "Netherlands"]
DEFAULT_REGION: Final = "USA"

REGIONS: Final = {
    "Netherlands": {
        "region": "1E8C7794-FF5F-49BC-9596-A1E0C86C5B19",
        "locale": "nl-NL",
        "locale_short": "NL",
        "locale_url": "https://login.ford.nl",
        "countrycode": "NLD"
    },
    "UK&Europe": {
        "region": "1E8C7794-FF5F-49BC-9596-A1E0C86C5B19",
        "locale": "en-GB",
        "locale_short": "IE",  # Temp fix
        "locale_url": "https://login.ford.co.uk",
        "countrycode": "GBR"
    },
    "Australia": {
        "region": "5C80A6BB-CF0D-4A30-BDBF-FC804B5C1A98",
        "locale": "en-AU",
        "locale_short": "AUS",
        "locale_url": "https://login.ford.com",
        "countrycode": "AUS"
    },
    "USA": {
        "region": "71A3AD0A-CF46-4CCF-B473-FC7FE5BC4592",  # ???
        "locale": "en-US",
        "locale_short": "USA",
        "locale_url": "https://login.ford.com",  # Reverted from AU to US because it appears to be working
        "countrycode": "USA"
    },
    "Canada": {
        "region": "71A3AD0A-CF46-4CCF-B473-FC7FE5BC4592",
        "locale": "en-CA",
        "locale_short": "CAN",
        "locale_url": "https://login.ford.com",
        "countrycode": "USA"
    }
}

WINDOW_POSITIONS: Final = {
    "CLOSED": {
        "Fully_Closed": "Closed",
        "Fully_closed_position": "Closed",
        "Fully closed position": "Closed",
    },
    "OPEN": {
        "Fully open position": "Open",
        "Fully_Open": "Open",
        "Btwn 10% and 60% open": "Open-Partial",
    },
}

ROOT_STATES: Final = "states"
ROOT_EVENTS: Final = "events"
ROOT_METRICS: Final = "metrics"
ROOT_VEHICLES: Final = "vehicles"
UNSUPPORTED: Final = "Unsupported"

class ApiKey(NamedTuple):
    key: str
    state_fn: Callable[[dict], Any] = None
    attrs_fn: Callable[[dict, UnitSystem], Any] = None


class Tag(ApiKey, Enum):

    def __hash__(self) -> int:
        return hash(self.key)

    def __str__(self):
        return self.key

    def get_state(self, data):
        if self.state_fn:
            return self.state_fn(data)
        return None

    def get_attributes(self, data, units: UnitSystem):
        if self.attrs_fn:
            return self.attrs_fn(data, units)
        return None

    # Helper functions to simplify the callable implementations
    @staticmethod
    def to_camel(s):
        # Use regular expression substitution to replace underscores and hyphens with spaces,
        # then title case the string (capitalize the first letter of each word), and remove spaces
        s = sub(r"(_|-)+", " ", s).title().replace(" ", "")

        # Join the string, ensuring the first letter is lowercase
        return ''.join([s[0].lower(), s[1:]])

    @staticmethod
    def get_events(data):
        """Get the "events" dictionary."""
        return data.get(ROOT_EVENTS, {})

    @staticmethod
    def get_states(data):
        """Get the "states" dictionary."""
        return data.get(ROOT_STATES, {})

    @staticmethod
    def get_vehicles(data):
        """Get the "vehicles" dictionary."""
        return data.get(ROOT_VEHICLES, {})

    @staticmethod
    def get_metrics(data):
        """Get the metrics dictionary."""
        return data.get(ROOT_METRICS, {})

    @staticmethod
    def get_metrics_keyvalue(data, metrics_key, default=UNSUPPORTED):
        """Get a value from metrics with default fallback."""
        return data.get(ROOT_METRICS, {}).get(metrics_key, {}).get("value", default)

    @staticmethod
    def get_metrics_dict(data, metrics_key):
        """Get a complete metrics dictionary."""
        return data.get(ROOT_METRICS, {}).get(metrics_key, {})

    @staticmethod
    def localize_distance(value, units):
        if value is not None and value != -1:
            return units.length(value, UnitOfLength.KILOMETERS)
        return None

    @staticmethod
    def localize_temperature(value, units):
        if value is not None and value != -1:
            return units.temperature(value, UnitOfTemperature.CELSIUS)
        return None

    # State and attribute callable functions grouped by Tag

    # FUEL state + attributes
    def get_fuel_state(data):
        fuel_level = Tag.get_metrics_keyvalue(data, "fuelLevel")
        if fuel_level is not None:
            return round(fuel_level)
        return None

    def get_fuel_attrs(data, units:UnitSystem):
        fuel = {}
        fuel_range = Tag.get_metrics_keyvalue(data, "fuelRange", -1)
        if fuel_range != -1:
            fuel["fuelRange"] = Tag.localize_distance(fuel_range, units)

        # for PEV's
        battery_range = Tag.get_metrics_keyvalue(data, "xevBatteryRange", -1)
        if battery_range != -1:
            fuel["batteryRange"] = Tag.localize_distance(battery_range, units)

        return fuel

    # SOC state + attributes
    def get_soc_state(data):
        battery_soc = Tag.get_metrics_keyvalue(data, "xevBatteryStateOfCharge")
        if battery_soc is not None:
            return round(battery_soc, 2)
        return None

    def get_soc_attrs(data, units:UnitSystem):
        battery_range = Tag.get_metrics_keyvalue(data, "xevBatteryRange", -1)
        if battery_range != -1:
            return {"batteryRange": Tag.localize_distance(battery_range, units)}
        return None

    # BATTERY attributes
    def get_battery_attrs(data, units:UnitSystem):
        attrs = {}
        data_metrics = Tag.get_metrics(data)
        if "batteryVoltage" in data_metrics:
            attrs["batteryVoltage"] = data_metrics.get("batteryVoltage", 0)
        if "batteryLoadStatus" in data_metrics:
            attrs["batteryLoadStatus"] = data_metrics.get("batteryLoadStatus", UNSUPPORTED)
        return attrs or None

    # SEATBELT state + attributes
    def get_seatbelt_state(data):
        tmp_data = Tag.get_metrics(data).get("seatBeltStatus", [{}])
        if (len(tmp_data) > 0 and "value" in tmp_data[0]):
            return tmp_data[0]["value"]
        else:
            return None

    def get_seatbelt_attrs(data, units:UnitSystem):
        attrs = {}
        for a_seat in Tag.get_metrics(data).get("seatBeltStatus", [{}]):
            if "vehicleOccupantRole" in a_seat and "value" in a_seat:
                attrs[Tag.to_camel(a_seat["vehicleOccupantRole"])] = a_seat["value"]
        return attrs or None

    # TIRE_PRESSURE state + attributes
    def get_tire_pressure_state(data):
        return Tag.get_metrics(data).get("tirePressureSystemStatus", [{}])[0].get("value", UNSUPPORTED)

    def get_tire_pressure_attrs(data, units:UnitSystem):
        data_metrics = Tag.get_metrics(data)
        if "tirePressure" not in data_metrics:
            return None

        tire_pressures = {}
        digits = 0
        if units.pressure_unit == UnitOfPressure.PSI:
            digits = 1
        elif units.pressure_unit == UnitOfPressure.BAR:
            digits = 2

        for a_tire in data_metrics["tirePressure"]:
            tire_pressures[Tag.to_camel(a_tire["vehicleWheel"])] = f"{round(units.pressure(a_tire["value"], UnitOfPressure.KPA), digits)} {units.pressure_unit}"

        for a_tire in data_metrics["tirePressureStatus"]:
            tire_pressures[f"{Tag.to_camel(a_tire["vehicleWheel"])}_state"] = a_tire["value"]

        return tire_pressures

    # GPS state + attributes
    def get_gps_state(data):
        return Tag.get_metrics(data).get("position", {}).get("value", UNSUPPORTED).get("location", {})

    def get_gps_attr(data, units:UnitSystem):
        ret_gps = Tag.get_metrics_dict(data, "position")
        data_metrics = Tag.get_metrics(data)
        if "compassDirection" in data_metrics:
            ret_gps["compassDirection"] = data_metrics.get("compassDirection", {}).get("value", UNSUPPORTED)
        if "heading" in data_metrics:
            ret_gps["heading"] = data_metrics.get("heading", {}).get("value", UNSUPPORTED)
        return ret_gps

    # ALARM attributes
    def get_alarm_attr(data, units:UnitSystem):
        ret_alarm = Tag.get_metrics_dict(data, "alarmStatus")
        data_metrics = Tag.get_metrics(data)
        if "panicAlarmStatus" in data_metrics:
            ret_alarm["panicAlarmStatus"] = data_metrics.get("panicAlarmStatus", {}).get("value", UNSUPPORTED)
        return ret_alarm

    # DOOR_STATUS state + attributes
    def get_door_status_state(data):
        data_metrics = Tag.get_metrics(data)
        for value in data_metrics.get("doorStatus", []):
            if value["value"].upper() in ["CLOSED", "INVALID", "UNKNOWN"]:
                continue
            return "Open"
        if data_metrics.get("hoodStatus", {}).get("value", UNSUPPORTED).upper() == "OPEN":
            return "Open"
        return "Closed"

    def get_door_status_attrs(data, units:UnitSystem):
        data_metrics = Tag.get_metrics(data)
        ret_doors = {}
        for a_door in data_metrics.get("doorStatus", []):
            if "vehicleSide" in a_door:
                if "vehicleDoor" in a_door and a_door['vehicleDoor'].upper() == "UNSPECIFIED_FRONT":
                    ret_doors[Tag.to_camel(a_door['vehicleSide'])] = a_door['value']
                else:
                    ret_doors[Tag.to_camel(a_door['vehicleDoor'])] = a_door['value']
            else:
                ret_doors[Tag.to_camel(a_door["vehicleDoor"])] = a_door['value']

        if "hoodStatus" in data_metrics and "value" in data_metrics["hoodStatus"]:
            ret_doors["hood"] = data_metrics["hoodStatus"]["value"]

        return ret_doors or None

    # WINDOW_POSITION state + attributes
    def get_window_position_state(data):
        data_metrics = Tag.get_metrics(data)
        for window in data_metrics.get("windowStatus", []):
            windowrange = window.get("value", {}).get("doubleRange", {})
            if windowrange.get("lowerBound", 0.0) != 0.0 or windowrange.get("upperBound", 0.0) != 0.0:
                return "Open"
        return "Closed"

    def get_window_position_attrs(data, units:UnitSystem):
        data_metrics = Tag.get_metrics(data)
        ret_windows = {}
        for a_window in data_metrics.get("windowStatus", []):
            if "value" in a_window:
                if "vehicleWindow" in a_window and a_window["vehicleWindow"].upper().startswith("UNSPECIFIED_"):
                    front_or_rear_txt = a_window["vehicleWindow"].split("_")[1]
                    if front_or_rear_txt.upper() == "FRONT":
                        ret_windows[Tag.to_camel(a_window["vehicleSide"])] = a_window["value"]
                    else:
                        ret_windows[Tag.to_camel(front_or_rear_txt + "_" + a_window["vehicleSide"])] = a_window["value"]
                else:
                    ret_windows[Tag.to_camel(a_window["vehicleWindow"])] = a_window["value"]
            else:
                ret_windows[Tag.to_camel(a_window["vehicleWindow"] + "_") + a_window["vehicleSide"]] = a_window

        return ret_windows

    # LAST_REFRESH state
    def get_last_refresh_state(data):
        return dt.as_local(dt.parse_datetime(data.get("updateTime", 0)))

    # ELVEH state + attributes
    def get_elveh_state(data):
        data_metrics = Tag.get_metrics(data)
        if "xevBatteryRange" in data_metrics:
            return round(data_metrics.get("xevBatteryRange", {}).get("value"), 2)
        return None

    def get_elveh_attrs(data, units:UnitSystem):
        data_metrics = Tag.get_metrics(data)
        if "xevBatteryRange" not in data_metrics:
            return None

        elecs = {}
        metrics_mapping = {
            # Standard metrics with units parameter (even if not used)
            "xevBatteryIoCurrent":              ("batteryAmperage", lambda value, units: float(value), 0),
            "xevBatteryVoltage":                ("batteryVoltage", lambda value, units: float(value), 0),
            "xevBatteryStateOfCharge":          ("batteryCharge", lambda value, units: value, 0),
            "xevBatteryActualStateOfCharge":    ("batteryActualCharge", lambda value, units: value, 0),
            "xevBatteryPerformanceStatus":      ("batteryPerformanceStatus", lambda value, units: value, UNSUPPORTED),
            "xevBatteryEnergyRemaining":        ("batteryEnergyRemaining", lambda value, units: value, 0),
            "xevBatteryCapacity":               ("maximumBatteryCapacity", lambda value, units: value, 0),
            "xevBatteryMaximumRange":           ("maximumBatteryRange", lambda value, units: Tag.localize_distance(value, units), 0),
            "tripXevBatteryRangeRegenerated":   ("tripRangeRegenerated", lambda value, units: Tag.localize_distance(value, units), 0),
            # tripXevBatteryChargeRegenerated should be a previous FordPass feature called
            # "Driving Score". A % based on how much regen vs brake you use
            "tripXevBatteryChargeRegenerated":  ("tripDrivingScore", lambda value, units: value, 0),
            "xevTractionMotorVoltage":          ("motorVoltage", lambda value, units: float(value), 0),
            "xevTractionMotorCurrent":          ("motorAmperage", lambda value, units: float(value), 0),
        }
        
        # Process all metrics in a single loop
        for metric_key, (attr_name, transform_fn, default) in metrics_mapping.items():
            if metric_key in data_metrics:
                value = data_metrics.get(metric_key, {}).get("value", default)
                elecs[attr_name] = transform_fn(value, units)

        # Returning 0 in else - to prevent attribute from not displaying
        if "xevBatteryIoCurrent" in data_metrics and "xevBatteryVoltage" in data_metrics:
            batt_volt = elecs.get("batteryVoltage", 0)
            batt_amps = elecs.get("batteryAmperage", 0)

            if batt_volt != 0 and batt_amps != 0:
                elecs["batterykW"] = round((batt_volt * batt_amps) / 1000, 2)
            else:
                elecs["batterykW"] = 0

        # Returning 0 in else - to prevent attribute from not displaying
        if "xevTractionMotorVoltage" in data_metrics and "xevTractionMotorCurrent" in data_metrics:
            motor_volt = elecs.get("motorVoltage", 0)
            motor_amps = elecs.get("motorAmperage", 0)
            if motor_volt != 0 and motor_amps != 0:
                elecs["motorkW"] = round((motor_volt * motor_amps) / 1000, 2)
            else:
                elecs["motorkW"] = 0

        if "customMetrics" in data_metrics:
            for key in data_metrics.get("customMetrics", {}):
                if "accumulated-vehicle-speed-cruising-coaching-score" in key:
                    elecs["tripSpeedScore"] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

                if "accumulated-deceleration-coaching-score" in key:
                    elecs["tripDecelerationScore"] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

                if "accumulated-acceleration-coaching-score" in key:
                    elecs["tripAccelerationScore"] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

                if "custom:vehicle-electrical-efficiency" in key:
                    # Still don't know what this value is, but if I add it and get more data it could help to figure it out
                    elecs["tripElectricalEfficiency"] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

                if "custom:xevRemoteDataResponseStatus" in key:
                    elecs["remoteDataResponseStatus"] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

                if ":custom:xev-" in key:
                    entryName = Tag.to_camel(key.split(":custom:xev-")[1])
                    elecs[entryName] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

        data_events = Tag.get_events(data)
        if "customEvents" in data_events:
            tripDataStr = data_events.get("customEvents", {}).get("xev-key-off-trip-segment-data", {}).get("oemData", {}).get("trip_data", {}).get("stringArrayValue", [])
            for dataStr in tripDataStr:
                tripData = json.loads(dataStr)
                if "ambient_temperature" in tripData:
                    elecs["tripAmbientTemp"] = Tag.localize_temperature(tripData["ambient_temperature"], units)
                if "outside_air_ambient_temperature" in tripData:
                    elecs["tripOutsideAirAmbientTemp"] = Tag.localize_temperature(tripData["outside_air_ambient_temperature"], units)
                if "trip_duration" in tripData:
                    elecs["tripDuration"] = str(dt.parse_duration(str(tripData["trip_duration"])))
                if "cabin_temperature" in tripData:
                    elecs["tripCabinTemp"] = Tag.localize_temperature(tripData["cabin_temperature"], units)
                if "energy_consumed" in tripData:
                    elecs["tripEnergyConsumed"] = round(tripData["energy_consumed"] / 1000, 2)
                if "distance_traveled" in tripData:
                    elecs["tripDistanceTraveled"] = Tag.localize_distance(tripData["distance_traveled"], units)
                if ("energy_consumed" in tripData and tripData["energy_consumed"] is not None and "distance_traveled" in tripData and tripData["distance_traveled"] is not None):
                    if elecs["tripDistanceTraveled"] == 0 or elecs["tripEnergyConsumed"] == 0:
                        elecs["tripEfficiency"] = 0
                    else:
                        elecs["tripEfficiency"] = elecs["tripDistanceTraveled"] / elecs["tripEnergyConsumed"]
        return elecs

    # ELVEH_CHARGING attributes
    def get_elveh_charging_attrs(data, units:UnitSystem):
        data_metrics = Tag.get_metrics(data)
        if "xevBatteryChargeDisplayStatus" not in data_metrics:
            return None
        cs = {}

        metrics_mapping = {
            "xevPlugChargerStatus": ("plugStatus", lambda value, units: value, UNSUPPORTED),
            "xevChargeStationCommunicationStatus": ("chargingStationStatus", lambda value, units: value, UNSUPPORTED),
            "xevBatteryChargeDisplayStatus": ("chargingStatus", lambda value, units: value, UNSUPPORTED),
            "xevChargeStationPowerType": ("chargingType", lambda value, units: value, UNSUPPORTED),
            "xevBatteryChargerVoltageOutput": ("chargingVoltage", lambda value, units: float(value), 0),
            "xevBatteryChargerCurrentOutput": ("chargingAmperage", lambda value, units: float(value), 0),
            "xevBatteryTemperature": ("batteryTemperature", lambda value, units: Tag.localize_temperature(value, units), 0),
            "xevBatteryStateOfCharge": ("stateOfCharge", lambda value, units: value, 0),
            "xevBatteryChargerEnergyOutput": ("chargerEnergyOutput", lambda value, units: value, 0),
            # "tripXevBatteryDistanceAccumulated": ("distanceAccumulated", lambda value, units: units.length(value, UnitOfLength.KILOMETERS), 0),
        }

        # Process all metrics in a single loop
        for metric_key, (attr_name, transform_fn, default) in metrics_mapping.items():
            if metric_key in data_metrics:
                value = data_metrics.get(metric_key, {}).get("value", default)
                cs[attr_name] = transform_fn(value, units)

        # handle the self-calculated custom metrics stuff
        if "xevBatteryChargerVoltageOutput" in data_metrics and "xevBatteryChargerCurrentOutput" in data_metrics:
            ch_volt = cs.get("chargingVoltage", 0)
            ch_amps = cs.get("chargingAmperage", 0)

            if ch_volt != 0 and ch_amps != 0:
                cs["chargingkW"] = round((ch_volt * ch_amps) / 1000, 2)
            elif ch_volt != 0 and "xevBatteryIoCurrent" in data_metrics:
                # Get Battery Io Current for DC Charging calculation
                batt_amps = float(data_metrics.get("xevBatteryIoCurrent", {}).get("value", 0))
                # DC Charging calculation: Use absolute value for amperage to handle negative values
                if batt_amps != 0:
                    cs["chargingkW"] = round((ch_volt * abs(batt_amps)) / 1000, 2)
                else:
                    cs["chargingkW"] = 0
            else:
                cs["chargingkW"] = 0

        if "xevBatteryTimeToFullCharge" in data_metrics:
            cs_update_time = dt.parse_datetime(data_metrics.get("xevBatteryTimeToFullCharge", {}).get("updateTime", 0))
            cs_est_end_time = cs_update_time + timedelta(minutes=data_metrics.get("xevBatteryTimeToFullCharge", {}).get("value", 0))
            cs["estimatedEndTime"] = dt.as_local(cs_est_end_time)

        if "customMetrics" in data_metrics:
            for key in data_metrics.get("customMetrics", {}):
                if "custom:charge-power-kw" in key:
                    cs["chargePowerKw"] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

        return cs

    # ELVEH_PLUG attributes
    def get_elveh_plug_attrs(data, units:UnitSystem):
        data_metrics = Tag.get_metrics(data)
        if "xevPlugChargerStatus" not in data_metrics:
            return None
        cs = {}

        if "xevChargeStationCommunicationStatus" in data_metrics:
            cs["ChargeStationCommunicationStatus"] = data_metrics.get("xevChargeStationCommunicationStatus", {}).get("value", UNSUPPORTED)

        if "xevChargeStationPowerType" in data_metrics:
            cs["chargeStationPowerType"] = data_metrics.get("xevChargeStationPowerType", {}).get("value", UNSUPPORTED)

        return cs

    # EVCC_STATUS state
    def get_evcc_status_state(data):
        data_metrics = Tag.get_metrics(data)
        val = data_metrics.get("xevPlugChargerStatus", {}).get("value", UNSUPPORTED).upper()
        if val == 'DISCONNECTED':
            return "A"
        elif val == 'CONNECTED':
            if "xevBatteryChargeDisplayStatus" in data_metrics:
                secondary_val = data_metrics.get("xevBatteryChargeDisplayStatus", {}).get("value", UNSUPPORTED).upper()
                if secondary_val == "IN_PROGRESS":
                    return "C"
            return "B"
        elif val == 'CHARGING' or val == 'CHARGINGAC':
            return "C"
        else:
            return "UNKNOWN"

    # ZONE_LIGHTING state + attributes
    def get_zone_lighting_state(data):
        data_metrics = Tag.get_metrics(data)
        return data_metrics.get("zoneLighting", {}).get("zoneStatusData", {}).get("value", UNSUPPORTED)

    def get_zone_lighting_attrs(data, units:UnitSystem):
        data_metrics = Tag.get_metrics(data)
        if "zoneLighting" not in data_metrics:
            return None

        if data_metrics["zoneLighting"] is None or data_metrics["zoneLighting"].get("zoneStatusData") is None:
            return None

        zone = {}

        # Process zone status data
        if data_metrics["zoneLighting"]["zoneStatusData"]:
            for key, value in data_metrics["zoneLighting"]["zoneStatusData"].items():
                if value and "value" in value:
                    zone[Tag.to_camel("zone_" + key)] = value["value"]

        # Process light switch status data
        if data_metrics["zoneLighting"].get("lightSwitchStatusData"):
            for key, value in data_metrics["zoneLighting"]["lightSwitchStatusData"].items():
                if value and "value" in value:
                    zone[Tag.to_camel(key)] = value["value"]

        # Process fault status and shutdown warning
        for status_field in ["zoneLightingFaultStatus", "zoneLightingShutDownWarning"]:
            if data_metrics["zoneLighting"].get(status_field) and "value" in data_metrics["zoneLighting"][status_field]:
                zone[status_field] = data_metrics["zoneLighting"][status_field]["value"]

        return zone

    # REMOTE_START_STATUS state + attributes
    def get_remote_start_status_state(data):
        countdown_timer = Tag.get_metrics_keyvalue(data, "remoteStartCountdownTimer", 0)
        return "Active" if countdown_timer > 0 else "Inactive"

    def get_remote_start_status_attrs(data, units:UnitSystem):
        return {"countdown": Tag.get_metrics_keyvalue(data, "remoteStartCountdownTimer", 0)}

    # MESSAGES state + attributes
    def get_messages_state(data):
        messages = data.get("messages")
        return len(messages) if messages is not None else None

    def get_messages_attrs(data, units:UnitSystem):
        messages = {}
        count = 1
        for value in data.get("messages", []):
            messages[f"msg{count:03}_Date"] = f"{value["createdDate"]}"
            messages[f"msg{count:03}_Type"] = f"{value["messageType"]}"
            messages[f"msg{count:03}_Subject"] = f"{value["messageSubject"]}"
            messages[f"msg{count:03}_Content"] = f"{value["messageBody"]}"
            count = count + 1
        return messages

    # DIESEL_SYSTEM_STATUS attributes
    def get_diesel_system_status_attrs(data, units:UnitSystem):
        data_metrics = Tag.get_metrics(data)
        if data_metrics.get("indicators", {}).get("dieselExhaustOverTemp", {}).get("value") is not None:
            return {"dieselExhaustOverTemp": data_metrics["indicators"]["dieselExhaustOverTemp"]["value"]}
        return None

    # EXHAUST_FLUID_LEVEL attributes
    def get_exhaust_fluid_level_attrs(data, units:UnitSystem):
        data_metrics = Tag.get_metrics(data)
        exhaustdata = {}

        if data_metrics.get("dieselExhaustFluidLevelRangeRemaining", {}).get("value") is not None:
            exhaustdata["dieselExhaustFluidRange"] = data_metrics["dieselExhaustFluidLevelRangeRemaining"]["value"]

        indicators = data_metrics.get("indicators", {})
        indicator_fields = ["dieselExhaustFluidLow", "dieselExhaustFluidSystemFault"]

        for field in indicator_fields:
            if indicators.get(field, {}).get("value") is not None:
                exhaustdata[field] = indicators[field]["value"]

        return exhaustdata or None

    # SPEED attributes
    def get_speed_attrs(data, units:UnitSystem):
        data_metrics = Tag.get_metrics(data)
        attribs = {}

        metric_fields = [
            "acceleration",
            "acceleratorPedalPosition",
            "brakePedalStatus",
            "brakeTorque",
            "gearLeverPosition",
            "parkingBrakeStatus",
            "torqueAtTransmission",
            "wheelTorqueStatus"
            "yawRate"
        ]
        # Fields that are only relevant for non-electric vehicles
        if "xevBatteryVoltage" not in data_metrics:
            metric_fields.append("engineSpeed")
            metric_fields.append("tripFuelEconomy")

        for field in metric_fields:
            if field in data_metrics and "value" in data_metrics[field]:
                attribs[field] = data_metrics[field]["value"]

        return attribs or None

    # INDICATORS state + attributes
    def get_indicators_state(data):
        return sum(1 for indicator in Tag.get_metrics(data).get("indicators", {}).values() if indicator.get("value"))

    def get_indicators_attrs(data, units:UnitSystem):
        data_metrics = Tag.get_metrics(data)
        alerts = {}

        for key, value in data_metrics.get("indicators", {}).items():
            if value.get("value") is not None:
                if value.get("additionalInfo") is not None:
                    alerts[f"{Tag.to_camel(key)}_{Tag.to_camel(value.get("additionalInfo"))}"] = value["value"]
                else:
                    alerts[Tag.to_camel(key)] = value["value"]

        return alerts or None

    # OUTSIDE_TEMP attributes
    def get_outside_temp_attrs(data, units:UnitSystem):
        ambient_temp = Tag.get_metrics_keyvalue(data, "ambientTemp")
        if ambient_temp is not None:
            return {"ambientTemp": Tag.localize_temperature(ambient_temp, units)}
        return None

    # DEEPSLEEP state
    def get_deepsleep_state(data):
        state = Tag.get_states(data).get("commandPreclusion", {}).get("value", {}).get("toState", UNSUPPORTED)
        if state.upper() == "COMMANDS_PRECLUDED":
            return "ACTIVE"
        elif state.upper() == "COMMANDS_PERMITTED":
            return "DISABLED"
        else:
            return state

    ##################################################
    ##################################################

    TRACKER = ApiKey(key="tracker")
    DOOR_LOCK = ApiKey(key="doorlock")

    IGNITION = ApiKey(key="ignition")
    GUARD_MODE = ApiKey(key="guardmode")

    UPDATE_DATA = ApiKey(key="update_data")
    REQUEST_REFRESH = ApiKey(key="request_refresh")

    ##################################################
    ##################################################

    ODOMETER            = ApiKey(key="odometer",
                                 state_fn=lambda data: Tag.get_metrics_keyvalue(data, "odometer"),
                                 attrs_fn=lambda data, units: Tag.get_metrics_dict(data, "odometer"))
    FUEL                = ApiKey(key="fuel",
                                 state_fn=get_fuel_state,
                                 attrs_fn=get_fuel_attrs)
    BATTERY             = ApiKey(key="battery",
                                 state_fn=lambda data: round(Tag.get_metrics_keyvalue(data, "batteryStateOfCharge", 0)),
                                 attrs_fn=get_battery_attrs)
    OIL                 = ApiKey(key="oil",
                                 state_fn=lambda data: Tag.get_metrics_keyvalue(data, "oilLifeRemaining"),
                                 attrs_fn=lambda data, units: Tag.get_metrics_dict(data, "oilLifeRemaining"))
    TIRE_PRESSURE       = ApiKey(key="tirePressure",
                                 state_fn=get_tire_pressure_state,
                                 attrs_fn=get_tire_pressure_attrs)
    GPS                 = ApiKey(key="gps",
                                 state_fn=get_gps_state,
                                 attrs_fn=get_gps_attr)
    ALARM               = ApiKey(key="alarm",
                                 state_fn=lambda data: Tag.get_metrics_keyvalue(data, "alarmStatus"),
                                 attrs_fn=get_alarm_attr)
    IGNITION_STATUS     = ApiKey(key="ignitionStatus",
                                 state_fn=lambda data: Tag.get_metrics_keyvalue(data, "ignitionStatus"),
                                 attrs_fn=lambda data, units: Tag.get_metrics_dict(data, "ignitionStatus"))
    DOOR_STATUS         = ApiKey(key="doorStatus",
                                 state_fn=get_door_status_state,
                                 attrs_fn=get_door_status_attrs)
    WINDOW_POSITION     = ApiKey(key="windowPosition",
                                 state_fn=get_window_position_state,
                                 attrs_fn=get_window_position_attrs)
    LAST_REFRESH        = ApiKey(key="lastRefresh",
                                 state_fn=get_last_refresh_state)
    ELVEH               = ApiKey(key="elVeh",
                                 state_fn=get_elveh_state,
                                 attrs_fn=get_elveh_attrs)
    ELVEH_CHARGING      = ApiKey(key="elVehCharging",
                                 state_fn=lambda data: Tag.get_metrics_keyvalue(data, "xevBatteryChargeDisplayStatus"),
                                 attrs_fn=get_elveh_charging_attrs)
    ELVEH_PLUG          = ApiKey(key="elVehPlug",
                                 state_fn=lambda data: Tag.get_metrics_keyvalue(data, "xevPlugChargerStatus"),
                                 attrs_fn=get_elveh_plug_attrs)
    DEEPSLEEP           = ApiKey(key="deepSleep",
                                 state_fn=get_deepsleep_state)
    REMOTE_START_STATUS = ApiKey(key="remoteStartStatus",
                                 state_fn=get_remote_start_status_state,
                                 attrs_fn=get_remote_start_status_attrs)
    ZONE_LIGHTING       = ApiKey(key="zoneLighting",
                                 state_fn=get_zone_lighting_state,
                                 attrs_fn=get_zone_lighting_attrs)
    MESSAGES            = ApiKey(key="messages",
                                 state_fn=get_messages_state,
                                 attrs_fn=get_messages_attrs)
    DIESEL_SYSTEM_STATUS= ApiKey(key="dieselSystemStatus",
                                 state_fn=lambda data: Tag.get_metrics_keyvalue(data, "dieselExhaustFilterStatus"),
                                 attrs_fn=get_diesel_system_status_attrs)
    EXHAUST_FLUID_LEVEL = ApiKey(key="exhaustFluidLevel",
                                 state_fn=lambda data: Tag.get_metrics_keyvalue(data, "dieselExhaustFluidLevel"),
                                 attrs_fn=get_exhaust_fluid_level_attrs)
    SPEED               = ApiKey(key="speed",
                                 state_fn=lambda data: Tag.get_metrics_keyvalue(data, "speed"),
                                 attrs_fn=get_speed_attrs)
    INDICATORS          = ApiKey(key="indicators",
                                 state_fn=get_indicators_state,
                                 attrs_fn=get_indicators_attrs)
    COOLANT_TEMP        = ApiKey(key="coolantTemp",
                                 state_fn=lambda data: Tag.get_metrics_keyvalue(data, "engineCoolantTemp"))
    OUTSIDE_TEMP        = ApiKey(key="outsideTemp",
                                 state_fn=lambda data: Tag.get_metrics_keyvalue(data, "outsideTemperature"),
                                 attrs_fn=get_outside_temp_attrs)
    ENGINE_OIL_TEMP     = ApiKey(key="engineOilTemp",
                                 state_fn=lambda data: Tag.get_metrics_keyvalue(data, "engineOilTemp"))
    SOC                 = ApiKey(key="soc",
                                 state_fn=get_soc_state,
                                 attrs_fn=get_soc_attrs)
    EVCC_STATUS         = ApiKey(key="evccStatus",
                                 state_fn=get_evcc_status_state)
    SEATBELT            = ApiKey(key="seatbelt",
                                 state_fn=get_seatbelt_state,
                                 attrs_fn=get_seatbelt_attrs)

    DEEPSLEEP_IN_PROGRESS   = ApiKey(key="deepSleepInProgress",
                                     state_fn=lambda data: Tag.get_metrics_keyvalue(data, "deepSleepInProgress"))
    FIRMWAREUPG_IN_PROGRESS = ApiKey(key="firmwareUpgInProgress",
                                     state_fn=lambda data: Tag.get_metrics_keyvalue(data, "firmwareUpgradeInProgress"),
                                     attrs_fn=lambda data, units: Tag.get_metrics_dict(data, "firmwareUpgradeInProgress"))

    # Debug Sensors (Disabled by default)
    EVENTS = ApiKey(key="events",
                    state_fn=lambda data: len(Tag.get_events(data)),
                    attrs_fn=lambda data, units: Tag.get_events(data))
    METRICS = ApiKey(key="metrics",
                     state_fn=lambda data: len(Tag.get_metrics(data)),
                     attrs_fn=lambda data, units: Tag.get_metrics(data))
    STATES = ApiKey(key="states",
                    state_fn=lambda data: len(Tag.get_states(data)),
                    attrs_fn=lambda data, units: Tag.get_states(data))
    VEHICLES = ApiKey(key="vehicles",
                      state_fn=lambda data: len(Tag.get_vehicles(data)),
                      attrs_fn=lambda data, units: Tag.get_vehicles(data))

# tags that are only available for gas/diesel/plugin-hybrid (PHEV) vehicles...
FUEL_OR_PEV_ONLY_TAGS: Final = [
    Tag.FUEL,
    Tag.ENGINE_OIL_TEMP,
    Tag.DIESEL_SYSTEM_STATUS,
    Tag.EXHAUST_FLUID_LEVEL,
]

# tags that are only available for electric vehicles...
EV_ONLY_TAGS: Final = [
    Tag.SOC,
    Tag.EVCC_STATUS,
    Tag.ELVEH,
    Tag.ELVEH_PLUG,
    Tag.ELVEH_CHARGING,
]


@dataclass
class ExtSensorEntityDescription(SensorEntityDescription, frozen_or_thawed=True):
    tag: Tag | None = None
    skip_existence_check: bool | None = None


SENSORS = [
    # Tag.ODOMETER: {"icon": "mdi:counter", "state_class": "total", "device_class": "distance", "api_key": "odometer", "measurement": UnitOfLength.KILOMETERS},
    ExtSensorEntityDescription(
        tag=Tag.ODOMETER,
        key=Tag.ODOMETER.key,
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        has_entity_name=True,
    ),
    # Tag.FUEL: {"icon": "mdi:gas-station", "api_key": "fuelLevel", "measurement": PERCENTAGE},
    ExtSensorEntityDescription(
        tag=Tag.FUEL,
        key=Tag.FUEL.key,
        icon="mdi:gas-station",
        native_unit_of_measurement=PERCENTAGE,
        has_entity_name=True,
    ),
    # Tag.BATTERY: {"icon": "mdi:car-battery", "state_class": "measurement", "api_key": "batteryStateOfCharge", "measurement": PERCENTAGE},
    ExtSensorEntityDescription(
        tag=Tag.BATTERY,
        key=Tag.BATTERY.key,
        icon="mdi:car-battery",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        has_entity_name=True,
    ),
    # Tag.OIL: {"icon": "mdi:oil", "api_key": "oilLifeRemaining", "measurement": PERCENTAGE},
    ExtSensorEntityDescription(
        tag=Tag.OIL,
        key=Tag.OIL.key,
        icon="mdi:oil",
        native_unit_of_measurement=PERCENTAGE,
        has_entity_name=True,
    ),
    # Tag.TIRE_PRESSURE: {"icon": "mdi:car-tire-alert", "api_key": "tirePressure"},
    ExtSensorEntityDescription(
        tag=Tag.TIRE_PRESSURE,
        key=Tag.TIRE_PRESSURE.key,
        icon="mdi:car-tire-alert",
        has_entity_name=True,
    ),
    # Tag.GPS: {"icon": "mdi:radar", "api_key": "position"},
    ExtSensorEntityDescription(
        tag=Tag.GPS,
        key=Tag.GPS.key,
        icon="mdi:radar",
        has_entity_name=True,
    ),
    # Tag.ALARM: {"icon": "mdi:bell", "api_key": "alarmStatus"},
    ExtSensorEntityDescription(
        tag=Tag.ALARM,
        key=Tag.ALARM.key,
        icon="mdi:bell",
        has_entity_name=True,
    ),
    # Tag.IGNITION_STATUS: {"icon": "hass:power", "api_key": "ignitionStatus"},
    ExtSensorEntityDescription(
        tag=Tag.IGNITION_STATUS,
        key=Tag.IGNITION_STATUS.key,
        icon="hass:power",
        has_entity_name=True,
    ),
    # Tag.DOOR_STATUS: {"icon": "mdi:car-door", "api_key": "doorStatus"},
    ExtSensorEntityDescription(
        tag=Tag.DOOR_STATUS,
        key=Tag.DOOR_STATUS.key,
        icon="mdi:car-door",
        has_entity_name=True,
    ),
    # Tag.WINDOW_POSITION: {"icon": "mdi:car-door", "api_key": "windowStatus"},
    ExtSensorEntityDescription(
        tag=Tag.WINDOW_POSITION,
        key=Tag.WINDOW_POSITION.key,
        icon="mdi:car-door",
        has_entity_name=True,
    ),
    # Tag.LAST_REFRESH: {"icon": "mdi:clock", "device_class": "timestamp", "api_key": "lastRefresh", "skip_existence_check": True},
    ExtSensorEntityDescription(
        tag=Tag.LAST_REFRESH,
        key=Tag.LAST_REFRESH.key,
        icon="mdi:clock",
        device_class=SensorDeviceClass.TIMESTAMP,
        skip_existence_check=True,
        has_entity_name=True,
    ),
    # Tag.ELVEH: {"icon": "mdi:ev-station", "api_key": "xevBatteryRange", "device_class": "distance", "state_class": "measurement", "measurement": UnitOfLength.KILOMETERS},
    ExtSensorEntityDescription(
        tag=Tag.ELVEH,
        key=Tag.ELVEH.key,
        icon="mdi:ev-station",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        has_entity_name=True,
    ),
    # Tag.ELVEH_CHARGING: {"icon": "mdi:ev-station", "api_key": "xevBatteryChargeDisplayStatus"},
    ExtSensorEntityDescription(
        tag=Tag.ELVEH_CHARGING,
        key=Tag.ELVEH_CHARGING.key,
        icon="mdi:ev-station",
        has_entity_name=True,
    ),
    # Tag.ELVEH_PLUG: {"icon": "mdi:connection", "api_key": "xevPlugChargerStatus"},
    ExtSensorEntityDescription(
        tag=Tag.ELVEH_PLUG,
        key=Tag.ELVEH_PLUG.key,
        icon="mdi:connection",
        has_entity_name=True,
    ),
    # Tag.SPEED: {"icon": "mdi:speedometer", "device_class": "speed", "state_class": "measurement", "api_key": "speed", "measurement": UnitOfSpeed.METERS_PER_SECOND},
    ExtSensorEntityDescription(
        tag=Tag.SPEED,
        key=Tag.SPEED.key,
        icon="mdi:speedometer",
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        has_entity_name=True,
    ),
    # Tag.INDICATORS: {"icon": "mdi:engine-outline", "api_key": "indicators"},
    ExtSensorEntityDescription(
        tag=Tag.INDICATORS,
        key=Tag.INDICATORS.key,
        icon="mdi:engine-outline",
        has_entity_name=True,
    ),
    # Tag.COOLANT_TEMP: {"icon": "mdi:coolant-temperature", "api_key": "engineCoolantTemp", "state_class": "measurement", "device_class": "temperature", "measurement": UnitOfTemperature.CELSIUS},
    ExtSensorEntityDescription(
        tag=Tag.COOLANT_TEMP,
        key=Tag.COOLANT_TEMP.key,
        icon="mdi:coolant-temperature",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        has_entity_name=True,
    ),
    # Tag.OUTSIDE_TEMP: {"icon": "mdi:thermometer", "state_class": "measurement", "device_class": "temperature", "api_key": "outsideTemperature", "measurement": UnitOfTemperature.CELSIUS},
    ExtSensorEntityDescription(
        tag=Tag.OUTSIDE_TEMP,
        key=Tag.OUTSIDE_TEMP.key,
        icon="mdi:thermometer",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        has_entity_name=True,
    ),
    # Tag.ENGINE_OIL_TEMP: {"icon": "mdi:oil-temperature", "state_class": "measurement", "device_class": "temperature", "api_key": "engineOilTemp", "measurement": UnitOfTemperature.CELSIUS},
    ExtSensorEntityDescription(
        tag=Tag.ENGINE_OIL_TEMP,
        key=Tag.ENGINE_OIL_TEMP.key,
        icon="mdi:oil-temperature",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        has_entity_name=True,
    ),
    # Tag.DEEPSLEEP: {"icon": "mdi:power-sleep", "name": "Deep Sleep Mode Active", "api_key": "commandPreclusion", "api_class": "states"},
    ExtSensorEntityDescription(
        tag=Tag.DEEPSLEEP,
        key=Tag.DEEPSLEEP.key,
        icon="mdi:power-sleep",
        name="Deep Sleep Mode Active",
        has_entity_name=True,
    ),
    # Tag.REMOTE_START_STATUS: {"icon": "mdi:remote", "api_key": "remoteStartCountdownTimer"},
    ExtSensorEntityDescription(
        tag=Tag.REMOTE_START_STATUS,
        key=Tag.REMOTE_START_STATUS.key,
        icon="mdi:remote",
        has_entity_name=True,
    ),
    # Tag.MESSAGES: {"icon": "mdi:message-text", "api_key": "messages", "measurement": "messages", "skip_existence_check": True},
    ExtSensorEntityDescription(
        tag=Tag.MESSAGES,
        key=Tag.MESSAGES.key,
        icon="mdi:message-text",
        native_unit_of_measurement="messages",
        skip_existence_check=True,
        has_entity_name=True,
    ),
    # Tag.DIESEL_SYSTEM_STATUS: {"icon": "mdi:smoking-pipe", "api_key": "dieselExhaustFilterStatus"},
    ExtSensorEntityDescription(
        tag=Tag.DIESEL_SYSTEM_STATUS,
        key=Tag.DIESEL_SYSTEM_STATUS.key,
        icon="mdi:smoking-pipe",
        has_entity_name=True,
    ),
    # Tag.EXHAUST_FLUID_LEVEL: {"icon": "mdi:barrel", "api_key": "dieselExhaustFluidLevel", "measurement": PERCENTAGE},
    ExtSensorEntityDescription(
        tag=Tag.EXHAUST_FLUID_LEVEL,
        key=Tag.EXHAUST_FLUID_LEVEL.key,
        icon="mdi:barrel",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        has_entity_name=True,
    ),
    # Tag.SOC: {"icon": "mdi:battery-high", "api_key": "xevBatteryStateOfCharge", "state_class": "measurement", "measurement": PERCENTAGE},
    ExtSensorEntityDescription(
        tag=Tag.SOC,
        key=Tag.SOC.key,
        icon="mdi:battery-high",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        has_entity_name=True,
    ),
    # Tag.EVCC_STATUS: {"icon": "mdi:state-machine", "api_key": "CAN_BE_IGNORED_IF_TYPE_IS_SINGLE", "skip_existence_check": True},
    ExtSensorEntityDescription(
        tag=Tag.EVCC_STATUS,
        key=Tag.EVCC_STATUS.key,
        icon="mdi:state-machine",
        skip_existence_check=True,
        has_entity_name=True,
    ),
    ExtSensorEntityDescription(
        tag=Tag.SEATBELT,
        key=Tag.SEATBELT.key,
        icon="mdi:seatbelt",
        skip_existence_check=True,
        has_entity_name=True,
    ),

    # Debug sensors (disabled by default)
    # Tag.EVENTS: {"icon": "mdi:calendar", "api_key": "events", "skip_existence_check": True, "debug": True},
    ExtSensorEntityDescription(
        tag=Tag.EVENTS,
        key=Tag.EVENTS.key,
        icon="mdi:calendar",
        entity_registry_enabled_default=False,
        skip_existence_check=True,
        has_entity_name=True,
    ),
    # Tag.METRICS: {"icon": "mdi:chart-line", "api_key": "metrics", "skip_existence_check": True, "debug": True},
    ExtSensorEntityDescription(
        tag=Tag.METRICS,
        key=Tag.METRICS.key,
        icon="mdi:chart-line",
        entity_registry_enabled_default=False,
        skip_existence_check=True,
        has_entity_name=True,
    ),
    # Tag.STATES: {"icon": "mdi:car", "api_key": "states", "skip_existence_check": True, "debug": True},
    ExtSensorEntityDescription(
        tag=Tag.STATES,
        key=Tag.STATES.key,
        icon="mdi:car",
        entity_registry_enabled_default=False,
        skip_existence_check=True,
        has_entity_name=True,
    ),
    # Tag.VEHICLES: {"icon": "mdi:car-multiple", "api_key": "vehicles", "skip_existence_check": True, "debug": True},
    ExtSensorEntityDescription(
        tag=Tag.VEHICLES,
        key=Tag.VEHICLES.key,
        icon="mdi:car-multiple",
        entity_registry_enabled_default=False,
        skip_existence_check=True,
        has_entity_name=True,
    ),
]

# UNHANDLED_METTRICS:
# hybridVehicleModeStatus
# seatBeltStatus
# configurations
# vehicleLifeCycleMode
# displaySystemOfMeasure


SENSORSX = {
    # Tag.FIRMWAREUPGINPROGRESS: {"icon": "mdi:one-up", "name": "Firmware Update In Progress"},
    # Tag.ZONELIGHTING: {"icon": "mdi:spotlight-beam"},
}

SWITCHES = {
    Tag.IGNITION: {"icon": "hass:power"},
    #Tag.GUARDMODE: {"icon": "mdi:shield-key"}
}

BUTTONS = {
    Tag.UPDATE_DATA:        {"icon": "mdi:refresh"},
    Tag.REQUEST_REFRESH:    {"icon": "mdi:car-connected"}
}