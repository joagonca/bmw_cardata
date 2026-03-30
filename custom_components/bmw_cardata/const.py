"""Constants for BMW CarData integration."""

from __future__ import annotations

from typing import Final, NamedTuple

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfLength, UnitOfPressure


class SensorDef(NamedTuple):
    """Definition for a numeric sensor entity."""

    name: str
    unit: str | None
    device_class: SensorDeviceClass | None
    icon: str | None
    drivetrain: str | None


class BinarySensorDef(NamedTuple):
    """Definition for a binary sensor entity."""

    name: str
    device_class: BinarySensorDeviceClass | None
    icon: str | None
    drivetrain: str | None


class EnumSensorDef(NamedTuple):
    """Definition for an enum sensor entity."""

    name: str
    options: list[str]
    icon: str | None
    translation_key: str
    drivetrain: str | None
    state_icons: dict[str, str] | None

# Integration domain
DOMAIN: Final = "bmw_cardata"
ATTRIBUTION: Final = "Data provided by BMW CarData API"

# Configuration keys
CONF_CLIENT_ID: Final = "client_id"
CONF_VIN: Final = "vin"
CONF_TOKENS: Final = "tokens"
CONF_VEHICLE_INFO: Final = "vehicle_info"
CONF_MQTT_DEBUG: Final = "mqtt_debug"

# Token keys
TOKEN_ACCESS: Final = "access_token"
TOKEN_REFRESH: Final = "refresh_token"
TOKEN_ID: Final = "id_token"
TOKEN_GCID: Final = "gcid"
TOKEN_EXPIRES_AT: Final = "expires_at"
TOKEN_REFRESH_EXPIRES_AT: Final = "refresh_expires_at"
TOKEN_UPDATED_AT: Final = "updated_at"

# BMW API endpoints
API_BASE_URL: Final = "https://api-cardata.bmwgroup.com"
AUTH_BASE_URL: Final = "https://customer.bmwgroup.com"
DEVICE_CODE_ENDPOINT: Final = f"{AUTH_BASE_URL}/gcdm/oauth/device/code"
TOKEN_ENDPOINT: Final = f"{AUTH_BASE_URL}/gcdm/oauth/token"

# MQTT settings
MQTT_BROKER_HOST: Final = "customer.streaming-cardata.bmwgroup.com"
MQTT_BROKER_PORT: Final = 9000
MQTT_KEEPALIVE: Final = 60
MQTT_TOPIC_PATTERN: Final = "{gcid}/{vin}"

# OAuth settings
DEFAULT_SCOPES: Final = "authenticate_user openid cardata:streaming:read cardata:api:read"
TOKEN_REFRESH_BUFFER: Final = 300  # Refresh 5 minutes before expiry

# Events
EVENT_MQTT_DEBUG: Final = "bmw_cardata_mqtt_debug"

# Diagnostics
DIAG_MAX_MESSAGES: Final = 100
CONF_MQTT_BUFFER_SIZE: Final = "mqtt_buffer_size"

# Platforms
PLATFORMS: Final = ["sensor", "binary_sensor", "device_tracker"]

# Drivetrain types
DRIVETRAIN_CONV: Final = "CONV"  # Conventional combustion engine
DRIVETRAIN_PHEV: Final = "PHEV"  # Plug-in hybrid electric
DRIVETRAIN_BEV: Final = "BEV"    # Battery electric vehicle

# Location keys for device tracker
LOCATION_LATITUDE_KEY: Final = "vehicle.cabin.infotainment.navigation.currentLocation.latitude"
LOCATION_LONGITUDE_KEY: Final = "vehicle.cabin.infotainment.navigation.currentLocation.longitude"
LOCATION_ALTITUDE_KEY: Final = "vehicle.cabin.infotainment.navigation.currentLocation.altitude"

# Drivetrain filter values for entity definitions
# None = all drivetrains, "electric" = PHEV/BEV only, "combustion" = CONV/PHEV only
DRIVETRAIN_ELECTRIC: Final = "electric"
DRIVETRAIN_COMBUSTION: Final = "combustion"

# Known sensor keys with metadata
KNOWN_SENSORS: Final[dict[str, SensorDef]] = {
    "vehicle.vehicle.travelledDistance": SensorDef(
        name="Odometer",
        unit=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        icon="mdi:counter",
        drivetrain=None,
    ),
    "vehicle.drivetrain.lastRemainingRange": SensorDef(
        name="Total Range",
        unit=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        icon="mdi:gas-station",
        drivetrain=None,
    ),
    "vehicle.drivetrain.electricEngine.kombiRemainingElectricRange": SensorDef(
        name="Electric Range",
        unit=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        icon="mdi:battery-charging",
        drivetrain=DRIVETRAIN_ELECTRIC,
    ),
    "vehicle.chassis.axle.row1.wheel.left.tire.pressure": SensorDef(
        name="Front Left Tire Pressure",
        unit=UnitOfPressure.KPA,
        device_class=SensorDeviceClass.PRESSURE,
        icon="mdi:car-tire-alert",
        drivetrain=None,
    ),
    "vehicle.chassis.axle.row1.wheel.right.tire.pressure": SensorDef(
        name="Front Right Tire Pressure",
        unit=UnitOfPressure.KPA,
        device_class=SensorDeviceClass.PRESSURE,
        icon="mdi:car-tire-alert",
        drivetrain=None,
    ),
    "vehicle.chassis.axle.row2.wheel.left.tire.pressure": SensorDef(
        name="Rear Left Tire Pressure",
        unit=UnitOfPressure.KPA,
        device_class=SensorDeviceClass.PRESSURE,
        icon="mdi:car-tire-alert",
        drivetrain=None,
    ),
    "vehicle.chassis.axle.row2.wheel.right.tire.pressure": SensorDef(
        name="Rear Right Tire Pressure",
        unit=UnitOfPressure.KPA,
        device_class=SensorDeviceClass.PRESSURE,
        icon="mdi:car-tire-alert",
        drivetrain=None,
    ),
    "vehicle.drivetrain.batteryManagement.header": SensorDef(
        name="Battery",
        unit=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        icon="mdi:battery",
        drivetrain=DRIVETRAIN_ELECTRIC,
    ),
    "vehicle.drivetrain.fuelSystem.level": SensorDef(
        name="Fuel Level",
        unit=PERCENTAGE,
        device_class=None,
        icon="mdi:gas-station",
        drivetrain=DRIVETRAIN_COMBUSTION,
    ),
    "vehicle.drivetrain.electricEngine.charging.smeEnergyDeltaFullyCharged": SensorDef(
        name="Energy to Full Charge",
        unit=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        icon="mdi:battery-charging",
        drivetrain=DRIVETRAIN_ELECTRIC,
    ),
}

