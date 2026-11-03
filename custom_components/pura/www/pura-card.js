/**
 * Pura Card — a Lovelace card for Pura smart fragrance diffusers.
 *
 * Bundled with the Pura integration (https://github.com/natekspencer/ha-pura),
 * which serves and registers this file automatically. Point it at a Pura device
 * and it discovers that device's entities (fragrance slots, intensity, timer,
 * nightlight, away mode, ...) automatically via the entity registry.
 *
 * Originally created by sabourinj (https://github.com/sabourinj/ha-pura-card).
 *
 * MIT License
 *
 * Copyright (c) 2026 sabourinj
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */

const CARD_VERSION = "0.2.0";

const INTENSITY_LEVELS = ["subtle", "light", "medium", "pronounced", "strong"];
// Mirrors INTENSITY_MAP in the integration's select.py; used for pura.start_timer.
const INTENSITY_VALUE = { subtle: 1, light: 3, medium: 5, pronounced: 7, strong: 10 };
const CONTROLLER_LABEL = {
  default: "Manual",
  schedule: "Schedule",
  timer: "Timer",
  away: "Away",
};
const DEFAULT_TIMER_DURATIONS = [30, 60, 120];

const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
  );

const isUnavailable = (stateObj) =>
  !stateObj || stateObj.state === "unavailable" || stateObj.state === "unknown";

// Stable, pleasant hue per fragrance name so each scent gets its own tint.
const fragranceHue = (name) => {
  let hash = 0;
  for (const ch of String(name || "")) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return hash % 360;
};

/**
 * Pura's fragrance color as a tint that stays visible on the card: keep its hue and
 * saturation, but clamp the lightness so near-black (or near-white) fragrances still
 * contrast with a dark (or light) theme. Returns undefined for anything but #RRGGBB.
 */
const fragranceTint = (hex, darkMode) => {
  const match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex || "");
  if (!match) return undefined;
  const [r, g, b] = match.slice(1).map((c) => parseInt(c, 16) / 255);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  const d = max - min;
  let h = 0;
  if (d) {
    if (max === r) h = ((g - b) / d) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
  }
  const sat = d ? d / (1 - Math.abs(2 * l - 1)) : 0;
  const [lo, hi] = darkMode ? [0.55, 0.85] : [0.3, 0.6];
  const light = Math.min(hi, Math.max(lo, l));
  return `hsl(${Math.round((h * 60 + 360) % 360)} ${Math.round(sat * 100)}% ${Math.round(light * 100)}%)`;
};

const slotFromEntity = (entityId, stateObj) => {
  const match =
    entityId.match(/slot_(\d)/) ||
    String(stateObj?.attributes?.friendly_name || "").match(/slot\s*(\d)/i);
  return match ? Number(match[1]) : undefined;
};

