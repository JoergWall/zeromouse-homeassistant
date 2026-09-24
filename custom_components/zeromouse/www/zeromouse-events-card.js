/*
 * ZeroMOUSE event gallery card.
 *
 * Shows the newest ZeroMOUSE events like the app does (all images of an event
 * cycling at `fps`) and optionally matches each event with a passage of a
 * Sure Petcare pet (the `since` attribute of its presence binary_sensor).
 *
 * type: custom:zeromouse-events-card
 * limit: 10
 * fps: 2
 * correlate:
 *   - entity: binary_sensor.tiger
 *     name: Tiger
 *     color: "#2a78d6"
 */

const LABELS = {
  de: {
    prey: "Beute erkannt",
    clean: "Keine Beute erkannt",
    undecidable: "Nicht entscheidbar",
    out: "Rausgehen erkannt",
    hand: "Hand erkannt",
    early: "Zu früh ausgelöst",
    late: "Zu spät ausgelöst",
    free: "Freier Eintritt",
    test: "Test",
    unknown: "Unbekannt",
    in: "kam herein",
    left: "ging hinaus",
    none: "Keine Sure-Petcare-Zuordnung",
    empty: "Keine Ereignisse",
    error: "Fehler beim Laden",
  },
  en: {
    prey: "Prey detected",
    clean: "No prey detected",
    undecidable: "Inconclusive",
    out: "Leaving detected",
    hand: "Hand detected",
    early: "Triggered too early",
    late: "Triggered too late",
    free: "Free entry",
    test: "Test",
    unknown: "Unknown",
    in: "came in",
    left: "went out",
    none: "No Sure Petcare match",
    empty: "No events",
    error: "Loading failed",
  },
};

const ICONS = {
  prey: "mdi:rodent",
  clean: "mdi:login",
  undecidable: "mdi:help-circle-outline",
  out: "mdi:logout",
  hand: "mdi:hand-back-right-outline",
};

const COLORS = {
  prey: "var(--error-color, #db4437)",
  clean: "var(--success-color, #43a047)",
  undecidable: "var(--warning-color, #ffa600)",
};

// Which Sure Petcare direction (attribute `where`) fits a classification.
const WANT_WHERE = { out: 2, prey: 1, clean: 1, undecidable: 1, hand: 1 };

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

/*
 * Match ZeroMOUSE events with Sure Petcare passages.
 * Every new value of the `since` attribute of a pet's presence sensor is one
 * passage, `where` 1 = came in, 2 = went out. Greedy one-to-one matching by the
 * smallest time difference within [-before, +after] seconds.
 * Returns {event_id: {cat, t, where, d}}.
 */
async function correlate(hass, events, cats, before, after) {
  if (!cats?.length || !events.length) return {};
  const times = events.map((e) => Date.parse(e.time)).filter((t) => !isNaN(t));
  if (!times.length) return {};
  const start = new Date(Math.min(...times) - (before + 900) * 1000);
  const hist = await hass.callWS({
    type: "history/history_during_period",
    start_time: start.toISOString(),
    entity_ids: cats.map((c) => c.entity),
    minimal_response: false,
    no_attributes: false,
    significant_changes_only: false,
  });

  const passages = [];
  for (const c of cats) {
    const seen = new Set();
    const rows = [...(hist[c.entity] || [])];
    const current = hass.states[c.entity];
    if (current) rows.push({ a: current.attributes });
    for (const row of rows) {
      const a = row.a || row.attributes;
      if (!a?.since || seen.has(a.since)) continue;
      seen.add(a.since);
      passages.push({ cat: c, t: Date.parse(a.since), where: a.where });
    }
  }

  const pairs = [];
  events.forEach((e, i) => {
    const t = Date.parse(e.time);
    if (isNaN(t)) return;
    const want = WANT_WHERE[e.classification];
    passages.forEach((p, j) => {
      const d = (p.t - t) / 1000;
      if (d < -before || d > after) return;
      if (want && p.where !== want) return;
      pairs.push({ i, j, d });
    });
  });
  pairs.sort((x, y) => Math.abs(x.d) - Math.abs(y.d));
  const usedE = new Set();
  const usedP = new Set();
  const result = {};
  for (const { i, j, d } of pairs) {
    if (usedE.has(i) || usedP.has(j)) continue;
    usedE.add(i);
    usedP.add(j);
    result[events[i].event_id] = { ...passages[j], d };
  }
  return result;
}

