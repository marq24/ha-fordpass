# **Changelog**

## Version 2025.5.9 - HA-Switch/DeviceTracker/Lock implementation refactored
Same procedure as yesterday (2025.5.8) — this time for DeviceTracker, Switch and Lock entities.

While testing the 'Ignition' switch, I realized that the 'Ignition' switch changing the ignition state. Instead, the 'remote start state' is changes — that make plenty of sense when you look a bit deeper into the code and realize that the switch will send a `RemoteStart` command to the vehicle. So I have renamed the switch to `Remote Start` and changed the icon (but for compatibility reasons I have kept the original entity name).


## Version 2025.5.8 - HA-Sensor implementation refactored
The integration now uses the standard Home Assistant SensorEntityDescription objects to define the sensors. This allows for a more consistent and maintainable codebase, as well as better compatibility with Home Assistant's features of the future.

While refactoring, I also took the opportunity to clean up the code and (IMHO) improve the overall structure of the integration. The refactoring should not change any existing functionality, but it will make it easier to add new features in the future.

> [!NOTE]
> The refactoring is a major change, so please report any issues you encounter. I have tested the integration with my own vehicles, but there might be some edge cases that I have not considered.
> 
> Please don't get upset if you find a bug, I will fix it as soon as possible — for me, it's a long weekend!

### New Features:
While I was working on the refactoring, I have found some additional data in the response of the backend, which was not present in the previous versions of the integration. So I have added a new Sensor and some new attributes (to existing sensors):

#### New Sensor:
- Seatbelt buckle/unbuckle status (when available)

#### New Attributes:

- Speed Sensor: acceleration, yawRate, wheelTorqueStatus
- GPS Sensor: Compass direction &amp; heading
- TirePressure Sensor: tirePressureStatus
- Battery Sensor: batteryStatus
- Alarm Sensor: panicAlarmStatus
- ELVeh Sensor: batteryEnergyRemaining

### BreakingChange — List of incompatible changes:
No major change without incompatible changes — sorry for that!

- Battery Sensor: Attribute 'BatteryVoltage' has been renamed to 'batteryVoltage' (starting now with lowercase)
- Indicator Sensor: The attribute keys can end with the 'additionalInfo' property [appended with an '_' (underscore)]. This 'additionalInfo' looks to me like a service key or something similar that might can become handy when you want to visit a workshop.
- Message Sensor: Attributes will be 'numbered' list of all messages — including the fields: 'Date', 'Type' 'Subject' and 'Content'. The keys will start with 'msgNNN_' (where NNN is the message number starting with 001)

### I need you!
It would be cool if you could take some additional minutes and read: https://github.com/marq24/ha-fordpass?tab=readme-ov-file#i-need-you

## Version 2025.5.7
- PEV support (Fixed): The integration supports PEV (Plug-in Electric Vehicle). It looks like that in previous releases, there was an issue when adding sensors for this vehicle type.

  <br/>This means that the integration will now handle Electric Vehicle [EV] (with SOC info), PEV's (with SOC & fuel info) and vehicles with a combustion engine (fuel info), providing the appropriate sensors and attributes for each engine type.

## Version 2025.5.6
- Bugfix for #22 

## Version 2025.5.5
- General backend-communication enhancements: The integration now should handle the situation, when the HA instance might not have a stable internet connection (and just retry to update the data with the next refresh cycle)

## Version 2025.5.4
- Added additional EVData & EVCharging attributes (might not be present for all vehicles)

  <br/>The in the backend response JSON some additional (custom) data fields have been found and so they will be added to the attribute list of the EVData & EVCharging Sensor entities.

## Version 2025.5.3
- BreakingChange - Window Positions only return "value" (when present)

  <br/>While debugging my window position information, I realized that in contract to the `doorStatus` the `windowStatus` return `UNSPECIFIED_FRONT` and `UNSPECIFIED_REAR`... 
  
  <br/>This must be handled — and while I am already at this section of the code, I decided to include only the value object per window - since the attribute name (Passenger, Driver, ReadPassenger & ReadDriver) should be enough to locate the window.

## Version 2025.5.2
- Support for none existing `hoodStatus` - fixing #21

## Version 2025.5.1
- For EV-Vehicles, the Integration now uses the SOC (State of Charge) as global battery level (and not the level of the 12 V battery)
- clean up some configuration code
- fixing log Warnings as reported in #17 and #18

