# Using the fordpass integration as data provider for EVCC
### Required preparation

#### Create a Long-lived access token
You need a HA long-lived access token and the IP/hostname of your HA instance. For information how to create such a long-lived access token, please see @marq24 ['Use evcc with your Home Assistant sensor data' documentation](https://github.com/marq24/ha-evcc/blob/main/HA_AS_EVCC_SOURCE.md).

#### Required replacement in the following yaml example
Below you will find a valid evcc vehicle configuration - __but you have to make two replacements__:
1. The text '__[YOUR-HA-INSTANCE]__' have to be replaced with the IP/host name of your Home Assistant installation.

   E.g. when your HA is reachable via: http://192.168.10.20:8123, then you need to replaced `[YOUR-HA-INSTANCE]` with `192.168.10.20`


2. The text '__[YOUR-TOKEN-HERE]__' have to be replaced with the _Long-lived access token_ you have just created in HA.

   E.g. when your token is: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiIzNWVjNzg5M2Y0ZjQ0MzBmYjUwOGEwMmU4N2Q0MzFmNyIsImlhdCI6MTcxNTUwNzYxMCwiZXhwIjoyMDMwODY3NjEwfQ.GMWO8saHpawkjNzk-uokxYeaP0GFKPQSeDoP3lCO488`, then you need to replaced `[YOUR-TOKEN-HERE]` with this (long) token text.

So as short example (with all replacements) would look like:

```
      ...
      source: http
      uri: http://192.168.10.20:8123/api/states/sensor.senec_grid_state_power
      method: GET
      headers:
        - Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiIzNWVjNzg5M2Y0ZjQ0MzBmYjUwOGEwMmU4N2Q0MzFmNyIsImlhdCI6MTcxNTUwNzYxMCwiZXhwIjoyMDMwODY3NjEwfQ.GMWO8saHpawkjNzk-uokxYeaP0GFKPQSeDoP3lCO488
      insecure: true
      ...
```

### Additional Template Sensor is need to provide EVCC vehicle status

We need to create a HA sensor that will provide the status of charging - this will be A, B, C, D, E, F as described in the [evcc documentation](https://github.com/evcc-io/evcc/blob/master/api/chargemodestatus.go).

<!--
| Status | Code | Fzg. angeschlossen | Laden aktiv | Description                                                                |
| --- |------|--------------------|-------------|----------------------------------------------------------------------------|
| StatusA | "A"  | nein               | nein        | Ladestation betriebsbereit, Fahrzeug getrennt                              |
| StatusB | "B"  | ja                 | nein        | Fahrzeug verbunden, Netzspannung liegt nicht an                            |
| StatusC | "C"  | ja                 | ja          | Fahrzeug lädt, Netzspannung liegt an                                       |
| StatusD | "D"  | ja                 | ja          | Fahrzeug lädt mit externer Belüfungsanforderung (für Blei-Säure-Batterien) |
| StatusE | "E"  | ja                 | nein        | Fehler Fahrzeug / Kabel (CP-Kurzschluss, 0V)                               |
| StatusF | "F"  | ja                 | nein        | Fehler EVSE oder Abstecken simulieren (CP-Wake-up, -12V)                   |

The original evcc code can be found [here](https://github.com/evcc-io/evcc/blob/c338a8ec0cbf1df853e300bf50a213fae2b9ff69/vehicle/ford/provider.go#L58C5-L76). Here is the section just for your reference:

```go
// Status implements the api.ChargeState interface
func (v *Provider) Status() (api.ChargeStatus, error) {
    status := api.StatusNone

    res, err := v.statusG()
    if err == nil {
        switch res.Metrics.XevPlugChargerStatus.Value {
        case "DISCONNECTED":
            status = api.StatusA // disconnected
        case "CONNECTED":
            status = api.StatusB // connected, not charging
        case "CHARGING", "CHARGINGAC":
            status = api.StatusC // charging
        default:
            err = fmt.Errorf("unknown charge status: %s", res.Metrics.XevPlugChargerStatus.Value)
        }
    }

    return status, err
}
```
-->

From the original Ford evcc integration it looks like that we only needs to provide status A, B or C and we can get this from the HA sensor status from `sensor.fordpass_elvehcharging` (you need to adjust the following template sensor if you have a different sensor name).

#### Create the template sensor
1. Go to the HA configuration and select `Configuration` -> `Helpers` -> `Add Helper`
2. Select `Template` and in the next selection select `Template for Sensor`
3. Enter a name for the sensor (e.g. `fordpass_evcc_charging_code`)
4. Enter the following template code:
   ```
   {% set val = states('sensor.fordpass_elvehcharging')|upper %}{% if val == 'DISCONNECTED' -%}A{% elif val == 'CONNECTED' -%}B{% elif val == 'CHARGING' or val == 'CHARGINGAC' -%}C{%- else %}UNKNOWN{%- endif %}
   ```
5. Optional you can select your fordpass Vehicle as `Device`
6. Click `OK`

### Check if the status of the new template sensor is working

Make sure that the new created sensor `sensor.fordpass_evcc_charging_code` will provide the correct status code (A, B or C) - you can check this in the HA Developer Tools -> States.

### Finally, the sample evcc.yaml vehicle section for my Ford MachE

This is my evcc.config vehicle section for my Ford MachE - which is configured in the fordpass integration as `fordpass` and so all sensors of this integration are prefixed with `fordpass_`:

>[!NOTE]
> I have no clue how a second vehicle would show up in the HA fordpass integration - so if somebody would like to share this info, I would be quite happy to document this here.

```yaml
vehicles:
- name: ford_mach_e
  type: custom
  title: MachE GT-XXXXX
  capacity: 84.65
  soc:
    source: http
    uri: http://[YOUR-HA-INSTANCE]:8123/api/states/sensor.fordpass_elveh
    method: GET
    headers:
      - Authorization: Bearer [YOUR-TOKEN-HERE]
      - Content-Type: application/json
    insecure: true
    jq: .attributes."Battery Charge" | tonumber
    timeout: 2s # timeout in golang duration format, see https://golang.org/pkg/time/#ParseDuration

  range:
    source: http
    uri: http://[YOUR-HA-INSTANCE]:8123/api/states/sensor.fordpass_elveh
    method: GET
    headers:
      - Authorization: Bearer [YOUR-TOKEN-HERE]
      - Content-Type: application/json
    insecure: true
    jq: .state | tonumber
    timeout: 2s # timeout in golang duration format, see https://golang.org/pkg/time/#ParseDuration

  status:
    source: http
    uri: http://[YOUR-HA-INSTANCE]/api/states/sensor.fordpass_evcc_charging_code
    method: GET
    headers:
      - Authorization: Bearer [YOUR-TOKEN-HERE]
      - Content-Type: application/json
    insecure: true
    jq: .state
    timeout: 2s # timeout in golang duration format, see https://golang.org/pkg/time/#ParseDuration
```