// Signature of everything that should trigger a reload.
function dataSignature(hass, cats) {
  const parts = [];
  for (const [id, ent] of Object.entries(hass.entities || {})) {
    if (ent.platform === "zeromouse" && id.startsWith("sensor.")) {
      const ev = hass.states[id]?.attributes?.event_id;
      if (ev) parts.push(ev);
    }
  }
  for (const c of cats || []) parts.push(hass.states[c.entity]?.attributes?.since ?? "");
  return parts.join("|");
}

class ZeroMouseEventsCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._events = [];
    this._matches = {};
    this._frames = new Map(); // event_id -> {slots: [objectURL|null], pos, paused}
    this._blobs = new Map(); // image url -> object URL
    this._loading = null;
  }

  static getStubConfig() {
    return { limit: 6, fps: 2 };
  }

  setConfig(config) {
    this._config = {
      limit: 10,
      fps: 2,
      show_hidden: false,
      window_before: 60,
      window_after: 180,
      language: "de",
      correlate: [],
      ...config,
    };
    this._t = LABELS[this._config.language] || LABELS.de;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const sig = this._signature(hass);
    if (sig !== this._sig) {
      this._sig = sig;
      this._load();
    }
  }

  getCardSize() {
    return 2 + Math.ceil(this._config.limit / 2) * 5;
  }

  getGridOptions() {
    return { columns: "full" };
  }

  connectedCallback() {
    const interval = Math.max(100, 1000 / (Number(this._config?.fps) || 2));
    this._timer = setInterval(() => this._tick(), interval);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
  }

  // Reload when a ZeroMOUSE event or a Sure Petcare passage changes.
  _signature(hass) {
    return dataSignature(hass, this._config.correlate);
  }

  async _load() {
    if (!this._hass || this._loading) {
      this._reloadPending = !!this._loading;
      return;
    }
    const cfg = this._config;
    this._loading = (async () => {
      try {
        const fetchLimit = cfg.show_hidden ? cfg.limit : Math.min(100, cfg.limit * 3);
        const { events } = await this._hass.callWS({
          type: "zeromouse/events",
          limit: fetchLimit,
        });
        this._events = events
          .filter((e) => cfg.show_hidden || !e.is_hidden)
          .slice(0, cfg.limit);
        this._error = null;
        this._matches = await this._correlate(this._events).catch((err) => {
          console.warn("zeromouse-events-card: correlation failed", err);
          return {};
        });
      } catch (err) {
        console.error("zeromouse-events-card", err);
        this._error = err.message || String(err);
      }
      this._render();
      this._loadImages();
    })();
    await this._loading;
    this._loading = null;
    if (this._reloadPending) {
      this._reloadPending = false;
      this._load();
    }
  }

  _correlate(events) {
    const cfg = this._config;
    return correlate(this._hass, events, cfg.correlate, cfg.window_before, cfg.window_after);
  }

  _imageUrl(e, idx) {
    return `/api/zeromouse/image/${e.entry_id}/${encodeURIComponent(
      e.device_id
    )}/${encodeURIComponent(e.event_id)}/${idx}`;
  }

  async _fetchBlob(url) {
    if (this._blobs.has(url)) return this._blobs.get(url);
    const resp = await this._hass.fetchWithAuth(url);
    if (!resp.ok) throw new Error(`${resp.status}`);
    const obj = URL.createObjectURL(await resp.blob());
    this._blobs.set(url, obj);
    return obj;
  }

  async _loadImages() {
    const wanted = new Set();
    const jobs = [];
    const frames = new Map();
    for (const e of this._events) {
      const order = e.images.length ? [...e.images] : e.title_image != null ? [e.title_image] : [];
      const prev = this._frames.get(e.event_id);
      const titlePos = Math.max(0, order.indexOf(e.title_image));
      const state = {
        slots: new Array(order.length).fill(null),
        pos: prev ? Math.min(prev.pos, order.length - 1) : titlePos,
        paused: prev?.paused || false,
      };
      frames.set(e.event_id, state);
      order.forEach((idx, k) => {
        const url = this._imageUrl(e, idx);
        wanted.add(url);
        // Serve cached images right away.
        if (this._blobs.has(url)) state.slots[k] = this._blobs.get(url);
        else jobs.push({ id: e.event_id, k, url, state, first: k === titlePos });
      });
    }
    this._frames = frames;
    for (const id of frames.keys()) this._showFrame(id);
    // Free images of events that are gone.
    for (const [url, obj] of this._blobs) {
      if (!wanted.has(url)) {
        URL.revokeObjectURL(obj);
        this._blobs.delete(url);
      }
    }
    // Title images first, then the rest; four downloads at a time.
    jobs.sort((a, b) => Number(b.first) - Number(a.first));
    const worker = async () => {
      while (jobs.length) {
        const job = jobs.shift();
        try {
          job.state.slots[job.k] = await this._fetchBlob(job.url);
        } catch (err) {
          continue;
        }
        if (job.k === job.state.pos) this._showFrame(job.id);
      }
    };
    await Promise.all([worker(), worker(), worker(), worker()]);
  }

  _tick() {
    for (const [id, st] of this._frames) {
      if (st.paused || st.slots.filter(Boolean).length < 2) continue;
      do {
        st.pos = (st.pos + 1) % st.slots.length;
      } while (!st.slots[st.pos]);
      this._showFrame(id);
    }
  }

  _showFrame(id) {
    const st = this._frames.get(id);
    const box = this.shadowRoot.querySelector(`[data-event="${CSS.escape(id)}"]`);
    const url = st?.slots[st.pos];
    if (!box || !url) return;
    const img = box.querySelector("img");
    if (img.src !== url) img.src = url;
    img.classList.add("ready");
    box.querySelector(".count").textContent = `${st.pos + 1}/${st.slots.length}`;
  }

  _format(iso, withSeconds) {
    const tz = this._hass?.config?.time_zone;
    const opts = withSeconds
      ? { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: tz }
      : {
          day: "2-digit",
          month: "2-digit",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
          timeZone: tz,
        };
    const locale = this._config.language === "en" ? "en-GB" : "de-DE";
    return new Intl.DateTimeFormat(locale, opts).format(new Date(iso)).replace(",", "");
  }

  _render() {
    if (!this._config) return;
    const t = this._t;
    const cfg = this._config;
    let body;
    if (this._error) {
      body = `<div class="msg">${esc(t.error)}: ${esc(this._error)}</div>`;
    } else if (!this._events.length) {
      body = `<div class="msg">${this._hass ? esc(t.empty) : ""}</div>`;
    } else {
      body = `<div class="grid">${this._events.map((e) => this._renderEvent(e)).join("")}</div>`;
    }
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { padding: 16px; }
        .header { font-size: 20px; font-weight: 500; margin: 0 0 12px; }
        .grid { display: grid; gap: 16px;
                grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); }
        .ev { border-radius: 16px; overflow: hidden;
              background: var(--secondary-background-color);
              box-shadow: var(--ha-card-box-shadow, none); }
        .media { position: relative; aspect-ratio: 4 / 3; background: #000;
                 cursor: pointer; }
        .media img { width: 100%; height: 100%; object-fit: cover; display: block;
                     opacity: 0; transition: opacity .2s; }
        .media img.ready { opacity: 1; }
        .count { position: absolute; right: 8px; bottom: 8px; font-size: 12px;
                 color: #fff; background: rgba(0,0,0,.45); border-radius: 8px;
                 padding: 1px 6px; font-variant-numeric: tabular-nums; }
        .paused .count::after { content: " ❚❚"; }
        .info { padding: 10px 12px 12px; }
        .title { display: flex; align-items: center; gap: 8px; font-weight: 600;
                 font-size: 16px; }
        .title ha-icon { --mdc-icon-size: 22px; }
        .meta { color: var(--secondary-text-color); font-size: 13px; margin-top: 2px; }
        .corr { display: flex; align-items: center; gap: 6px; margin-top: 8px;
                font-size: 13px; }
        .corr.none { color: var(--secondary-text-color); }
        .dot { width: 10px; height: 10px; border-radius: 50%; flex: none; }
        .msg { color: var(--secondary-text-color); padding: 8px 0; }
      </style>
      <ha-card>
        ${cfg.title ? `<div class="header">${esc(cfg.title)}</div>` : ""}
        ${body}
      </ha-card>`;
    for (const box of this.shadowRoot.querySelectorAll(".media")) {
      box.addEventListener("click", () => {
        const st = this._frames.get(box.dataset.event);
        if (!st) return;
        st.paused = !st.paused;
        box.classList.toggle("paused", st.paused);
      });
    }
    for (const id of this._frames.keys()) this._showFrame(id);
  }

  _renderEvent(e) {
    const t = this._t;
    const cls = e.classification || "unknown";
    const color = COLORS[cls] || "var(--secondary-text-color)";
    const icon = ICONS[cls] || "mdi:cat";
    const when = e.time ? this._format(e.time, false) : "";
    const st = this._frames.get(e.event_id);
    let corr = "";
    if (this._config.correlate.length) {
      const m = this._matches[e.event_id];
      if (m) {
        const sign = m.d >= 0 ? "+" : "−";
        const dir = m.where === 2 ? t.left : t.in;
        corr = `<div class="corr"><span class="dot" style="background:${esc(
          m.cat.color || "var(--primary-color)"
        )}"></span><b>${esc(m.cat.name || m.cat.entity)}</b> ${esc(dir)} · Sure Petcare ${esc(
          this._format(new Date(m.t).toISOString(), true)
        )} (${sign}${Math.round(Math.abs(m.d))} s)</div>`;
      } else {
        corr = `<div class="corr none">${esc(t.none)}</div>`;
      }
    }
    return `
      <div class="ev">
        <div class="media${st?.paused ? " paused" : ""}" data-event="${esc(e.event_id)}">
          <img alt="${esc(t[cls] || cls)}">
          <span class="count"></span>
        </div>
        <div class="info">
          <div class="title"><ha-icon icon="${icon}" style="color:${color}"></ha-icon>
            <span>${esc(t[cls] || cls)}</span></div>
          <div class="meta">${esc(e.device_name)} | ${esc(when)}${
            e.cat ? ` · ${esc(e.cat)}` : ""
          }</div>
          ${corr}
        </div>
      </div>`;
  }
}

/*
 * ZeroMOUSE timeline: one row per day, one round cat comic per event.
 * The comic tells who (via Sure Petcare), its background colour the result.
 *
 * type: custom:zeromouse-timeline-card
 * days: 10
 * correlate:
 *   - entity: binary_sensor.tiger
 *     name: Tiger
 *     icon: /local/zeromouse/tiger-{class}.webp
 * unknown_icon: /local/zeromouse/unbekannt.webp
 */
const TL_CLASSES = ["clean", "prey", "undecidable"];
const TL_COLORS = { clean: "#4cae2c", prey: "#e3161b", undecidable: "#f98407" };
const TL_TEXT = {
  de: {
    title: "Wer kam wann – mit oder ohne Beute",
    unknown: "Unbekannt",
    prey: "Beute",
    time: "Uhrzeit",
    loading: "Lade …",
    error: "Fehler beim Laden",
    weekdays: ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"],
    note:
      "Hinweis: Bei „Beute erkannt“ und „Nicht entscheidbar“ sperrt ZeroMOUSE die Klappe – " +
      "Sure Petcare erkennt die Katze dann nicht. Diese Ereignisse erscheinen deshalb immer als „Unbekannt“.",
  },
  en: {
    title: "Who came when – with or without prey",
    unknown: "Unknown",
    prey: "Prey",
    time: "Time of day",
    loading: "Loading …",
    error: "Loading failed",
    weekdays: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
    note:
      "Note: on “Prey detected” and “Inconclusive” ZeroMOUSE blocks the flap, so Sure Petcare " +
      "never sees the cat pass. These events are therefore always shown as “Unknown”.",
  },
};

class ZeroMouseTimelineCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._events = null;
    this._matches = {};
  }

  static getStubConfig() {
    return { days: 10 };
  }

  setConfig(config) {
    const text = TL_TEXT[config.language] || TL_TEXT.de;
    this._t = text;
    this._labels = LABELS[config.language] || LABELS.de;
    this._config = {
      days: 10,
      title: text.title,
      window_before: 60,
      window_after: 180,
      correlate: [],
      unknown_icon: null,
      unknown_name: text.unknown,
      night_start: 22,
      night_end: 6,
      note: text.note,
      ...config,
    };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const sig = dataSignature(hass, this._config.correlate);
    if (sig !== this._sig) {
      this._sig = sig;
      this._load();
    }
  }

  getCardSize() {
    return 4 + this._config.days;
  }

  getGridOptions() {
    return { columns: "full" };
  }

  // Calendar parts of a timestamp in the Home Assistant time zone.
  _parts(ms) {
    const tz = this._hass?.config?.time_zone;
    const f = new Intl.DateTimeFormat("en-CA", {
      timeZone: tz,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      weekday: "short",
      hourCycle: "h23",
    });
    const p = Object.fromEntries(f.formatToParts(new Date(ms)).map((x) => [x.type, x.value]));
    const wd = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].indexOf(p.weekday);
    return {
      key: `${p.year}-${p.month}-${p.day}`,
      label: `${this._t.weekdays[wd]} ${p.day}.${p.month}.`,
      date: `${p.day}.${p.month}.${p.year}`,
      hour: +p.hour + +p.minute / 60 + +p.second / 3600,
      hm: `${p.hour}:${p.minute}`,
    };
  }

  async _load() {
    if (!this._hass || this._loading) {
      this._reloadPending = !!this._loading;
      return;
    }
    const cfg = this._config;
    this._loading = (async () => {
      try {
        const since = new Date(Date.now() - (cfg.days * 24 + 1) * 3600 * 1000);
        const { events } = await this._hass.callWS({
          type: "zeromouse/events",
          since: since.toISOString(),
          limit: 1000,
        });
        this._events = events.filter((e) => TL_CLASSES.includes(e.classification) && e.time);
        this._matches = await correlate(
          this._hass, this._events, cfg.correlate, cfg.window_before, cfg.window_after
        ).catch((err) => {
          console.warn("zeromouse-timeline-card: correlation failed", err);
          return {};
        });
        this._error = null;
      } catch (err) {
        console.error("zeromouse-timeline-card", err);
        this._error = err.message || String(err);
      }
      this._render();
    })();
    await this._loading;
    this._loading = null;
    if (this._reloadPending) {
      this._reloadPending = false;
      this._load();
    }
  }

  _icon(cat, cls) {
    const tpl = cat ? cat.icon : this._config.unknown_icon;
    return tpl ? tpl.replace("{class}", cls) : null;
  }

  _svg() {
    const cfg = this._config;
    const cats = cfg.correlate;
    // Days: today first, `days` rows.
    const days = [];
    const seen = new Set();
    for (let i = 0; days.length < cfg.days && i < cfg.days * 2; i++) {
      const p = this._parts(Date.now() - i * 86400000);
      if (!seen.has(p.key)) {
        seen.add(p.key);
        days.push(p);
      }
    }
    const rowOf = Object.fromEntries(days.map((d, i) => [d.key, i]));

    // Lanes inside a day row: cats spread around the centre, unknown in the middle.
    const half = Math.ceil(cats.length / 2);
    const order = [
      ...cats.slice(0, half).map((c) => c.entity),
      null,
      ...cats.slice(half).map((c) => c.entity),
    ];
    // SVG text does not wrap: split the note into lines that fit the plot width
    const noteLines = [];
    for (const word of (cfg.note || "").split(/\s+/).filter(Boolean)) {
      const last = noteLines[noteLines.length - 1];
      if (last !== undefined && (last + " " + word).length <= 118) {
        noteLines[noteLines.length - 1] = last + " " + word;
      } else {
        noteLines.push(word);
      }
    }
    const NOTE_H = noteLines.length ? noteLines.length * 18 + 10 : 0;
    const ROW_H = 68, ICON = 26, ML = 104, MR = 28, MT = 128 + NOTE_H, MB = 48, W = 940;
    const laneStep = Math.min(20, (ROW_H - ICON) / Math.max(1, order.length - 1));
    const laneY = (entity) =>
      (order.indexOf(entity) - (order.length - 1) / 2) * laneStep;
    const plotW = W - ML - MR;
    const H = MT + days.length * ROW_H + MB;
    const x = (h) => ML + (h / 24) * plotW;

    const counts = { unknown: 0, prey: 0 };
    cats.forEach((c) => (counts[c.entity] = 0));
    const marks = [];
    for (const e of this._events || []) {
      const t = Date.parse(e.time);
      const p = this._parts(t);
      const row = rowOf[p.key];
      if (row === undefined) continue;
      const m = this._matches[e.event_id];
      const cat = m?.cat || null;
      counts[cat ? cat.entity : "unknown"]++;
      if (e.classification === "prey") counts.prey++;
      const cx = x(p.hour);
      const cy = MT + row * ROW_H + ROW_H / 2 + laneY(cat ? cat.entity : null);
      const name = cat ? cat.name || cat.entity : cfg.unknown_name;
      const label = this._labels[e.classification] || e.classification;
      const title = `${name} · ${label} · ${p.date} ${p.hm}` +
        (m ? ` · Sure Petcare ${m.d >= 0 ? "+" : "−"}${Math.round(Math.abs(m.d))} s` : "");
      marks.push({ cx, cy, cls: e.classification, cat, title, t });
    }
    // Draw older first so newer events end up on top.
    marks.sort((a, b) => a.t - b.t);

    const o = [];
    o.push(`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(cfg.title)}">`);
    o.push(`<defs><clipPath id="c" clipPathUnits="objectBoundingBox"><circle cx=".5" cy=".5" r=".5"/></clipPath></defs>`);
    // Header
    const first = days[days.length - 1];
    const last = days[0];
    const catTxt = cats.map((c) => `${esc(c.name || c.entity)} ${counts[c.entity]}`).join(" · ");
    o.push(`<text x="${ML}" y="36" class="ink" font-size="22" font-weight="700">${esc(cfg.title)}</text>`);
    o.push(`<text x="${ML}" y="60" class="ink2" font-size="14">${esc(first.date.slice(0, 6))} – ${esc(last.date)} · ${catTxt} · ${esc(cfg.unknown_name)} ${counts.unknown} · ${esc(this._t.prey)} ${counts.prey}</text>`);
    // Legend: cats, then colours
    let lx = ML;
    const ly = 92;
    for (const c of [...cats, null]) {
      const href = this._icon(c, "clean");
      const name = c ? c.name || c.entity : cfg.unknown_name;
      if (href) o.push(`<image href="${esc(href)}" x="${lx}" y="${ly - 12}" width="24" height="24" clip-path="url(#c)"/>`);
      else o.push(`<circle cx="${lx + 12}" cy="${ly}" r="11" class="unk"/>`);
      o.push(`<text x="${lx + 30}" y="${ly + 5}" class="ink" font-size="14">${esc(name)}</text>`);
      lx += 30 + name.length * 8 + 26;
    }
    lx += 16;
    for (const cls of TL_CLASSES) {
      o.push(`<circle cx="${lx + 7}" cy="${ly}" r="7" fill="${TL_COLORS[cls]}"/>`);
      o.push(`<text x="${lx + 20}" y="${ly + 5}" class="ink2" font-size="14">${esc(this._labels[cls])}</text>`);
      lx += 20 + this._labels[cls].length * 7.4 + 22;
    }
    noteLines.forEach((line, i) => {
      o.push(`<text x="${ML}" y="${ly + 34 + i * 18}" class="ink2 note" font-size="13">${esc(line)}</text>`);
    });
    // Rows, night bands, grid
    days.forEach((d, i) => {
      const y = MT + i * ROW_H;
      o.push(`<rect x="${ML}" y="${y}" width="${plotW}" height="${ROW_H}" class="${i % 2 ? "band" : "surface"}"/>`);
      o.push(`<text x="${ML - 14}" y="${y + ROW_H / 2 + 5}" text-anchor="end" class="ink" font-size="14">${esc(d.label)}</text>`);
    });
    const nightW = (a, b) => `<rect x="${x(a)}" y="${MT}" width="${x(b) - x(a)}" height="${days.length * ROW_H}" class="night"/>`;
    o.push(nightW(0, cfg.night_end), nightW(cfg.night_start, 24));
    for (let h = 0; h <= 24; h += 3) {
      o.push(`<line x1="${x(h)}" x2="${x(h)}" y1="${MT}" y2="${MT + days.length * ROW_H}" class="grid"/>`);
      o.push(`<text x="${x(h)}" y="${MT + days.length * ROW_H + 22}" text-anchor="middle" class="ink2" font-size="13">${String(h).padStart(2, "0")}</text>`);
    }
    o.push(`<text x="${ML + plotW / 2}" y="${H - 6}" text-anchor="middle" class="ink2" font-size="13">${esc(this._t.time)}</text>`);
    // Events
    for (const m of marks) {
      const href = this._icon(m.cat, m.cls);
      const r = ICON / 2;
      o.push(`<g class="mark"><title>${esc(m.title)}</title>`);
      if (href) {
        o.push(`<image href="${esc(href)}" x="${m.cx - r}" y="${m.cy - r}" width="${ICON}" height="${ICON}" clip-path="url(#c)"/>`);
      } else {
        o.push(`<circle cx="${m.cx}" cy="${m.cy}" r="${r - 1}" class="unk"/>`);
      }
      // Unknown cat keeps its grey background: show the result as a ring.
      if (!m.cat || !m.cat.icon || !m.cat.icon.includes("{class}")) {
        o.push(`<circle cx="${m.cx}" cy="${m.cy}" r="${r - 1}" fill="none" stroke="${TL_COLORS[m.cls]}" stroke-width="3"/>`);
      }
      o.push(`</g>`);
    }
    o.push(`</svg>`);
    return o.join("");
  }

  _render() {
    if (!this._config) return;
    let body;
    if (this._error) body = `<div class="msg">${esc(this._t.error)}: ${esc(this._error)}</div>`;
    else if (!this._events) body = `<div class="msg">${esc(this._t.loading)}</div>`;
    else body = this._svg();
    this.shadowRoot.innerHTML = `
      <style>
        ha-card { padding: 8px; overflow: hidden; }
        svg { width: 100%; height: auto; display: block; }
        text { font-family: var(--ha-font-family-body, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif); }
        .ink { fill: var(--primary-text-color); }
        .ink2 { fill: var(--secondary-text-color); }
        .surface { fill: var(--card-background-color, #fff); }
        .band { fill: var(--secondary-background-color, #f4f3f0); opacity: .6; }
        .night { fill: var(--primary-text-color); opacity: .045; }
        .grid { stroke: var(--divider-color, #e5e4e0); stroke-width: 1; }
        .unk { fill: #9b9ea4; }
        .note { font-style: italic; }
        .mark { cursor: default; }
        .mark:hover { filter: drop-shadow(0 0 3px rgba(0,0,0,.5)); }
        .msg { color: var(--secondary-text-color); padding: 16px; }
      </style>
      <ha-card>${body}</ha-card>`;
  }
}

// Loaded very early as an "extra module": the frontend replaces
// window.customElements (scoped registry polyfill) while booting, so register
// again in whatever registry is current until it sticks.
const registerCard = () => {
  if (!customElements.get("zeromouse-events-card")) {
    customElements.define("zeromouse-events-card", class extends ZeroMouseEventsCard {});
  }
  if (!customElements.get("zeromouse-timeline-card")) {
    customElements.define("zeromouse-timeline-card", class extends ZeroMouseTimelineCard {});
  }
};
registerCard();
const registerTimer = setInterval(registerCard, 500);
setTimeout(() => clearInterval(registerTimer), 60000);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "zeromouse-events-card",
  name: "ZeroMOUSE Ereignisse",
  description: "Ereignisse mit animierten Bildern, optional mit Sure Petcare verknüpft",
});
window.customCards.push({
  type: "zeromouse-timeline-card",
  name: "ZeroMOUSE Zeitleiste",
  description: "Ereignisse pro Tag, mit Katze (Sure Petcare) und Beute-Status",
});
