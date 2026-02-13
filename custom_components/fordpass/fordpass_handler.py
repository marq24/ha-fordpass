import json
import logging
from datetime import timedelta, datetime
from numbers import Number
from re import sub
from typing import Final, Iterable

from homeassistant.const import UnitOfLength, UnitOfTemperature, UnitOfPressure
from homeassistant.util import dt
from homeassistant.util.unit_system import UnitSystem

from .const_shared import (
    ZONE_LIGHTS_VALUE_ALL_ON,
    ZONE_LIGHTS_VALUE_FRONT,
    ZONE_LIGHTS_VALUE_REAR,
    ZONE_LIGHTS_VALUE_DRIVER,
    ZONE_LIGHTS_VALUE_PASSENGER,
    ZONE_LIGHTS_VALUE_OFF,
    XEVPLUGCHARGER_STATE_CHARGING,
    XEVPLUGCHARGER_STATE_CHARGINGAC,
    XEVPLUGCHARGER_STATE_DISCONNECTED,
    XEVPLUGCHARGER_STATE_CONNECTED,
    XEVBATTERYCHARGEDISPLAY_STATE_IN_PROGRESS,
    VEHICLE_LOCK_STATE_LOCKED,
    VEHICLE_LOCK_STATE_PARTLY,
    VEHICLE_LOCK_STATE_UNLOCKED,
    REMOTE_START_STATE_ACTIVE,
    REMOTE_START_STATE_INACTIVE,
    HONK_AND_FLASH,
    DAYS_MAP
)

_LOGGER = logging.getLogger(__name__)

ROOT_STATES: Final = "states"
ROOT_EVENTS: Final = "events"
ROOT_METRICS: Final = "metrics"
ROOT_VEHICLES: Final = "vehicles"
ROOT_MESSAGES: Final = "messages"
ROOT_REMOTE_CLIMATE_CONTROL: Final = "rcc"
ROOT_PREFERRED_CHARGE_TIMES: Final = "pct"
ROOT_ENERGY_TRANSFER_STATUS: Final = "ets"
ROOT_ENERGY_TRANSFER_LOGS: Final = "etl"
ROOT_UPDTIME: Final = "updateTime"

