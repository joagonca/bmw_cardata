# BMW CarData Card

A custom Lovelace card for Home Assistant that displays BMW vehicle data with a visual design.

## Features

- **Vehicle profile image** - Cached for performance
- **Top-down tire diagram** - Shows all 4 tire pressures with color-coded status
- **Range/fuel/battery bars** - Visual progress indicators
- **Lock & charging status** - Header indicators with animated charging icon
- **Theme-adaptive** - Respects your Home Assistant theme
- **Responsive** - Adapts to different card sizes
- **Card editor** - Configure via UI

## Installation

### Manual Installation

1. Copy the `bmw-cardata-card` folder to your Home Assistant `config/www/` directory
2. Add the resource in Home Assistant:
   - Go to **Settings → Dashboards → Resources**
   - Add resource: `/local/bmw-cardata-card/bmw-cardata-card.js`
   - Type: JavaScript Module

### HACS Installation

*Coming soon*

## Configuration

### Basic Configuration

```yaml
type: custom:bmw-cardata-card
entity_prefix: sensor.bmw_330e
```

### Full Configuration

```yaml
type: custom:bmw-cardata-card
name: My BMW 330e
entity_prefix: sensor.bmw_330e
tire_thresholds:
  low: 200      # kPa - yellow warning
  critical: 180 # kPa - red warning
max_values:
  total_range: 600
  electric_range: 80
  fuel_level: 100
  battery_soc: 100
show_fuel: true
show_charging: true
```

### Explicit Entity Configuration

If your entities don't follow the prefix pattern, you can specify each entity:

```yaml
type: custom:bmw-cardata-card
name: My BMW
entities:
  vehicle_image: camera.bmw_image
  odometer: sensor.bmw_odometer
  total_range: sensor.bmw_total_range
  electric_range: sensor.bmw_electric_range
  fuel_level: sensor.bmw_fuel_level
  battery_soc: sensor.bmw_battery_soc
  charging_power: sensor.bmw_charging_power
  lock_status: binary_sensor.bmw_locked
  tire_pressure_fl: sensor.bmw_tire_pressure_fl
  tire_pressure_fr: sensor.bmw_tire_pressure_fr
  tire_pressure_rl: sensor.bmw_tire_pressure_rl
  tire_pressure_rr: sensor.bmw_tire_pressure_rr
```

## Entity Naming Convention

When using `entity_prefix`, the card expects entities named as:

| Data | Expected Entity |
|------|-----------------|
| Odometer | `{prefix}_odometer` |
| Total Range | `{prefix}_total_range` |
| Electric Range | `{prefix}_electric_range` |
| Fuel Level | `{prefix}_fuel_level` |
| Battery SoC | `{prefix}_battery_soc` |
| Charging Power | `{prefix}_charging_power` |
| Lock Status | `{prefix}_lock_status` |
| Front Left Tire | `{prefix}_tire_pressure_fl` |
| Front Right Tire | `{prefix}_tire_pressure_fr` |
| Rear Left Tire | `{prefix}_tire_pressure_rl` |
| Rear Right Tire | `{prefix}_tire_pressure_rr` |
| Vehicle Image | `camera.{prefix}_image` |

## Tire Pressure Color Coding

| Status | Condition | Color |
|--------|-----------|-------|
| Good | ≥ low threshold | Green |
| Warning | < low threshold | Yellow |
| Critical | < critical threshold | Red |
| Unknown | No data | Gray |

Default thresholds: Low = 200 kPa (2.0 bar), Critical = 180 kPa (1.8 bar)

## Screenshots

*Coming soon*

## Troubleshooting

### Card not appearing
- Check browser console for errors
- Verify the resource is added correctly
- Clear browser cache and reload

### Missing data
- Verify entity names match the expected pattern
- Check that entities exist in Developer Tools → States

### Tire pressures showing wrong values
- Tire pressures are expected in kPa
- The card converts to bar for display (kPa / 100)
