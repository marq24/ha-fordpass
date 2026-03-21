# Comparison of ha-fordpass and ha-fordconnect-query integrations

The main technical difference between these two integrations is that [ha-fordpass](https://github.com/marq24/ha-fordpass) uses reverse-engineered APIs for full vehicle control (like it can be done via the FordPass App), while [ha-fordconnect-query](https://github.com/marq24/ha-fordconnect-query) uses official Ford Connect Query APIs and is strictly read-only. [^1], [^2]

## Key Technical Differences

| Feature [^1], [^2], [^3], [^4], [^5], [^6], [^7], [^8], [^9], [^10], [^11], [^12] | ha-fordpass                                       | ha-fordconnect-query                                                           |
|-------------------------------------------------------------------|---------------------------------------------------|--------------------------------------------------------------------------------|
| API Type                                                          | Reverse-engineered FordPass app API               | Official FordConnect Query API                                                 |
| Capabilities                                                      | __Read & Write__: Remote start, lock/unlock, etc. | __Read Only__: Sensor data only                                                |
| Communication                                                     | __Websockets__: Real-time push updates            | __Cloud Polling__: Checks for data every 60s                                   |
| Auth Method                                                       | Requires external browser dev tools for setup     | Standard __OAuth 2.0__ via Ford Developer Portal (need to register an account) |
| Stability                                                         | At risk of breaking if Ford updates their app     | More stable as it uses supported services (that are provided by Ford)          |

## Core Comparison

### ha-fordpass

* The most important technical advantage lies in the use of Websockets, which allows Home Assistant to immediately receive "push" updates when the status of a vehicle changes (e.g., the car is locked via the official app).
* The ha-fordpass integration simulates the communication behavior of the FordPass app
* It provides deep control of yozr vehicle but is more complex to set up, requiring you to capture tokens using browser developer tools.
* Since it's fully reverse-engineered, it's prone to breaking if Ford updates their app.
* Since the integration uses undocumented Ford services, your FordPass User account may be at risk of being temporarily suspended by Ford. This is very unlikely since the integration really simulates the activities from the official app (but it's still recommended to use a separate account for this purpose).

### ha-fordconnect-query

* Has been developed as a future-proof alternative to ha-fordpass
* It uses the official FordConnect Query API.
* It lacks control features like the remote start (or any other remote vehicle controls)
* It is much easier to configure because it follows standard industry OAuth procedures.
* Is intended to be a reliable backup if the reverse-engineered FordPass API is ever shut down.
* Once you have registered your developer account and created the OAuth application, it can be used with any Ford vehicle and any Ford account (of the specific region).
* Since only official Ford services are used, your FordPass User account should be safe from being temporarily suspended by Ford.

### Final remark

> [!NOTE]
> Both integrations can be run in parallel without interfering with each other. [^2]

---

[^1]: [https://github.com](https://github.com/marq24/ha-fordconnect-query/blob/main/README.md#:~:text=My%20main%20motivation%20comes%20from%20the%20fact,%28when%20the%20FordPass%20Integration%20will%20stop%20working%29.)
[^2]: [https://github.com](https://github.com/marq24/ha-fordpass/releases)
[^3]: [https://community.home-assistant.io](https://community.home-assistant.io/t/an-cloud-push-alternative-to-existing-fordpass-integration/899770)
[^4]: [https://github.com](https://github.com/marq24/ha-fordpass/releases)
[^5]: [https://developer.ford.com](https://developer.ford.com/apis#:~:text=The%20FordConnect%20Query%20API%20enables%20developers%20to,point%20for%20building%20innovative%20connected%20vehicle%20experiences.)
[^6]: [https://www.facebook.com](https://www.facebook.com/groups/HomeAssistant/posts/4259642560973748/)
[^7]: [https://github.com](https://github.com/itchannel/fordpass-ha)
[^8]: [https://community.home-assistant.io](https://community.home-assistant.io/t/an-cloud-push-alternative-to-existing-fordpass-integration/899770)
[^9]: [https://community.home-assistant.io](https://community.home-assistant.io/t/an-cloud-push-alternative-to-existing-fordpass-integration/899770)
[^10]: [https://github.com](https://github.com/marq24/ha-fordconnect-query/blob/main/README.md)
[^11]: [https://github.com](https://github.com/marq24/ha-fordconnect-query/blob/main/README.md)
[^12]: [https://github.com](https://github.com/marq24/ha-fordconnect-query/blob/main/README.md)
[^13]: [https://community.home-assistant.io](https://community.home-assistant.io/t/an-cloud-push-alternative-to-existing-fordpass-integration/899770)
[^14]: [https://community.home-assistant.io](https://community.home-assistant.io/t/an-cloud-push-alternative-to-existing-fordpass-integration/899770)
[^15]: [https://github.com](https://github.com/marq24/ha-fordpass/releases)
[^16]: [https://github.com](https://github.com/marq24/ha-fordconnect-query/blob/main/README.md)
[^17]: [https://community.home-assistant.io](https://community.home-assistant.io/t/fordconnect-query-integration-a-read-only-alternative-to-fordpass/972684)