UNSUPPORTED: Final = str("Unsupported")
UNDEFINED: Final = str("Undefined")

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
    def get_preferred_charge_times(data):
        """Get the metrics dictionary."""
        return data.get(ROOT_PREFERRED_CHARGE_TIMES, {})

    @staticmethod
    def get_energy_transfer_status(data):
        """Get the metrics dictionary."""
        return data.get(ROOT_ENERGY_TRANSFER_STATUS, {})

    @staticmethod
    def get_energy_transfer_logs_list(data):
        """Get the metrics dictionary."""
        return data.get(ROOT_ENERGY_TRANSFER_LOGS, {}).get("energyTransferLogs", [])

    @staticmethod
    def get_value_for_metrics_key(data, metrics_key, default=UNSUPPORTED):
        """Get a value from metrics with a default fallback."""
        return data.get(ROOT_METRICS, {}).get(metrics_key, {}).get("value", default)

    @staticmethod
    def get_metrics_dict(data, metrics_key):
        """Get a complete metrics dictionary."""
        return data.get(ROOT_METRICS, {}).get(metrics_key, {})

    @staticmethod
    def get_attr_of_metrics_value_dict(data, metrics_key, metrics_attr, default=UNSUPPORTED):
        """Get an attribute that is present in the value dict."""
        return data.get(ROOT_METRICS, {}).get(metrics_key, {}).get("value", {}).get(metrics_attr, default)

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
                _LOGGER.debug(f"Invalid distance value: '{value}' caused {type(e).__name__} {e}")
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
                _LOGGER.debug(f"Invalid temperature value: '{value}' caused {type(e).__name__} {e}")
        return None

    @staticmethod
    def is_essential_vehicle_data_available(data):
        if data is not None and ROOT_METRICS in data:
            return len(data.get(ROOT_METRICS, {}).keys()) > 0
        return False

    ###########################################################
    # State- and attribute-callable functions grouped by Tag
    ###########################################################

    # ODOMETER state
    def get_odometer_state(data, prev_state=None):
        new_odometer = FordpassDataHandler.get_value_for_metrics_key(data, "odometer", None)
        if new_odometer is not None and isinstance(new_odometer, Number):

            # make sure that the prev_state is a number...
            try:
                if prev_state is not None and not isinstance(prev_state, Number):
                    prev_state = float(prev_state)
            except BaseException as exc:
                _LOGGER.debug(f"get_odometer_state(): invalid prev_state value: '{prev_state}' caused {type(exc).__name__} {exc}")
                prev_state = None

            # we make sure that the prev_state is a number (few lines above)...
            if prev_state is None or new_odometer >= prev_state:
                return new_odometer

        return prev_state

    # FUEL state + attributes
    def get_fuel_state(data, prev_state=None):
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
    def get_soc_state(data, prev_state=None):
        battery_soc = FordpassDataHandler.get_value_for_metrics_key(data, "xevBatteryStateOfCharge")
        if isinstance(battery_soc, Number):
            return round(float(battery_soc), 2)
        return None

    def get_soc_attrs(data, units:UnitSystem):
        battery_range = FordpassDataHandler.get_value_for_metrics_key(data, "xevBatteryRange")
        if isinstance(battery_range, Number):
            return {"batteryRange": FordpassDataHandler.localize_distance(battery_range, units)}
        return None


    # BATTERY state + attributes
    def get_battery_state(data, prev_state=None):
        battery_voltage = FordpassDataHandler.get_value_for_metrics_key(data, "batteryStateOfCharge")
        if isinstance(battery_voltage, Number):
            return round(float(battery_voltage), 0)
        return None

    def get_battery_attrs(data, units:UnitSystem):
        attrs = {}
        data_metrics = FordpassDataHandler.get_metrics(data)
        if "batteryVoltage" in data_metrics:
            if data_metrics["batteryVoltage"].get("vehicleBattery", UNDEFINED).lower() == "primary_battery":
                attrs["batteryVoltage"] = FordpassDataHandler.get_value_for_metrics_key(data, "batteryVoltage")
            else:
                attrs["batteryVoltageObject"] = data_metrics.get("batteryVoltage", 0)

        if "batteryLoadStatus" in data_metrics:
            if data_metrics["batteryLoadStatus"].get("vehicleBattery", UNDEFINED).lower() == "primary_battery":
                attrs["batteryLoadStatus"] = FordpassDataHandler.get_value_for_metrics_key(data, "batteryLoadStatus")
            else:
                attrs["batteryLoadStatusObject"] = data_metrics.get("batteryLoadStatus", UNSUPPORTED)
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

        if "tirePressure" in data_metrics:
            for a_tire in data_metrics["tirePressure"]:
                a_val = a_tire.get("value", UNSUPPORTED)
                if a_val is not None and a_val != UNSUPPORTED and isinstance(a_val, Number):
                    if "vehicleWheel" in a_tire:
                        attrs[FordpassDataHandler.to_camel(a_tire["vehicleWheel"])] = f"{round(units.pressure(a_val, UnitOfPressure.KPA), digits)} {units.pressure_unit}"

        if "tirePressureStatus" in data_metrics:
            for a_tire in data_metrics["tirePressureStatus"]:
                a_val = a_tire.get("value", UNSUPPORTED)
                if a_val is not None and a_val != UNSUPPORTED:
                    if "vehicleWheel" in a_tire:
                        attrs[f"{FordpassDataHandler.to_camel(a_tire['vehicleWheel'])}_state"] = a_val

        if "tirePressureSystemStatus" in data_metrics:
            count = 0
            for a_system_state in data_metrics["tirePressureSystemStatus"]:
                a_val = a_system_state.get("value", UNSUPPORTED)
                if a_val is not None and a_val != UNSUPPORTED:
                    if "vehicleWheel" in a_system_state:
                        attrs[f"{FordpassDataHandler.to_camel(a_system_state['vehicleWheel'])}_system_state"] = a_val
                    else:
                        if count == 0:
                            attrs[f"systemState"] = a_val
                        else:
                            attrs[f"systemState{count}"] = a_val
                        count += 1

        return attrs


    # GPS state + attributes [+ LAT & LON getters for device tracker]
    def get_gps_state(data, prev_state=None):
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
        val = FordpassDataHandler.get_gps_state(data, None).get("lat", UNSUPPORTED)
        if val != UNSUPPORTED:
            return float(val)
        return None

    def get_gps_lon(data) -> float:
        val = FordpassDataHandler.get_gps_state(data, None).get("lon", UNSUPPORTED)
        if val != UNSUPPORTED:
            return float(val)
        return None

    # ALARM attributes
    def get_alarm_attr(data, units:UnitSystem):
        attrs = FordpassDataHandler.get_metrics_dict(data, "alarmStatus")
        data_metrics = FordpassDataHandler.get_metrics(data)
        if "panicAlarmStatus" in data_metrics:
            val = data_metrics.get("panicAlarmStatus", {}).get("value", UNSUPPORTED)
            if val != UNSUPPORTED:
                attrs["panicAlarmStatus"] = val
        return attrs or None

    # DOOR_LOCK state
    def get_door_lock_state(data, prev_state=None):
        # EXAMPLE data:

        # # UNKNOWN
        # obj1 = [{
        #     "updateTime": "2025-06-30T05:34:24.902Z",
        #     "oemCorrelationId": "xxx",
        #     "value": "LOCKED",
        #     "vehicleDoor": "FRONT_LEFT",
        #     "determinationMethod": "ACTUAL"
        # }, {
        #     "updateTime": "2025-06-30T05:34:24.902Z",
        #     "oemCorrelationId": "xxx",
        #     "value": "LOCKED",
        #     "vehicleDoor": "FRONT_RIGHT",
        #     "determinationMethod": "ACTUAL"
        # }, {
        #     "updateTime": "2025-06-30T05:34:24.902Z",
        #     "oemCorrelationId": "xxx",
        #     "value": "LOCKED",
        #     "vehicleDoor": "REAR_LEFT",
        #     "determinationMethod": "ACTUAL"
        # }, {
        #     "updateTime": "2025-06-30T05:34:24.902Z",
        #     "oemCorrelationId": "xxx",
        #     "value": "LOCKED",
        #     "vehicleDoor": "REAR_RIGHT",
        #     "determinationMethod": "ACTUAL"
        # }]
        #
        # # MACH-E
        # obj2 = [{
        #     "updateTime": "2025-06-09T11:09:31Z",
        #     "oemCorrelationId": "xxx",
        #     "value": "LOCKED",
        #     "vehicleDoor": "UNSPECIFIED_FRONT",
        #     "vehicleOccupantRole": "DRIVER",
        #     "vehicleSide": "DRIVER"
        # }, {
        #     "updateTime": "2025-06-09T11:09:31Z",
        #     "oemCorrelationId": "xxx",
        #     "value": "LOCKED",
        #     "vehicleDoor": "ALL_DOORS"
        # }]
        #
        # # F150
        # obj3 = [{
        #     "updateTime": "2025-06-13T00:05:54Z",
        #     "oemCorrelationId": "xxx",
        #     "tags": {
        #         "DOOR_LATCH_TYPE": "MECHANICAL"
        #     },
        #     "value": "UNKNOWN",
        #     "vehicleDoor": "UNSPECIFIED_REAR",
        #     "vehicleOccupantRole": "PASSENGER",
        #     "vehicleSide": "DRIVER"
        # }, {
        #     "updateTime": "2025-06-13T00:05:54Z",
        #     "oemCorrelationId": "xxx",
        #     "tags": {
        #         "DOOR_LATCH_TYPE": "MECHANICAL"
        #     },
        #     "value": "UNKNOWN",
        #     "vehicleDoor": "INNER_TAILGATE",
        #     "vehicleOccupantRole": "UNKNOWN",
        #     "vehicleSide": "UNKNOWN"
        # }, {
        #     "updateTime": "2025-06-13T00:05:54Z",
        #     "oemCorrelationId": "xxx",
        #     "tags": {
        #         "DOOR_LATCH_TYPE": "MECHANICAL"
        #     },
        #     "value": "UNKNOWN",
        #     "vehicleDoor": "TAILGATE",
        #     "vehicleOccupantRole": "UNKNOWN",
        #     "vehicleSide": "UNKNOWN"
        # }, {
        #     "updateTime": "2025-06-13T00:05:54Z",
        #     "oemCorrelationId": "xxx",
        #     "tags": {
        #         "DOOR_LATCH_TYPE": "MECHANICAL"
        #     },
        #     "value": "UNKNOWN",
        #     "vehicleDoor": "FRUNK",
        #     "vehicleOccupantRole": "UNKNOWN",
        #     "vehicleSide": "UNKNOWN"
        # }, {
        #     "updateTime": "2025-06-13T01:42:10Z",
        #     "oemCorrelationId": "xxx",
        #     "value": "LOCKED",
        #     "vehicleDoor": "ALL_DOORS"
        # }, {
        #     "updateTime": "2025-06-13T01:42:10Z",
        #     "oemCorrelationId": "xxx",
        #     "value": "LOCKED",
        #     "vehicleDoor": "UNSPECIFIED_FRONT",
        #     "vehicleOccupantRole": "DRIVER",
        #     "vehicleSide": "DRIVER"
        # }]

        data_metrics = FordpassDataHandler.get_metrics(data)

        all_doors = data_metrics.get("doorLockStatus", [])
        required_locked_doors = len(all_doors)

        if required_locked_doors == 0:
            _LOGGER.debug("No doorLockStatus found in the data - returning UNSUPPORTED")
            return UNSUPPORTED

        locked_doors = 0
        for a_lock_state in all_doors:
            a_upper_case_lock_value = a_lock_state.get("value", UNSUPPORTED).upper()
            if a_upper_case_lock_value in ["LOCKED", "DOUBLE_LOCKED"]:
                # if we have an ALL_DOORS lock state, we can ignore the other door lock states
                if "vehicleDoor" in a_lock_state and a_lock_state["vehicleDoor"].upper() == "ALL_DOORS":
                    # we instantly return the 'VEHICLE_LOCK_STATE_LOCKED' and skip the complete
                    # loop [and don't bother with any additional stuff]
                    return VEHICLE_LOCK_STATE_LOCKED
                else:
                    locked_doors += 1

            # we ignore unknown, or MECHANICAL door latch types...
            elif a_upper_case_lock_value == "UNKNOWN" or ("tags" in a_lock_state and "DOOR_LATCH_TYPE" in a_lock_state["tags"] and a_lock_state["tags"]["DOOR_LATCH_TYPE"] == "MECHANICAL"):
                required_locked_doors -= 1

        if locked_doors > 0:
            if locked_doors >= required_locked_doors:
                return VEHICLE_LOCK_STATE_LOCKED
            else:
                return VEHICLE_LOCK_STATE_PARTLY
        else:
            return VEHICLE_LOCK_STATE_UNLOCKED

    def get_door_lock_attrs(data, units:UnitSystem):
        data_metrics = FordpassDataHandler.get_metrics(data)
        attrs = {}
        for a_door in data_metrics.get("doorLockStatus", []):
            if "vehicleSide" in a_door:
                if "vehicleDoor" in a_door and a_door['vehicleDoor'].upper() == "UNSPECIFIED_FRONT":
                    attrs[FordpassDataHandler.to_camel(a_door['vehicleSide']+" FRONT")] = a_door['value']
                elif "vehicleDoor" in a_door and a_door['vehicleDoor'].upper() == "UNSPECIFIED_REAR":
                    attrs[FordpassDataHandler.to_camel(a_door['vehicleSide']+" REAR")] = a_door['value']
                else:
                    attrs[FordpassDataHandler.to_camel(a_door['vehicleDoor'])] = a_door['value']
            else:
                attrs[FordpassDataHandler.to_camel(a_door["vehicleDoor"])] = a_door['value']
        return attrs


    # DOOR_STATUS state + attributes
    def get_door_status_state(data, prev_state=None):
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
                    attrs[FordpassDataHandler.to_camel(a_door['vehicleSide']+" FRONT")] = a_door['value']
                elif "vehicleDoor" in a_door and a_door['vehicleDoor'].upper() == "UNSPECIFIED_REAR":
                    attrs[FordpassDataHandler.to_camel(a_door['vehicleSide']+" REAR")] = a_door['value']
                else:
                    attrs[FordpassDataHandler.to_camel(a_door['vehicleDoor'])] = a_door['value']
            else:
                attrs[FordpassDataHandler.to_camel(a_door["vehicleDoor"])] = a_door['value']

        if "hoodStatus" in data_metrics and "value" in data_metrics["hoodStatus"]:
            attrs["hood"] = data_metrics["hoodStatus"]["value"]

        return attrs or None


    # WINDOW_POSITION state + attributes
    def get_window_position_state(data, prev_state=None):
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
    def get_last_refresh_state(data, prev_state=None):
        return dt.as_local(dt.parse_datetime(data.get(ROOT_UPDTIME, "1970-01-01T00:00:00.000Z")))


    # ELVEH state + attributes
    def get_elveh_state(data, prev_state=None):
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

        xev_next_departure_time_schedule_id = None
        xev_next_departure_time_location_id = None

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
                    if "next-departure-time-schedule-id" in key:
                        xev_next_departure_time_schedule_id = data_metrics.get("customMetrics", {}).get(key, {}).get("value")
                    elif "next-departure-time-location-id" in key:
                        xev_next_departure_time_location_id = data_metrics.get("customMetrics", {}).get(key, {}).get("value")
                    else:
                        entryName = FordpassDataHandler.to_camel(key.split(":custom:xev-")[1])
                        attrs[entryName] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

        if xev_next_departure_time_schedule_id is not None: #and xev_next_departure_time_location_id is not None:
            # IF there is a 'schedule_id' defined, then we set the attribute, in order to make the processing
            # of this data a bit easier - since you must not check for existence of both id's all the time
            attrs["nextScheduledDepartureTime"] = UNDEFINED
            xev_departure_locations = data_metrics.get("configurations", {}).get("xevDepartureSchedulesSetting",{}).get("value", {}).get("departureLocations", {})
            for a_depart_location in xev_departure_locations:
                if "departureSchedules" in a_depart_location and (
                        len(xev_departure_locations) == 1 or
                        a_depart_location.get("locationId", None) == xev_next_departure_time_location_id
                ) :
                    for a_schedule in a_depart_location["departureSchedules"]:
                        if str(a_schedule.get("scheduleId", None)) == str(xev_next_departure_time_schedule_id):
                            if a_schedule.get("scheduleStatus", "OFF").upper() == "ON":
                                a_schedule_obj = a_schedule.get("schedule", {})
                                if len(a_schedule_obj) > 0:
                                    _LOGGER.debug(f"{a_schedule_obj}")
                                    time_obj = a_schedule_obj.get("weeklySchedule", {})
                                    day_of_week = time_obj.get("dayOfWeek", UNSUPPORTED).upper()
                                    time_of_day = time_obj.get("timeOfDay", UNSUPPORTED)
                                    tz = a_schedule_obj.get("timeZone", UNSUPPORTED)

                                    if "LOCAL_TIME" == tz:
                                        if day_of_week in DAYS_MAP and time_of_day != UNSUPPORTED:
                                            # Get the current date and time in local timezone
                                            now = datetime.now()

                                            # Get the weekday number for the specified day
                                            target_weekday = DAYS_MAP[day_of_week]
                                            target_time = datetime.strptime(time_of_day, "%H:%M").time()

                                            # Calculate days until the next target day
                                            days_until = (target_weekday - now.weekday() + 7) % 7
                                            if days_until == 0 and now.time() >= target_time:
                                                days_until = 7  # If today is Friday but the time is past, go to next week

                                            # Calculate the next date
                                            next_date = now + timedelta(days=days_until)

                                            # Set the target time
                                            attrs["nextScheduledDepartureTime"] = next_date.replace(hour=target_time.hour, minute=target_time.minute, second=0, microsecond=0)

                                    break

        data_events = FordpassDataHandler.get_events(data)
        if "customEvents" in data_events:
            trip_data_str = data_events.get("customEvents", {}).get("xev-key-off-trip-segment-data", {}).get("oemData", {}).get("trip_data", {}).get("stringArrayValue", [])
            for dataStr in trip_data_str:
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


    # AUTO_UPDATE state + on/off
    def get_auto_updates_state(data, prev_state):
        return (data.get(ROOT_METRICS, {})
                .get("configurations", {})
                .get("automaticSoftwareUpdateOptInSetting",{})
                .get("value", UNSUPPORTED))

    async def on_off_auto_updates(data, vehicle, turn_on:bool) -> bool:
        if turn_on:
            return await vehicle.auto_updates_on()
        else:
            return await vehicle.auto_updates_off()


    # ELVEH_CHARGING start/stop cancel/pause
    # def get_start_stop_charge_switch_state(data, prev_state=None):
    #     # we will use a ha switch entity for this, so we need to return "ON" or "OFF"
    #     data_metrics = FordpassDataHandler.get_metrics(data)
    #     val = data_metrics.get("xevPlugChargerStatus", {}).get("value", UNSUPPORTED)
    #     if val != UNSUPPORTED:
    #         val = val.upper()
    #         if val == XEVPLUGCHARGER_STATE_CHARGING or val == XEVPLUGCHARGER_STATE_CHARGINGAC:
    #             return "ON"
    #         elif val == XEVPLUGCHARGER_STATE_CONNECTED and "xevBatteryChargeDisplayStatus" in data_metrics:
    #             secondary_val = data_metrics.get("xevBatteryChargeDisplayStatus", {}).get("value", UNSUPPORTED).upper()
    #             if secondary_val == XEVBATTERYCHARGEDISPLAY_STATE_IN_PROGRESS:
    #                 return "ON"
    #     return "OFF"
    #
    # async def on_off_start_stop_charge(data, vehicle, turn_on:bool) -> bool:
    #     if turn_on:
    #         return await vehicle.start_charge()
    #     else:
    #         return await vehicle.stop_charge()

    def get_cancel_pause_charge_switch_state(data, prev_state=None):
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

    async def on_off_cancel_pause_charge(data, vehicle, turn_on:bool) -> bool:
            if turn_on:
                return await vehicle.cancel_charge()
            else:
                return await vehicle.pause_charge()

    def _get_eleveh_charging_power_from_metrics(data_metrics):
        if "xevBatteryChargerVoltageOutput" in data_metrics and "xevBatteryChargerCurrentOutput" in data_metrics:
            ch_volt = float(data_metrics.get("xevBatteryChargerVoltageOutput", {}).get("value", 0))
            ch_amps = float(data_metrics.get("xevBatteryChargerCurrentOutput", {}).get("value", 0))
            if isinstance(ch_volt, Number) and ch_volt != 0 and isinstance(ch_amps, Number) and ch_amps != 0:
                return round((ch_volt * ch_amps) / 1000, 2)
            elif isinstance(ch_volt, Number) and ch_volt != 0 and "xevBatteryIoCurrent" in data_metrics:
                # Get Battery Io Current for DC Charging calculation
                batt_amps = float(data_metrics.get("xevBatteryIoCurrent", {}).get("value", 0))
                # DC Charging calculation: Use absolute value for amperage to handle negative values
                if isinstance(batt_amps, Number) and batt_amps != 0:
                    return round((ch_volt * abs(batt_amps)) / 1000, 2)
                else:
                    return 0
            else:
                return 0
        return None

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
        charging_kw = FordpassDataHandler._get_eleveh_charging_power_from_metrics(data_metrics)
        if charging_kw is not None:
            attrs["chargingkW"] = charging_kw

        if "xevBatteryTimeToFullCharge" in data_metrics:
            cs_update_time = dt.parse_datetime(data_metrics.get("xevBatteryTimeToFullCharge", {}).get("updateTime", 0))
            cs_est_end_time = cs_update_time + timedelta(minutes=data_metrics.get("xevBatteryTimeToFullCharge", {}).get("value", 0))
            attrs["estimatedEndTime"] = dt.as_local(cs_est_end_time)

        if "customMetrics" in data_metrics:
            for key in data_metrics.get("customMetrics", {}):
                if "custom:charge-power-kw" in key:
                    attrs["chargePowerKw"] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

                if "custom:global-ac-current-limit" in key:
                    attrs["globalAcCurrentLimit"] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

                if "custom:max-ac-current-display" in key:
                    attrs["maxAcCurrent"] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

                if "custom:global-ac-target-soc" in key:
                    attrs["globalAcTargetSoc"] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

                if "custom:current-charging-current-display" in key:
                    attrs["currentChargingCurrent"] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

                if "custom:global-dc-power-limit" in key:
                    attrs["globalDcPowerLimit"] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

                if "custom:max-dc-power-display" in key:
                    attrs["maxDcPower"] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

                if "custom:global-dc-target-soc" in key:
                    attrs["globalDcTargetSoc"] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

                if "custom:current-charging-power-display" in key:
                    attrs["currentChargingPower"] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

                if "custom:fast-charge-bulk" in key:
                    attrs["fastChargeBulk"] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

                if "custom:fast-charge-complete" in key:
                    attrs["fastChargeComplete"] = data_metrics.get("customMetrics", {}).get(key, {}).get("value")

        return attrs

    # ELVEH_CHARGING_power state
    def get_elveh_charging_power_state(data, prev_state=None):
        charging_kw = FordpassDataHandler._get_eleveh_charging_power_from_metrics(data_metrics = FordpassDataHandler.get_metrics(data))
        if charging_kw is not None:
            return charging_kw
        return None

    # ELVEH_PLUG attributes
    def get_elveh_plug_attrs(data, units:UnitSystem):
        data_metrics = FordpassDataHandler.get_metrics(data)
        if "xevPlugChargerStatus" not in data_metrics:
            return None
        attrs = {}

        if "xevChargeStationCommunicationStatus" in data_metrics:
            attrs["ChargingStationStatus"] = data_metrics.get("xevChargeStationCommunicationStatus", {}).get("value", UNSUPPORTED)

        if "xevChargeStationPowerType" in data_metrics:
            attrs["ChargingType"] = data_metrics.get("xevChargeStationPowerType", {}).get("value", UNSUPPORTED)

        return attrs

    # EVCC_STATUS state
    def get_evcc_status_state(data, prev_state=None):
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
    def get_zone_lighting_state(data, prev_state=None):
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

    async def set_zone_lighting(data, vehicle, target_value: str, current_value:str) -> bool:
        return await vehicle.set_zone_lighting(target_value, current_value)


    # REMOTE_START state + on_off
    def get_remote_start_state(data, prev_state=None):
        val = FordpassDataHandler.get_value_for_metrics_key(data, "remoteStartCountdownTimer", 0)
        return "ON" if val > 0 else "OFF"

    # this was 'IGNITION' switch - we keep the key name for compatibility...
    async def on_off_remote_start(data, vehicle, turn_on:bool) -> bool:
        if turn_on:
            return await vehicle.remote_start()
        else:
            return await vehicle.cancel_remote_start()


    # REMOTE_START_STATUS state + attributes
    def get_remote_start_status_state(data, prev_state=None):
        val = FordpassDataHandler.get_value_for_metrics_key(data, "remoteStartCountdownTimer", 0)
        return REMOTE_START_STATE_ACTIVE if val > 0 else REMOTE_START_STATE_INACTIVE

    def get_remote_start_status_attrs(data, units:UnitSystem):
        return {"countdown": FordpassDataHandler.get_value_for_metrics_key(data, "remoteStartCountdownTimer", 0)}


    # REMOTE_START_COUNTDOWN state
    def get_remote_start_countdown_state(data, prev_state=None):
        return FordpassDataHandler.get_value_for_metrics_key(data, "remoteStartCountdownTimer", 0)


    # MESSAGES state + attributes
    def get_messages_state(data, prev_state=None):
        messages = data.get(ROOT_MESSAGES)
        return len(messages) if messages is not None else None

    def get_messages_attrs(data, units:UnitSystem):
        attrs = {}
        msg_data = data.get(ROOT_MESSAGES, [])
        if len(msg_data) > 0:
            attrs["json_src"] = msg_data.copy()
            count = 1
            for a_msg in msg_data:
                attrs[f"msg{count:03}_Date"] = f"{a_msg['createdDate']}"
                attrs[f"msg{count:03}_Type"] = f"{a_msg['messageType']}"
                attrs[f"msg{count:03}_Subject"] = f"{a_msg['messageSubject']}"
                attrs[f"msg{count:03}_Content"] = f"{a_msg['messageBody']}"
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
            "wheelTorqueStatus",
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
    def get_indicators_state(data, prev_state=None):
        return sum(1 for indicator in FordpassDataHandler.get_metrics(data).get("indicators", {}).values() if indicator.get("value"))

    def get_indicators_attrs(data, units:UnitSystem):
        data_metrics = FordpassDataHandler.get_metrics(data)
        attrs = {}

        for key, value in data_metrics.get("indicators", {}).items():
            if value.get("value") is not None:
                if value.get("additionalInfo") is not None:
                    attrs[f"{FordpassDataHandler.to_camel(key)}_{FordpassDataHandler.to_camel(value.get('additionalInfo'))}"] = value["value"]
                else:
                    attrs[FordpassDataHandler.to_camel(key)] = value["value"]

        return attrs or None


    # OUTSIDE_TEMP attributes
    def get_outside_temp_attrs(data, units:UnitSystem):
        ambient_temp = FordpassDataHandler.get_value_for_metrics_key(data, "ambientTemp")
        if isinstance(ambient_temp, Number):
            return {"ambientTemp": FordpassDataHandler.localize_temperature(ambient_temp, units)}
        return None


    # CABIN_TEMP state + attributes (from trip data)
    def get_cabin_temperature_state(data, prev_state=None):
        data_events = FordpassDataHandler.get_events(data)
        if "customEvents" in data_events:
            trip_data_str = data_events.get("customEvents", {}).get("xev-key-off-trip-segment-data", {}).get("oemData", {}).get("trip_data", {}).get("stringArrayValue", [])
            for dataStr in trip_data_str:
                tripData = json.loads(dataStr)
                if "cabin_temperature" in tripData and isinstance(tripData["cabin_temperature"], Number):
                    return tripData["cabin_temperature"]
        return None

    def get_cabin_temperature_attrs(data, units:UnitSystem):
        data_events = FordpassDataHandler.get_events(data)
        attrs = {}
        if "customEvents" in data_events:
            trip_data_str = data_events.get("customEvents", {}).get("xev-key-off-trip-segment-data", {}).get("oemData", {}).get("trip_data", {}).get("stringArrayValue", [])
            for dataStr in trip_data_str:
                tripData = json.loads(dataStr)
                if "ambient_temperature" in tripData and isinstance(tripData["ambient_temperature"], Number):
                    attrs["tripAmbientTemp"] = FordpassDataHandler.localize_temperature(tripData["ambient_temperature"], units)
                if "outside_air_ambient_temperature" in tripData and isinstance(tripData["outside_air_ambient_temperature"], Number):
                    attrs["tripOutsideAirAmbientTemp"] = FordpassDataHandler.localize_temperature(tripData["outside_air_ambient_temperature"], units)
        return attrs or None


    # LAST_ENERGY_CONSUMED state + attributes (from trip data)
    def get_last_energy_consumed_state(data, prev_state=None):
        data_events = FordpassDataHandler.get_events(data)
        if "customEvents" in data_events:
            trip_data_str = data_events.get("customEvents", {}).get("xev-key-off-trip-segment-data", {}).get("oemData", {}).get("trip_data", {}).get("stringArrayValue", [])
            for dataStr in trip_data_str:
                tripData = json.loads(dataStr)
                if "energy_consumed" in tripData and isinstance(tripData["energy_consumed"], Number):
                    return round(float(tripData["energy_consumed"]), 3)
        return None

    def get_last_energy_consumed_attrs(data, units:UnitSystem):
        data_events = FordpassDataHandler.get_events(data)
        attrs = {}
        if "customEvents" in data_events:
            root = data_events.get("customEvents", {}).get("xev-key-off-trip-segment-data", {})
            attrs["tripUpdateTime"] = root.get("updateTime", None)
            trip_data_str = root.get("oemData", {}).get("trip_data", {}).get("stringArrayValue", [])
            for dataStr in trip_data_str:
                tripData = json.loads(dataStr)
                if "trip_duration" in tripData and isinstance(tripData["trip_duration"], Number):
                    attrs["tripDuration"] = str(dt.parse_duration(str(tripData["trip_duration"])))
                if "distance_traveled" in tripData and isinstance(tripData["distance_traveled"], Number):
                    attrs["tripDistanceTraveled"] = FordpassDataHandler.localize_distance(tripData["distance_traveled"], units)
        return attrs or None


    # LAST_ENERGY_TRANSFER_LOG_ENTRY state + attributes (from energy_transfer_logs)
    def get_energy_transfer_log_state(data, prev_state=None):
        # {
        #     "id": "a_entry_id_here",
        #     "deviceId": "VIN-HERE",
        #     "eventType": "ChargeData",
        #     "chargerType": "AC_BASIC",
        #     "energyConsumed": 60.19749,
        #     "timeStamp": "2025-11-28T07:58:23Z",
        #     "preferredChargeAmount": 0,
        #     "targetSoc": 100,
        #     "plugDetails": {
        #         "plugInTime": "2025-11-27T16:03:54Z",
        #         "plugOutTime": "2025-11-28T07:57:20Z",
        #         "totalPluggedInTime": 57206,
        #         "plugInDte": 100.0,
        #         "totalDistanceAdded": 367.5
        #     },
        #     "power": {
        #         "min": 601.2,
        #         "max": 10405.2,
        #         "median": 0.0,
        #         "average": 5261.678141145299,
        #         "weightedAverage": 6781.453876504839
        #     },
        #     "stateOfCharge": {
        #         "firstSOC": 28,
        #         "lastSOC": 100,
        #         "socDifference": 72
        #     },
        #     "energyTransferDuration": {
        #         "begin": "2025-11-27T16:05:09Z",
        #         "end": "2025-11-28T04:33:05Z",
        #         "totalTime": 21138
        #     },
        #     "location": {
        #         "id": 1,
        #         "type": "SAVED",
        #         "name": "HH7",
        #         "address": {
        #             "address1": "[STREET]",
        #             "address2": None,
        #             "city": "[CITY]",
        #             "state": "North-Rhine-Westphalia",
        #             "country": "DEU",
        #             "postalCode": "[POSTAL-CODE]"
        #         },
        #         "geoHash": "anyHashHere",
        #         "tags": None,
        #         "latitude": 22.123456,
        #         "longitude": 4.12345,
        #         "timeZoneOffset": "UTC+01:00",
        #         "network": "UNKNOWN"
        #     }
        # }
        log_list = FordpassDataHandler.get_energy_transfer_logs_list(data)
        if len(log_list) > 0:
            entry = log_list[0]
            if entry is not None and "energyConsumed" in entry and isinstance(entry["energyConsumed"], Number):
                return round(float(entry["energyConsumed"]), 3)
        return None

    def get_energy_transfer_log_attrs(data, units:UnitSystem):
        log_list = FordpassDataHandler.get_energy_transfer_logs_list(data)
        attrs = {}
        if len(log_list) > 0:
            energy_transfer_log_list_entry = log_list[0]
            attrs = energy_transfer_log_list_entry.copy()
            attrs.pop("id")
            attrs.pop("deviceId")

            # we need to convert the 'totalDistanceAdded' to possible miles
            if "plugDetails" in attrs and "totalDistanceAdded" in attrs["plugDetails"]:
                org_val_in_km = attrs["plugDetails"]["totalDistanceAdded"]
                attrs["plugDetails"]["totalDistanceAdded"] = FordpassDataHandler.localize_distance(org_val_in_km, units)

        return attrs or None


    # GLOBAL_AC_CURRENT_LIMIT state + set_value
    def get_global_ac_current_limit_state(data, prev_state=None):
        cm_data = FordpassDataHandler.get_metrics_dict(data, "customMetrics")
        if cm_data is not None:
            for key in cm_data:
                if "custom:global-ac-current-limit" in key:
                    return cm_data.get(key, {}).get("value")
        return None

    async def set_global_ac_current_limit(data, vehicle, target_value: str, current_value:str):
        # we don't need the data here - since we do not fetch additional info from it
        # - instead we try to set the value directly...
        return await vehicle.set_charge_settings("globalCurrentLimit", target_value)


    # GLOBAL_DC_POWER_LIMIT state + set_value
    def get_global_dc_power_limit_state(data, prev_state=None):
        cm_data = FordpassDataHandler.get_metrics_dict(data, "customMetrics")
        if cm_data is not None:
            for key in cm_data:
                if "custom:global-dc-power-limit" in key:
                    return cm_data.get(key, {}).get("value")
        return None

    async def set_global_dc_power_limit(data, vehicle, target_value: str, current_value:str):
        # we don't need the data here - since we do not fetch additional info from it
        # - instead we try to set the value directly...
        return await vehicle.set_charge_settings("globalDCPowerLimit", target_value)


    # GLOBAL_TARGET_SOC state + set_value
    def get_global_target_soc_state(data, prev_state=None):
        cm_data = FordpassDataHandler.get_metrics_dict(data, "customMetrics")
        if cm_data is not None:
            for key in cm_data:
                # ONLY if 'custom:global-ac-target-soc' or 'custom:global-dc-target-soc' is in the customMetrics,
                # then the vehicle supports setting the global target SOC!
                if "custom:global-ac-target-soc" in key or "custom:global-dc-target-soc" in key:
                    ce_data = FordpassDataHandler.get_events(data).get("customEvents", {}).get("xev-hv-battery-monitoring", {}).get("oemData", {})
                    if ce_data is not None and "target_soc" in ce_data:
                        return ce_data.get("target_soc", {}).get("longValue", None)
        return None

    async def set_global_target_soc(data, vehicle, target_value: str, current_value:str):
        # we don't need the data here - since we do not fetch additional info from it
        # - instead we try to set the value directly...
        return await vehicle.set_charge_settings("globalTargetSoc", target_value)


    # ELVEH_TARGET_CHARGE name + state + set_value
    def get_elev_target_charge_name(data, index:int = 0):
        all_pct_data = FordpassDataHandler.get_preferred_charge_times(data)
        if len(all_pct_data) > index:
            ets_data_at_idx = list(all_pct_data.values())[index]
            return ets_data_at_idx.get("location", {}).get("name", UNSUPPORTED)
        else:
            return UNSUPPORTED

    def is_elev_target_charge_supported(data, index:int = 0):
        all_pct_data = FordpassDataHandler.get_preferred_charge_times(data)
        if len(all_pct_data) > index:
            ets_data_at_idx = list(all_pct_data.values())[index]
            if "chargeProfile" in ets_data_at_idx and "location" in ets_data_at_idx:
                if all(key in ets_data_at_idx["chargeProfile"] for key in ["chargeMode", "schedules"]):
                    if all(key in ets_data_at_idx["location"] for key in ["address", "id", "latitude", "longitude", "name", "type"]):
                        return True
        return False

    def get_elev_target_charge_state(data, index:int = 0):
        all_pct_data = FordpassDataHandler.get_preferred_charge_times(data)
        if len(all_pct_data) > index:
            pct_data_at_idx = list(all_pct_data.values())[index]
            return pct_data_at_idx.get("chargeProfile", {}).get("targetSoc", UNSUPPORTED)
        else:
            #_LOGGER.debug(f"get_elev_target_charge_state(): No 'preferred_charge_times' data found for index: {index} in: {len(all_pct_data)}")
            return UNSUPPORTED

    async def set_elev_target_charge(data, vehicle, target_value, current_value:str):
        all_pct_data = FordpassDataHandler.get_preferred_charge_times(data)
        if len(all_pct_data) > 0:
            pct_data_at_idx_0 = next(iter(all_pct_data.values()))
            return await FordpassDataHandler.set_elev_target_charge_int(vehicle, target_value, pct_data_at_idx_0)
        else:
            return False

    async def set_elev_target_charge_alt1(data, vehicle, target_value, current_value:str):
        all_pct_data = FordpassDataHandler.get_preferred_charge_times(data)
        if len(all_pct_data) > 1:
            pct_data_at_idx = list(all_pct_data.values())[1]
            return await FordpassDataHandler.set_elev_target_charge_int(vehicle, target_value, pct_data_at_idx)
        else:
            return False

    async def set_elev_target_charge_alt2(data, vehicle, target_value, current_value:str):
        all_pct_data = FordpassDataHandler.get_preferred_charge_times(data)
        if len(all_pct_data) > 2:
            pct_data_at_idx = list(all_pct_data.values())[2]
            return await FordpassDataHandler.set_elev_target_charge_int(vehicle, target_value, pct_data_at_idx)
        else:
            return False

    async def set_elev_target_charge_int(vehicle, target_value, pct_data) -> bool:
        if pct_data is not None and len(pct_data) > 0:
            if "chargeProfile" in pct_data and "location" in pct_data:
                if not all(key in pct_data["chargeProfile"] for key in ["chargeMode", "schedules"]):
                    _LOGGER.info(f"set_elev_target_charge(): {pct_data} does not contain all required chargeProfile data")
                    return False
                if not all(key in pct_data["location"] for key in ["address", "id", "latitude", "longitude", "name", "type"]):
                    _LOGGER.info(f"set_elev_target_charge(): {pct_data} does not contain required location data")
                    return False

            target_value = int(float(target_value))
            if 50 <= target_value <= 100:
                if target_value < 80:
                    # for values below 80 percent, ford only accepts 50,60 or 70 percent
                    # round down to the nearest 10 percent
                    target_value = int(float(target_value)/10) * 10

                # the value we want to set from is the 'targetSoc'
                # and it can go from 20 to 100 percent... lower makes
                # little sense...
                post_data = {
                    "chargeProfile": {
                        "chargeMode":pct_data["chargeProfile"]["chargeMode"],
                        "schedules": pct_data["chargeProfile"]["schedules"],
                        "targetSoc": target_value
                    },
                    "location": {
                        "address":  pct_data["location"]["address"],
                        "id":       pct_data["location"]["id"],
                        "latitude": pct_data["location"]["latitude"],
                        "longitude":pct_data["location"]["longitude"],
                        "name":     pct_data["location"]["name"],
                        "type":     pct_data["location"]["type"],
                    },
                    "vin": vehicle.vin
                }
                return await vehicle.set_charge_target(post_data)

        _LOGGER.info(f"set_elev_target_charge(): target_value {target_value} is not in the valid range (50-100)")
        return False


    # RCC (remote climate control) state
    def get_rcc_state(data, rcc_key):
        value_list = data.get(ROOT_REMOTE_CLIMATE_CONTROL, {}).get("rccUserProfiles", [])
        if value_list is None or isinstance(value_list, (str, bytes)) or not isinstance(value_list, Iterable):
            return UNSUPPORTED

        for a_list_entry in value_list:
            if a_list_entry.get("preferenceType", "") == rcc_key:
                value = a_list_entry.get("preferenceValue", UNSUPPORTED)
                if value != UNSUPPORTED:
                    if rcc_key == "SetPointTemp_Rq":
                        if value.lower() != "hi" and value.lower() != "lo":
                            value = float(value.replace("_", "."))
                    elif rcc_key in ["RccLeftRearClimateSeat_Rq", "RccLeftFrontClimateSeat_Rq", "RccRightRearClimateSeat_Rq", "RccRightFrontClimateSeat_Rq"]:
                        value = value.lower()
                return value
        return UNSUPPORTED

    # number(s) for the RCC
    async def set_rcc_SetPointTemp_Rq(data, vehicle, target_value: str, current_value:str):
        if target_value.lower() != "hi" and target_value.lower() != "lo":
            if not (target_value.endswith("0") or target_value.endswith("5")):
                _LOGGER.info(f"RCC SetPointTemp_Rq: target_value {target_value} is not a valid value, must end with 0 or 5")
                return False
        return await FordpassDataHandler.set_rcc_int("SetPointTemp_Rq", data, vehicle, target_value.replace('.', '_'))

    # switches for the RCC
    async def on_off_rcc_RccRearDefrost_Rq(data, vehicle, turn_on:bool):
        return await FordpassDataHandler.set_rcc_int("RccRearDefrost_Rq", data, vehicle, "On" if turn_on else "Off")
    async def on_off_rcc_RccHeatedWindshield_Rq(data, vehicle, turn_on:bool):
        return await FordpassDataHandler.set_rcc_int("RccHeatedWindshield_Rq", data, vehicle, "On" if turn_on else "Off")
    async def on_off_rcc_RccHeatedSteeringWheel_Rq(data, vehicle, turn_on:bool):
        return await FordpassDataHandler.set_rcc_int("RccHeatedSteeringWheel_Rq", data, vehicle, "On" if turn_on else "Off")

    # selects for the RCC
    # to support HA translations for select-entities, all options must be lowercase!
    # but the Ford API using strings like 'Heated2' or 'Cooled2' - so we need to convert the
    # first letter of the 'target_value' (a select entity option) to uppercase.
    async def set_rcc_RccLeftRearClimateSeat_Rq(data, vehicle, target_value: str, current_value:str):
        return await FordpassDataHandler.set_rcc_int("RccLeftRearClimateSeat_Rq", data, vehicle, target_value[0].upper() + target_value[1:])
    async def set_rcc_RccLeftFrontClimateSeat_Rq(data, vehicle, target_value: str, current_value:str):
        return await FordpassDataHandler.set_rcc_int("RccLeftFrontClimateSeat_Rq", data, vehicle, target_value[0].upper() + target_value[1:])
    async def set_rcc_RccRightRearClimateSeat_Rq(data, vehicle, target_value: str, current_value:str):
        return await FordpassDataHandler.set_rcc_int("RccRightRearClimateSeat_Rq", data, vehicle, target_value[0].upper() + target_value[1:])
    async def set_rcc_RccRightFrontClimateSeat_Rq(data, vehicle, target_value: str, current_value:str):
        return await FordpassDataHandler.set_rcc_int("RccRightFrontClimateSeat_Rq", data, vehicle, target_value[0].upper() + target_value[1:])

    async def set_rcc_int(rcc_key:str, data:dict, vehicle, new_value: str) -> bool:
        list_data = data.get(ROOT_REMOTE_CLIMATE_CONTROL, {}).get("rccUserProfiles", [])
        if list_data is None or not isinstance(list_data, Iterable) or len(list_data) == 0:
            return False

        # Find and update the preference
        preference_found = False
        for a_list_entry in list_data:
            if a_list_entry.get("preferenceType", "") == rcc_key:
                old_value = a_list_entry.get("preferenceValue")
                a_list_entry["preferenceValue"] = new_value
                preference_found = True
                _LOGGER.debug(f"RCC: Updating {rcc_key} from '{old_value}' to '{new_value}'")
                break

        if not preference_found:
            _LOGGER.info(f"RCC: preferenceType '{rcc_key}' not found in rccUserProfiles. Available types: {[p.get('preferenceType') for p in list_data]}")

        rcc_dict = {
            "crccStateFlag": "On",
            "userPreferences": list_data,
            "vin": vehicle.vin
        }

        # ok we hardcode the new set values in our data object of our bridge...
        # grrr this does not work - we don't have access to the data conatiner object...
        #data[ROOT_REMOTE_CLIMATE_CONTROL]["rccUserProfiles"] = list_data

        return await vehicle.set_rcc(rcc_dict, list_data)

    # DEVICE_CONNECTIVITY state
    def get_device_connectivity_state(data, prev_state=None):
        state = FordpassDataHandler.get_states(data).get("deviceConnectivity", {}).get("value", {}).get("toState", UNSUPPORTED)
        if state.upper() == "CONNECTED":
            return "CONNECTED"
        elif state.upper() == "DISCONNECTED":
            return "DISCONNECTED"
        else:
            return state

    #####################################
    ## CURRENTLY UNSUPPORTED CALLABLES ##
    #####################################

    # DEEPSLEEP state
    def get_deepsleep_state(data, prev_state=None):
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

    def get_guard_mode_state(data, prev_state=None):
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

    async def on_off_guard_mode(data, vehicle, turn_on:bool) -> bool:
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

    async def honk_and_light_short(coordinator, vehicle):
        await vehicle.honk_and_light(duration=HONK_AND_FLASH.SHORT)

    async def honk_and_light(coordinator, vehicle):
        await vehicle.honk_and_light(duration=HONK_AND_FLASH.DEFAULT)

    async def honk_and_light_long(coordinator, vehicle):
        await vehicle.honk_and_light(duration=HONK_AND_FLASH.LONG)

    async def extend_remote_start(coordinator, vehicle):
        await vehicle.remote_start()

    async def messages_delete_last(coordinator, vehicle):
        msgs = coordinator.data.get(ROOT_MESSAGES, {})
        if len(msgs) > 0:
            message_ids = [int(message['messageId']) for message in msgs if (len(message['relevantVin']) == 0 or message['relevantVin'] == vehicle.vin)]
            if len(message_ids) > 0:
                if await vehicle.delete_messages([message_ids[0]]):
                    await vehicle.ws_check_for_message_update_required()
                    return True
        return False

    async def messages_delete_all(coordinator, vehicle):
        msgs = coordinator.data.get(ROOT_MESSAGES, {})
        if len(msgs) > 0:
            message_ids = [int(message['messageId']) for message in msgs if (len(message['relevantVin']) == 0 or message['relevantVin'] == vehicle.vin)]
            if len(message_ids) > 0:
                if await vehicle.delete_messages(message_ids):
                    await vehicle.ws_check_for_message_update_required()
                    return True
        return False

    async def messages_delete_with_id_called_from_service(coordinator, msg_id: int):
        _LOGGER.debug(f"messages_delete_id_from_service(): msg_id: {msg_id} called...")
        msgs = coordinator.data.get(ROOT_MESSAGES, {})
        if len(msgs) > 0:
            message_ids = [int(message['messageId']) for message in msgs if (len(message['relevantVin']) == 0 or message['relevantVin'] == coordinator.bridge.vin)]
            if len(message_ids) > 0:
                if msg_id in message_ids:
                    _LOGGER.debug(f"messages_delete_id_from_service(): will delete message_id: {msg_id} now")
                    if await coordinator.bridge.delete_messages([msg_id]):
                        _LOGGER.debug(f"messages_delete_id_from_service(): message_id: {msg_id} deleted successfully")
                        await coordinator.bridge.ws_check_for_message_update_required()
                        return True
                else:
                    _LOGGER.debug(f"messages_delete_id_from_service(): message id not found in available messages: {message_ids}")
            else:
                _LOGGER.debug(f"messages_delete_id_from_service(): no messages found for vin: {coordinator.bridge.vin}")
        else:
            _LOGGER.debug(f"messages_delete_id_from_service(): no messages found in coordinator.data")
        return False

    # just for development purposes...
    async def start_charge_vehicle(coordinator, vehicle):
        await vehicle.start_charge()
    async def stop_charge_vehicle(coordinator, vehicle):
        await vehicle.stop_charge()
    async def cancel_charge_vehicle(coordinator, vehicle):
        await vehicle.cancel_charge()
    async def pause_charge_vehicle(coordinator, vehicle):
        await vehicle.pause_charge()