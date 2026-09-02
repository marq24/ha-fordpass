# Surplus Charge – PV surplus charging and emergency charging

This automation controls charging of a Ford  in Home Assistant so that:

- charging starts immediately in a critical SoC state,
- the battery does not fall below the minimum threshold of 20 %,
- surplus PV power above 3 kW is used whenever available,
- charging pauses when solar power drops,
- and charging stops automatically once the battery reaches 80 %.

The automation is designed for a vehicle with FordPass entities, solar power sensor and home battery sensor, but it can be adapted e.g. to use dynamic power tariffs with minimal changes.

## What the automation does

The automation evaluates a combination of vehicle status, charge level, solar generation, and home battery state:

1. Minimum charge / emergency charging
   - If the car battery drops below 20 % and the vehicle is not charging, charging is started immediately.
   - Purpose: the vehicle should never fall below the defined minimum threshold.
   - Emergency charging is also triggered when no PV power is available.

2. PV surplus charging above 20 %
   - Once the vehicle reaches 20 %, the automation checks whether enough solar power is available.
   - If the solar system produces more than 3000 W and the home battery is above 50 %, charging continues using solar energy.
   - If the surplus is insufficient or the car battery is too low, charging is paused.

3. Waiting state when plugged in
   - If the vehicle is connected but there is not yet enough surplus power, the charge command remains off and the vehicle waits.
   - The car remains plugged in, but charging does not start until the required conditions are met.

4. Stop when PV power drops
   - If the solar output falls below 3000 W while charging is active, charging is stopped.
   - The vehicle remains in a ready-to-charge or waiting state and will resume only when sufficient surplus power is available again.

5. Target limit at 80 %
   - When the vehicle reaches 80 %, charging is terminated.
   - This keeps the car battery in a useful range and prevents overcharging beyond the configured target.

## How the logic works in practice

The automation uses several triggers and conditions:

- `sensor.hostname_scb_solar_power`
  - measures PV output in watts,
  - threshold: 3000 W (3 kW),
  - determines whether enough surplus energy is available for charging.

- `sensor.hostname_scb_battery_soc`
  - measures the home battery state of charge,
  - threshold: 50 %,
  - prevents charging when the storage system is too low.

- `sensor.fordpass_<vin>_soc`
  - shows the vehicle battery state of charge,
  - minimum threshold: 20 %,
  - target threshold: 80 %.

- `switch.fordpass_<vin>_elvehcharge`
  - is the switch used to start or stop charging.

- `sensor.fordpass_<vin>_elvehcharging`
  - indicates whether the vehicle is currently charging or paused.

- `sensor.fordpass_<vin>_elvehplug`
  - indicates whether the vehicle is plugged in.

 `notify.mobile_app` 
   - your mobile app notification target. Used for "debugging"

## Key flow rules

The automation is split into `choose` blocks. That means the order of the conditions matters, because Home Assistant executes the first matching rule.

The core logic is:

- Below 20 %: charge immediately, even without PV surplus.
- Between 20 % and 80 %: continue charging only if enough PV surplus is available.
- Above 80 %: stop charging.
- If the car is plugged in but no surplus is available: remain in a waiting state.

## How to customize the automation

### 1. Adjust the entity IDs mentioned above

### 2. Change thresholds

The most important values are:

- `above: 3000` → PV power threshold in watts
- `below: 20` → minimum charge threshold
- `above: 19` and `below: 80` → charging range
- `above: 50` → minimum home battery level

If you want to charge only with a 4 kW surplus, change `3000` to `4000`.

If you want to stop at 90 % instead of 80 %, change both the `below: 80` condition and the matching notification text.

## How to install this automation 

1. Open **Settings → Automations & Scenes**.
2. Click **Create Automation**.
3. Open the 3-dot menu and choose **Edit in YAML**.
4. Replace the YAML with the automation above.
5. Save the automation.
6. Run it once manually for a quick validation.
7. Plug in the vehicle and monitor traces/logbook to confirm expected behavior.

If you prefer file-based YAML:
1. Add the automation block to `automations.yaml`.
2. Go to **Developer Tools → YAML**.
3. Click **Reload Automations**.

