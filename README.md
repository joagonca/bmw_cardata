# BMW CarData Home Assistant Integration

A Home Assistant custom integration for the BMW CarData API, providing real-time vehicle telematics data from BMW Group vehicles (BMW, MINI, Rolls-Royce, Toyota Supra).

## Features

- **Real-time streaming** via MQTT (bypasses the 50 requests/day REST API limit)
- **OAuth 2.0 Device Code Flow** with PKCE for secure authentication
- **Automatic token refresh** - tokens are managed and refreshed automatically
- **Multi-vehicle support** - add multiple vehicles from the same BMW account with shared authentication
- **Location tracking** - device tracker entity for zone-based automations (enter/leave events)
- **State persistence** - entity values are preserved across Home Assistant restarts

## Supported Entities

### Device Tracker

The integration creates a device tracker entity for each vehicle, enabling:
- Vehicle location on the Home Assistant map
- Zone-based automations (e.g., notify when car arrives home)
- Location history tracking

**Example automation:**
```yaml
automation:
  - alias: "Car arrived home"
    trigger:
      - platform: zone
        entity_id: device_tracker.bmw_location
        zone: zone.home
        event: enter
    action:
      - service: notify.mobile_app
        data:
          message: "Your BMW has arrived home"
```

### Sensors

| Entity | Description | Unit | Electric Only |
|--------|-------------|------|---------------|
| Battery | Calculated battery percentage (Electric Range / Target Electric Range) | % | ✓ |
| Odometer | Total distance travelled | km | |
| Total Range | Combined remaining range (fuel + electric) | km | |
| Electric Range | Remaining electric-only range | km | ✓ |
| Target Electric Range | Target range based on charge settings | km | ✓ |
| Front Left Tire Pressure | Tire pressure | kPa | |
| Front Right Tire Pressure | Tire pressure | kPa | |
| Rear Left Tire Pressure | Tire pressure | kPa | |
| Rear Right Tire Pressure | Tire pressure | kPa | |

### Binary Sensors

| Entity | Description | Electric Only |
|--------|-------------|---------------|
| Charging Climatization | Cabin pre-conditioning active during charging | ✓ |
| Charging Profile Complete | Remote Charging Profile configuration complete | ✓ |
| Trunk | Trunk open/closed | |
| Hood | Hood open/closed | |
| Charging Port | Charging port connected | ✓ |
| Driver Door | Driver door open/closed | |
| Front Passenger Door | Front passenger door open/closed | |
| Rear Left Door | Rear left door open/closed | |
| Rear Right Door | Rear right door open/closed | |

> **Note**: Entities marked "Electric Only" are only created for PHEV and BEV vehicles. Conventional (CONV) vehicles will not have these entities. All entities include a `last_changed` attribute showing when the value was last updated by the vehicle.

## Prerequisites

