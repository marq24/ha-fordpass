# Fordpass Home Assistant Integration (EV dedicated) [v1.7x fork]


[![hacs_badge](https://img.shields.io/badge/HACS-custom-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)

> [!WARNING]
> ## Disclaimer - Use could lead to a (temporary) lock of your Fordpass account.
> **This integration is not officially supported by Ford and as such using this integration could result in your account being locked out!** 
> 
> Please be aware, that we are developing this integration to best of our knowledge and belief, but cant give a guarantee. Therefore, use this integration **at your own risk**!
> 
> - It's recommended to use/create a **separate Fordpass account** for this integration (see step-by-step procedure further below).
> - It's recommended to use an **update interval of 240 seconds or higher** to prevent a lock of your Fordpass account.

> [!NOTE]
> This fork is WIP - and since I just own a EV (Mustang MachE 2023) I will focus on the features of the electrical vehicle data.

> [!WARNING]
> ## This fork is **not compatible** with the original Fordpass integration
> - The entity names have been changed in oder to ensure that the sensor names include the VIN.
> - The sensor attribute names does not contain spaces anymore to make post-processing easier (using camelcase).

> [!NOTE]
> ## All credits must go to @itchannel and @SquidBytes
> There is a new token obtaining system introduced in the origin fordpass repository. This fork has been released in order to provide a release version of the v1.7x that can be installed via the new HACS (2.0) system (where you only can install 'released' integration versions). 
> 
> The token used by this integration is currently removed whenever the integration is updated. With this 1.7x update, the token will be wiped during every update, requiring users to manually add the token during the initial setup.
> 
> To prevent this issue, we will be moving the token file outside the FordPass directory. This change will ensure that the token is preserved during updates. This will require reconfiguration of your setup.
> Please see the Installation section, or the [docs](./doc/OBTAINING_TOKEN.md) for help.

## Credit
- https://github.com/itchannel/fordpass-ha - Original fordpass integration by @itchannel and @SquidBytes
- https://github.com/clarkd - Initial Home Assistant automation idea and Python code (Lock/Unlock)
- https://github.com/pinballnewf - Figuring out the application ID issue
- https://github.com/degrashopper - Fixing 401 error for certain installs
- https://github.com/tonesto7 - Extra window statuses and sensors
- https://github.com/JacobWasFramed - Updated unit conversions
- https://github.com/heehoo59 - French Translation
- https://github.com/SquidBytes - EV updates and documentation

## Installation Instructions (3 Steps)
### Step 1. HACS add the Integration

[![Open your Home Assistant instance and adding repository to HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=marq24&repository=ha-fordpass&category=integration)

1. In HA HACS, you need to add a new custom repository (via the 'three dots' menu in the top right corner).
2. Enter https://github.com/marq24/ha-fordpass as the repository URL (and select  the type `Integration`).
3. After adding the new repository, you can search for `fordpass` in the search bar.
4. Important there is already a default HACS fordpass integration - Please make sure to select the 'correct' one with the description: _Fordpass integration for Home Assistant [fork optimized for EVCC].
5. Install the 'correct' (aka 'this') fordpass integration (v1.71 or higher).
6. Restart HA.

### Step 2. Setup the Integration

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=fordpass)

7. After the restart go to  `Settings` -> `Devices & Services` area
8. Add the new integration `Fordpass` and follw the instructions:<br/>
   You will need to provide:
   - Your Fordpass Email
   - Select a Fordpass Region (USA, EU, UK, AU) [it's expected that only USA will work right now]

### Step 3. The hard part - the  **Token Setup**
The actual token request requires an external browser to get finally the Fordpass access token. [Yes this is for sure quite unusual process when setting up a HA integration, but it's the only way to get the token right now]

Please follow the steps:
1. Copy the URL listed in the first input field
2. Open a new browser (with enabled developer tools) and paste the copied URL it into your second browser
3. In this second browser: Enter your Fordpass credentials (again) and press the login button
4. Watch the developer tools Network-tab till you see the `?code=` request (this request will fail, but it's not important)
5. Copy the full `Request-URL` from this `?code=` request from the browsers developer tools and paste it in the HA integration setup Token field [you must copy the complete URL - so ist must start with `fordapp://userauthorized/?code= ... `]

More details (how to deal with the browser developer tools) to obtain your token can be found in the [docs](./doc/OBTAINING_TOKEN.md).

## Usage with EVCC

[All information, how to use this integration as provider for Ford EV data can be found in a seperate section.](./doc/EVCC.md)

## Use of a separate Fordpass account is recommended

It's recommended to use a separate Fordpass account for this integration. This is to prevent any issues with the Fordpass account being locked due to the polling of the API. Here are is a short procedure:

1. Create a new Fordpass account with a different email address (and confirm the account by eMail) - It's important, that you can access this eMail account from your mobile phone with the installed FordPass App!
2. From the Fordpass app (logged in with your original account), you can select `Settings` from the main screen (at the bottom there are three options: `Connected Services >`, `Location >` & `Settings >`)
3. On the next screen select `Vehicle Access` (from the options: `Phone As A Key >`, `Software updates >` & `Vehicle Access >`)
4. Select `Invite Driver(s) Invite` and then enter the next screen the eMail address of the new account you created in step 1. 
5. Now you can log out from the Fordpass app and log-in with the new account.
6. Wait till the invitation eMail arrives and accept the invitation with the button at the bottom of eMail.
7. Finally, you should have now connected your car to the new Fordpass account.
8. You can now log out again of the Fordpass app with your second account and re-login with your original Fordpass account.
9. You can double-check with a regular browser, that the car is now accessible with the new account by web.  


## **Changelog**
[Updates](info.md)

## Usage
Your car must have the latest onboard modem functionality and have registered/authorised the fordpass application

## Services
<!-- I haven't looked into these services, but it might be easier to maintain a Wiki with the various services compared to the README. Just a thought. -->
### Car Refresh
@itchannel and @SquidBytes have added a service to poll the car for updates, due to the battery drain they have left this up to you to set the interval. The service to be called is "refresh_status" and can be accessed in home assistant using "fordpas.refresh_status". 

Optionally you can add the "vin" parameter followed by your VIN number to only refresh one vehicle. By default, this service will refresh all registered cars in HA.

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
