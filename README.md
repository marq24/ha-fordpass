# FordPass Home Assistant Integration 2025 (EV/PHEV/Petrol/Diesel)

<!--
> [!NOTE]  
> Highlights information that users should take into account, even when skimming.

> [!TIP]
> Optional information to help a user be more successful.

> [!IMPORTANT]  
> Crucial information necessary for users to succeed.

> [!WARNING]  
> Critical content demanding immediate user attention due to potential risks.

> [!CAUTION]
> Negative potential consequences of an action.
-->
> [!NOTE]
> Even if this integration was initially forked from [@itchannel and @SquidBytes](https://github.com/itchannel/fordpass-ha), the current version is a complete rewrite and is __not compatible__ with the __original FordPass integration__.
> 
> I have been continuously working on improvements of the integration in the past month, especially on the compatibility with the latest Home Assistant versions and apply clean code standards. I hope this effort will make it much easier for other developers to understand how the communication with the FordPass backend works and how to extend/adjust the integration in the future.
>
> This is a __cloud push integration__, which means that the data is pushed from Ford backend systems to Home Assistant via a websocket connection — so you receive data as it changes. __No polling__ (in a certain interval) __is required anymore__.
> 
> It would be quite gentle if you could consider supporting the development of this integration by any kind of contribution — TIA

[![hacs_badge][hacsbadge]][hacs] [![github][ghsbadge]][ghs] [![BuyMeCoffee][buymecoffeebadge]][buymecoffee] [![PayPal][paypalbadge]][paypal] [![hainstall][hainstallbadge]][hainstall]

> [!NOTE]
> My main motivation comes from the fact that I own a Ford Mustang Mach-E 2023, and I wanted to have a Home Assistant integration that just works with my car. I will focus on the features that are available for electrical vehicles, but of course I will try not to mess up the features for petrol or diesel vehicles. [If you like to support me with this challange: Please see also the _I need you_ section](https://github.com/marq24/ha-fordpass#i-need-you)


> [!WARNING]
> ## Disclaimer — The use of this HA integration could lead to a (temporary) lock of your FordPass account.
> **This integration is not officially supported by Ford, and as such, using this integration could result in your account being locked out!** 
> 
> Please be aware that I am developing this integration to the best of my knowledge and belief, but can't give a guarantee. Therefore, use this integration **at your own risk**!
> 
> It's recommended to use/create a **separate FordPass account** for this integration ([see the 'step-by-step' procedure further below](https://github.com/marq24/ha-fordpass?tab=readme-ov-file#use-of-a-separate-fordpass-account-is-recommended)).


> [!IMPORTANT]
> ## Unusual Integration Setup 
> Status Quo in spring/summer 2025: This integration requires an unusual setup process to be able to access the data of your vehicle. This is because Ford has changed (once again) the access policies to the required backend APIs (and revoked the access to the APIs for individual developers).
> 
> The current implementation is based on API calls the original FordPass App (for Android & iOS) performs, and it's some sort of reverse engineered.
> 
> This approach implies that when Ford is going to change something in their none-public/undocumented API, it's quite likely that the integration will break instantly.
> 
> __It's impossible to predict__ when this will happen, but __I will try__ to keep the integration up-to-date and working __as long as possible__, since I drive a Ford myself.
> 
> ## Fetch & Store FordPass Access Token
> During the integration setup, you will be guided through the process to obtain an access token for your vehicle in the context of your FordPass account.
> 
> This should be a _one-time process_, and the access token will be stored in a file outside the custom integration directory (This is to prevent the access token from being deleted during updates of the integration itself). As already explaind, I can't give any guarantee that process will work in the future.
> 
> The overall setup process is described in short in the [Installation section](#installation-instructions-3-steps) below, and in detail in the [linked documentation](./doc/OBTAINING_TOKEN.md).

---

## Requirements
1. Your car must have the latest onboard modem functionality and have been registered/authorized with the fordpass application.
2. You need a Home Assistant instance (v2023.9 or higher) with the [HACS](https://hacs.xyz) custom integration installed.
3. You __must have removed any previous FordPass integration from your Home Assistant instance__ (especially the original FordPass integration from @itchannel and @SquidBytes) before you can use this fork of the integration. Please be aware that it's quite likely that a configuration can be disabled! [see also the incompatibility information](https://github.com/marq24/ha-fordpass?tab=readme-ov-file#this-fork-is-not-compatible-with-the-original-fordpass-integration-from-itchannel-and-squidbytes)

> [!IMPORTANT]
> This is a HACS custom integration — not a Home Assistant Add-on. Don't try to add this repository as an add-on in Home Assistant.
> 
> The IMHO simplest way to install this integration is via the two buttons below ('_OPEN HACS REPOSITORY ON MY HA_' and '_ADD INTEGRATION TO MY HA_').


## Installation Instructions (3 Steps)
### Step 1. HACS add the Integration

[![Open your Home Assistant instance and adding repository to HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=marq24&repository=ha-fordpass&category=integration)

1. In HA HACS, you need to add a new custom repository (via the 'three dots' menu in the top right corner).
2. Enter https://github.com/marq24/ha-fordpass as the repository URL (and select  the type `Integration`).
3. After adding the new repository, you can search for `fordpass` in the search bar.
4. Important there is already a default HACS fordpass integration — Please make sure to select the 'correct' one with the description: _FordPass integration for Home Assistant [fork optimized for EV's & EVCC]_.
5. Install the 'correct' (aka 'this') fordpass integration (v2025.5.0 or higher).
6. Restart HA.

### Step 2. Setup the Integration

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=fordpass)

7. After the restart go to  `Settings` -> `Devices & Services` area
8. Add the new integration `FordPass` and follow the instructions:<br/>
   You will need to provide:
   - Your __FordPass Email__/Account 
   - __Select a FordPass Region__ — Currently you can select between:
     - 'Germany'
     - 'Netherlands'
     - 'UK & other European Countries'
     - 'Canada, the USA & Rest of the World'
     
     But there is no information __if__ the selection of the region __has any impact__ on the provided data — at least I have not found any differences so far. No matter which region you select, the integration will work (🤞) with all vehicles that are registered in your FordPass account.

### Step 3. The hard part — the **Token Setup**
The actual token request requires an external browser to get finally the FordPass access token. [Yes this is for sure quite unusual process when setting up a HA integration, but it's the only way to get the token right now]

Please follow the steps:
1. Copy the URL listed in the first input field
2. Open a new browser (with enabled developer tools) and paste the copied URL it into your second browser
3. In this second browser: Enter your FordPass credentials (again) and press the login button
4. Watch the developer tools Network-tab till you see the `?code=` request (this request will fail, but it's not important)
5. Copy the full `Request-URL` from this `?code=` request from the browser's developer tools and paste it in the HA integration setup Token field [you must copy the complete URL - so ist must start with `fordapp://userauthorized/?code= ... `]

More details (how to deal with the browser developer tools) to get your token can be found in the [additional 'obtaining token document'](./doc/OBTAINING_TOKEN.md).


## Usage with EVCC

[All information, how to use this integration as provider for Ford EV data can be found in a separate section in this repository.](./doc/EVCC.md)


## Use of a separate FordPass account is recommended

> [!TIP]
> It's recommended to use a separate FordPass account for this integration. This is to prevent any issues with the FordPass account being locked due to the polling of the API.

Here is a short procedure how to create a second account:

1. Create a new FordPass account with a different email address (and confirm the account by eMail) - It's important, that you can access this eMail account from your mobile phone with the installed FordPass App!
2. From the FordPass app (logged in with your original account), you can select `Settings` from the main screen (at the bottom there are three options: `Connected Services >`, `Location >` & `Settings >`)
3. On the next screen select `Vehicle Access` (from the options: `Phone As A Key >`, `Software updates >` & `Vehicle Access >`)
4. Select `Invite Driver(s) Invite` and then enter the next screen the eMail address of the new account you created in step 1. 
5. Now you can log out from the FordPass app and log-in with the new account.
6. Wait till the invitation eMail arrives and accept the invitation with the button at the bottom of eMail.
7. Finally, you should have now connected your car to the new FordPass account.
8. You can now log out again of the FordPass app with your second account and re-login with your original FordPass account.
9. You can double-check with a regular browser, that the car is now accessible with the new account by web.  


## Services

### Clear Tokens
If you are experiencing any sign in issues, please try clearing your tokens using the "clear_tokens" service call.

### Poll API (local refresh) — also available as button in the UI
This service allows you to sync the data of the integration (read via the websocket) with the Ford backends by manually polling all data. This can become Handy if you want to ensure that HA data is in sync with the Ford backend data.

### Request Update (remote refresh) — also available as button in the UI
This service will contact the modem in the vehicle and request to sync data between the vehicle and the ford backends. **Please note that this will have an impact on the battery of your vehicle.**


## Sensors
**Sensors may change as the integration is being developed**
~~Supports Multiple Regions~~

| Sensor Name                        | Petrol/Diesel | (P)HEV/BEV |
|------------------------------------|---------------|------------|
| Odometer                           | X             | X          |                 
| Battery (12V)                      | X             | X          |            
| Oil                                | X             | X          |   
| Tire Pressure                      | X             | X          |            
| GPS/Location Data (JSON)           | X             | X          |                 
| Alarm Status                       | X             | X          |
| Status Ignition                    | X             | X          |          
| Status Door                        | X             | X          |              
| Window Position                    | X             | X          |    
| last refresh (timestamp)           | X             | X          |
| Speed                              | X             | X          |
| Indicators/Warnings                | X             | X          |
| Temperature Coolant                | X             | X          |
| Temperature Outdoors               | X             | X          |
| Status Remote Start                | X             | X          |
| FordPass Messages                  | X             | X          |
| Belt Status                        | X             | X          |
| Fuel Level (can be > 100%)         | X             |            |
| Temperature Engine Oil             | X             |            |
| Status Diesel System               | X             |            |
| AdBlue Level                       | X             |            |
| EV-Data collection                 |               | X          |
| EV Plug Status                     |               | X          |
| EV Charging information            |               | X          |
| State of Charge (SOC)              |               | X          |
| EVCC status code ('A', 'B' or 'C') |               | X          |
| ~~Sleep Mode~~                     |               |            |
| ~~Zone Lighting~~                  |               |            |

## Buttons / Switches / Other

| Type          | Sensor Name                          | Petrol/Diesel | (P)HEV/BEV |
|---------------|--------------------------------------|---------------|------------|
| Button        | Remote Sync (Car with Ford backend)  | X             | X          |
| Button        | Local Sync (Ford backend with HA)    | X             | X          |
| Lock          | Lock/Unlock Vehicle                  | X             | X          |
| Switch        | Remote Start (❄/☀)                  | X             | X          |
| Switch        | ~~Guard Mode (Only supported cars)~~ |               |            |
| DeviceTracker | Vehicle Tracker                      | X             | X          |

## Want to report an issue?

Please use the [GitHub Issues](https://github.com/marq24/ha-fordpass/issues) for reporting any issues you encounter with this integration. Please be so kind before creating a new issues, check the closed ones if your problem has been already reported (& solved).

To speed up the support process, you might like to already prepare and provide DEBUG log output. In the case of a technical issue, I would need this DEBUG log output to be able to help/fix the issue. There is a short [tutorial/guide 'How to provide DEBUG log' here](https://github.com/marq24/ha-senec-v3/blob/master/docs/HA_DEBUG.md) — please take the time to quickly go through it.

For this integration, you need to add:
```
logger:
  default: warning
  logs:
    custom_components.fordpass: debug
```


## I need You!

This might be a quite unusual request, but I would like to ask you to consider supporting the testing of this integration by granting me access to your car data. 

It's correct that this implies that you are willing to share your vehicle data (like the location) with me and I would __fully understand if you are not willing to do so__. But at least it must be allowed to ask. Since I can't afford to buy another Ford vehicle (nor do I actually have the space), it would be great if I would be able to test (besides with my EV, also) PEV's, DIESEL and GAS vehicles with this integration.

You can do this by adding my FordPass account to your existing vehicle as it's described here in the section [Use of a separate FordPass account is recommended](#use-of-a-separate-fordpass-account-is-recommended).

So if you are willing to help, please send me a short eMail and I will send you my FordPass account eMail address, so you can add me to your vehicle (and can accept your invite). You can end the sharing at any time by removing my account from your vehicle in your FordPass app.


## Supporting the development
If you like this integration and want to support the development, please consider supporting me on [GitHub Sponsors][ghs] or [BuyMeACoffee][buymecoffee] or [PayPal][paypal]. 

[![GitHub Sponsors][ghsbadge]][ghs] [![BuyMeCoffee][buymecoffeebadge]][buymecoffee] [![PayPal][paypalbadge]][paypal]


> [!WARNING]
> ## This fork is **not compatible** with the original FordPass integration from @itchannel and @SquidBytes
> Before you can use this fork with your vehicle, you must have removed the original FordPass integration from HA and must have deleted all configuration entries. Please be aware that it's quite likely that a configuration can be disabled!
>
> ### Incompatible changes:
> - The VIN has been added to all the entity names, to ensure that names stay unique in HA when you have multiple vehicles.
> - The sensor attribute names do not contain spaces anymore to make post-processing easier. Additionally, all the attribute names are now using camelcase. This means that all attributes start with a lower-case character (don't let you fool by the HA user interface, which always will show the first character as upper-case).
> - The access-token(s) is stored outside the custom integration
>
> ### Additional enhancements:
> - This is now a cloud __push__ integration, which means that the data is pushed to Home Assistant via a websocket connection. This is a major improvement over the original integration, which was a cloud __pull__ integration.
> - Additional Sensors for EV/PHEV vehicles
> - Buttons to local/remote refresh data in HA
> - Sensor to provide EVCC-Charging state [see evcc.io website for details](https://evcc.io)
> - Translation of Entity names (DE/EN)
> - Code cleanup and refactoring


## Change Log
[See GitHub releases](https://github.com/marq24/ha-fordpass/releases) of this repository or [for older update information that was not part of this repository a separate document](./info.md) for the complete change log of this integration.


## Credits
- https://github.com/itchannel/fordpass-ha - Original fordpass integration by @itchannel and @SquidBytes

### Credits (of the original integration)
- https://github.com/SquidBytes - EV updates and documentation
- https://github.com/clarkd - Initial Home Assistant automation idea and Python code (Lock/Unlock)
- https://github.com/pinballnewf - Figuring out the application ID issue
- https://github.com/degrashopper - Fixing 401 error for certain installs
- https://github.com/tonesto7 - Extra window statuses and sensors
- https://github.com/JacobWasFramed - Updated unit conversions
- https://github.com/heehoo59 - French Translation


[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge&logo=homeassistantcommunitystore&logoColor=ccc

[ghs]: https://github.com/sponsors/marq24
[ghsbadge]: https://img.shields.io/github/sponsors/marq24?style=for-the-badge&logo=github&logoColor=ccc&link=https%3A%2F%2Fgithub.com%2Fsponsors%2Fmarq24&label=Sponsors

[buymecoffee]: https://www.buymeacoffee.com/marquardt24
[buymecoffeebadge]: https://img.shields.io/badge/buy%20me%20a-coffee-blue.svg?style=for-the-badge&logo=buymeacoffee&logoColor=ccc

[paypal]: https://paypal.me/marq24
[paypalbadge]: https://img.shields.io/badge/paypal-me-blue.svg?style=for-the-badge&logo=paypal&logoColor=ccc

[hainstall]: https://my.home-assistant.io/redirect/config_flow_start/?domain=fordpass
[hainstallbadge]: https://img.shields.io/badge/dynamic/json?style=for-the-badge&logo=home-assistant&logoColor=ccc&label=usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.fordpass.total