1. **BMW ConnectedDrive account** with a mapped vehicle
2. **BMW CarData Portal access** - Register at [bmw-cardata.bmwgroup.com](https://bmw-cardata.bmwgroup.com)
3. **Client ID** - Obtain from the BMW CarData Portal after registration
4. **VIN Authorization** - Each vehicle must be individually authorized in the CarData Portal

## Installation

### Manual Installation

1. Copy the `custom_components/bmw_cardata` directory to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant
3. Go to **Settings → Devices & Services → Add Integration**
4. Search for "BMW CarData"

### HACS Installation

*Coming soon*

## Configuration

The integration is configured via the UI:

1. **Enter Client ID** - From your BMW CarData Portal
2. **Authorize with BMW** - Visit the displayed URL and enter the code shown
3. **Select Vehicle** - Choose from your PRIMARY vehicles

### Multi-Vehicle Setup

Each integration instance supports a single VIN. To monitor multiple vehicles:

1. Add the integration for your first vehicle
2. Add the integration again for each additional vehicle
3. Use the same Client ID - authentication tokens are shared automatically
4. Select a different VIN each time

The integration handles token sharing and MQTT connection management automatically, ensuring all vehicles receive updates efficiently through a single connection per account.

## How It Works

### Authentication

The integration uses OAuth 2.0 Device Code Flow with PKCE:

1. You enter your Client ID from the BMW CarData Portal
2. A verification URL and code are displayed
3. You visit the URL on any device and enter the code
4. The integration polls for authorization completion
5. Tokens are securely stored in Home Assistant's config entry

### Data Updates

- **Initial load**: REST API call to fetch basic vehicle data
- **Real-time updates**: MQTT streaming connection for telemetry data
- **Token refresh**: Automatic refresh before expiry (access token: 1hr, refresh token: 2 weeks)
- **State persistence**: Entity values are restored after Home Assistant restarts

### Rate Limits

- REST API: 50 requests/day (only used for initial setup and basic data)
- MQTT Streaming: Unlimited real-time updates

## Troubleshooting

### No data appearing

- Ensure the VIN is authorized in the BMW CarData Portal (not just in ConnectedDrive)
- Check Home Assistant logs for connection errors
- Data arrives on vehicle events (ignition, trips, charging) - may take time for first update

### Authentication errors

- Verify your Client ID is correct
- Check that your BMW CarData subscription is active
- Try re-authenticating by removing and re-adding the integration

### "No PRIMARY vehicles found"

- You must be the PRIMARY user of the vehicle in BMW ConnectedDrive
- SECONDARY users cannot access CarData API

### Entity shows "Unavailable"

- This occurs when MQTT is disconnected and no previous data exists
- Once data is received, entities retain their last known value even if MQTT temporarily disconnects
- After a restart, previous values are restored automatically

## Development

### File Structure

```
custom_components/bmw_cardata/
├── __init__.py          # Integration setup
├── manifest.json        # Integration metadata
├── config_flow.py       # Configuration UI flow
├── const.py             # Constants and entity definitions
├── coordinator.py       # Data coordinator with MQTT and token management
├── entity.py            # Base entity class with state restoration
├── sensor.py            # Sensor entities
├── binary_sensor.py     # Binary sensor entities
├── device_tracker.py    # Location tracking entity
├── strings.json         # UI strings
└── translations/
    └── en.json          # English translations
```

### Adding New Entities

To add new entities, update `KNOWN_SENSORS` or `KNOWN_BINARY_SENSORS` in `const.py`.

## Required Streaming Keys

When configuring your container in the BMW CarData Portal, add these technical descriptors to receive data for the built-in entities.

### All Vehicles

```
vehicle.vehicle.travelledDistance
vehicle.drivetrain.lastRemainingRange
vehicle.chassis.axle.row1.wheel.left.tire.pressure
vehicle.chassis.axle.row1.wheel.right.tire.pressure
vehicle.chassis.axle.row2.wheel.left.tire.pressure
vehicle.chassis.axle.row2.wheel.right.tire.pressure
vehicle.body.trunk.isOpen
vehicle.body.hood.isOpen
vehicle.cabin.door.row1.driver.isOpen
vehicle.cabin.door.row1.passenger.isOpen
vehicle.cabin.door.row2.driver.isOpen
vehicle.cabin.door.row2.passenger.isOpen
vehicle.cabin.infotainment.navigation.currentLocation.latitude
vehicle.cabin.infotainment.navigation.currentLocation.longitude
vehicle.cabin.infotainment.navigation.currentLocation.altitude
```

### Electric Vehicles Only (PHEV/BEV)

```
vehicle.drivetrain.electricEngine.kombiRemainingElectricRange
vehicle.powertrain.electric.range.target
vehicle.drivetrain.electricEngine.charging.profile.climatizationActive
vehicle.drivetrain.electricEngine.charging.profile.isRcpConfigComplete
vehicle.body.chargingPort.status
```

> **Tip**: You can add additional keys from BMW's Telematics Data Catalogue by updating `const.py`.

## License

MIT License - see [LICENSE](LICENSE) for details.