```
alias: EV - PV Überschussladen & Notladung
description: >-
  Steuert das Laden des Ford Explorers mit 20% Mindestladung, PV-Überschuss bis
  80% und automatischem Wartezustand bei Anstecken.
triggers:
  - trigger: numeric_state
    entity_id:
      - sensor.hostname_scb_solar_power
    for:
      minutes: 3
    id: start_pv_charge
    above: 3000
  - trigger: numeric_state
    entity_id:
      - sensor.hostname_scb_solar_power
    for:
      minutes: 3
    id: stop_pv_charge
    below: 3000
  - trigger: numeric_state
    entity_id: sensor.fordpass_<vin>_soc
    below: 20
    id: soc_critical_low
  - trigger: numeric_state
    entity_id: sensor.fordpass_<vin>_soc
    above: 19
    id: soc_reached_20
  - trigger: numeric_state
    entity_id: sensor.fordpass_<vin>_soc
    above: 80
    id: battery_full
  - trigger: state
    entity_id: sensor.fordpass_<vin>_elvehplug
    to:
      - CONNECTED
      - Connected
    id: plugged_in
conditions:
  - condition: zone
    entity_id: device_tracker.fordpass_<vin>_tracker
    zone: zone.home
  - condition: state
    entity_id: sensor.fordpass_<vin>_elvehplug
    state:
      - CONNECTED
      - Connected
actions:
  - choose:
      - conditions:
          - condition: numeric_state
            entity_id: sensor.fordpass_<vin>_soc
            below: 20
          - condition: state
            entity_id: sensor.fordpass_<vin>_elvehcharging
            state:
              - STOPPED
        sequence:
          - action: notify.mobile_app
            data:
              title: '⚡ Ford Explorer: Notladung aktiv'
              message: >-
                Akkustand kritisch ({{
                states('sensor.fordpass_<vin>_soc') }} %). Fahrzeug
                wird sofort geladen, bis 20 % erreicht sind.
          - action: switch.turn_on
            target:
              entity_id: switch.fordpass_<vin>_elvehcharge
            continue_on_error: true
      - conditions:
          - condition: trigger
            id: soc_reached_20
          - condition: state
            entity_id: sensor.fordpass_<vin>_elvehcharging
            state:
              - IN_PROGRESS
        sequence:
          - if:
              - condition: numeric_state
                entity_id: sensor.hostname_scb_solar_power
                above: 3000
              - condition: numeric_state
                entity_id: sensor.hostname_scb_battery_soc
                above: 50
            then:
              - action: notify.mobile_app
                data:
                  title: '☀️ Ford Explorer: PV-Laden aktiv'
                  message: >-
                    20 % Mindestladung erreicht. Ausreichend PV-Leistung
                    vorhanden – Ladevorgang wird mit Solarstrom bis 80 %
                    fortgesetzt.
            else:
              - action: notify.mobile_app
                data:
                  title: '⏸️ Ford Explorer: Ladung pausiert'
                  message: >-
                    20 % Mindestladung erreicht. Aktuell kein ausreichender
                    PV-Überschuss oder Hausspeicher < 50 % – Ladevorgang
                    pausiert.
              - action: switch.turn_off
                target:
                  entity_id: switch.fordpass_<vin>_elvehcharge
                continue_on_error: true
      - conditions:
          - condition: or
            conditions:
              - condition: trigger
                id: start_pv_charge
              - condition: trigger
                id: plugged_in
          - condition: numeric_state
            entity_id: sensor.fordpass_<vin>_soc
            above: 19
            below: 80
          - condition: state
            entity_id: sensor.fordpass_<vin>_elvehcharging
            state:
              - STOPPED
          - condition: numeric_state
            entity_id: sensor.hostname_scb_solar_power
            above: 3000
          - condition: numeric_state
            entity_id: sensor.hostname_scb_battery_soc
            above: 50
        sequence:
          - action: notify.mobile_app
            data:
              title: '☀️ Ford Explorer: PV-Laden gestartet'
              message: >-
                Genug PV-Leistung vorhanden. Laden gestartet bei {{
                states('sensor.fordpass_<vin>_soc') }} % (Ziel: 80
                %).
          - action: switch.turn_on
            target:
              entity_id: switch.fordpass_<vin>_elvehcharge
            continue_on_error: true
      - conditions:
          - condition: trigger
            id: stop_pv_charge
          - condition: state
            entity_id: sensor.fordpass_<vin>_elvehcharging
            state:
              - IN_PROGRESS
          - condition: numeric_state
            entity_id: sensor.fordpass_<vin>_soc
            above: 19
        sequence:
          - action: notify.mobile_app
            data:
              title: '☁️ Ford Explorer: PV-Laden pausiert'
              message: >-
                PV-Leistung reicht nicht mehr aus. Ladevorgang gestoppt bei {{
                states('sensor.fordpass_<vin>_soc') }} %.
          - action: switch.turn_off
            target:
              entity_id: switch.fordpass_<vin>_elvehcharge
            continue_on_error: true
      - conditions:
          - condition: trigger
            id: battery_full
          - condition: state
            entity_id: sensor.fordpass_<vin>_elvehcharging
            state:
              - IN_PROGRESS
        sequence:
          - action: notify.mobile_app
            data:
              title: '✅ Ford Explorer: 80 % erreicht'
              message: Das Ladeziel von 80 % wurde erreicht. Ladevorgang beendet.
          - action: switch.turn_off
            target:
              entity_id: switch.fordpass_<vin>_elvehcharge
            continue_on_error: true
    default:
      - if:
          - condition: trigger
            id: plugged_in
          - condition: numeric_state
            entity_id: sensor.fordpass_<vin>_soc
            above: 19
        then:
          - action: switch.turn_off
            target:
              entity_id: switch.fordpass_<vin>_elvehcharge
            continue_on_error: true
          - action: notify.mobile_app
            data:
              title: '🔌 Ford Explorer: Angesteckt (Wartezustand)'
              message: >-
                Fahrzeug verbunden bei {{
                states('sensor.fordpass_<vin>_soc') }} %. Aktuell
                kein ausreichender PV-Überschuss oder Hausspeicher < 50 % –
                Ladevorgang wartet auf Solarstrom.
mode: single
```