const formatDuration = (minutes) => {
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h}h ${m}m` : `${h}h`;
};

const formatRemaining = (ms) => {
  const totalMin = Math.max(0, Math.ceil(ms / 60000));
  if (totalMin < 60) return `${totalMin} min`;
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
};

/** Find a Pura device's entities using registry translation keys and names. */
function discoverEntities(hass, deviceId, overrides = {}) {
  const found = { bays: {} };
  const entries = Object.values(hass.entities || {}).filter(
    (e) => e.device_id === deviceId && (!e.platform || e.platform === "pura")
  );

  const bay = (slot) => (found.bays[slot] ||= { slot });
  // Two-slot sensors without a recognisable slot are skipped rather than guessed;
  // they can still be set explicitly via `entities` overrides.
  const assignSlot = (id, stateObj, field) => {
    const slot = slotFromEntity(id, stateObj);
    if (slot) bay(slot)[field] = id;
  };

  for (const entry of entries) {
    const id = entry.entity_id;
    const domain = id.split(".")[0];
    const key = entry.translation_key;
    const stateObj = hass.states[id];

    if (domain === "select" && key === "fragrance") found.fragrance = id;
    else if (domain === "select" && key === "intensity") found.intensity = id;
    else if (domain === "sensor" && key === "active_fragrance") found.active_fragrance = id;
    else if (domain === "sensor" && key === "controller") found.controller = id;
    else if (domain === "sensor" && key === "timer") found.timer = id;
    else if (domain === "sensor" && key === "battery") found.battery = id;
    else if (domain === "sensor" && key === "intensity") found.fan_intensity = id; // Pura Car
    else if (domain === "sensor" && key === "bay_fragrance") assignSlot(id, stateObj, "name");
    else if (domain === "sensor" && key === "bay_fragrance_remaining")
      assignSlot(id, stateObj, "remaining");
    else if (domain === "sensor" && key === "bay_runtime") assignSlot(id, stateObj, "runtime");
    // Single-slot devices (Mini, Car)
    else if (domain === "sensor" && key === "fragrance") bay(1).name = id;
    else if (domain === "sensor" && key === "fragrance_remaining") bay(1).remaining = id;
    else if (domain === "sensor" && key === "runtime") bay(1).runtime = id;
    else if (domain === "switch" && key === "diffusion_mode") found.auto_alternate = id;
    else if (domain === "switch" && key === "away_mode") found.away_mode = id;
    else if (domain === "switch" && key === "ambient_mode") found.ambient_mode = id;
    else if (domain === "light") found.nightlight = id;
    else if (domain === "binary_sensor" && key === "connected") found.connected = id;
    else if (domain === "binary_sensor" && (key === "low_fragrance" || key === "bay_low_fragrance"))
      found.low_fragrance = id;
  }

  // Explicit overrides from YAML win over discovery.
  for (const [key, value] of Object.entries(overrides || {})) {
    const slotMatch = key.match(/^slot_(\d)_(name|remaining|runtime)$/);
    if (slotMatch) bay(Number(slotMatch[1]))[slotMatch[2]] = value;
    else found[key] = value;
  }
  return found;
}

class PuraCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("pura-card-editor");
  }

  static getStubConfig(hass) {
    const entry = Object.values(hass.entities || {}).find(
      (e) => e.platform === "pura" && e.device_id
    );
    return { device_id: entry?.device_id || "" };
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._renderKey = "";
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
  }

  setConfig(config) {
    if (!config) throw new Error("Invalid configuration");
    this._config = {
      show_intensity: true,
      show_timer: true,
      show_nightlight: true,
      show_settings: true,
      timer_durations: DEFAULT_TIMER_DURATIONS,
      ...config,
    };
    this._renderKey = "";
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  connectedCallback() {
    // Refresh the timer countdown even when no state changes arrive, but only while
    // a timer is counting down (plus one tick after it ends to show the presets again).
    this._tick = setInterval(() => {
      const timer = this._hass && this._entities ? this._state(this._entities.timer) : undefined;
      const active = timer ? Date.parse(timer.state) > Date.now() : false;
      if (!active && !this._timerWasActive) return;
      this._timerWasActive = active;
      this._renderKey = "";
      this._render();
    }, 30000);
  }

  disconnectedCallback() {
    clearInterval(this._tick);
  }

  getCardSize() {
    return 5;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  // ---------------------------------------------------------------- helpers

  _state(entityId) {
    return entityId ? this._hass.states[entityId] : undefined;
  }

  _call(domain, service, data) {
    return this._hass.callService(domain, service, data).catch((err) => {
      this.dispatchEvent(
        new CustomEvent("hass-notification", {
          detail: { message: err?.message || String(err) },
          bubbles: true,
          composed: true,
        })
      );
    });
  }

  /** Open the device's page in Settings (admin only, like Home Assistant's own UI). */
  _openDevice() {
    if (!this._hass.user?.is_admin || !this._config.device_id) return;
    history.pushState(null, "", `/config/devices/device/${encodeURIComponent(this._config.device_id)}`);
    window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
  }

  _moreInfo(entityId) {
    if (!entityId) return;
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        detail: { entityId },
        bubbles: true,
        composed: true,
      })
    );
  }

  _formatState(stateObj) {
    if (!stateObj) return "";
    return this._hass.formatEntityState
      ? this._hass.formatEntityState(stateObj)
      : `${stateObj.state} ${stateObj.attributes.unit_of_measurement || ""}`.trim();
  }

  // ---------------------------------------------------------------- actions

  _onClick(ev) {
    const target = ev.target.closest("[data-action]");
    if (!target || target.hasAttribute("disabled")) return;
    const { action, value } = target.dataset;
    const e = this._entities;

    switch (action) {
      case "bay": {
        const option = `slot_${value}`;
        if (!e.fragrance) return this._moreInfo(e.bays[value]?.name);
        this._call("select", "select_option", {
          entity_id: e.fragrance,
          option: this._activeOption() === option ? "off" : option,
        });
        break;
      }
      case "power": {
        const option = this._activeOption() ? "off" : this._bestSlotOption();
        if (option) this._call("select", "select_option", { entity_id: e.fragrance, option });
        break;
      }
      case "intensity":
        this._call("select", "select_option", { entity_id: e.intensity, option: value });
        break;
      case "timer":
        this._startTimer(Number(value));
        break;
      case "toggle":
        this._call("homeassistant", "toggle", { entity_id: value });
        break;
      case "device":
        this._openDevice();
        break;
      case "more-info":
        this._moreInfo(value);
        break;
    }
  }

  /**
   * The slot that is actually diffusing, as "slot_N", or undefined when idle.
   *
   * The integration's Fragrance select reports the slot a timer was *started*
   * with, so it goes stale when auto-alternate switches slots mid-timer. The
   * Active fragrance sensor follows the live slot, so match its name to a slot
   * and only fall back to the select when the name is missing or ambiguous.
   */
  _activeOption() {
    const e = this._entities;
    const selected = this._state(e.fragrance)?.state;
    const selectedSlot = selected && selected.startsWith("slot_") ? selected : undefined;
    const activeName = this._state(e.active_fragrance)?.state;
    if (!e.active_fragrance || !activeName || isUnavailable(this._state(e.active_fragrance)))
      return selectedSlot;
    if (activeName === "none") return undefined;

    const matches = Object.values(e.bays)
      .filter((bay) => this._state(bay.name)?.state === activeName)
      .map((bay) => `slot_${bay.slot}`);
    if (matches.length === 1) return matches[0];
    if (matches.includes(selectedSlot)) return selectedSlot;
    return matches[0] || selectedSlot;
  }

  /** The installed slot with the most fragrance left (matches the integration's timer logic). */
  _bestSlotOption() {
    const options = (this._state(this._entities.fragrance)?.attributes.options || []).filter(
      (o) => o !== "off"
    );
    if (!options.length) return undefined;
    const remaining = (option) =>
      Number(this._state(this._entities.bays[option.replace("slot_", "")]?.remaining)?.state) || 0;
    return options.sort((a, b) => remaining(b) - remaining(a))[0];
  }

  _startTimer(minutes) {
    const e = this._entities;
    const current = this._activeOption();
    const intensity =
      INTENSITY_VALUE[this._state(e.intensity)?.state] ?? this._config.timer_intensity ?? 5;
    const data = {
      device_id: this._config.device_id,
      intensity,
      duration: { hours: Math.floor(minutes / 60), minutes: minutes % 60, seconds: 0 },
    };
    if (current) data.slot = current.replace("slot_", "");
    this._call("pura", "start_timer", data);
  }

  // ---------------------------------------------------------------- render

  _render() {
    if (!this._hass || !this._config) return;
    const config = this._config;

    if (!config.device_id) {
      this._paint("no-device", this._renderMessage("Select a Pura device in the card editor."));
      return;
    }

    const e = (this._entities = discoverEntities(this._hass, config.device_id, config.entities));
    const ids = [
      e.fragrance, e.intensity, e.active_fragrance, e.controller, e.timer, e.battery,
      e.fan_intensity, e.auto_alternate, e.away_mode, e.ambient_mode, e.nightlight,
      e.connected, e.low_fragrance,
      ...Object.values(e.bays).flatMap((b) => [b.name, b.remaining, b.runtime]),
    ].filter(Boolean);

    const device = this._hass.devices?.[config.device_id];
    const key = JSON.stringify([
      config,
      !!this._hass.themes?.darkMode,
      !!this._hass.user?.is_admin,
      [device?.name_by_user, device?.name, device?.area_id ? this._hass.areas?.[device.area_id]?.name : null],
      e, // which entity fills each role, so swapping one for another rerenders
      ids.map((id) => {
        const s = this._hass.states[id];
        return s && [
          s.state, s.attributes.rgb_color, s.attributes.options, s.attributes.friendly_name,
          s.attributes.entity_picture, s.attributes.color,
        ];
      }),
    ]);
    if (key === this._renderKey) return;

    if (!ids.length) {
      this._paint(key, this._renderMessage("No Pura entities found for this device."));
      return;
    }
    this._paint(key, this._renderCard());
  }

  _paint(key, html) {
    this._renderKey = key;
    this.shadowRoot.innerHTML = `<style>${STYLES}</style>${html}`;
    // Fall back to the drawn vial if a fragrance image can't be loaded.
    for (const img of this.shadowRoot.querySelectorAll(".vial-img")) {
      img.addEventListener("error", () => img.closest(".bay")?.classList.remove("has-img"), {
        once: true,
      });
    }
  }

  _renderMessage(text) {
    return `<ha-card><div class="message"><ha-icon icon="mdi:scent"></ha-icon>${esc(text)}</div></ha-card>`;
  }

  _renderCard() {
    const hass = this._hass;
    const config = this._config;
    const e = this._entities;
    const device = hass.devices?.[config.device_id];
    const area = device?.area_id ? hass.areas?.[device.area_id]?.name : undefined;
    const title = config.name || device?.name_by_user || device?.name || "Pura";

    const fragranceState = this._state(e.fragrance);
    const activeOption = this._activeOption();
    const running = !!activeOption;
    const controller = this._state(e.controller)?.state;
    const away = controller === "away" || this._state(e.away_mode)?.state === "on";
    const offline = this._state(e.connected)?.state === "off";
    const locked = away || offline || isUnavailable(fragranceState);

    // Mini/Car have no Active fragrance sensor, so fall back to the active slot's fragrance.
    const activeFragranceState = this._state(e.active_fragrance);
    const activeBayState = running ? this._state(e.bays[activeOption.replace("slot_", "")]?.name) : undefined;
    const activeName = !isUnavailable(activeFragranceState)
      ? activeFragranceState.state
      : !isUnavailable(activeBayState)
        ? activeBayState.state
        : "";
    const subtitle = [
      area && area !== title ? area : null,
      running ? `Diffusing ${activeName}`.trim() : "Idle",
    ]
      .filter(Boolean)
      .map(esc)
      .join(" · ");

    const chips = [];
    if (offline) chips.push(`<span class="chip warn"><ha-icon icon="mdi:wifi-off"></ha-icon>Offline</span>`);
    if (controller && CONTROLLER_LABEL[controller] && controller !== "default")
      chips.push(
        `<span class="chip ${controller === "away" ? "warn" : ""}">${esc(CONTROLLER_LABEL[controller])}</span>`
      );
    const battery = this._state(e.battery);
    if (battery && !isUnavailable(battery))
      chips.push(`<span class="chip"><ha-icon icon="mdi:battery"></ha-icon>${esc(battery.state)}%</span>`);

    const power = e.fragrance
      ? `<button class="power ${running ? "on" : ""}" data-action="power" ${locked ? "disabled" : ""}
           title="${running ? "Turn off" : "Turn on"}"><ha-icon icon="mdi:power"></ha-icon></button>`
      : "";

    return `
      <ha-card class="${running ? "running" : ""} ${e.fan_intensity ? "car" : ""}">
        <div class="header">
          <button class="badge" data-action="more-info" data-value="${esc(e.fragrance || e.active_fragrance || "")}"
            title="Fragrance">
            <ha-icon icon="mdi:scent"></ha-icon>
          </button>
          <div class="titles">
            ${hass.user?.is_admin && device
              ? `<button class="title link" data-action="device" title="Open device page">
                  <span class="title-text">${esc(title)}</span><ha-icon icon="mdi:chevron-right"></ha-icon>
                </button>`
              : `<div class="title">${esc(title)}</div>`}
            <div class="subtitle">${subtitle}</div>
          </div>
          <div class="chips">${chips.join("")}</div>
          ${power}
        </div>
        ${away ? `<div class="banner"><ha-icon icon="mdi:home-export-outline"></ha-icon>Away mode is on — controls are paused.</div>` : ""}
        ${this._renderBays(activeOption, locked)}
        ${config.show_intensity && e.intensity ? this._renderIntensity(running, locked) : ""}
        ${config.show_timer && e.timer && e.fragrance ? this._renderTimer(locked) : ""}
        ${this._renderFooter()}
      </ha-card>`;
  }

  _renderBays(activeOption, locked) {
    const slots = Object.values(this._entities.bays).sort((a, b) => a.slot - b.slot);
    if (!slots.length) return "";

    const tiles = slots.map((bay) => {
      const nameState = this._state(bay.name);
      const remainingState = this._state(bay.remaining);
      const runtimeState = this._state(bay.runtime);
      const empty = isUnavailable(nameState) && isUnavailable(remainingState);
      const name = empty ? "Empty" : nameState?.state || "Fragrance";
      // A missing, unknown or unavailable remaining sensor means "unknown", not 0%.
      const remaining = isUnavailable(remainingState) ? NaN : Number(remainingState.state);
      const known = !empty && Number.isFinite(remaining);
      const pct = known ? Math.max(0, Math.min(100, remaining)) : 0;
      const active = activeOption === `slot_${bay.slot}`;
      const low = known && pct <= (this._config.low_threshold ?? 15);
      const hue = fragranceHue(name);
      const disabled = empty || (locked && !!this._entities.fragrance);
      const picture = empty ? undefined : nameState?.attributes?.entity_picture;
      // Pura's own color for the fragrance, falling back to a hue derived from its name.
      const color = empty ? undefined : fragranceTint(nameState?.attributes?.color, this._hass.themes?.darkMode);
      const tint = color ? `;--tint:${color}` : "";

      return `
        <button class="bay ${active ? "active" : ""} ${empty ? "empty" : ""} ${picture ? "has-img" : ""}"
          style="--hue:${hue}${tint}" data-action="bay" data-value="${bay.slot}" ${disabled ? "disabled" : ""}
          title="${empty
            ? "No fragrance installed"
            : !this._entities.fragrance
              ? "Show details"
              : active
                ? "Stop"
                : `Diffuse ${esc(name)}`}">
          <div class="vial">
            ${active ? `<span class="mist m1"></span><span class="mist m2"></span><span class="mist m3"></span>` : ""}
            <div class="glass">${known ? `<div class="fill" style="height:${pct}%"></div>` : ""}</div>
            ${picture ? `<div class="vial-frame"><img class="vial-img" src="${esc(picture)}" alt="" loading="lazy"></div>` : ""}
          </div>
          <div class="bay-info">
            <div class="slot-label">${slots.length > 1 ? `Slot ${bay.slot}` : "Fragrance"}${active ? ` · <span class="live">Active</span>` : ""}</div>
            <div class="bay-name">${esc(name)}</div>
            ${picture && known ? `<div class="meter"><div style="width:${pct}%"></div></div>` : ""}
            ${empty ? "" : `
              <div class="bay-meta">
                ${known ? `<span class="${low ? "low" : ""}">${Math.round(pct)}% left</span>` : ""}
                ${runtimeState && !isUnavailable(runtimeState) ? `<span>${esc(this._formatState(runtimeState))} used</span>` : ""}
              </div>`}
          </div>
        </button>`;
    });
    return `<div class="bays">${tiles.join("")}</div>`;
  }

  _renderIntensity(running, locked) {
    const current = this._state(this._entities.intensity)?.state;
    const disabled = !running || locked;
    const buttons = INTENSITY_LEVELS.map(
      (level, i) => `
        <button class="level ${current === level ? "selected" : ""}" data-action="intensity" data-value="${level}"
          ${disabled ? "disabled" : ""} title="${level[0].toUpperCase() + level.slice(1)}">
          <span class="bars">${INTENSITY_LEVELS.map((_, j) => `<i class="${j <= i ? "lit" : ""}"></i>`).join("")}</span>
        </button>`
    ).join("");
    const label = current && current !== "off" && running ? current[0].toUpperCase() + current.slice(1) : "—";
    return `
      <div class="section">
        <div class="section-head"><span>Intensity</span><span class="value">${esc(label)}</span></div>
        <div class="levels">${buttons}</div>
      </div>`;
  }

  _renderTimer(locked) {
    const timerState = this._state(this._entities.timer);
    const end = timerState ? Date.parse(timerState.state) : NaN;
    const remaining = end - Date.now();

    if (remaining > 0) {
      const endText = new Date(end).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
      return `
        <div class="section timer-active">
          <ha-icon icon="mdi:timer-sand"></ha-icon>
          <div class="timer-text"><b>${esc(formatRemaining(remaining))}</b> left · ends ${esc(endText)}</div>
          <button class="pill" data-action="power" ${locked ? "disabled" : ""}>Stop</button>
        </div>`;
    }

    const durations = (this._config.timer_durations || DEFAULT_TIMER_DURATIONS)
      .map(Number)
      .filter((m) => m > 0);
    // pura.start_timer fails when no fragrance is installed, so don't offer it.
    const disabled = locked || !this._bestSlotOption();
    return `
      <div class="section">
        <div class="section-head"><span>Timer</span></div>
        <div class="timers">
          ${durations
            .map(
              (m) =>
                `<button class="pill" data-action="timer" data-value="${m}" ${disabled ? "disabled" : ""}>
                  <ha-icon icon="mdi:timer-outline"></ha-icon>${formatDuration(m)}</button>`
            )
            .join("")}
        </div>
      </div>`;
  }

  _renderFooter() {
    const e = this._entities;
    const config = this._config;
    const toggles = [];

    if (config.show_nightlight && e.nightlight) {
      const s = this._state(e.nightlight);
      const on = s?.state === "on";
      const rgb = s?.attributes.rgb_color;
      const swatch = rgb ? `rgb(${rgb.join(",")})` : "var(--state-light-active-color, #ffc107)";
      toggles.push(`
        <span class="toggle-group">
          <button class="toggle ${on ? "on" : ""}" style="--swatch:${esc(swatch)}" data-action="toggle"
            data-value="${esc(e.nightlight)}" ${isUnavailable(s) ? "disabled" : ""}>
            <ha-icon icon="${on ? "mdi:lightbulb-on" : "mdi:lightbulb-outline"}"></ha-icon>Nightlight
          </button>
          <button class="toggle more" data-action="more-info" data-value="${esc(e.nightlight)}" title="Color & brightness">
            <ha-icon icon="mdi:palette-outline"></ha-icon>
          </button>
        </span>`);
    }

    if (config.show_settings) {
      const add = (entityId, icon, label) => {
        const s = this._state(entityId);
        if (!s) return;
        toggles.push(`
          <button class="toggle ${s.state === "on" ? "on" : ""}" data-action="toggle" data-value="${esc(entityId)}"
            ${isUnavailable(s) ? "disabled" : ""}>
            <ha-icon icon="${icon}"></ha-icon>${label}
          </button>`);
      };
      add(e.auto_alternate, "mdi:swap-horizontal", "Auto-alternate");
      add(e.ambient_mode, "mdi:weather-night", "Ambient");
      add(e.away_mode, "mdi:home-export-outline", "Away mode");
    }

    return toggles.length ? `<div class="footer">${toggles.join("")}</div>` : "";
  }
}

const STYLES = `
  :host { --pura-accent: var(--primary-color); }
  ha-card { padding: 16px; display: flex; flex-direction: column; gap: 16px; overflow: hidden; }
  button { font: inherit; color: inherit; background: none; border: none; cursor: pointer; padding: 0; }
  button[disabled] { cursor: default; opacity: 0.45; }
  ha-icon { --mdc-icon-size: 18px; }

  .message { display: flex; align-items: center; gap: 12px; color: var(--secondary-text-color); }

  .header { display: flex; align-items: center; gap: 12px; }
  .badge {
    width: 42px; height: 42px; border-radius: 50%; flex: none; cursor: pointer;
    border: none; padding: 0; display: grid; place-items: center;
    background: color-mix(in srgb, var(--pura-accent) 14%, transparent); color: var(--pura-accent);
  }
  .badge ha-icon { --mdc-icon-size: 22px; }
  .running .badge { animation: breathe 3.2s ease-in-out infinite; }
  .titles { flex: 1; min-width: 0; }
  .title { font-size: 16px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .title.link { display: inline-flex; align-items: center; gap: 2px; max-width: 100%; text-align: left; }
  .title.link .title-text { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
  .title.link ha-icon {
    flex: none; display: flex; /* centre the icon itself, not its text baseline */
    --mdc-icon-size: 18px; color: var(--secondary-text-color); transition: transform 0.18s ease-in-out;
  }
  .title.link:hover ha-icon, .title.link:focus-visible ha-icon { transform: translateX(3px); }
  .subtitle { font-size: 13px; color: var(--secondary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .chips { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
  .chip {
    display: inline-flex; align-items: center; gap: 4px; font-size: 12px; padding: 3px 8px; border-radius: 12px;
    background: var(--secondary-background-color); color: var(--secondary-text-color);
  }
  .chip ha-icon { --mdc-icon-size: 14px; }
  .chip.warn { background: color-mix(in srgb, var(--warning-color, #ffa600) 18%, transparent); color: var(--warning-color, #ffa600); }
  .power {
    width: 40px; height: 40px; border-radius: 50%; flex: none; display: grid; place-items: center;
    border: 1px solid var(--divider-color); transition: background 0.2s, color 0.2s;
  }
  .power.on { background: var(--pura-accent); color: var(--text-primary-color, #fff); border-color: transparent; }

  .banner {
    display: flex; align-items: center; gap: 8px; font-size: 13px; padding: 8px 12px; border-radius: 10px;
    background: color-mix(in srgb, var(--warning-color, #ffa600) 14%, transparent);
  }

  .bays { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
  .bay {
    --tint: hsl(var(--hue) 65% 58%);
    display: flex; align-items: center; gap: 14px; text-align: left; padding: 12px; border-radius: 14px;
    border: 1px solid var(--divider-color); background: var(--card-background-color);
    transition: border-color 0.25s, background 0.25s, box-shadow 0.25s;
  }
  .bay:not([disabled]):hover { border-color: var(--tint); }
  .bay.active {
    border-color: var(--tint);
    background: color-mix(in srgb, var(--tint) 10%, var(--card-background-color));
    box-shadow: 0 0 0 1px var(--tint) inset;
  }
  .bay.empty { opacity: 0.55; }
  .vial { position: relative; width: 28px; height: 56px; flex: none; }
  .glass {
    position: absolute; inset: 6px 0 0 0; border-radius: 6px 6px 10px 10px; overflow: hidden;
    border: 2px solid color-mix(in srgb, var(--tint) 55%, var(--divider-color));
    background: color-mix(in srgb, var(--tint) 6%, transparent);
  }
  .vial::before {
    content: ""; position: absolute; top: 0; left: 8px; right: 8px; height: 8px; border-radius: 3px 3px 0 0;
    background: color-mix(in srgb, var(--tint) 55%, var(--divider-color));
  }
  .fill {
    position: absolute; left: 0; right: 0; bottom: 0; transition: height 0.6s ease;
    background: linear-gradient(to top, var(--tint), color-mix(in srgb, var(--tint) 60%, #fff));
  }
  .vial-frame, .meter { display: none; }
  /* Vial photos are a tall, narrow bottle centred in a square image; Car pods are round */
  .bay.has-img .vial { width: 44px; height: 96px; }
  .car .bay.has-img .vial { width: 64px; height: 64px; }
  .bay.has-img .vial::before, .bay.has-img .glass { display: none; }
  .bay.has-img .mist { z-index: 1; }
  /* Product photos are padded, so fill (and crop) the frame and zoom in a little */
  .bay.has-img .vial-frame { display: block; position: absolute; inset: 0; overflow: hidden; border-radius: 8px; }
  .vial-img {
    display: block; width: 100%; height: 100%; object-fit: cover;
    transform: scale(1.1); transform-origin: center;
  }
  .car .vial-img { transform: scale(1.2); }
  .bay.has-img .meter {
    display: block; height: 4px; margin-bottom: 6px; border-radius: 2px; overflow: hidden;
    background: var(--divider-color);
  }
  .meter > div { height: 100%; background: var(--tint); transition: width 0.6s ease; }
  .mist {
    position: absolute; left: 50%; top: -2px; width: 8px; height: 8px; border-radius: 50%;
    background: var(--tint); opacity: 0; animation: mist 2.4s ease-out infinite;
  }
  .m2 { animation-delay: 0.8s; } .m3 { animation-delay: 1.6s; }
  .bay-info { min-width: 0; flex: 1; }
  .slot-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--secondary-text-color); }
  .live { color: var(--tint); font-weight: 600; }
  .bay-name { font-size: 15px; font-weight: 500; margin: 2px 0 4px; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
  .bay-meta { display: flex; flex-wrap: wrap; gap: 4px 10px; font-size: 12px; color: var(--secondary-text-color); }
  .bay-meta .low { color: var(--error-color, #db4437); font-weight: 500; }

  .section { display: flex; flex-direction: column; gap: 8px; }
  .section-head { display: flex; justify-content: space-between; font-size: 13px; color: var(--secondary-text-color); }
  .section-head .value { color: var(--primary-text-color); text-transform: capitalize; }
  .levels { display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; }
  .level {
    height: 36px; border-radius: 10px; display: grid; place-items: center;
    background: var(--secondary-background-color); transition: background 0.2s;
  }
  .level.selected { background: color-mix(in srgb, var(--pura-accent) 22%, transparent); box-shadow: 0 0 0 1.5px var(--pura-accent) inset; }
  .bars { display: flex; align-items: flex-end; gap: 2px; height: 14px; }
  .bars i { width: 3px; border-radius: 2px; background: var(--disabled-text-color, #bbb); }
  .bars i:nth-child(1) { height: 4px; } .bars i:nth-child(2) { height: 6px; } .bars i:nth-child(3) { height: 9px; }
  .bars i:nth-child(4) { height: 11px; } .bars i:nth-child(5) { height: 14px; }
  .bars i.lit { background: var(--pura-accent); }

  .timers { display: flex; flex-wrap: wrap; gap: 8px; }
  .pill {
    display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; border-radius: 18px; font-size: 13px;
    border: 1px solid var(--divider-color);
  }
  .pill:not([disabled]):hover { border-color: var(--pura-accent); color: var(--pura-accent); }
  .timer-active {
    flex-direction: row; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 12px;
    background: color-mix(in srgb, var(--pura-accent) 10%, transparent);
  }
  .timer-active ha-icon { color: var(--pura-accent); }
  .timer-text { flex: 1; font-size: 14px; }

  .footer { display: flex; flex-wrap: wrap; gap: 8px; padding-top: 12px; border-top: 1px solid var(--divider-color); }
  .toggle-group { display: inline-flex; }
  .toggle-group .toggle:first-child { border-radius: 18px 0 0 18px; border-right: none; }
  .toggle-group .more { border-radius: 0 18px 18px 0; padding: 7px 10px; }
  .toggle {
    display: inline-flex; align-items: center; gap: 6px; padding: 7px 12px; border-radius: 18px; font-size: 13px;
    border: 1px solid var(--divider-color); color: var(--secondary-text-color);
  }
  .toggle.on { color: var(--primary-text-color); background: var(--secondary-background-color); }
  .toggle.on ha-icon { color: var(--swatch, var(--pura-accent)); }

  @keyframes breathe { 50% { box-shadow: 0 0 0 6px color-mix(in srgb, var(--pura-accent) 12%, transparent); } }
  @keyframes mist {
    0% { transform: translate(-50%, 0) scale(0.6); opacity: 0.55; }
    100% { transform: translate(calc(-50% + 6px), -22px) scale(1.8); opacity: 0; }
  }
  @media (prefers-reduced-motion: reduce) {
    .mist, .running .badge { animation: none; }
    .title.link ha-icon { transition: none; }
  }
`;

// ------------------------------------------------------------------ editor

const EDITOR_SCHEMA = [
  { name: "device_id", required: true, selector: { device: { integration: "pura" } } },
  { name: "name", selector: { text: {} } },
  {
    type: "grid",
    name: "",
    schema: [
      { name: "show_intensity", selector: { boolean: {} } },
      { name: "show_timer", selector: { boolean: {} } },
      { name: "show_nightlight", selector: { boolean: {} } },
      { name: "show_settings", selector: { boolean: {} } },
    ],
  },
  {
    name: "timer_durations",
    selector: {
      select: {
        multiple: true,
        mode: "list",
        options: [15, 30, 45, 60, 90, 120, 180, 240, 480].map((m) => ({
          value: String(m),
          label: formatDuration(m),
        })),
      },
    },
  },
];

const EDITOR_LABELS = {
  device_id: "Pura device",
  name: "Name (optional)",
  show_intensity: "Show intensity",
  show_timer: "Show timer",
  show_nightlight: "Show nightlight",
  show_settings: "Show mode toggles",
  timer_durations: "Timer presets",
};

class PuraCardEditor extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    if (this._form) this._form.hass = hass;
  }

  setConfig(config) {
    this._config = config;
    this._render();
  }

  async connectedCallback() {
    // ha-form is lazy-loaded by HA; loading a built-in card editor guarantees it exists.
    if (!customElements.get("ha-form")) {
      try {
        const helpers = await window.loadCardHelpers?.();
        const card = await helpers?.createCardElement({ type: "entities", entities: [] });
        await card?.constructor?.getConfigElement?.();
      } catch (_err) {
        /* best effort */
      }
    }
    this._render();
  }

  _render() {
    if (!this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (schema) => EDITOR_LABELS[schema.name] ?? schema.name;
      this._form.addEventListener("value-changed", (ev) => {
        const value = { ...ev.detail.value };
        if (Array.isArray(value.timer_durations))
          value.timer_durations = value.timer_durations.map(Number).sort((a, b) => a - b);
        this.dispatchEvent(
          new CustomEvent("config-changed", { detail: { config: value }, bubbles: true, composed: true })
        );
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.schema = EDITOR_SCHEMA;
    this._form.data = {
      show_intensity: true,
      show_timer: true,
      show_nightlight: true,
      show_settings: true,
      ...this._config,
      timer_durations: (this._config.timer_durations || DEFAULT_TIMER_DURATIONS).map(String),
    };
  }
}

if (!customElements.get("pura-card")) customElements.define("pura-card", PuraCard);
if (!customElements.get("pura-card-editor")) customElements.define("pura-card-editor", PuraCardEditor);

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "pura-card")) {
  window.customCards.push({
    type: "pura-card",
    name: "Pura Card",
    description: "Control a Pura smart fragrance diffuser: slots, intensity, timers, nightlight and away mode.",
    preview: true,
    documentationURL: "https://github.com/natekspencer/ha-pura#-dashboard-card",
  });
}

console.info(
  `%c PURA-CARD %c v${CARD_VERSION} `,
  "color:#fff;background:#7b5cd6;font-weight:700;border-radius:3px 0 0 3px",
  "color:#7b5cd6;background:#f1edff;border-radius:0 3px 3px 0"
);
