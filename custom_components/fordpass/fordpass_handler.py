import json
import logging
from datetime import timedelta
from numbers import Number
from re import sub
from typing import Final

from homeassistant.const import UnitOfLength, UnitOfTemperature, UnitOfPressure
from homeassistant.util import dt
from homeassistant.util.unit_system import UnitSystem

from custom_components.fordpass.const import (
    ZONE_LIGHTS_VALUE_ALL_ON,
    ZONE_LIGHTS_VALUE_FRONT,
    ZONE_LIGHTS_VALUE_REAR,
    ZONE_LIGHTS_VALUE_DRIVER,
    ZONE_LIGHTS_VALUE_PASSENGER,
    ZONE_LIGHTS_VALUE_OFF,
    XEVPLUGCHARGER_STATE_CHARGING, XEVPLUGCHARGER_STATE_DISCONNECTED, XEVPLUGCHARGER_STATE_CONNECTED,
    XEVPLUGCHARGER_STATE_CHARGINGAC,
    XEVBATTERYCHARGEDISPLAY_STATE_IN_PROGRESS
)

_LOGGER = logging.getLogger(__name__)

ROOT_STATES: Final = "states"
ROOT_EVENTS: Final = "events"
ROOT_METRICS: Final = "metrics"
ROOT_VEHICLES: Final = "vehicles"
ROOT_MESSAGES: Final = "messages"
ROOT_UPDTIME: Final = "updateTime"

UNSUPPORTED: Final = str("Unsupported")

