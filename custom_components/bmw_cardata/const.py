"""Constants for BMW CarData integration."""

from __future__ import annotations

from typing import Final

# Integration domain
DOMAIN: Final = "bmw_cardata"

# Configuration keys
CONF_CLIENT_ID: Final = "client_id"
CONF_VIN: Final = "vin"
CONF_TOKENS: Final = "tokens"
CONF_VEHICLE_INFO: Final = "vehicle_info"

# Token keys
TOKEN_ACCESS: Final = "access_token"
TOKEN_REFRESH: Final = "refresh_token"
TOKEN_ID: Final = "id_token"
TOKEN_GCID: Final = "gcid"
TOKEN_EXPIRES_AT: Final = "expires_at"
TOKEN_REFRESH_EXPIRES_AT: Final = "refresh_expires_at"

# BMW API endpoints
API_BASE_URL: Final = "https://api-cardata.bmwgroup.com"
AUTH_BASE_URL: Final = "https://customer.bmwgroup.com"
DEVICE_CODE_ENDPOINT: Final = f"{AUTH_BASE_URL}/gcdm/oauth/device/code"
TOKEN_ENDPOINT: Final = f"{AUTH_BASE_URL}/gcdm/oauth/token"

# MQTT settings
MQTT_BROKER_HOST: Final = "api-cardata-streaming.bmwgroup.com"
MQTT_BROKER_PORT: Final = 8883
MQTT_KEEPALIVE: Final = 60
MQTT_TOPIC_PATTERN: Final = "{gcid}/{vin}"

# OAuth settings
DEFAULT_SCOPES: Final = "openid cardata offline_access"
TOKEN_REFRESH_BUFFER: Final = 300  # Refresh 5 minutes before expiry

# Platforms
PLATFORMS: Final = ["sensor", "binary_sensor"]

# Known sensor keys with metadata
# Format: key -> (name, unit, device_class, icon)
KNOWN_SENSORS: Final[dict[str, tuple[str, str | None, str | None, str | None]]] = {
    "vehicle.vehicle.travelledDistance": (
        "Odometer",
        "km",
        "distance",
        "mdi:counter",
    ),
    "vehicle.drivetrain.lastRemainingRange": (
        "Total Range",
        "km",
        "distance",
        "mdi:gas-station",
    ),
    "vehicle.drivetrain.electricEngine.kombiRemainingElectricRange": (
        "Electric Range",
        "km",
        "distance",
        "mdi:battery-charging",
    ),
    "vehicle.powertrain.electric.range.target": (
        "Target Electric Range",
        "km",
        "distance",
        "mdi:target",
    ),
    "vehicle.chassis.axle.row1.wheel.left.tire.pressure": (
        "Front Left Tire Pressure",
        "kPa",
        "pressure",
        "mdi:car-tire-alert",
    ),
    "vehicle.chassis.axle.row1.wheel.right.tire.pressure": (
        "Front Right Tire Pressure",
        "kPa",
        "pressure",
        "mdi:car-tire-alert",
    ),
    "vehicle.chassis.axle.row2.wheel.left.tire.pressure": (
        "Rear Left Tire Pressure",
        "kPa",
        "pressure",
        "mdi:car-tire-alert",
    ),
    "vehicle.chassis.axle.row2.wheel.right.tire.pressure": (
        "Rear Right Tire Pressure",
        "kPa",
        "pressure",
        "mdi:car-tire-alert",
    ),
    "vehicle.electricalSystem.battery.stateOfCharge": (
        "Battery State of Charge",
        "%",
        "battery",
        "mdi:battery",
    ),
    "vehicle.drivetrain.fuelSystem.remainingFuel": (
        "Fuel Level",
        "%",
        None,
        "mdi:gas-station",
    ),
}

# Known binary sensor keys with metadata
# Format: key -> (name, device_class, icon)
KNOWN_BINARY_SENSORS: Final[dict[str, tuple[str, str | None, str | None]]] = {
    "vehicle.drivetrain.electricEngine.charging.profile.climatizationActive": (
        "Charging Climatization",
        None,
        "mdi:air-conditioner",
    ),
    "vehicle.drivetrain.electricEngine.charging.profile.isRcpConfigComplete": (
        "Charging Profile Complete",
        None,
        "mdi:check-circle",
    ),
    "vehicle.body.trunk.isOpen": (
        "Trunk",
        "opening",
        "mdi:car-back",
    ),
    "vehicle.body.hood.isOpen": (
        "Hood",
        "opening",
        "mdi:car",
    ),
    "vehicle.body.trunk.isLocked": (
        "Trunk Lock",
        "lock",
        "mdi:lock",
    ),
    "vehicle.body.chargingPort.status": (
        "Charging Port",
        "plug",
        "mdi:ev-plug-type2",
    ),
    "vehicle.cabin.door.row1.driver.isOpen": (
        "Driver Door",
        "door",
        "mdi:car-door",
    ),
    "vehicle.cabin.door.row1.passenger.isOpen": (
        "Front Passenger Door",
        "door",
        "mdi:car-door",
    ),
    "vehicle.cabin.door.row2.driver.isOpen": (
        "Rear Left Door",
        "door",
        "mdi:car-door",
    ),
    "vehicle.cabin.door.row2.passenger.isOpen": (
        "Rear Right Door",
        "door",
        "mdi:car-door",
    ),
}

# All known keys for reference
ALL_KNOWN_KEYS: Final = set(KNOWN_SENSORS.keys()) | set(KNOWN_BINARY_SENSORS.keys())
