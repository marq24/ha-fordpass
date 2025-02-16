"""All vehicle sensors from the accessible by the API"""

import json
import logging
from datetime import timedelta

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass
)
from homeassistant.const import (
    UnitOfTemperature,
    UnitOfLength
)
from homeassistant.util import dt

from . import FordPassEntity
from .const import CONF_PRESSURE_UNIT, DOMAIN, SENSORS, COORDINATOR

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add the Entities from the config."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    sensors = []
    for key, value in SENSORS.items():
        # make sure that we do not crash on not valid configurations
        if "api_key" in value:
            sensor = CarSensor(coordinator, key, config_entry.options)
            api_key = value["api_key"]
            api_class = value.get("api_class", None)
            sensor_type = value.get("sensor_type", None)
            string = isinstance(api_key, str)

            if string and sensor_type == "single":
                sensors.append(sensor)
            elif string:
                if api_key and api_class and api_key in coordinator.data.get(api_class, {}):
                    sensors.append(sensor)
                    continue
                if api_key and api_key in coordinator.data.get("metrics", {}):
                    sensors.append(sensor)
            else:
                for key in api_key:
                    if key and key in coordinator.data.get("metrics", {}):
                        sensors.append(sensor)
                        continue

    _LOGGER.debug(hass.config.units)
    async_add_entities(sensors, True)