class FordpassDataHandler:
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
    def get_value_for_metrics_key(data, metrics_key, default=UNSUPPORTED):
        """Get a value from metrics with default fallback."""
        return data.get(ROOT_METRICS, {}).get(metrics_key, {}).get("value", default)

    @staticmethod
    def get_metrics_dict(data, metrics_key):
        """Get a complete metrics dictionary."""
        return data.get(ROOT_METRICS, {}).get(metrics_key, {})

    @staticmethod
    def get_value_at_index_for_metrics_key(data, metrics_key, index=0, default=UNSUPPORTED):
        sub_data = data.get(ROOT_METRICS, {}).get(metrics_key, [{}])
        if len(sub_data) > index:
            return sub_data[index].get("value", default)
        else:
            return default

    @staticmethod
    def localize_distance(value, units):
        if value is not None and value != UNSUPPORTED:
            try:
                if not isinstance(value, Number):
                    value = float(value)
                return units.length(value, UnitOfLength.KILOMETERS)
            except ValueError as ve:
                _LOGGER.debug(f"Invalid distance value: '{value}' caused {ve}")
            except BaseException as e:
                _LOGGER.debug(f"Invalid distance value: '{value}' caused {type(e)} {e}")
        return None

    @staticmethod
    def localize_temperature(value, units):
        if value is not None and value != UNSUPPORTED:
            try:
                if not isinstance(value, Number):
                    value = float(value)
                return units.temperature(value, UnitOfTemperature.CELSIUS)
            except ValueError as ve:
                _LOGGER.debug(f"Invalid temperature value: '{value}' caused {ve}")
            except BaseException as e:
                _LOGGER.debug(f"Invalid temperature value: '{value}' caused {type(e)} {e}")
        return None

    ###########################################################
    # State- and attribute-callable functions grouped by Tag
    ###########################################################

    # FUEL state + attributes
    def get_fuel_state(data):
        fuel_level = FordpassDataHandler.get_value_for_metrics_key(data, "fuelLevel", None)
        if fuel_level is not None and isinstance(fuel_level, Number):
            return round(fuel_level)
        return None

    def get_fuel_attrs(data, units:UnitSystem):
        attrs = {}
        fuel_range = FordpassDataHandler.get_value_for_metrics_key(data, "fuelRange")
        if isinstance(fuel_range, Number):
            attrs["fuelRange"] = FordpassDataHandler.localize_distance(fuel_range, units)

        # for PEV's
        battery_range = FordpassDataHandler.get_value_for_metrics_key(data, "xevBatteryRange")
        if isinstance(battery_range, Number):
            attrs["batteryRange"] = FordpassDataHandler.localize_distance(battery_range, units)

        return attrs


    # SOC state + attributes
    def get_soc_state(data):
        battery_soc = FordpassDataHandler.get_value_for_metrics_key(data, "xevBatteryStateOfCharge")
        if isinstance(battery_soc, Number):
            return round(battery_soc, 2)
        return None

    def get_soc_attrs(data, units:UnitSystem):
        battery_range = FordpassDataHandler.get_value_for_metrics_key(data, "xevBatteryRange")
        if isinstance(battery_range, Number):
            return {"batteryRange": FordpassDataHandler.localize_distance(battery_range, units)}
        return None


    # BATTERY attributes
    def get_battery_attrs(data, units:UnitSystem):
        attrs = {}
        data_metrics = FordpassDataHandler.get_metrics(data)
        if "batteryVoltage" in data_metrics:
            attrs["batteryVoltage"] = data_metrics.get("batteryVoltage", 0)
        if "batteryLoadStatus" in data_metrics:
            attrs["batteryLoadStatus"] = data_metrics.get("batteryLoadStatus", UNSUPPORTED)
        return attrs or None


    # SEATBELT attributes
    def get_seatbelt_attrs(data, units:UnitSystem):
        attrs = {}
        for a_seat in FordpassDataHandler.get_metrics(data).get("seatBeltStatus", [{}]):
            if "vehicleOccupantRole" in a_seat and "value" in a_seat:
                attrs[FordpassDataHandler.to_camel(a_seat["vehicleOccupantRole"])] = a_seat["value"]
        return attrs or None


    # TIRE_PRESSURE attributes
    def get_tire_pressure_attrs(data, units:UnitSystem):
        data_metrics = FordpassDataHandler.get_metrics(data)
        if "tirePressure" not in data_metrics:
            return None

        attrs = {}
        digits = 0
        if units.pressure_unit == UnitOfPressure.PSI:
            digits = 1
        elif units.pressure_unit == UnitOfPressure.BAR:
            digits = 2

        for a_tire in data_metrics["tirePressure"]:
            a_val = a_tire.get("value", UNSUPPORTED)
            if a_val is not None and a_val != UNSUPPORTED and isinstance(a_val, Number):
                attrs[FordpassDataHandler.to_camel(a_tire["vehicleWheel"])] = f"{round(units.pressure(a_val, UnitOfPressure.KPA), digits)} {units.pressure_unit}"

        for a_tire in data_metrics["tirePressureStatus"]:
            a_val = a_tire.get("value", UNSUPPORTED)
            if a_val is not None and a_val != UNSUPPORTED:
                attrs[f"{FordpassDataHandler.to_camel(a_tire["vehicleWheel"])}_state"] = a_val

        return attrs


    # GPS state + attributes [+ LAT & LON getters for device tracker]
    def get_gps_state(data):
        return FordpassDataHandler.get_metrics(data).get("position", {}).get("value", {}).get("location", {})

    def get_gps_attr(data, units:UnitSystem):
        attrs = FordpassDataHandler.get_metrics_dict(data, "position")
        data_metrics = FordpassDataHandler.get_metrics(data)
        if "compassDirection" in data_metrics:
            attrs["compassDirection"] = data_metrics.get("compassDirection", {}).get("value", UNSUPPORTED)
        if "heading" in data_metrics:
            attrs["heading"] = data_metrics.get("heading", {}).get("value", UNSUPPORTED)
        return attrs or None

    def get_gps_tracker_attr(data, units:UnitSystem):
        # units will be 'None' in this case (just to let you know)
        position_data = FordpassDataHandler.get_value_for_metrics_key(data, "position")
        attrs = {}
        if "location" in position_data and "alt" in position_data["location"]:
            attrs["Altitude"] = position_data["location"]["alt"]
        if "gpsCoordinateMethod" in position_data:
            attrs["gpsCoordinateMethod"] = position_data["gpsCoordinateMethod"]
        if "gpsDimension" in position_data:
            attrs["gpsDimension"] = position_data["gpsDimension"]
        return attrs or None

    def get_gps_lat(data) -> float:
        val = FordpassDataHandler.get_gps_state(data).get("lat", UNSUPPORTED)
        if val != UNSUPPORTED:
            return float(val)
        return None

    def get_gps_lon(data) -> float:
        val = FordpassDataHandler.get_gps_state(data).get("lon", UNSUPPORTED)
        if val != UNSUPPORTED:
            return float(val)
        return None


    # ALARM attributes
    def get_alarm_attr(data, units:UnitSystem):
        attrs = FordpassDataHandler.get_metrics_dict(data, "alarmStatus")
        data_metrics = FordpassDataHandler.get_metrics(data)
        if "panicAlarmStatus" in data_metrics:
            attrs["panicAlarmStatus"] = data_metrics.get("panicAlarmStatus", {}).get("value", UNSUPPORTED)
        return attrs or None

    # DOOR_LOCK state
    def get_door_lock_state(data):
        data_metrics = FordpassDataHandler.get_metrics(data)
        key_list = ["ALL_DOORS", "UNSPECIFIED_FRONT", "DRIVER"]
        for a_key in key_list:
            for a_lock_state in data_metrics.get("doorLockStatus", []):
                if a_lock_state.get("vehicleDoor", "").upper() == a_key:
                    return a_lock_state.get("value", UNSUPPORTED)

        # fallback implementation...
        if "doorLockStatus" in data_metrics:
            all_lock_states = data_metrics["doorLockStatus"]
            if len(all_lock_states) > 0:
                _LOGGER.warning(f"Unknown vehicleDoor - please create a issue https://github.com/marq24/ha-fordpass/issues and provide this warning message - TIA VehicleDoor is: '{all_lock_states[0].get('vehicleDoor', '@@@UNKNOWN@@@')}', all vehicleDoors are: '{all_lock_states}'")
                return all_lock_states[0].get("value", UNSUPPORTED)

        return UNSUPPORTED

    # DOOR_STATUS state + attributes
    def get_door_status_state(data):
        data_metrics = FordpassDataHandler.get_metrics(data)
        for value in data_metrics.get("doorStatus", []):
            if value["value"].upper() in ["CLOSED", "INVALID", "UNKNOWN"]:
                continue
            return "Open"
        if data_metrics.get("hoodStatus", {}).get("value", UNSUPPORTED).upper() == "OPEN":
            return "Open"
        return "Closed"

    def get_door_status_attrs(data, units:UnitSystem):
        data_metrics = FordpassDataHandler.get_metrics(data)
        attrs = {}
        for a_door in data_metrics.get("doorStatus", []):
            if "vehicleSide" in a_door:
                if "vehicleDoor" in a_door and a_door['vehicleDoor'].upper() == "UNSPECIFIED_FRONT":
                    attrs[FordpassDataHandler.to_camel(a_door['vehicleSide'])] = a_door['value']
                else:
                    attrs[FordpassDataHandler.to_camel(a_door['vehicleDoor'])] = a_door['value']
            else:
                attrs[FordpassDataHandler.to_camel(a_door["vehicleDoor"])] = a_door['value']

        if "hoodStatus" in data_metrics and "value" in data_metrics["hoodStatus"]:
            attrs["hood"] = data_metrics["hoodStatus"]["value"]

        return attrs or None


    # WINDOW_POSITION state + attributes
    def get_window_position_state(data):
        data_metrics = FordpassDataHandler.get_metrics(data)
        for window in data_metrics.get("windowStatus", []):
            windowrange = window.get("value", {}).get("doubleRange", {})
            if windowrange.get("lowerBound", 0.0) != 0.0 or windowrange.get("upperBound", 0.0) != 0.0:
                return "Open"
        return "Closed"

    def get_window_position_attrs(data, units:UnitSystem):
        data_metrics = FordpassDataHandler.get_metrics(data)
        attrs = {}
        for a_window in data_metrics.get("windowStatus", []):
            if "value" in a_window:
                if "vehicleWindow" in a_window and a_window["vehicleWindow"].upper().startswith("UNSPECIFIED_"):
                    front_or_rear_txt = a_window["vehicleWindow"].split("_")[1]
                    if front_or_rear_txt.upper() == "FRONT":
                        attrs[FordpassDataHandler.to_camel(a_window["vehicleSide"])] = a_window["value"]
                    else:
                        attrs[FordpassDataHandler.to_camel(front_or_rear_txt + "_" + a_window["vehicleSide"])] = a_window["value"]
                else:
                    attrs[FordpassDataHandler.to_camel(a_window["vehicleWindow"])] = a_window["value"]
            else:
                attrs[FordpassDataHandler.to_camel(a_window["vehicleWindow"] + "_") + a_window["vehicleSide"]] = a_window

        return attrs


    # LAST_REFRESH state
    def get_last_refresh_state(data):
        return dt.as_local(dt.parse_datetime(data.get(ROOT_UPDTIME, "1970-01-01T00:00:00.000Z")))


    # ELVEH state + attributes
    def get_elveh_state(data):
        data_metrics = FordpassDataHandler.get_metrics(data)
        if "xevBatteryRange" in data_metrics:
            val = data_metrics.get("xevBatteryRange", {}).get("value", UNSUPPORTED)
            if val != UNSUPPORTED and isinstance(val, Number):
                return round(val, 2)
        return None

    def get_elveh_attrs(data, units:UnitSystem):
        data_metrics = FordpassDataHandler.get_metrics(data)
        if "xevBatteryRange" not in data_metrics:
            return None

        attrs = {}
        metrics_mapping = {
            # Standard metrics with units parameter (even if not used)
            "xevBatteryIoCurrent":              ("batteryAmperage", lambda value, units: float(value), 0),
            "xevBatteryVoltage":                ("batteryVoltage", lambda value, units: float(value), 0),
            "xevBatteryStateOfCharge":          ("batteryCharge", lambda value, units: value, 0),
            "xevBatteryActualStateOfCharge":    ("batteryActualCharge", lambda value, units: value, 0),
            "xevBatteryPerformanceStatus":      ("batteryPerformanceStatus", lambda value, units: value, UNSUPPORTED),
            "xevBatteryEnergyRemaining":        ("batteryEnergyRemaining", lambda value, units: value, 0),
            "xevBatteryCapacity":               ("maximumBatteryCapacity", lambda value, units: value, 0),
            "xevBatteryMaximumRange":           ("maximumBatteryRange", lambda value, units: FordpassDataHandler.localize_distance(value, units), 0),
            "tripXevBatteryRangeRegenerated":   ("tripRangeRegenerated", lambda value, units: FordpassDataHandler.localize_distance(value, units), 0),
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
                attrs[attr_name] = transform_fn(value, units)

        # Returning 0 in else - to prevent attribute from not displaying
        if "xevBatteryIoCurrent" in data_metrics and "xevBatteryVoltage" in data_metrics:
            batt_volt = attrs.get("batteryVoltage", 0)
            batt_amps = attrs.get("batteryAmperage", 0)

            if isinstance(batt_volt, Number) and batt_volt != 0 and isinstance(batt_amps, Number) and batt_amps != 0:
                attrs["batterykW"] = round((batt_volt * batt_amps) / 1000, 2)
            else:
                attrs["batterykW"] = 0

        # Returning 0 in else - to prevent attribute from not displaying
        if "xevTractionMotorVoltage" in data_metrics and "xevTractionMotorCurrent" in data_metrics:
            motor_volt = attrs.get("motorVoltage", 0)
            motor_amps = attrs.get("motorAmperage", 0)
            if isinstance(motor_volt, Number) and motor_volt != 0 and isinstance(motor_amps, Number) and motor_amps != 0:
                attrs["motorkW"] = round((motor_volt * motor_amps) / 1000, 2)
            else:
                attrs["motorkW"] = 0

        if "customMetrics" in data_metrics:
            for key in data_metrics.get("customMetrics", {}):
                if "accumulated-vehicle-speed-cruising-coaching-score" in key:
                    attrs["tripSpeedScore"] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

                if "accumulated-deceleration-coaching-score" in key:
                    attrs["tripDecelerationScore"] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

                if "accumulated-acceleration-coaching-score" in key:
                    attrs["tripAccelerationScore"] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

                if "custom:vehicle-electrical-efficiency" in key:
                    # Still don't know what this value is, but if I add it and get more data it could help to figure it out
                    attrs["tripElectricalEfficiency"] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

                if "custom:xevRemoteDataResponseStatus" in key:
                    attrs["remoteDataResponseStatus"] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

                if ":custom:xev-" in key:
                    entryName = FordpassDataHandler.to_camel(key.split(":custom:xev-")[1])
                    attrs[entryName] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

        data_events = FordpassDataHandler.get_events(data)
        if "customEvents" in data_events:
            tripDataStr = data_events.get("customEvents", {}).get("xev-key-off-trip-segment-data", {}).get("oemData", {}).get("trip_data", {}).get("stringArrayValue", [])
            for dataStr in tripDataStr:
                tripData = json.loads(dataStr)
                if "ambient_temperature" in tripData and isinstance(tripData["ambient_temperature"], Number):
                    attrs["tripAmbientTemp"] = FordpassDataHandler.localize_temperature(tripData["ambient_temperature"], units)
                if "outside_air_ambient_temperature" in tripData and isinstance(tripData["outside_air_ambient_temperature"], Number):
                    attrs["tripOutsideAirAmbientTemp"] = FordpassDataHandler.localize_temperature(tripData["outside_air_ambient_temperature"], units)
                if "trip_duration" in tripData:
                    attrs["tripDuration"] = str(dt.parse_duration(str(tripData["trip_duration"])))
                if "cabin_temperature" in tripData and isinstance(tripData["cabin_temperature"], Number):
                    attrs["tripCabinTemp"] = FordpassDataHandler.localize_temperature(tripData["cabin_temperature"], units)
                if "energy_consumed" in tripData and isinstance(tripData["energy_consumed"], Number):
                    attrs["tripEnergyConsumed"] = round(tripData["energy_consumed"] / 1000, 2)
                if "distance_traveled" in tripData and isinstance(tripData["distance_traveled"], Number):
                    attrs["tripDistanceTraveled"] = FordpassDataHandler.localize_distance(tripData["distance_traveled"], units)

                if "energy_consumed" in tripData and isinstance(tripData["energy_consumed"], Number)  and "distance_traveled" in tripData and isinstance(tripData["distance_traveled"], Number):
                    if attrs["tripDistanceTraveled"] == 0 or attrs["tripEnergyConsumed"] == 0:
                        attrs["tripEfficiency"] = 0
                    else:
                        attrs["tripEfficiency"] = attrs["tripDistanceTraveled"] / attrs["tripEnergyConsumed"]
        return attrs


    # ELVEH_CHARGING attributes
    def get_elveh_switch_state(data):
        # we will use a ha switch entity for this, so we need to return "ON" or "OFF"
        data_metrics = FordpassDataHandler.get_metrics(data)
        val = data_metrics.get("xevPlugChargerStatus", {}).get("value", UNSUPPORTED)
        if val != UNSUPPORTED:
            val = val.upper()
            if val == XEVPLUGCHARGER_STATE_CHARGING or val == XEVPLUGCHARGER_STATE_CHARGINGAC:
                return "ON"
            elif val == XEVPLUGCHARGER_STATE_CONNECTED and "xevBatteryChargeDisplayStatus" in data_metrics:
                secondary_val = data_metrics.get("xevBatteryChargeDisplayStatus", {}).get("value", UNSUPPORTED).upper()
                if secondary_val == XEVBATTERYCHARGEDISPLAY_STATE_IN_PROGRESS:
                    return "ON"
        return "OFF"

    async def get_elveh_on_off(vehicle, turn_on:bool) -> bool:
            if turn_on:
                return await vehicle.start_charge()
            else:
                return await vehicle.stop_charge()

    def get_elveh_charging_attrs(data, units:UnitSystem):
        data_metrics = FordpassDataHandler.get_metrics(data)
        if "xevBatteryChargeDisplayStatus" not in data_metrics:
            return None
        attrs = {}

        metrics_mapping = {
            "xevPlugChargerStatus": ("plugStatus", lambda value, units: value, UNSUPPORTED),
            "xevChargeStationCommunicationStatus": ("chargingStationStatus", lambda value, units: value, UNSUPPORTED),
            "xevBatteryChargeDisplayStatus": ("chargingStatus", lambda value, units: value, UNSUPPORTED),
            "xevChargeStationPowerType": ("chargingType", lambda value, units: value, UNSUPPORTED),
            "xevBatteryChargerVoltageOutput": ("chargingVoltage", lambda value, units: float(value), 0),
            "xevBatteryChargerCurrentOutput": ("chargingAmperage", lambda value, units: float(value), 0),
            "xevBatteryTemperature": ("batteryTemperature", lambda value, units: FordpassDataHandler.localize_temperature(value, units), 0),
            "xevBatteryStateOfCharge": ("stateOfCharge", lambda value, units: value, 0),
            "xevBatteryChargerEnergyOutput": ("chargerEnergyOutput", lambda value, units: value, 0),
            # "tripXevBatteryDistanceAccumulated": ("distanceAccumulated", lambda value, units: units.length(value, UnitOfLength.KILOMETERS), 0),
        }

        # Process all metrics in a single loop
        for metric_key, (attr_name, transform_fn, default) in metrics_mapping.items():
            if metric_key in data_metrics:
                value = data_metrics.get(metric_key, {}).get("value", default)
                attrs[attr_name] = transform_fn(value, units)

        # handle the self-calculated custom metrics stuff
        if "xevBatteryChargerVoltageOutput" in data_metrics and "xevBatteryChargerCurrentOutput" in data_metrics:
            ch_volt = attrs.get("chargingVoltage", 0)
            ch_amps = attrs.get("chargingAmperage", 0)

            if isinstance(ch_volt, Number) and ch_volt != 0 and isinstance(ch_amps, Number) and ch_amps != 0:
                attrs["chargingkW"] = round((ch_volt * ch_amps) / 1000, 2)
            elif isinstance(ch_volt, Number) and ch_volt != 0 and "xevBatteryIoCurrent" in data_metrics:
                # Get Battery Io Current for DC Charging calculation
                batt_amps = float(data_metrics.get("xevBatteryIoCurrent", {}).get("value", 0))
                # DC Charging calculation: Use absolute value for amperage to handle negative values
                if isinstance(batt_amps, Number) and batt_amps != 0:
                    attrs["chargingkW"] = round((ch_volt * abs(batt_amps)) / 1000, 2)
                else:
                    attrs["chargingkW"] = 0
            else:
                attrs["chargingkW"] = 0

        if "xevBatteryTimeToFullCharge" in data_metrics:
            cs_update_time = dt.parse_datetime(data_metrics.get("xevBatteryTimeToFullCharge", {}).get("updateTime", 0))
            cs_est_end_time = cs_update_time + timedelta(minutes=data_metrics.get("xevBatteryTimeToFullCharge", {}).get("value", 0))
            attrs["estimatedEndTime"] = dt.as_local(cs_est_end_time)

        if "customMetrics" in data_metrics:
            for key in data_metrics.get("customMetrics", {}):
                if "custom:charge-power-kw" in key:
                    attrs["chargePowerKw"] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

        return attrs


    # ELVEH_PLUG attributes
    def get_elveh_plug_attrs(data, units:UnitSystem):
        data_metrics = FordpassDataHandler.get_metrics(data)
        if "xevPlugChargerStatus" not in data_metrics:
            return None
        attrs = {}

        if "xevChargeStationCommunicationStatus" in data_metrics:
            attrs["ChargeStationCommunicationStatus"] = data_metrics.get("xevChargeStationCommunicationStatus", {}).get("value", UNSUPPORTED)

        if "xevChargeStationPowerType" in data_metrics:
            attrs["chargeStationPowerType"] = data_metrics.get("xevChargeStationPowerType", {}).get("value", UNSUPPORTED)

        return attrs

    # EVCC_STATUS state
    def get_evcc_status_state(data):
        data_metrics = FordpassDataHandler.get_metrics(data)
        val = data_metrics.get("xevPlugChargerStatus", {}).get("value", UNSUPPORTED)
        if val != UNSUPPORTED:
            val = val.upper()
            if val == XEVPLUGCHARGER_STATE_DISCONNECTED:
                return "A"
            elif val == XEVPLUGCHARGER_STATE_CONNECTED:
                if "xevBatteryChargeDisplayStatus" in data_metrics:
                    secondary_val = data_metrics.get("xevBatteryChargeDisplayStatus", {}).get("value", UNSUPPORTED).upper()
                    if secondary_val == XEVBATTERYCHARGEDISPLAY_STATE_IN_PROGRESS:
                        return "C"
                return "B"
            elif val == XEVPLUGCHARGER_STATE_CHARGING or val == XEVPLUGCHARGER_STATE_CHARGINGAC:
                return "C"
            else:
                return "UNKNOWN"
        return val


    # ZONE_LIGHTING state + attributes
    def get_zone_lighting_state(data):
        # "pttb-power-mode-change-event": {
        #     "updateTime": "2025-06-12T21:45:25Z",
        #     "oemData": {
        #         "ftcp_version": { "stringValue": "6.0.45"},
        #         "current_power_mode": {"stringValue": "Off"},
        #         "zone_2_active_power_status": {"stringValue": "Off"},
        #         "vehicle_common_correlation_id": {},
        #         "zone_3_active_power_status": {"stringValue": "Off"}
        #     }
        # }
        # it's a bit sad, but it looks like, that only in the event section we can find the status of the zoneLight stuff
        oem_data = FordpassDataHandler.get_events(data).get("customEvents", {}).get("pttb-power-mode-change-event", {}).get("oemData", {})
        value = oem_data.get("current_power_mode", {}).get("stringValue", UNSUPPORTED)
        if value != UNSUPPORTED:
            if value.upper() == "ON":
                zone1 = oem_data.get("zone_1_active_power_status", {}).get("stringValue", "OFF").upper() == "ON"
                zone2 = oem_data.get("zone_2_active_power_status", {}).get("stringValue", "OFF").upper() == "ON"
                zone3 = oem_data.get("zone_3_active_power_status", {}).get("stringValue", "OFF").upper() == "ON"
                zone4 = oem_data.get("zone_4_active_power_status", {}).get("stringValue", "OFF").upper() == "ON"
                if (zone1 or zone2) and (zone3 or zone4):
                    return ZONE_LIGHTS_VALUE_ALL_ON
                elif zone1:
                    return ZONE_LIGHTS_VALUE_FRONT
                elif zone2:
                    return ZONE_LIGHTS_VALUE_REAR
                elif zone3:
                    return ZONE_LIGHTS_VALUE_DRIVER
                elif zone4:
                    return ZONE_LIGHTS_VALUE_PASSENGER
            else:
                return ZONE_LIGHTS_VALUE_OFF
        return None

    def get_zone_lighting_attrs(data, units:UnitSystem):
        oem_data = FordpassDataHandler.get_events(data).get("customEvents", {}).get("pttb-power-mode-change-event", {}).get("oemData", {})
        if len(oem_data) == 0:
            return None
        else:
            attrs = {}
            list = ["current_power_mode", "zone_1_active_power_status", "zone_2_active_power_status", "zone_3_active_power_status", "zone_4_active_power_status"]
            for key in list:
                if key in oem_data:
                    value = oem_data[key].get("stringValue", UNSUPPORTED)
                    if value != UNSUPPORTED:
                        attrs[FordpassDataHandler.to_camel(key)] = value
            return attrs

    async def set_zone_lighting(vehicle, target_value: str, current_value:str) -> bool:
        return await vehicle.set_zone_lighting(target_value, current_value)


    # REMOTE_START state + on_off
    def get_remote_start_state(data):
        val = FordpassDataHandler.get_value_for_metrics_key(data, "remoteStartCountdownTimer", 0)
        return "ON" if val > 0 else "OFF"

    # this was 'IGNITION' switch - we keep the key name for compatibility...
    async def remote_start_on_off(vehicle, turn_on:bool) -> bool:
        if turn_on:
            return await vehicle.remote_start()
        else:
            return await vehicle.cancel_remote_start()

    # REMOTE_START_STATUS state + attributes
    def get_remote_start_status_state(data):
        val = FordpassDataHandler.get_value_for_metrics_key(data, "remoteStartCountdownTimer", 0)
        return "Active" if val > 0 else "Inactive"

    def get_remote_start_status_attrs(data, units:UnitSystem):
        return {"countdown": FordpassDataHandler.get_value_for_metrics_key(data, "remoteStartCountdownTimer", 0)}


    # MESSAGES state + attributes
    def get_messages_state(data):
        messages = data.get(ROOT_MESSAGES)
        return len(messages) if messages is not None else None

    def get_messages_attrs(data, units:UnitSystem):
        attrs = {}
        count = 1
        for a_msg in data.get(ROOT_MESSAGES, []):
            attrs[f"msg{count:03}_Date"] = f"{a_msg["createdDate"]}"
            attrs[f"msg{count:03}_Type"] = f"{a_msg["messageType"]}"
            attrs[f"msg{count:03}_Subject"] = f"{a_msg["messageSubject"]}"
            attrs[f"msg{count:03}_Content"] = f"{a_msg["messageBody"]}"
            count = count + 1
        return attrs


    # DIESEL_SYSTEM_STATUS attributes
    def get_diesel_system_status_attrs(data, units:UnitSystem):
        data_metrics = FordpassDataHandler.get_metrics(data)
        if data_metrics.get("indicators", {}).get("dieselExhaustOverTemp", {}).get("value") is not None:
            return {"dieselExhaustOverTemp": data_metrics["indicators"]["dieselExhaustOverTemp"]["value"]}
        return None


    # EXHAUST_FLUID_LEVEL attributes
    def get_exhaust_fluid_level_attrs(data, units:UnitSystem):
        data_metrics = FordpassDataHandler.get_metrics(data)
        attrs = {}

        if data_metrics.get("dieselExhaustFluidLevelRangeRemaining", {}).get("value") is not None:
            attrs["dieselExhaustFluidRange"] = data_metrics["dieselExhaustFluidLevelRangeRemaining"]["value"]

        indicators = data_metrics.get("indicators", {})
        indicator_fields = ["dieselExhaustFluidLow", "dieselExhaustFluidSystemFault"]

        for field in indicator_fields:
            if indicators.get(field, {}).get("value") is not None:
                attrs[field] = indicators[field]["value"]

        return attrs or None


    # SPEED attributes
    def get_speed_attrs(data, units:UnitSystem):
        data_metrics = FordpassDataHandler.get_metrics(data)
        attrs = {}

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
                attrs[field] = data_metrics[field]["value"]

        return attrs or None


    # INDICATORS state + attributes
    def get_indicators_state(data):
        return sum(1 for indicator in FordpassDataHandler.get_metrics(data).get("indicators", {}).values() if indicator.get("value"))

    def get_indicators_attrs(data, units:UnitSystem):
        data_metrics = FordpassDataHandler.get_metrics(data)
        attrs = {}

        for key, value in data_metrics.get("indicators", {}).items():
            if value.get("value") is not None:
                if value.get("additionalInfo") is not None:
                    attrs[f"{FordpassDataHandler.to_camel(key)}_{FordpassDataHandler.to_camel(value.get("additionalInfo"))}"] = value["value"]
                else:
                    attrs[FordpassDataHandler.to_camel(key)] = value["value"]

        return attrs or None


    # OUTSIDE_TEMP attributes
    def get_outside_temp_attrs(data, units:UnitSystem):
        ambient_temp = FordpassDataHandler.get_value_for_metrics_key(data, "ambientTemp")
        if isinstance(ambient_temp, Number):
            return {"ambientTemp": FordpassDataHandler.localize_temperature(ambient_temp, units)}
        return None

    #####################################
    ## CURRENTLY UNSUPPORTED CALLABLES ##
    #####################################

    # DEEPSLEEP state
    def get_deepsleep_state(data):
        state = FordpassDataHandler.get_states(data).get("commandPreclusion", {}).get("value", {}).get("toState", UNSUPPORTED)
        if state.upper() == "COMMANDS_PRECLUDED":
            return "ACTIVE"
        elif state.upper() == "COMMANDS_PERMITTED":
            return "DISABLED"
        else:
            return state

    # GUARD_MODE state + on_off (and is_supported_check)
    def is_guard_mode_supported(data):
        # marq24: need to find a vehicle that still supports 'guard' mode to test this...
        # Need to find the correct response for enabled vs. disabled, so this may be spotty at the moment
        guard_status_data = data.get("guardstatus", {})
        return "returnCode" in guard_status_data and guard_status_data["returnCode"] == 200

    def get_guard_mode_state(data):
        # marq24: need to find a vehicle that still supports 'guard' mode to test this...
        # Need to find the correct response for enabled vs. disabled, so this may be spotty at the moment
        guard_status_data = data.get("guardstatus", {})
        _LOGGER.debug(f"guardstatus: {guard_status_data}")
        if "returnCode" in guard_status_data and guard_status_data["returnCode"] == 200:
            if "session" in guard_status_data and "gmStatus" in guard_status_data["session"]:
                if guard_status_data["session"]["gmStatus"] == "enable":
                    return "ON"
                return "OFF"
            return UNSUPPORTED
        return UNSUPPORTED

    async def guardmode_on_off(vehicle, turn_on:bool) -> bool:
        if turn_on:
            return await vehicle.enable_guard()
        else:
            return await vehicle.disable_guard()


    # BUTTON actions
    ##################
    async def reload_data(coordinator, vehicle):
        await coordinator.async_request_refresh_force_classic_requests()

    async def request_update_and_reload(coordinator, vehicle):
        await vehicle.request_update()
        await coordinator.async_request_refresh_force_classic_requests()

    async def lock_vehicle(coordinator, vehicle):
        await vehicle.lock()

    async def unlock_vehicle(coordinator, vehicle):
        await vehicle.unlock()
