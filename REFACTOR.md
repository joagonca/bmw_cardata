# Refactor: Split coordinator.py into Separate Modules

## Problem

`custom_components/bmw_cardata/coordinator.py` is 721 lines containing three unrelated classes and four module-level factory functions:

| Component | Lines | Responsibility |
|-----------|-------|----------------|
| `BMWTokenManager` | 51–189 (~140 lines) | Shared OAuth token lifecycle (refresh, storage, multi-entry sync) |
| `BMWMqttManager` | 190–519 (~330 lines) | Shared MQTT connection (paho client, reconnect, VIN routing) |
| `get_token_manager` / `get_mqtt_manager` / `remove_*` | 522–559 (~40 lines) | Singleton factories stored in `hass.data[DOMAIN]` |
| `BMWCarDataCoordinator` | 560–721 (~160 lines) | Per-VIN HA DataUpdateCoordinator (initial fetch, MQTT processing, entity data) |

The token and MQTT managers are **shared singletons** (one per account, independent of any single coordinator). They have their own lifecycle, locking, and threading concerns. Keeping them in the same file as the coordinator conflates three distinct responsibilities and makes the file hard to navigate.

## Target Structure

```
custom_components/bmw_cardata/
├── coordinator.py       # BMWCarDataCoordinator only (~160 lines)
├── token_manager.py     # BMWTokenManager + get/remove factory functions (~180 lines)
├── mqtt_manager.py      # BMWMqttManager + get/remove factory functions (~370 lines)
├── __init__.py          # (update imports)
├── ...                  # (other files unchanged)
```

## Current Import Graph

These files import from `coordinator.py`:

```
__init__.py         → BMWCarDataCoordinator, get_token_manager, get_mqtt_manager,
                      remove_token_manager, remove_mqtt_manager
entity.py           → BMWCarDataCoordinator
sensor.py           → BMWCarDataCoordinator
binary_sensor.py    → BMWCarDataCoordinator
device_tracker.py   → BMWCarDataCoordinator
diagnostics.py      → BMWCarDataCoordinator
```

Only `__init__.py` imports the manager classes/factories. All entity files only need `BMWCarDataCoordinator`.

## Internal Dependencies Between the Three Classes

```
BMWTokenManager       ← standalone, depends on: const, utils, aiohttp
BMWMqttManager        ← depends on: BMWTokenManager (passed in constructor)
BMWCarDataCoordinator ← depends on: BMWTokenManager, BMWMqttManager (passed in constructor)
```

The dependency is strictly downward: `TokenManager → MqttManager → Coordinator`. No circular imports.

## Step-by-Step Implementation

### Step 1: Create `token_manager.py`

Extract from `coordinator.py` lines 51–189 and the factory functions at lines 522–532, 546–553.

**Contents:**
- `class BMWTokenManager` (full class as-is)
- `def get_token_manager(hass, client_id) -> BMWTokenManager`
- `def remove_token_manager(hass, client_id) -> None`

**Imports needed:**
```python
import asyncio
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_TOKENS,
    DEFAULT_SCOPES,
    DOMAIN,
    TOKEN_ENDPOINT,
    TOKEN_EXPIRES_AT,
    TOKEN_REFRESH,
    TOKEN_REFRESH_BUFFER,
    TOKEN_REFRESH_EXPIRES_AT,
)
from .utils import format_token_expiry, parse_token_response
```

**Note:** `async_refresh_tokens()` uses `import aiohttp` inline (line 120) for `aiohttp.FormData`. Move to top-level import in the new file.

### Step 2: Create `mqtt_manager.py`

Extract from `coordinator.py` lines 190–519 and the factory functions at lines 533–559.

**Contents:**
- `class BMWMqttManager` (full class as-is)
- `def get_mqtt_manager(hass, token_manager, gcid) -> BMWMqttManager`
- `async def remove_mqtt_manager(hass, gcid) -> None`

**Imports needed:**
```python
import asyncio
import json
import logging
import ssl
import threading
from typing import Any, Callable

import paho.mqtt.client as mqtt

from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    MQTT_BROKER_HOST,
    MQTT_BROKER_PORT,
    MQTT_KEEPALIVE,
    MQTT_TOPIC_PATTERN,
    TOKEN_ID,
)
from .token_manager import BMWTokenManager  # ← new import path
```

### Step 3: Slim down `coordinator.py`

Keep only `BMWCarDataCoordinator` (lines 560–721).

**Updated imports:**
```python
import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_MQTT_DEBUG,
    CONF_MQTT_BUFFER_SIZE,
    CONF_CLIENT_ID,
    CONF_TOKENS,
    CONF_VIN,
    DIAG_MAX_MESSAGES,
    DOMAIN,
    DRIVETRAIN_BEV,
    DRIVETRAIN_CONV,
    EVENT_MQTT_DEBUG,
    TOKEN_ACCESS,
)
from .mqtt_manager import BMWMqttManager       # ← new import path
from .token_manager import BMWTokenManager     # ← new import path
from .utils import async_bmw_api_get, extract_telemetry_value
```

**Removed imports** (no longer needed in coordinator.py):
- `json`, `ssl`, `threading`, `time`, `paho.mqtt.client`
- `async_get_clientsession`
- `DEFAULT_SCOPES`, `TOKEN_ENDPOINT`, `TOKEN_EXPIRES_AT`, `TOKEN_ID`, `TOKEN_REFRESH`, `TOKEN_REFRESH_BUFFER`, `TOKEN_REFRESH_EXPIRES_AT`
- `MQTT_BROKER_HOST`, `MQTT_BROKER_PORT`, `MQTT_KEEPALIVE`, `MQTT_TOPIC_PATTERN`
- `format_token_expiry`, `parse_token_response`

### Step 4: Update `__init__.py` imports

Change:
```python
from .coordinator import (
    BMWCarDataCoordinator,
    get_mqtt_manager,
    get_token_manager,
    remove_mqtt_manager,
    remove_token_manager,
)
```

To:
```python
from .coordinator import BMWCarDataCoordinator
from .mqtt_manager import get_mqtt_manager, remove_mqtt_manager
from .token_manager import get_token_manager, remove_token_manager
```

### Step 5: Verify no other files need changes

Entity files (`entity.py`, `sensor.py`, `binary_sensor.py`, `device_tracker.py`, `diagnostics.py`) only import `BMWCarDataCoordinator` from `coordinator.py` — this path doesn't change.

## Validation Checklist

After the refactor:

- [ ] `python3 -c "import ast; ast.parse(open(f).read())"` passes for all `.py` files
- [ ] `grep -rn 'from .coordinator import' custom_components/` shows only `BMWCarDataCoordinator`
- [ ] `grep -rn 'from .token_manager import' custom_components/` shows `__init__.py` and `mqtt_manager.py`
- [ ] `grep -rn 'from .mqtt_manager import' custom_components/` shows `__init__.py` and `coordinator.py`
- [ ] No circular imports: `token_manager` → (nothing local except const/utils), `mqtt_manager` → `token_manager`, `coordinator` → both managers
- [ ] Integration loads in Home Assistant without errors
- [ ] MQTT connection and telemetry streaming still work
- [ ] Multi-vehicle setup (shared managers) still works

## What NOT to Change

- **No logic changes.** This is a pure structural move. Every line of code stays identical.
- **No renames** except import paths.
- **No changes to `const.py`, `utils.py`, `config_flow.py`**, entity files, or `manifest.json`.
- **Don't split further.** Three files (token, mqtt, coordinator) is the right granularity. The factory functions belong with their respective class.