class CarSensor(FordPassEntity, SensorEntity):
    def __init__(self, coordinator, sensor_key:str, options):

        super().__init__(internal_key=sensor_key, coordinator=coordinator)
        self.sensor_key = sensor_key
        self.ford_options = options

        # additional data containers for sensors
        self.units = coordinator.hass.config.units
        self.metrics = self.coordinator.data.get("metrics", {})
        self.events = coordinator.data.get("events", {})

    def get_value(self, ftype):
        """Get sensor value and attributes from coordinator data"""
        self.units = self.coordinator.hass.config.units
        
        self.metrics = self.coordinator.data.get("metrics", {})
        self.events = self.coordinator.data.get("events", {})

        if ftype == "state":
            if self.sensor_key == "odometer":
                return self.metrics.get("odometer", {}).get("value")
                # return self.metrics.get("odometer", {}).get("value", {})

            if self.sensor_key == "fuel":
                fuel_level = self.metrics.get("fuelLevel", {}).get("value")
                if fuel_level is not None:
                    return round(fuel_level)
                battery_soc = self.metrics.get("xevBatteryStateOfCharge", {}).get("value")
                if battery_soc is not None:
                    return round(battery_soc, 2)
                return None

            if self.sensor_key == "battery":
                return round(self.metrics.get("batteryStateOfCharge", {}).get("value", 0))

            if self.sensor_key == "oil":
                return round(self.metrics.get("oilLifeRemaining", {}).get("value", 0))

            if self.sensor_key == "tirePressure":
                return self.metrics.get("tirePressureSystemStatus", [{}])[0].get("value", "Unsupported")

            if self.sensor_key == "gps":
                return self.metrics.get("position", {}).get("value", "Unsupported").get("location", {})

            if self.sensor_key == "alarm":
                return self.metrics.get("alarmStatus", {}).get("value", "Unsupported")

            if self.sensor_key == "ignitionStatus":
                return self.metrics.get("ignitionStatus", {}).get("value", "Unsupported")

            if self.sensor_key == "firmwareUpgInProgress":
                return self.metrics.get("firmwareUpgradeInProgress", {}).get("value", "Unsupported")

            if self.sensor_key == "deepSleepInProgress":
                return self.metrics.get("deepSleepInProgress", {}).get("value", "Unsupported")

            if self.sensor_key == "doorStatus":
                for value in self.metrics.get("doorStatus", []):
                    if value["value"] in ["CLOSED", "Invalid", "UNKNOWN"]:
                        continue
                    return "Open"
                if self.metrics.get("hoodStatus", {}).get("value") == "OPEN":
                    return "Open"
                return "Closed"

            if self.sensor_key == "windowPosition":
                for window in self.metrics.get("windowStatus", []):
                    windowrange = window.get("value", {}).get("doubleRange", {})
                    if windowrange.get("lowerBound", 0.0) != 0.0 or windowrange.get("upperBound", 0.0) != 0.0:
                        return "Open"
                return "Closed"

            if self.sensor_key == "lastRefresh":
                return dt.as_local(dt.parse_datetime(self.coordinator.data.get("updateTime", 0)))

            if self.sensor_key == "elVeh" and "xevBatteryRange" in self.metrics:
                return round(self.metrics.get("xevBatteryRange", {}).get("value"), 2)

            # SquidBytes: Added elVehCharging
            if self.sensor_key == "elVehCharging":
                return self.metrics.get("xevPlugChargerStatus", {}).get("value", "Unsupported")

            if self.sensor_key == "zoneLighting":
                return self.metrics("zoneLighting", {}).get("zoneStatusData", {}).get("value", "Unsupported")

            if self.sensor_key == "remoteStartStatus":
                countdown_timer = self.metrics.get("remoteStartCountdownTimer", {}).get("value", 0)
                return "Active" if countdown_timer > 0 else "Inactive"

            if self.sensor_key == "messages":
                messages = self.coordinator.data.get("messages")
                return len(messages) if messages is not None else None

            if self.sensor_key == "dieselSystemStatus":
                return self.metrics.get("dieselExhaustFilterStatus", {}).get("value", "Unsupported")

            if self.sensor_key == "exhaustFluidLevel":
                return self.metrics.get("dieselExhaustFluidLevel", {}).get("value", "Unsupported")

            if self.sensor_key == "speed":
                return self.metrics.get("speed", {}).get("value", "Unsupported")

            if self.sensor_key == "indicators":
                return sum(1 for indicator in self.metrics.get("indicators", {}).values() if indicator.get("value"))

            if self.sensor_key == "coolantTemp":
                return self.metrics.get("engineCoolantTemp", {}).get("value", "Unsupported")

            if self.sensor_key == "outsideTemp":
                return self.metrics.get("outsideTemperature", {}).get("value", "Unsupported")

            if self.sensor_key == "engineOilTemp":
                return self.metrics.get("engineOilTemp", {}).get("value", "Unsupported")

            if self.sensor_key == "deepSleep":
                state = self.states.get("commandPreclusion", {}).get("value", {}).get("toState", "Unsupported")
                if state == "COMMANDS_PRECLUDED":
                    return "ACTIVE"
                elif state == "COMMANDS_PERMITTED":
                    return "DISABLED"
                else:
                    return state

            if self.sensor_key == "events":
                return len(self.events)

            if self.sensor_key == "states":
                return len(self.coordinator.data.get("states", {}))

            if self.sensor_key == "vehicles":
                return len(self.coordinator.data.get("vehicles", {}))

            if self.sensor_key == "metrics":
                return len(self.metrics)
            return None


        if ftype == "attribute":
            if self.sensor_key == "odometer":
                return self.metrics.get("odometer", {})

            if self.sensor_key == "outsideTemp":
                ambient_temp = self.metrics.get("ambientTemp", {}).get("value")
                if ambient_temp is not None:
                    return {"ambientTemp": ambient_temp}
                return None

            if self.sensor_key == "fuel":
                fuel = {}
                fuel_range = self.metrics.get("fuelRange", {}).get("value", 0)
                battery_range = self.metrics.get("xevBatteryRange", {}).get("value", 0)
                if fuel_range != 0:
                    # Display fuel range for both Gas and Hybrid (assuming its not 0)
                    fuel["fuelRange"] = self.units.length(fuel_range, UnitOfLength.KILOMETERS)
                if battery_range != 0:
                    # Display Battery range for EV and Hybrid
                    fuel["batteryRange"] = self.units.length(battery_range, UnitOfLength.KILOMETERS)
                return fuel

            if self.sensor_key == "battery":
                return {
                    "BatteryVoltage": self.metrics.get("batteryVoltage", {}).get("value", 0)
                }

            if self.sensor_key == "oil":
                return self.metrics.get("oilLifeRemaining", {})

            if self.sensor_key == "tirePressure" and "tirePressure" in self.metrics:
                pressure_unit = self.ford_options.get(CONF_PRESSURE_UNIT)
                if pressure_unit == "PSI":
                    conversion_factor = 0.1450377377
                    decimal_places = 0
                elif pressure_unit == "BAR":
                    conversion_factor = 0.01
                    decimal_places = 2
                elif pressure_unit == "kPa":
                    conversion_factor = 1
                    decimal_places = 0
                else:
                    conversion_factor = 1
                    decimal_places = 0
                tire_pressures = {}
                for value in self.metrics["tirePressure"]:
                    tire_pressures[FordPassEntity.camel_case(value["vehicleWheel"])] = round(float(value["value"]) * conversion_factor, decimal_places)
                return tire_pressures

            if self.sensor_key == "gps":
                return self.metrics.get("position", {})

            if self.sensor_key == "alarm":
                return self.metrics.get("alarmStatus", {})

            if self.sensor_key == "ignitionStatus":
                return self.metrics.get("ignitionStatus", {})

            if self.sensor_key == "firmwareUpgInProgress":
                return self.metrics.get("firmwareUpgradeInProgress", {})

            if self.sensor_key == "deepSleep":
                return None

            if self.sensor_key == "doorStatus":
                doors = {}
                for value in self.metrics.get(self.sensor_key, []):
                    if "vehicleSide" in value:
                        if value['vehicleDoor'] == "UNSPECIFIED_FRONT":
                            doors[FordPassEntity.camel_case(value['vehicleSide'])] = value['value']
                        else:
                            doors[FordPassEntity.camel_case(value['vehicleDoor'])] = value['value']
                    else:
                        doors[FordPassEntity.camel_case(value["vehicleDoor"])] = value['value']
                if "hoodStatus" in self.metrics:
                    doors["hood"] = self.metrics["hoodStatus"]["value"]
                return doors or None

            if self.sensor_key == "windowPosition":
                windows = {}
                for window in self.metrics.get("windowStatus", []):
                    if window["vehicleWindow"] == "UNSPECIFIED_FRONT":
                        windows[FordPassEntity.camel_case(window["vehicleSide"])] = window
                    else:
                        windows[FordPassEntity.camel_case(window["vehicleWindow"])] = window
                return windows

            if self.sensor_key == "lastRefresh":
                return None

            if self.sensor_key == "elVeh":
                if "xevBatteryRange" not in self.metrics:
                    return None
                elecs = {}
                if "xevBatteryPerformanceStatus" in self.metrics:
                    elecs["batteryPerformanceStatus"] = self.metrics.get("xevBatteryPerformanceStatus", {}).get("value", "Unsupported")

                if "xevBatteryStateOfCharge" in self.metrics:
                    elecs["batteryCharge"] = self.metrics.get("xevBatteryStateOfCharge", {}).get("value", 0)

                if "xevBatteryActualStateOfCharge" in self.metrics:
                    elecs["batteryActualCharge"] = self.metrics.get("xevBatteryActualStateOfCharge", {}).get("value", 0)

                if "xevBatteryCapacity" in self.metrics:
                    elecs["maximumBatteryCapacity"] = self.metrics.get("xevBatteryCapacity", {}).get("value", 0)

                if "xevBatteryMaximumRange" in self.metrics:
                    elecs["maximumBatteryRange"] = self.units.length(self.metrics.get("xevBatteryMaximumRange", {}).get("value", 0), UnitOfLength.KILOMETERS)

                if "xevBatteryVoltage" in self.metrics:
                    elecs["batteryVoltage"] = float(self.metrics.get("xevBatteryVoltage", {}).get("value", 0))
                    batt_volt = elecs.get("batteryVoltage", 0)

                if "xevBatteryIoCurrent" in self.metrics:
                    elecs["batteryAmperage"] = float(self.metrics.get("xevBatteryIoCurrent", {}).get("value", 0))
                    batt_amps = elecs.get("batteryAmperage", 0)

                # Returning 0 in else - to prevent attribute from not displaying
                if "xevBatteryIoCurrent" in self.metrics and "xevBatteryVoltage" in self.metrics:
                    if batt_volt != 0 and batt_amps != 0:
                        elecs["batterykW"] = round((batt_volt * batt_amps) / 1000, 2)
                    else:
                        elecs["batterykW"] = 0

                if "xevTractionMotorVoltage" in self.metrics:
                    elecs["motorVoltage"] = float(self.metrics.get("xevTractionMotorVoltage", {}).get("value", 0))
                    motor_volt = elecs.get("motorVoltage", 0)

                if "xevTractionMotorCurrent" in self.metrics:
                    elecs["motorAmperage"] = float(self.metrics.get("xevTractionMotorCurrent", {}).get("value", 0))
                    motor_amps = elecs.get("motorAmperage", 0)

                # Returning 0 in else - to prevent attribute from not displaying
                if "xevTractionMotorVoltage" in self.metrics and "xevTractionMotorCurrent" in self.metrics:
                    if motor_volt != 0 and motor_amps != 0:
                        elecs["motorkW"] = round((motor_volt * motor_amps) / 1000, 2)
                    else:
                        elecs["motorkW"] = 0

                # tripXevBatteryChargeRegenerated should be a previous FordPass feature called "Driving Score". A % based on how much regen vs brake you use
                if "tripXevBatteryChargeRegenerated" in self.metrics:
                    elecs["tripDrivingScore"] = self.metrics.get("tripXevBatteryChargeRegenerated", {}).get("value", 0)

                if "tripXevBatteryRangeRegenerated" in self.metrics:
                    elecs["tripRangeRegenerated"] = self.units.length(self.metrics.get("tripXevBatteryRangeRegenerated", {}).get("value", 0), UnitOfLength.KILOMETERS)

                if "customMetrics" in self.metrics and "xevBatteryCapacity" in self.metrics:
                    for key in self.metrics.get("customMetrics", {}):
                        if "accumulated-vehicle-speed-cruising-coaching-score" in key:
                            elecs["tripSpeedScore"] = self.metrics.get("customMetrics", {}).get(key, {}).get("value")
                        if "accumulated-deceleration-coaching-score" in key:
                            elecs["tripDecelerationScore"] = self.metrics.get("customMetrics", {}).get(key, {}).get("value")
                        if "accumulated-acceleration-coaching-score" in key:
                            elecs["tripAccelerationScore"] = self.metrics.get("customMetrics", {}).get(key, {}).get("value")
                        if "custom:vehicle-electrical-efficiency" in key:
                            # Still don't know what this value is, but if I add it and get more data it could help to figure it out
                            elecs["tripElectricalEfficiency"] = self.metrics.get("customMetrics", {}).get(key, {}).get("value")

                if "customEvents" in self.events:
                    tripDataStr = self.events.get("customEvents", {}).get("xev-key-off-trip-segment-data", {}).get("oemData", {}).get("trip_data", {}).get("stringArrayValue", [])
                    for dataStr in tripDataStr:
                        tripData = json.loads(dataStr)
                        if "ambient_temperature" in tripData:
                            elecs["tripAmbientTemp"] = self.units.temperature(tripData["ambient_temperature"], UnitOfTemperature.CELSIUS)
                        if "outside_air_ambient_temperature" in tripData:
                            elecs["tripOutsideAirAmbientTemp"] = self.units.temperature(tripData["outside_air_ambient_temperature"], UnitOfTemperature.CELSIUS)
                        if "trip_duration" in tripData:
                            elecs["tripDuration"] = str(dt.parse_duration(str(tripData["trip_duration"])))
                        if "cabin_temperature" in tripData:
                            elecs["tripCabinTemp"] = self.units.temperature(tripData["cabin_temperature"], UnitOfTemperature.CELSIUS)
                        if "energy_consumed" in tripData:
                            elecs["tripEnergyConsumed"] = round(tripData["energy_consumed"] / 1000, 2)
                        if "distance_traveled" in tripData:
                            elecs["tripDistanceTraveled"] = self.units.length(tripData["distance_traveled"], UnitOfLength.KILOMETERS)
                        if ("energy_consumed" in tripData and tripData["energy_consumed"] is not None and "distance_traveled" in tripData and tripData["distance_traveled"] is not None):
                            if elecs["tripDistanceTraveled"] == 0 or elecs["tripEnergyConsumed"] == 0:
                                elecs["tripEfficiency"] = 0
                            else:
                                elecs["tripEfficiency"] = elecs["tripDistanceTraveled"] / elecs["tripEnergyConsumed"]
                return elecs

            # SquidBytes: Added elVehCharging
            if self.sensor_key == "elVehCharging":
                if "xevPlugChargerStatus" not in self.metrics:
                    return None
                cs = {}

                if "xevPlugChargerStatus" in self.metrics:
                    cs["plugStatus"] = self.metrics.get("xevPlugChargerStatus", {}).get("value", "Unsupported")

                if "xevChargeStationCommunicationStatus" in self.metrics:
                    cs["chargingStationStatus"] = self.metrics.get("xevChargeStationCommunicationStatus", {}).get("value", "Unsupported")

                if "xevBatteryChargeDisplayStatus" in self.metrics:
                    cs["chargingStatus"] = self.metrics.get("xevBatteryChargeDisplayStatus", {}).get("value", "Unsupported")

                if "xevChargeStationPowerType" in self.metrics:
                    cs["chargingType"] = self.metrics.get("xevChargeStationPowerType", {}).get("value", "Unsupported")

                # if "tripXevBatteryDistanceAccumulated" in self.metrics:
                #   cs["distanceAccumulated"] = self.units.length(self.metrics.get("tripXevBatteryDistanceAccumulated", {}).get("value", 0),UnitOfLength.KILOMETERS)

                if "xevBatteryChargerVoltageOutput" in self.metrics:
                    cs["chargingVoltage"] = float(self.metrics.get("xevBatteryChargerVoltageOutput", {}).get("value", 0))
                    ch_volt = cs["chargingVoltage"]

                if "xevBatteryChargerCurrentOutput" in self.metrics:
                    cs["chargingAmperage"] = float(self.metrics.get("xevBatteryChargerCurrentOutput", {}).get("value", 0))
                    ch_amps = cs["chargingAmperage"]

                # Returning 0 in else - to prevent attribute from not displaying
                if "xevBatteryChargerVoltageOutput" in self.metrics and "xevBatteryChargerCurrentOutput" in self.metrics:

                    # Get Battery Io Current for DC Charging calculation
                    if "xevBatteryIoCurrent" in self.metrics:
                        batt_amps = float(self.metrics.get("xevBatteryIoCurrent", {}).get("value", 0))

                    # AC Charging calculation
                    if ch_volt != 0 and ch_amps != 0:
                        cs["chargingkW"] = round((ch_volt * ch_amps) / 1000, 2)
                    # DC Charging calculation: Use absolute value for amperage to handle negative values
                    elif ch_volt != 0 and batt_amps != 0:
                        cs["chargingkW"] = round((ch_volt * abs(batt_amps)) / 1000, 2)
                    else:
                        cs["chargingkW"] = 0

                if "xevBatteryTemperature" in self.metrics:
                    cs["batteryTemperature"] = self.units.temperature(self.metrics.get("xevBatteryTemperature", {}).get("value", 0), UnitOfTemperature.CELSIUS)

                if "xevBatteryStateOfCharge" in self.metrics:
                    cs["stateOfCharge"] = self.metrics.get("xevBatteryStateOfCharge", {}).get("value", 0)

                if "xevBatteryTimeToFullCharge" in self.metrics:
                    cs_update_time = dt.parse_datetime(self.metrics.get("xevBatteryTimeToFullCharge", {}).get("updateTime", 0))
                    cs_est_end_time = cs_update_time + timedelta(minutes=self.metrics.get("xevBatteryTimeToFullCharge", {}).get("value", 0))
                    cs["estimatedEndTime"] = dt.as_local(cs_est_end_time)

                return cs

            if self.sensor_key == "zoneLighting":
                if "zoneLighting" not in self.metrics:
                    return None
                if (self.metrics[self.sensor_key] is not None and self.metrics[self.sensor_key]["zoneStatusData"] is not None):
                    zone = {}
                    if self.metrics[self.sensor_key]["zoneStatusData"] is not None:
                        for key, value in self.metrics[self.sensor_key]["zoneStatusData"].items():
                            zone[FordPassEntity.camel_case("zone_" + key)] = value["value"]

                    if (self.metrics[self.sensor_key]["lightSwitchStatusData"] is not None):
                        for key, value in self.metrics[self.sensor_key]["lightSwitchStatusData"].items():
                            if value is not None:
                                zone[FordPassEntity.camel_case(key)] = value["value"]

                    if (self.metrics[self.sensor_key]["zoneLightingFaultStatus"] is not None):
                        zone["zoneLightingFaultStatus"] = self.metrics[self.sensor_key]["zoneLightingFaultStatus"]["value"]

                    if (self.metrics[self.sensor_key]["zoneLightingShutDownWarning"] is not None):
                        zone["zoneLightingShutDownWarning"] = self.metrics[self.sensor_key]["zoneLightingShutDownWarning"]["value"]

                    return zone
                return None

            if self.sensor_key == "remoteStartStatus":
                return {"countdown": self.metrics.get("remoteStartCountdownTimer", {}).get("value", 0)}

            if self.sensor_key == "messages":
                messages = {}
                for value in self.coordinator.data.get("messages", []):
                    messages[FordPassEntity.camel_case(value["messageSubject"])] = value["createdDate"]
                return messages

            if self.sensor_key == "dieselSystemStatus":
                if self.metrics.get("indicators", {}).get("dieselExhaustOverTemp", {}).get("value") is not None:
                    return {"dieselExhaustOverTemp": self.metrics["indicators"]["dieselExhaustOverTemp"]["value"]}
                return None

            if self.sensor_key == "exhaustFluidLevel":
                exhaustdata = {}
                if self.metrics.get("dieselExhaustFluidLevelRangeRemaining", {}).get("value") is not None:
                    exhaustdata["dieselExhaustFluidRange"] = self.metrics["dieselExhaustFluidLevelRangeRemaining"]["value"]
                if self.metrics.get("indicators", {}).get("dieselExhaustFluidLow", {}).get("value") is not None:
                    exhaustdata["dieselExhaustFluidLow"] = self.metrics["indicators"]["dieselExhaustFluidLow"]["value"]
                if self.metrics.get("indicators", {}).get("dieselExhaustFluidSystemFault", {}).get("value") is not None:
                    exhaustdata["dieselExhaustFluidSystemFault"] = self.metrics["indicators"]["dieselExhaustFluidSystemFault"]["value"]
                return exhaustdata or None

            if self.sensor_key == "speed":
                attribs = {}
                if "acceleratorPedalPosition" in self.metrics:
                    attribs["acceleratorPedalPosition"] = self.metrics["acceleratorPedalPosition"]["value"]
                if "brakePedalStatus" in self.metrics:
                    attribs["brakePedalStatus"] = self.metrics["brakePedalStatus"]["value"]
                if "brakeTorque" in self.metrics:
                    attribs["brakeTorque"] = self.metrics["brakeTorque"]["value"]
                if "engineSpeed" in self.metrics and "xevBatteryVoltage" not in self.metrics:
                    attribs["engineSpeed"] = self.metrics["engineSpeed"]["value"]
                if "gearLeverPosition" in self.metrics:
                    attribs["gearLeverPosition"] = self.metrics["gearLeverPosition"]["value"]
                if "parkingBrakeStatus" in self.metrics:
                    attribs["parkingBrakeStatus"] = self.metrics["parkingBrakeStatus"]["value"]
                if "torqueAtTransmission" in self.metrics:
                    attribs["torqueAtTransmission"] = self.metrics["torqueAtTransmission"]["value"]
                if "tripFuelEconomy" in self.metrics and "xevBatteryVoltage" not in self.metrics:
                    attribs["tripFuelEconomy"] = self.metrics["tripFuelEconomy"]["value"]
                return attribs or None

            if self.sensor_key == "indicators":
                alerts = {}
                for key, value in self.metrics.get("indicators", {}).items():
                    if value.get("value") is not None:
                        # the 'key' is already in camel case...
                        alerts[key] = value["value"]
                return alerts or None

            if self.sensor_key == "events":
                return self.events

            if self.sensor_key == "metrics":
                return self.metrics

            if self.sensor_key == "states":
                return self.coordinator.data.get("states", {})

            if self.sensor_key == "vehicles":
                return self.coordinator.data.get("vehicles", {})

        return None

    @property
    def extra_state_attributes(self):
        """Return sensor attributes"""
        return self.get_value("attribute")

    @property
    def native_value(self):
        """Return Native Value"""
        return self.get_value("state")

    @property
    def icon(self):
        """Return sensor icon"""
        return SENSORS[self.sensor_key]["icon"]

    @property
    def native_unit_of_measurement(self):
        """Return sensor measurement"""
        return SENSORS.get(self.sensor_key, {}).get("measurement", None)

    @property
    def state_class(self):
        """Return sensor state_class for statistics"""
        if "state_class" in SENSORS[self.sensor_key]:
            if SENSORS[self.sensor_key]["state_class"] == "total":
                return SensorStateClass.TOTAL
            if SENSORS[self.sensor_key]["state_class"] == "measurement":
                return SensorStateClass.MEASUREMENT
            if SENSORS[self.sensor_key]["state_class"] == "total_increasing":
                return SensorStateClass.TOTAL_INCREASING
            return None
        return None

    @property
    def device_class(self):
        """Return sensor device class for statistics"""
        if "device_class" in SENSORS[self.sensor_key]:
            if SENSORS[self.sensor_key]["device_class"] == "distance":
                return SensorDeviceClass.DISTANCE
            if SENSORS[self.sensor_key]["device_class"] == "timestamp":
                return SensorDeviceClass.TIMESTAMP
            if SENSORS[self.sensor_key]["device_class"] == "temperature":
                return SensorDeviceClass.TEMPERATURE
            if SENSORS[self.sensor_key]["device_class"] == "battery":
                return SensorDeviceClass.BATTERY
            if SENSORS[self.sensor_key]["device_class"] == "speed":
                return SensorDeviceClass.SPEED
        return None

    @property
    def entity_registry_enabled_default(self):
        """Return if entity should be enabled when first added to the entity registry."""
        if "debug" in SENSORS[self.sensor_key]:
            return False
        return True
