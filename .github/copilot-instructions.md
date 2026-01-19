# AI Coding Agent Instructions for ha-fordpass

## Project Overview
**ha-fordpass** is a Home Assistant custom integration for Ford and Lincoln vehicles using the FordPass/Lincoln Way API. It's a **cloud push integration** using WebSocket for real-time data, not polling. The codebase is reverse-engineered from the official mobile apps to work with Ford's undocumented APIs.

**Key constraint**: Ford frequently changes their APIs. The integration may break without warning. All changes should be defensive and account for potential API response variations.

## Critical Architecture

### Data Flow Architecture
1. **`fordpass_bridge.py`** (2735 lines): WebSocket connection manager + OAuth token handling + all Ford API calls
2. **`fordpass_handler.py`** (1512 lines): Data parsing from Ford JSON → Home Assistant entity state/attributes
3. **`const_tags.py`** (1019 lines): Defines `Tag` enum - every entity (sensor, lock, button, etc.) is a Tag with state/attribute extraction logic
4. **Entity Platform Files** (`sensor.py`, `switch.py`, `lock.py`, etc.): Read coordinator data via Tags and expose to Home Assistant

### Data Structure (in-memory)
```python
coordinator.data = {
    "metrics": {},      # All sensor readings (vehicle state)
    "states": {},       # Event states
    "events": {},       # Recent events
    "vehicles": {},     # Vehicle metadata
    "messages": {},     # System messages
    "rcc": {},          # Remote climate control
    # ... other roots defined in fordpass_handler.py
}
```

### Entity Definition Pattern
All entities are defined via `Tag` enum entries:
```python
Tag.BATTERY_SOC = ApiKey(
    key="batterySOCActual",
    state_fn=lambda data, prev: FordpassDataHandler.get_battery_soc(data),
    attrs_fn=FordpassDataHandler.get_battery_attrs
)
```
- `state_fn`: Extracts the state value from coordinator.data
- `attrs_fn`: Extracts Home Assistant attributes
- `on_off_fn` / `select_fn` / `press_fn`: Async operations (commands)

## Developer Workflows

### Testing & Local Development
1. **No automated tests** - integration tests depend on real Ford API tokens (stored outside repo)
2. **Token Storage**: OAuth tokens stored in `$HA_CONFIG/custom_components/.storage/fordpass_tokens.json` (NOT tracked)
3. **Configuration Validation**: See `config_flow.py` - OAuth flow in browser extracts `?code=` from network tab (see `doc/DEV-TOOLS.md`)
4. **Services Available**:
   - `fordpass.refresh_status` - Request vehicle data refresh
   - `fordpass.clear_tokens` - Emergency token cleanup
   - `fordpass.poll_api` - Force refresh

### Adding a New Entity (Sensor Example)
1. **Define the Tag** in `const_tags.py`:
   ```python
   NEW_SENSOR = ApiKey(
       key="newMetricKey",
       state_fn=lambda data, _: FordpassDataHandler.get_value_for_metrics_key(data, "newMetricKey")
   )
   ```
2. **Add to SENSORS list** in `const_tags.py` with `SensorEntityDescription`
3. **No platform file changes needed** - `sensor.py` auto-discovers via SENSORS list

### Adding a New Command (Button/Switch)
Commands use the `press_fn` or `on_off_fn` callbacks:
```python
CUSTOM_COMMAND = ApiKey(
    key="customCmd",
    press_fn=FordpassDataHandler.my_command_handler
)
```
In `fordpass_handler.py`:
```python
@staticmethod
async def my_command_handler(coordinator, vehicle):
    return await vehicle.send_command("api_endpoint", {"param": "value"})
```

## Project-Specific Patterns & Conventions

### Vehicle Capability Detection
Different Ford vehicles support different features (EV vs gas, RCC, etc.). Capabilities are detected in `FordPassDataUpdateCoordinator`:
```python
self._engine_type = None  # BEV, PHEV, HEV, ICE
self._supports_REMOTE_CLIMATE_CONTROL = None
self._supports_GUARD_MODE = None
```
Use `coordinator.tag_not_supported_by_vehicle(tag)` to filter unsupported entities before creating them.

### Engine Type Tags
- **`EV_ONLY_TAGS`**: BEV/PHEV only (charging, SOC, etc.)
- **`FUEL_OR_PEV_ONLY_TAGS`**: Gas or hybrid vehicles
- **`RCC_TAGS`**: Remote climate control (not all vehicles)

