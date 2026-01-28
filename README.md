# BMW CarData Home Assistant Integration

A Home Assistant custom integration for the BMW CarData API, providing real-time vehicle telematics data from BMW Group vehicles (BMW, MINI, Rolls-Royce, Toyota Supra).

## Features

- **Real-time streaming** via MQTT (bypasses the 50 requests/day REST API limit)
- **OAuth 2.0 Device Code Flow** with PKCE for secure authentication
- **Automatic token refresh** - tokens are managed and refreshed automatically
- **Fixed + dynamic entity discovery** - known sensors created at setup, new keys discovered automatically

## Supported Entities

### Sensors

| Entity | Description | Unit |
|--------|-------------|------|
| Odometer | Total distance travelled | km |
| Total Range | Combined remaining range (fuel + electric) | km |
| Electric Range | Remaining electric-only range | km |
| Target Electric Range | Target range based on charge settings | km |
| Front Left Tire Pressure | Tire pressure | kPa |
| Front Right Tire Pressure | Tire pressure | kPa |
| Rear Left Tire Pressure | Tire pressure | kPa |
| Rear Right Tire Pressure | Tire pressure | kPa |

### Binary Sensors

| Entity | Description |
|--------|-------------|
| Charging Climatization | Whether cabin pre-conditioning is active during charging |
| Charging Profile Complete | Whether Remote Charging Profile configuration is complete |

> **Note**: Additional entities are created dynamically when new telemetry keys are discovered via MQTT streaming.

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

Each integration instance supports a single VIN. To monitor multiple vehicles, add the integration multiple times.

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

## Development

### File Structure

```
custom_components/bmw_cardata/
├── __init__.py          # Integration setup
├── manifest.json        # Integration metadata
├── config_flow.py       # Configuration UI flow
├── const.py             # Constants and entity definitions
├── coordinator.py       # Data coordinator with MQTT
├── entity.py            # Base entity class
├── sensor.py            # Sensor entities
├── binary_sensor.py     # Binary sensor entities
├── strings.json         # UI strings
└── translations/
    └── en.json          # English translations
```

### Adding New Entities

When new telemetry keys are discovered, they are:
1. Logged at INFO level with the key name and value
2. Automatically created as dynamic entities

To add them as fixed entities, update `KNOWN_SENSORS` or `KNOWN_BINARY_SENSORS` in `const.py`.

## License

This project is provided as-is for personal use with the BMW CarData API.

## Acknowledgments

- BMW CarData API documentation
- Home Assistant custom component development guidelines