## Version 2025.5.0
- Speed is measured in m/s (not in km/h) - so the `native_unit_of_measurement` is now m/s

## Version 2025.4.0
- Enhanced startup behavior
  - Sometimes (at least at HA restart) Ford API might not return initial data - this situation is now handled and logged appropriate
- No other features/functions have been added

## Version 2025.3.1
- Added separate Sensor for EV Plug state
- 'EV Charging' returns now the real 'charging state' of the vehicle - previously the plug state [DISCONNECTED/CONNECTED] was returned
- EVCC-Status can now also return status 'C' (since we are now really looking at the charging state of the vehicle)

## Version 2025.3.0
- Another bugfix for `DoorStatus` (caused by bad refactoring) - Issue #8
- changed version scheme - so that it will match all my (marq24) other integrations

## Version 1.77
- bugfix for refactor issue (missing `states` object) (caused by bad refactoring) - Issue #7

## Version 1.76
- added separate SOC Sensor for EV/PHEV vehicles
- added sensor that will provide EVCC charging-state information: A,B,C [makes template sensor obsolete]
- determine vehicle engine type (at startup) and add only corresponding sensors (e.g. no Fuel for EV's)
- internal refactoring [introduced "tag's"]

## Version 1.75
- First bugfix was required #5
- Added `Local Sync` button: Request the integration to refresh it's data against Ford APIs (when you don't want to wait for the next update interval)
- Added `Remote Sync` button: Request an update from the vehicle - this will train for sure the battery of your vehicle - since the internal components must be awakened - once the remote sync request have been successfully confirmed by the Ford backend, the integration will update its data after a pause of 15 seconds (same as manually press the `Local Sync`).