### Region Handling
Ford uses different regional APIs:
```python
REGION_OPTIONS_FORD = ["fra", "deu", ..., "usa", "rest_of_world"]
REGION_APP_IDS = {  # Maps regions to OAuth app IDs
    "europe": "667D773E-...",
    "north_america": "BFE8C5ED-..."
}
```
Config migration handles legacy region keys (`USA` → `usa`).

### Coordinator Pattern
The `FordPassDataUpdateCoordinator` extends Home Assistant's base coordinator:
- Manages WebSocket connection via `bridge.ws_connect()`
- Watchdog runs every 64 seconds to monitor WebSocket health
- On data update, all entities get `coordinator.data` snapshot atomically
- Graceful reauth on 401 errors (calls `_check_for_reauth()`)

### Error Handling with Ford APIs
Ford's undocumented API is fragile:
```python
try:
    value = float(value)
except (ValueError, TypeError) as e:
    _LOGGER.debug(f"Invalid value: {value} caused {e}")
    return None  # or UNSUPPORTED
```
- **UNSUPPORTED**: Value not available for this vehicle
- **None**: Value not yet received
- Log at DEBUG level for expected failures (defensive coding)

### Unit Conversion & Localization
Use `FordpassDataHandler` utilities:
```python
localize_distance(value, units)  # km → user's distance unit
localize_temperature(value, units)  # C → user's temp unit
```
Pressure units are configurable (PSI/kPa/BAR) via options → coordinator.units.

### State Restoration
Sensors with `SensorStateClass.TOTAL_INCREASING` restore previous state on HA restart:
```python
sensor._previous_state = restored_value  # Prevents fake jumps
```
See `sensor.py` for implementation.

## Integration Points & External Dependencies

### Ford API Authentication
1. OAuth 2.0 with PKCE flow (see `config_flow.py`)
2. Tokens stored securely outside component dir
3. Access token expires ~5 minutes → auto-refresh via `bridge`
4. Refresh token used to get new access tokens

### WebSocket Connection
- Real-time vehicle telemetry pushed from Ford servers
- Connection in `fordpass_bridge.py` class `ConnectedFordPassVehicle`
- If WebSocket dies, watchdog detects within 64 seconds and reconnects
- No polling interval needed (UPDATE_INTERVAL is fallback only)

### Home Assistant Services
Integration registers custom services in `__init__.py`:
```python
hass.services.async_register(DOMAIN, "refresh_status", async_refresh_status_service)
```

## Common Gotchas

1. **API Response Variations**: Always use `.get()` with defaults when parsing Ford JSON
2. **Vehicle Diversity**: Check `_engine_type` before using EV-specific fields
3. **Regional APIs**: Some endpoints differ by region - don't hardcode
4. **Token Expiry**: 5-minute window - bridge auto-handles but log refresh attempts
5. **Entity IDs Change**: Platform changes may alter entity IDs; users may have automations referencing old IDs
6. **Config Versions**: Bump `CONFIG_VERSION` in `const.py` if breaking changes; implement migration in `async_migrate_entry()`

## Quick File Reference

| File | Purpose |
|------|---------|
| `__init__.py` | Integration setup, coordinator, services |
| `fordpass_bridge.py` | WebSocket, OAuth, all Ford API calls |
| `fordpass_handler.py` | Data extraction logic (metrics → states) |
| `const_tags.py` | Tag definitions (every entity type) |
| `config_flow.py` | Initial OAuth setup + config schema |
| `sensor.py`, `switch.py`, `lock.py`, `button.py` | Entity platforms (mostly auto-generated from Tags) |
| `const.py` | Hard constants (version, API IDs, regions) |
| `const_shared.py` | Shared constants (units, manufacturers) |
| `doc/OBTAINING_TOKEN.md` | User-facing token extraction guide |

## Testing New Features

1. **Manual config entry creation** in HA UI with test vehicle credentials
2. **Monitor logs**: Set `logger: custom_components.fordpass: DEBUG`
3. **Services tab** in Developer Tools to test commands
4. **State Inspector** to verify entity states match expected data
5. **Browser Network Tab** (see `doc/DEV-TOOLS.md`) to debug Ford API responses
