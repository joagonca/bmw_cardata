"""Binary sensor platform for BMW CarData integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CHARGING_PORT_KEYS,
    DRIVETRAIN_CONV,
    ELECTRIC_BINARY_SENSOR_KEYS,
    KNOWN_BINARY_SENSORS,
)
from .coordinator import BMWCarDataCoordinator
from .entity import BMWCarDataEntity


def _to_bool(value: object) -> bool | None:
    """Coerce a telemetry value to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "on", "yes", "1")
    if isinstance(value, (int, float)):
        return bool(value)
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BMW CarData binary sensors."""
    coordinator: BMWCarDataCoordinator = entry.runtime_data
    drive_train = coordinator.vehicle_info.get("drive_train")
    is_electric = drive_train != DRIVETRAIN_CONV

    # Create entities for all known binary sensors
    entities: list[BMWCarDataBinarySensor] = []

    for key, (name, device_class, icon) in KNOWN_BINARY_SENSORS.items():
        # Skip electric-only sensors for conventional vehicles
        if not is_electric and key in ELECTRIC_BINARY_SENSOR_KEYS:
            continue

        entities.append(
            BMWCarDataBinarySensor(
                coordinator=coordinator,
                key=key,
                name=name,
                device_class=device_class,
                icon=icon,
            )
        )

    # Add composite charging port sensor for electric vehicles
    if is_electric:
        entities.append(BMWChargingPortBinarySensor(coordinator=coordinator))

    async_add_entities(entities)


class BMWChargingPortBinarySensor(BMWCarDataEntity, BinarySensorEntity):
    """Composite binary sensor that aggregates multiple charging port keys.

    ON when any port reports plugged; per-port state exposed as attributes.
    """

    # Use the first port key as the "primary" key for the base entity plumbing
    _PRIMARY_KEY = next(iter(CHARGING_PORT_KEYS))

    def __init__(self, coordinator: BMWCarDataCoordinator) -> None:
        """Initialize the charging port binary sensor."""
        super().__init__(coordinator, self._PRIMARY_KEY, "Charging Port")
        # Override unique_id to be stable and independent of primary key choice
        self._attr_unique_id = f"{coordinator.vin}_charging_port"
        self._attr_device_class = "plug"
        self._attr_icon = "mdi:ev-plug-type2"
        self._port_values: dict[str, bool | None] = {
            port: None for port in CHARGING_PORT_KEYS.values()
        }

    def _restore_native_value(self, state: str) -> None:
        """Restore the native value from state string."""
        self._last_value = state.lower() == "on"

    def _process_coordinator_data(self) -> None:
        """Read all four port keys and derive the aggregate value."""
        updated = False
        latest_ts: str | None = self._last_timestamp

        for key, port_name in CHARGING_PORT_KEYS.items():
            data = self.coordinator.data.get(key)
            if data is None:
                continue

            if isinstance(data, dict) and "value" in data:
                raw = data["value"]
                ts = data.get("timestamp")
            else:
                raw = data
                ts = None

            self._port_values[port_name] = _to_bool(raw)
            updated = True

            if ts and (latest_ts is None or ts > latest_ts):
                latest_ts = ts

        if updated:
            self._has_received_data = True
            self._last_timestamp = latest_ts
            # ON if any port is plugged
            known = [v for v in self._port_values.values() if v is not None]
            self._last_value = any(known) if known else None

    @property
    def is_on(self) -> bool | None:
        """Return true if any charging port is plugged."""
        if self._last_value is None:
            return None
        return bool(self._last_value)

    @property
    def extra_state_attributes(self) -> dict[str, str | bool | None]:
        """Return per-port plugged state alongside default attributes."""
        attrs = super().extra_state_attributes
        for port_name, plugged in self._port_values.items():
            attrs[f"{port_name}_plugged"] = plugged
        return attrs


class BMWCarDataBinarySensor(BMWCarDataEntity, BinarySensorEntity):
    """Representation of a BMW CarData binary sensor."""

    def __init__(
        self,
        coordinator: BMWCarDataCoordinator,
        key: str,
        name: str,
        device_class: str | None,
        icon: str | None,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, key, name)

        # Set device class
        if device_class:
            self._attr_device_class = device_class

        # Set icon
        if icon:
            self._attr_icon = icon

    def _restore_native_value(self, state: str) -> None:
        """Restore the native value from state string."""
        self._last_value = state.lower() == "on"

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        value = self._last_value
        if value is None:
            return None

        # Handle various boolean representations
        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            return value.lower() in ("true", "on", "yes", "1")

        if isinstance(value, (int, float)):
            return bool(value)

        return None