# Known binary sensor keys with metadata
KNOWN_BINARY_SENSORS: Final[dict[str, BinarySensorDef]] = {
    "vehicle.drivetrain.electricEngine.charging.profile.climatizationActive": BinarySensorDef(
        name="Charging Climatization",
        device_class=None,
        icon="mdi:air-conditioner",
        drivetrain=DRIVETRAIN_ELECTRIC,
    ),
    "vehicle.body.trunk.isOpen": BinarySensorDef(
        name="Trunk",
        device_class=BinarySensorDeviceClass.OPENING,
        icon="mdi:car-back",
        drivetrain=None,
    ),
    "vehicle.body.trunk.door.isOpen": BinarySensorDef(
        name="Trunk Door",
        device_class=BinarySensorDeviceClass.OPENING,
        icon="mdi:car-back",
        drivetrain=None,
    ),
    "vehicle.body.hood.isOpen": BinarySensorDef(
        name="Hood",
        device_class=BinarySensorDeviceClass.OPENING,
        icon="mdi:car",
        drivetrain=None,
    ),
    "vehicle.cabin.door.row1.driver.isOpen": BinarySensorDef(
        name="Driver Door",
        device_class=BinarySensorDeviceClass.DOOR,
        icon="mdi:car-door",
        drivetrain=None,
    ),
    "vehicle.cabin.door.row1.passenger.isOpen": BinarySensorDef(
        name="Front Passenger Door",
        device_class=BinarySensorDeviceClass.DOOR,
        icon="mdi:car-door",
        drivetrain=None,
    ),
    "vehicle.cabin.door.row2.driver.isOpen": BinarySensorDef(
        name="Rear Left Door",
        device_class=BinarySensorDeviceClass.DOOR,
        icon="mdi:car-door",
        drivetrain=None,
    ),
    "vehicle.cabin.door.row2.passenger.isOpen": BinarySensorDef(
        name="Rear Right Door",
        device_class=BinarySensorDeviceClass.DOOR,
        icon="mdi:car-door",
        drivetrain=None,
    ),
    "vehicle.body.chargingPort.status": BinarySensorDef(
        name="Charging Port",
        device_class=BinarySensorDeviceClass.PLUG,
        icon="mdi:ev-plug-type2",
        drivetrain=DRIVETRAIN_ELECTRIC,
    ),
}

# Known enum sensor keys with metadata
KNOWN_ENUM_SENSORS: Final[dict[str, EnumSensorDef]] = {
    "vehicle.drivetrain.electricEngine.charging.status": EnumSensorDef(
        name="Charging Status",
        options=[
            "nocharging",
            "initialization",
            "chargingactive",
            "chargingpaused",
            "chargingended",
            "chargingerror",
        ],
        icon="mdi:ev-station",
        translation_key="charging_status",
        drivetrain=DRIVETRAIN_ELECTRIC,
        state_icons={
            "nocharging": "mdi:power-plug-off",
            "initialization": "mdi:battery-clock",
            "chargingactive": "mdi:battery-charging",
            "chargingpaused": "mdi:battery-minus",
            "chargingended": "mdi:battery-check",
            "chargingerror": "mdi:battery-alert",
        },
    ),
    "vehicle.cabin.window.row1.driver.status": EnumSensorDef(
        name="Driver Window",
        options=["open", "intermediate", "closed"],
        icon="mdi:car-windshield",
        translation_key="window_status",
        drivetrain=None,
        state_icons=None,
    ),
    "vehicle.cabin.window.row1.passenger.status": EnumSensorDef(
        name="Front Passenger Window",
        options=["open", "intermediate", "closed"],
        icon="mdi:car-windshield",
        translation_key="window_status",
        drivetrain=None,
        state_icons=None,
    ),
    "vehicle.cabin.window.row2.driver.status": EnumSensorDef(
        name="Rear Left Window",
        options=["open", "intermediate", "closed"],
        icon="mdi:car-windshield",
        translation_key="window_status",
        drivetrain=None,
        state_icons=None,
    ),
    "vehicle.cabin.window.row2.passenger.status": EnumSensorDef(
        name="Rear Right Window",
        options=["open", "intermediate", "closed"],
        icon="mdi:car-windshield",
        translation_key="window_status",
        drivetrain=None,
        state_icons=None,
    ),
}

