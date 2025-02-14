# Fordpass Home Assistant Integration [v1.70 fork]

[![hacs_badge](https://img.shields.io/badge/HACS-custom-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)

<!-- Wrote up a little note thing for the breaking change. Not sure if you want to use it but I figured this could be a good start or something since I was already editing the readme. -->
> [!WARNING]
> # Breaking Change
> There is a new token obtaining system.
> 
> The token used by this integration is currently removed whenever the integration is updated. With this 1.70 update, the token will be wiped during every update, requiring users to manually add the token during the initial setup.
> 
> To prevent this issue, we will be moving the token file outside the FordPass directory. This change will ensure that the token is preserved during updates. This will require reconfiguration of your setup.
> Please see the Installation section, or the Wiki for help.


## Credit
- https://github.com/itchannel/fordpass-ha - Original Fordpass integration by @itchannel and @SquidBytes
- https://github.com/clarkd - Initial Home Assistant automation idea and Python code (Lock/Unlock)
- https://github.com/pinballnewf - Figuring out the application ID issue
- https://github.com/degrashopper - Fixing 401 error for certain installs
- https://github.com/tonesto7 - Extra window statuses and sensors
- https://github.com/JacobWasFramed - Updated unit conversions
- https://github.com/heehoo59 - French Translation
- https://github.com/SquidBytes - EV updates and documentation

## **Changelog**
[Updates](info.md)

## Installation
Use [HACS](https://hacs.xyz/) to add this repository as a custom integration repo [ https://github.com/marq24/ha-fordpass ]. 

Upon installation navigate to your integrations, and follow the configuration options. You will need to provide:
- Fordpass Email

You will then be prompted with `Setup Token` 

Follow the instructions on the [docs](./doc/OBTAINING_TOKEN.md) to obtain your token.

## Usage
Your car must have the lastest onboard modem functionality and have registered/authorised the fordpass application

## Services
<!-- I haven't looked into these services, but it might be easier to maintain a Wiki with the various services compared to the README. Just a thought. -->
### Car Refresh
I have added a service to poll the car for updates, due to the battery drain I have left this up to you to set the interval. The service to be called is "refresh_status" and can be accessed in home assistant using "fordpas.refresh_status". 

Optionally you can add the "vin" parameter followed by your VIN number to only refresh one vehicle. By default this service will refresh all registered cars in HA.

**This will take up to 5 mins to update from the car once the service has been run**

###
Click on options and choose imperial or metric to display in km/miles. Takes effect on next restart of home assistant. Default is Metric
<!-- These might need to be updated since its now different -->
### Clear Tokens
If you are experiencing any sign in issues, please trying clearing your tokens using the "clear_tokens" service call.

### Poll API
This service allows you to manually refresh/poll the API without waiting the set poll interval. Handy if you need quicker updates e.g. when driving for gps coordinates


## Sensors
### Currently Working
**Sensors may change as the integration is being developed**
<!-- Keeping this the same, but it will probably change and update alongside Fordconnect and the new app features -->

- Fuel Level
- Odometer
- Lock/Unlock
- Oil Status
- Last known GPS Coordinates/Map
- Tyre Status
- Battery Status
- Ignition Status
- Alarm Status
- Individual door statuses
- Remote Start
- Window Status (Only if your car supports it!)
- Last Car Refresh status
- Car Tracker
- Supports Multiple Regions
- Electric Vehicle Support
- TPMS Sensors
- Guard Mode (Only supported cars)
- Deep sleep status
- Fordpass messages and alerts

## Disclaimer

This integration is not officially supported by Ford and as such using this integration could result in your account being locked out!
