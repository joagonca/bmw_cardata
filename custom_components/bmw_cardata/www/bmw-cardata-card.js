/**
 * BMW CarData Card for Home Assistant
 * 
 * A custom Lovelace card displaying BMW vehicle data with visual design.
 */

const LitElement = Object.getPrototypeOf(customElements.get("ha-panel-lovelace"));
const html = LitElement.prototype.html;
const css = LitElement.prototype.css;

// Card version
const CARD_VERSION = "1.0.0";

// Console info
console.info(
  `%c BMW-CARDATA-CARD %c ${CARD_VERSION} `,
  "color: white; background: #1c69d4; font-weight: bold;",
  "color: #1c69d4; background: white; font-weight: bold;"
);

// Default thresholds for tire pressure (kPa)
const DEFAULT_TIRE_THRESHOLDS = {
  low: 200,
  critical: 180,
};

// Default max values for progress bars
const DEFAULT_MAX_VALUES = {
  total_range: 600,
  electric_range: 80,
  fuel_level: 100,
  battery_soc: 100,
};

class BMWCarDataCard extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      config: { type: Object },
      _imageCache: { type: String, state: true },
    };
  }

  static get styles() {
    return css`
      :host {
        --card-primary-color: var(--primary-color);
        --card-background: var(--ha-card-background, var(--card-background-color, white));
        --card-text-primary: var(--primary-text-color);
        --card-text-secondary: var(--secondary-text-color);
        --tire-good: var(--success-color, #4caf50);
        --tire-warn: var(--warning-color, #ff9800);
        --tire-critical: var(--error-color, #f44336);
        --charging-color: var(--success-color, #4caf50);
      }

      ha-card {
        padding: 16px;
        box-sizing: border-box;
      }

      /* Header */
      .header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 16px;
      }

      .vehicle-name {
        font-size: 1.4em;
        font-weight: 500;
        color: var(--card-text-primary);
      }

      .status-icons {
        display: flex;
        gap: 12px;
        align-items: center;
      }

      .status-icon {
        display: flex;
        align-items: center;
        gap: 4px;
        font-size: 0.9em;
        color: var(--card-text-secondary);
      }

      .status-icon ha-icon {
        --mdc-icon-size: 20px;
      }

      .status-icon.locked ha-icon {
        color: var(--success-color, #4caf50);
      }

      .status-icon.unlocked ha-icon {
        color: var(--warning-color, #ff9800);
      }

      .status-icon.charging {
        color: var(--charging-color);
      }

      .status-icon.charging ha-icon {
        animation: pulse 1.5s ease-in-out infinite;
      }

      @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
      }

      /* Main content */
      .content {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 16px;
      }

      /* Left panel - images */
      .left-panel {
        display: flex;
        flex-direction: column;
        gap: 16px;
      }

      .vehicle-image-container {
        position: relative;
        width: 100%;
        aspect-ratio: 16/9;
        border-radius: 8px;
        overflow: hidden;
        background: var(--card-background);
        display: flex;
        align-items: center;
        justify-content: center;
      }

      .vehicle-image {
        max-width: 100%;
        max-height: 100%;
        object-fit: contain;
      }

      .vehicle-image-placeholder {
        color: var(--card-text-secondary);
        opacity: 0.5;
      }

      .vehicle-image-placeholder ha-icon {
        --mdc-icon-size: 64px;
      }

      /* Tire diagram */
      .tire-diagram {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 8px;
      }

      .tire-diagram-title {
        font-size: 0.9em;
        color: var(--card-text-secondary);
        font-weight: 500;
      }

      .tire-container {
        position: relative;
        width: 120px;
        height: 160px;
      }

      .car-outline {
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        width: 60px;
        height: 120px;
        border: 2px solid var(--card-text-secondary);
        border-radius: 20px 20px 15px 15px;
        opacity: 0.3;
      }

      .car-outline::before {
        content: "";
        position: absolute;
        top: 15px;
        left: 50%;
        transform: translateX(-50%);
        width: 30px;
        height: 20px;
        border: 2px solid var(--card-text-secondary);
        border-radius: 5px 5px 0 0;
        border-bottom: none;
      }

      .tire {
        position: absolute;
        display: flex;
        flex-direction: column;
        align-items: center;
        font-size: 0.75em;
        font-weight: 600;
        padding: 4px 6px;
        border-radius: 4px;
        background: var(--card-background);
        box-shadow: 0 1px 3px rgba(0,0,0,0.2);
        min-width: 36px;
        text-align: center;
      }

      .tire.good {
        color: var(--tire-good);
        border: 1px solid var(--tire-good);
      }

      .tire.warn {
        color: var(--tire-warn);
        border: 1px solid var(--tire-warn);
      }

      .tire.critical {
        color: var(--tire-critical);
        border: 1px solid var(--tire-critical);
      }

      .tire.unknown {
        color: var(--card-text-secondary);
        border: 1px solid var(--card-text-secondary);
      }

      .tire-label {
        font-size: 0.7em;
        opacity: 0.7;
      }

      .tire-fl { top: 5px; left: 0; }
      .tire-fr { top: 5px; right: 0; }
      .tire-rl { bottom: 5px; left: 0; }
      .tire-rr { bottom: 5px; right: 0; }

      /* Right panel - data */
      .right-panel {
        display: flex;
        flex-direction: column;
        gap: 12px;
      }

      .data-item {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }

      .data-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
      }

      .data-label {
        font-size: 0.85em;
        color: var(--card-text-secondary);
      }

      .data-value {
        font-size: 1.1em;
        font-weight: 500;
        color: var(--card-text-primary);
      }

      .data-unit {
        font-size: 0.8em;
        color: var(--card-text-secondary);
        margin-left: 2px;
      }

      .progress-bar {
        height: 6px;
        background: var(--divider-color, #e0e0e0);
        border-radius: 3px;
        overflow: hidden;
      }

      .progress-fill {
        height: 100%;
        border-radius: 3px;
        transition: width 0.5s ease;
      }

      .progress-fill.range {
        background: linear-gradient(90deg, var(--card-primary-color), var(--success-color, #4caf50));
      }

      .progress-fill.electric {
        background: linear-gradient(90deg, #2196f3, #4caf50);
      }

      .progress-fill.fuel {
        background: linear-gradient(90deg, #ff9800, #ffc107);
      }

      .progress-fill.battery {
        background: linear-gradient(90deg, #4caf50, #8bc34a);
      }

      .data-item.odometer .data-value {
        font-size: 1.3em;
      }

      /* Footer */
      .footer {
        margin-top: 16px;
        padding-top: 12px;
        border-top: 1px solid var(--divider-color, #e0e0e0);
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.8em;
        color: var(--card-text-secondary);
      }

      .door-status {
        display: flex;
        gap: 8px;
      }

      .door-indicator {
        display: flex;
        align-items: center;
        gap: 2px;
      }

      .door-indicator ha-icon {
        --mdc-icon-size: 16px;
      }

      .door-indicator.open ha-icon {
        color: var(--warning-color, #ff9800);
      }

      .door-indicator.closed ha-icon {
        color: var(--success-color, #4caf50);
      }

      /* Responsive */
      @media (max-width: 400px) {
        .content {
          grid-template-columns: 1fr;
        }

        .left-panel {
          flex-direction: row;
          justify-content: space-around;
        }

        .vehicle-image-container {
          width: 50%;
          aspect-ratio: 4/3;
        }
      }
    `;
  }

  constructor() {
    super();
    this._imageCache = null;
  }

  setConfig(config) {
    if (!config.entities && !config.entity_prefix) {
      throw new Error("Please define entities or entity_prefix");
    }

    this.config = {
      tire_thresholds: DEFAULT_TIRE_THRESHOLDS,
      max_values: DEFAULT_MAX_VALUES,
      show_fuel: true,
      show_charging: true,
      show_doors: true,
      ...config,
    };
  }

  getCardSize() {
    return 5;
  }

  static getConfigElement() {
    return document.createElement("bmw-cardata-card-editor");
  }

  static getStubConfig() {
    return {
      entity_prefix: "sensor.bmw",
      tire_thresholds: DEFAULT_TIRE_THRESHOLDS,
    };
  }

  // Get entity state by key
  _getEntityState(key) {
    const entities = this.config.entities || {};
    
    // Try explicit entity first
    if (entities[key]) {
      const state = this.hass.states[entities[key]];
      return state ? state.state : null;
    }

    // Try entity_prefix pattern
    if (this.config.entity_prefix) {
      const entityId = `${this.config.entity_prefix}_${key}`;
      const state = this.hass.states[entityId];
      return state ? state.state : null;
    }

    return null;
  }

  // Get numeric value
  _getNumericValue(key) {
    const state = this._getEntityState(key);
    if (state === null || state === "unknown" || state === "unavailable") {
      return null;
    }
    const num = parseFloat(state);
    return isNaN(num) ? null : num;
  }

  // Get boolean value
  _getBooleanValue(key) {
    const state = this._getEntityState(key);
    if (state === null || state === "unknown" || state === "unavailable") {
      return null;
    }
    return state === "on" || state === "true" || state === true;
  }

  // Get tire pressure class based on thresholds
  _getTireClass(pressure) {
    if (pressure === null) return "unknown";
    const { low, critical } = this.config.tire_thresholds;
    if (pressure < critical) return "critical";
    if (pressure < low) return "warn";
    return "good";
  }

  // Format tire pressure for display
  _formatTirePressure(kpa) {
    if (kpa === null) return "—";
    // Convert to bar (1 bar = 100 kPa)
    const bar = kpa / 100;
    return bar.toFixed(1);
  }

  // Format number with thousands separator
  _formatNumber(num) {
    if (num === null) return "—";
    return num.toLocaleString();
  }

  // Calculate progress percentage
  _getProgress(value, maxKey) {
    if (value === null) return 0;
    const max = this.config.max_values[maxKey] || 100;
    return Math.min(100, (value / max) * 100);
  }

  // Get relative time
  _getRelativeTime(timestamp) {
    if (!timestamp) return "Unknown";
    const now = new Date();
    const then = new Date(timestamp);
    const diff = Math.floor((now - then) / 1000);

    if (diff < 60) return "Just now";
    if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} hours ago`;
    return `${Math.floor(diff / 86400)} days ago`;
  }

  // Get vehicle name
  _getVehicleName() {
    if (this.config.name) return this.config.name;
    
    // Try to get from device info
    const prefix = this.config.entity_prefix || "";
    const parts = prefix.split("_");
    if (parts.length > 1) {
      return parts.slice(1).map(p => p.charAt(0).toUpperCase() + p.slice(1)).join(" ");
    }
    return "BMW Vehicle";
  }

  // Get vehicle image URL
  _getVehicleImageUrl() {
    if (this._imageCache) return this._imageCache;
    
    const entities = this.config.entities || {};
    if (entities.vehicle_image) {
      const entity = this.hass.states[entities.vehicle_image];
      if (entity && entity.attributes.entity_picture) {
        this._imageCache = entity.attributes.entity_picture;
        return this._imageCache;
      }
    }
    
    // Try camera entity pattern
    if (this.config.entity_prefix) {
      const cameraId = `camera.${this.config.entity_prefix.replace("sensor.", "")}_image`;
      const camera = this.hass.states[cameraId];
      if (camera && camera.attributes.entity_picture) {
        this._imageCache = camera.attributes.entity_picture;
        return this._imageCache;
      }
    }

    return null;
  }

  render() {
    if (!this.hass || !this.config) {
      return html``;
    }

    // Get values
    const odometer = this._getNumericValue("odometer");
    const totalRange = this._getNumericValue("total_range");
    const electricRange = this._getNumericValue("electric_range");
    const fuelLevel = this._getNumericValue("fuel_level");
    const batterySoc = this._getNumericValue("battery_soc");
    // Tire pressures
    const tireFL = this._getNumericValue("tire_pressure_fl");
    const tireFR = this._getNumericValue("tire_pressure_fr");
    const tireRL = this._getNumericValue("tire_pressure_rl");
    const tireRR = this._getNumericValue("tire_pressure_rr");

    const isLocked = this._getBooleanValue("trunk_lock");

    const vehicleImage = this._getVehicleImageUrl();

    return html`
      <ha-card>
        <!-- Header -->
        <div class="header">
          <div class="vehicle-name">${this._getVehicleName()}</div>
          <div class="status-icons">
            ${isLocked !== null ? html`
              <div class="status-icon ${isLocked ? 'locked' : 'unlocked'}">
                <ha-icon icon="${isLocked ? 'mdi:lock' : 'mdi:lock-open'}"></ha-icon>
                ${isLocked ? 'Locked' : 'Unlocked'}
              </div>
            ` : ''}
          </div>
        </div>

        <!-- Main content -->
        <div class="content">
          <!-- Left panel -->
          <div class="left-panel">
            <!-- Vehicle image -->
            <div class="vehicle-image-container">
              ${vehicleImage ? html`
                <img class="vehicle-image" src="${vehicleImage}" alt="Vehicle" />
              ` : html`
                <div class="vehicle-image-placeholder">
                  <ha-icon icon="mdi:car-side"></ha-icon>
                </div>
              `}
            </div>

            <!-- Tire diagram -->
            <div class="tire-diagram">
              <div class="tire-diagram-title">Tire Pressure (bar)</div>
              <div class="tire-container">
                <div class="car-outline"></div>
                <div class="tire tire-fl ${this._getTireClass(tireFL)}">
                  <span class="tire-label">FL</span>
                  ${this._formatTirePressure(tireFL)}
                </div>
                <div class="tire tire-fr ${this._getTireClass(tireFR)}">
                  <span class="tire-label">FR</span>
                  ${this._formatTirePressure(tireFR)}
                </div>
                <div class="tire tire-rl ${this._getTireClass(tireRL)}">
                  <span class="tire-label">RL</span>
                  ${this._formatTirePressure(tireRL)}
                </div>
                <div class="tire tire-rr ${this._getTireClass(tireRR)}">
                  <span class="tire-label">RR</span>
                  ${this._formatTirePressure(tireRR)}
                </div>
              </div>
            </div>
          </div>

          <!-- Right panel -->
          <div class="right-panel">
            <!-- Total Range -->
            ${totalRange !== null ? html`
              <div class="data-item">
                <div class="data-header">
                  <span class="data-label">Total Range</span>
                  <span class="data-value">${this._formatNumber(totalRange)}<span class="data-unit">km</span></span>
                </div>
                <div class="progress-bar">
                  <div class="progress-fill range" style="width: ${this._getProgress(totalRange, 'total_range')}%"></div>
                </div>
              </div>
            ` : ''}

            <!-- Electric Range -->
            ${electricRange !== null ? html`
              <div class="data-item">
                <div class="data-header">
                  <span class="data-label">Electric Range</span>
                  <span class="data-value">${this._formatNumber(electricRange)}<span class="data-unit">km</span></span>
                </div>
                <div class="progress-bar">
                  <div class="progress-fill electric" style="width: ${this._getProgress(electricRange, 'electric_range')}%"></div>
                </div>
              </div>
            ` : ''}

            <!-- Battery SoC -->
            ${batterySoc !== null && this.config.show_charging ? html`
              <div class="data-item">
                <div class="data-header">
                  <span class="data-label">Battery</span>
                  <span class="data-value">${batterySoc}<span class="data-unit">%</span></span>
                </div>
                <div class="progress-bar">
                  <div class="progress-fill battery" style="width: ${batterySoc}%"></div>
                </div>
              </div>
            ` : ''}

            <!-- Fuel Level -->
            ${fuelLevel !== null && this.config.show_fuel ? html`
              <div class="data-item">
                <div class="data-header">
                  <span class="data-label">Fuel Level</span>
                  <span class="data-value">${fuelLevel}<span class="data-unit">%</span></span>
                </div>
                <div class="progress-bar">
                  <div class="progress-fill fuel" style="width: ${fuelLevel}%"></div>
                </div>
              </div>
            ` : ''}

            <!-- Odometer -->
            ${odometer !== null ? html`
              <div class="data-item odometer">
                <div class="data-header">
                  <span class="data-label">Odometer</span>
                  <span class="data-value">${this._formatNumber(odometer)}<span class="data-unit">km</span></span>
                </div>
              </div>
            ` : ''}
          </div>
        </div>

        <!-- Footer -->
        <div class="footer">
          <div class="last-updated">
            Updated: ${this._getRelativeTime(this._getEntityState("last_updated"))}
          </div>
        </div>
      </ha-card>
    `;
  }
}

// Card Editor
class BMWCarDataCardEditor extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      config: { type: Object },
      _devices: { type: Array, state: true },
    };
  }

  constructor() {
    super();
    this._devices = [];
  }

  async connectedCallback() {
    super.connectedCallback();
    await this._loadDevices();
  }

  async _loadDevices() {
    if (!this.hass) return;
    
    try {
      // Fetch all devices
      const devices = await this.hass.callWS({
        type: "config/device_registry/list",
      });
      
      // Filter to BMW CarData devices
      this._devices = devices.filter(
        (device) => device.identifiers?.some(
          (id) => id[0] === "bmw_cardata"
        )
      );
    } catch (e) {
      console.error("Failed to load BMW CarData devices:", e);
      this._devices = [];
    }
  }

  _getDeviceEntityPrefix(device) {
    // Get entity prefix from device name (e.g., "BMW iX" -> "sensor.bmw_ix")
    const name = device.name_by_user || device.name || "";
    return "sensor." + name.toLowerCase().replace(/[^a-z0-9]+/g, "_");
  }

  static get styles() {
    return css`
      .form {
        display: flex;
        flex-direction: column;
        gap: 16px;
      }

      .row {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }

      label {
        font-weight: 500;
        font-size: 0.9em;
      }

      input, select {
        padding: 8px;
        border: 1px solid var(--divider-color);
        border-radius: 4px;
        font-size: 1em;
      }

      .checkbox-row {
        display: flex;
        align-items: center;
        gap: 8px;
      }

      .section-title {
        font-weight: 600;
        margin-top: 16px;
        padding-bottom: 8px;
        border-bottom: 1px solid var(--divider-color);
      }
    `;
  }

  setConfig(config) {
    this.config = config;
  }

  _deviceChanged(ev) {
    if (!this.config) return;

    const deviceId = ev.target.value;
    const device = this._devices.find((d) => d.id === deviceId);
    
    if (!device) return;

    const newConfig = { ...this.config };
    newConfig.device_id = deviceId;
    newConfig.entity_prefix = this._getDeviceEntityPrefix(device);
    if (!newConfig.name) {
      newConfig.name = device.name_by_user || device.name;
    }

    const event = new CustomEvent("config-changed", {
      detail: { config: newConfig },
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(event);
  }

  _valueChanged(ev) {
    if (!this.config) return;

    const target = ev.target;
    const newConfig = { ...this.config };

    if (target.type === "checkbox") {
      newConfig[target.name] = target.checked;
    } else if (target.name.startsWith("tire_thresholds.")) {
      const key = target.name.split(".")[1];
      newConfig.tire_thresholds = {
        ...newConfig.tire_thresholds,
        [key]: parseInt(target.value) || 0,
      };
    } else {
      newConfig[target.name] = target.value;
    }

    const event = new CustomEvent("config-changed", {
      detail: { config: newConfig },
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(event);
  }

  render() {
    if (!this.config) {
      return html``;
    }

    return html`
      <div class="form">
        <div class="row">
          <label>Vehicle</label>
          <select
            name="device"
            @change="${this._deviceChanged}"
          >
            <option value="">-- Select a vehicle --</option>
            ${this._devices.map((device) => html`
              <option 
                value="${device.id}"
                ?selected="${this.config.device_id === device.id}"
              >
                ${device.name_by_user || device.name}
              </option>
            `)}
          </select>
        </div>

        <div class="row">
          <label>Vehicle Name (optional override)</label>
          <input
            type="text"
            name="name"
            .value="${this.config.name || ''}"
            @input="${this._valueChanged}"
            placeholder="BMW 330e"
          />
        </div>

        <div class="row">
          <label>Entity Prefix</label>
          <input
            type="text"
            name="entity_prefix"
            .value="${this.config.entity_prefix || ''}"
            @input="${this._valueChanged}"
            placeholder="sensor.bmw_330e"
          />
        </div>

        <div class="section-title">Tire Pressure Thresholds (kPa)</div>

        <div class="row">
          <label>Low Warning</label>
          <input
            type="number"
            name="tire_thresholds.low"
            .value="${this.config.tire_thresholds?.low || 200}"
            @input="${this._valueChanged}"
          />
        </div>

        <div class="row">
          <label>Critical Warning</label>
          <input
            type="number"
            name="tire_thresholds.critical"
            .value="${this.config.tire_thresholds?.critical || 180}"
            @input="${this._valueChanged}"
          />
        </div>

        <div class="section-title">Display Options</div>

        <div class="checkbox-row">
          <input
            type="checkbox"
            name="show_fuel"
            id="show_fuel"
            .checked="${this.config.show_fuel !== false}"
            @change="${this._valueChanged}"
          />
          <label for="show_fuel">Show Fuel Level</label>
        </div>

        <div class="checkbox-row">
          <input
            type="checkbox"
            name="show_charging"
            id="show_charging"
            .checked="${this.config.show_charging !== false}"
            @change="${this._valueChanged}"
          />
          <label for="show_charging">Show Battery/Charging</label>
        </div>
      </div>
    `;
  }
}

// Register the card
customElements.define("bmw-cardata-card", BMWCarDataCard);
customElements.define("bmw-cardata-card-editor", BMWCarDataCardEditor);

// Register with Home Assistant
window.customCards = window.customCards || [];
window.customCards.push({
  type: "bmw-cardata-card",
  name: "BMW CarData Card",
  description: "A card to display BMW vehicle data with visual layout",
  preview: true,
  documentationURL: "https://github.com/your-repo/bmw_cardata",
});