## Version 1.74
It could happen (e.g. when the integration is not running for a while, that the TOKEN REFRESH will not work (cause of an expired refresh token) - in this case the Integration will now allow you to re-enter the initial token-request (that requires the login via the web browser (where you must capture a code via the developers tools)

Additionally, the documentation have been updated (https://github.com/marq24/ha-fordpass/blob/main/doc/OBTAINING_TOKEN.md)

## Version 1.73
Only internal stuff have been updated - reduced the number of token-refresh requests - and enhanced further the debug logging output more refactoring some of the internal API stuff (just to learn how the internals are working).

## Version 1.72
Only internal stuff have been updated - mainly the debug logging output have been cleaned up and I have refactored some of the internal API stuff (just to learn how the internals are working).

## Version 1.71
Initial fork version ()

## Version 1.70
- New config flow to allow for a user to generate a token in their browser then enter into the application, bypasses WAF. 
## Version 1.69
- Versioning issue 1.69 is 1.70
## Version 1.68
- Fix for missing locale
- Fix duplicate Switches dictionary
- Fix DC fast charging bug
## Version 1.67
- Temp fix for login issues (Uses different region login servers, may get blocked soon!)
## Version 1.66
- Remove deprecated GPS source type
- Added data_description translations
## Version 1.65
- Add ability to use Lincoln vehicles again
## Version 1.64
- Add helper text for initial login when using a mobile number
- Added sensors containing all returned data from API (Disabled by default in HA) can be used for templates and other automations/research
## Version 1.63 
- Reworked authentication to use login.ford.com
## Version 1.62
- Skipped due to emergency release of auth changes
## Version 1.61
- Deepsleep status is now reported again as a sensor
- Compass Direction is now an attribute under the device_tracker entity
- Handle missing countdownTimer variable
- Handle missing events dictionary
- Temporary fix for elveh errors
- Added more Trip Data to elVeh (will assess to determine if previous Trip scores can be removed)
  - Trip Speed Score
  - Trip Deceleration Score
  - Trip Acceleration Score
  - Trip Electrical Efficiency (unsure what this value is, adding it to get more data)
- Fix for fuel not displaying properly for EV's (will assess to determine if duplicate values in other sensors can be removed)
- Better display for Trip Duration under elVeh
- elVeh kW conversions will display 0 if voltage or amperage is 0
## Version 1.60
- Versioning issue 1.59 is 1.60
## Version 1.59
- Add support for manual VIN entry (Lincoln cars hopefuly) - Please test this and report any errrors back!
- Fix for lastRefresh sensor not returning local time
- Fix for elVehCharging Estimated End Time not returning local time
- Fix for elVehCharging Battery Temp debug error
- elVehCharging now displays Plug Status as default
- Added device class for battery
- Fix for incorrect DoorStatus @sarangcr03 
- Added Trip Data to elVeh.
  - Trip Ambient Temp
  - Trip Outside Air Ambient Temp
  - Trip Duration
  - Trip Cabin Temp
  - Trip Energy Consumed (kW)
  - Trip Distance Traveled
  - Trip Efficiency
  - Driving Score now Trip Driving Score
  - Range Regen now Trip Range Regeneration
## Version 1.58
- Rewrote auth function to allow for more granular debugging
- Changed odometer to use native conversions in HA (pick from sensor options)
- No longer displays "unavaliable" if sensor goes offline, will instead show previous data and report an error in logs
- More EV features
- Add hood status to door locks
- Added tripFuelEconomy attribute under speed
- Added "Driving Score" and Range Regeneration attributes to elVeh (Driving score was a previous feature in the FordPass app. Its basically a "score" based on the maximum brake regen gained from a trip)
- Removed duplicate attributes from elVeh / elVehCharging
- Returning Estimated End Time as a timestamp for elVehCharging (previously was Time To Complete)
- Improved the elVehCharging display

## Version 1.57
- Rewrote command function to actively poll until success or failure is returned
- Fixed bug where elveh attributes wasn't showing
- Fixed bug where command wouldn't check token expiry first
## Version 1.56
- Fix for error when missing GPS data from vehicle
- Fix for electric vehicle error
- Better formatting of door statuses
- Fix for missing diesel stats
- Fix for initial integration error on startup
- Added temperature sensors
- Added extra attributes to speed sensor e.g. pedal positions and RPM
- Removed GPS sensor (All stats are in device_tracker entity)
- Added check if window position if supported, if not entity is not added
## Version 1.55
- Skipped due to git issue
## Version 1.54
- Fixed lock/unlock status (Waits 90seconds before checking command has completed)
- Added back diesel sensors
- Added indicator/warning sensor (Shows any faults on the vehicle)
## Version 1.53
- Updated vehicle endpoint to use new Autonomics API
- Added secondary Autonomic token
- Remapped commands to use new "command" API endpoint
- Remapped existing sensors to new json variables (Some are missinge)
- Added charge status sensor (Thanks @SquidBytes)
- Added new speed sensor (Will be adding more attributes to this like pedal position and torque settings soon)

*Please report any bugs as a separate issue so I can keep track easier*

There is a LOT more coming soon as the new API exposes an excessive amount of information including speed, pedal position, crash sensors and way more. 
## Version 1.52
- Update for discontinued API endpoints (Update, lock, remote start)
## Version 1.51
- Fix for incorrect tire pressure conversion
- Handling of blank nickName when configuring car in config flow
- Fix for incorrect URL reference in vehicles API
## Version 1.50
- Complete refactor of all code to make it more compliant
- Added new config flow to allow for choosing vehicles on setup instead of using VIN 
## Version 1.49
- Added German & Italian translations (@@lollo0296)
## Version 1.48
- Add translations for service strings
- Fix error on odometer missing config
- Handle unsupported car locks
- Add Units for elVeh DTE
## Version 1.47
- Add poll_api service to allow for manual refreshing of data outside of poll interval (e.g. poll more when driving)
- Add option to disable distance conversion when units displaying wrong in certain countries
- Add device_class to "last_refresh" sensor
- Add Locking/Unlocking status to lock entity
- Enabled support for debugging via the UI
## Version 1.46
- Fix diesel filter error
## Version 1.45
- Fix window position reporting as open always
## Version 1.44
- Fix incorrect window position status
- Add reload integration service 
## Version 1.43
- Add DPF status on supported vehicles
- Incorrect vehicle refresh time (@ronytomen)
- Refresh integration automatticly on options changes
## Version 1.42
- Fix incorrect tire pressure units (Thanks @costr for debugging)
## Version 1.41
- Fix options error in HA 2023
## Version 1.40
- Fix empty value bug for lighting attributes
- Fix casting bug for elvehdte and batterly level
- Fix empty but not null string for tire pressure 
- Add BAR units to options
## Version 1.39
- added statistics support to odometer sensor
- Fixed device_tracker not working correctly in automations
## Version 1.38
- Changed the default update interval from 5 minutes to 15 minutes (Reduce Ford API Requests)
- Add ability to change this interval in integration options (WARNING! setting this too low will result in your Fordpass account being locked!!!!)
## Version 1.37
- Update messages icon to new format
## Version 1.36
- Remove vehicle list endpoint on setup
- Add dutch translation (Thanks @Bert-R)
## Version 1.35
- Remove deprecated dotted module
- Add coordinator context for HA 2022.7
## Version 1.34
- Change oauth flow for latest Fordpass changes
## Version 1.33
- Fix occasional hacs error due to git tag issue
## Version 1.32
- Fix auth flow to comply with new endpoints
**Warning - If you encounter auth errors please delete the token file located in the install directory or use the "delete_token" service**
## Version 1.31
- Fix for multiple accounts
## Version 1.30
- Fix for elvDTE error
## Version 1.29
- Disabled guard mode
- Fixed elvDTE units
- set Vin check on install to warning only (Lincoln cars don't show in ford database)
## Version 1.28
- Added vin check on setup (Will check if given VIN is linked to the credentials)
## Version 1.27
- Fix fuel level error
- Add code for Vin debugging
## Version 1.25
- Updated user agent
- Added messages sensor to show current messages in fordpass

## Version 1.24
- Change device_state_attributes to extra_state_attributes (HA 2020.12.1)
- Changed session timeout to cope with timeouts in fordpass API (Helps prevent 403 error's)

## Version 1.23
**Breaking Change**

When installing this new version please go to "integrations" and click configure on Fordpass and choose your preferred units. Not doing this will result in an error!!

- Fixed tyre pressure status when sensor missing or broke
- Add DistanceToEmpty Imperial Conversion (Thanks @JacobWasFramed )
- Seperated pressure and distance measurement unit selection (Thanks @JacobWasFramed)
## Version 1.22
- Fix for custom config locations on certain HA installs

## Version 1.21
- Error handling for null fuel and elVehDTE attributes. Thanks @wietseschmitt

## Version 1.20
- Fixed incorrect reporting of guardmode switch status

## Version 1.19
- Added null guard status handling (effects some vehicles)

## Version 1.18
- Fix Guard mode error (Missing data array)

## Version 1.17
- Added VIN option to UI
- Added Guard mode switch (Need people to test as don't have access to a guard mode enabled vehicle)
- Added extra sensors (Credit @tonesto7)
    - Zonelighting (Supported models only)
    - Deep sleep status
    - Remote start status
    - Firmware update status
- Added partial opening status for windows (Credit @tonesto7)
- Added logic to only add supported sensors (Still in Beta)


## Version 1.16
- Fixed json error when adding multiple cars
- Added "vin" option to "refresh" service to allow for refreshing of individual cars
- Fixed service bug calling the wrong variable
- Updated manifest for latest HA requirements

## Version 1.15
- Added Version attribute to manifest.json

## Version 1.14
- Converted "lastrefresh" to home assistant local time

## Version 1.13
- Fixed window status for Undefined
- Tire pressure now reports based on region
- Fixed 401 error for certain token refreshes
- Token file has been moved to same folder as install (Can be changed by changing the token_location variable)

## Version 1.12
- Fixed window status reporting as Open

## Version 1.11
- Added check for "Undefined_window_position" window value
- Fixed bug when TMPS value was 0 (Some cars return 0 on individual tyre pressures)

## Version 1.10
- Fixed door open bug 2.0 (New position value)
- Added a check to see if a vehicle supports GPS before adding the entity

## Version 1.09
- Added individual TMPS Support
- Fixed door open bug

## Version 1.08
- Added Icons for each entity
- Added "clear_tokens" service call
- Added Electric Vehicle features
- Fixed "Invalid" lock status

## Version 1.07
- Support for multiple regions (Fixes unavaliable bug)
- Token renamed to fordpass_token

**In order to support regions you will need to reinstall the integration to change region** (Existing installs will default to North America)

## Version 1.06 
- Minor bug fix
## Version 1.05
- Added device_tracker type (fordpass_tracker)
- Added imperial or metric selection
- Change fuel reading to %
- Renamed lock entity from "lock.lock" to "lock.fordpass_doorlock"


## Version 1.04
- Added window position status
- Added service "fresh_status" to allow for polling the car at a set interval or event
- Added Last Refreshed sensor, so you can see when the car was last polled for data
- Added some more debug logging

## Version 1.03
- Added door status
- Added token saving
- Added car poll refresh