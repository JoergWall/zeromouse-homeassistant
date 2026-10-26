/*
 * ZeroMOUSE dashboard cards (loaded automatically by the integration).
 *
 * custom:zeromouse-events-card    events like in the app: animated pictures,
 *                                 filters, rate (wrong/right), delete, load more
 * custom:zeromouse-timeline-card  one row per day, one icon per event
 *
 * Both can show which cat it was. The integration matches events with the
 * passages of any cat flap integration (see `correlate` in the README) and also
 * uses ZeroMOUSE's own cat recognition.
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
    in: "kam herein",
    left: "ging hinaus",
    flap: "Klappe",
    by_zeromouse: "von ZeroMOUSE erkannt",
    none: "Keine Zuordnung zur Katzenklappe",
    empty: "Keine Ereignisse",
    empty_filtered: "Keine Ereignisse für diesen Filter",
    error: "Fehler beim Laden",
    wrong: "Falsch",
    right: "Richtig",
    unrate: "Bewertung entfernen",
    delete: "Löschen",
    cancel: "Abbrechen",
    confirm_wrong:
      "Dieses Ereignis als falsch klassifiziert melden? Deine Rückmeldung hilft, die Erkennung zu verbessern.",
    confirm_delete: "Dieses Ereignis endgültig löschen?",
    load_more: "Ältere laden",
    loading: "Lade …",
    filters: "Filter",
    filters_desc: "Verwende Filter, um die Ergebnisse nach Ereignistyp einzugrenzen",
    favorites_only: "Nur Favoriten anzeigen",
    favorites_desc: "Zeigt alle Favoriten, unabhängig von den anderen Filtern.",
    reset: "Zurücksetzen",
    failed: "Aktion fehlgeschlagen",
    pause: "Animation anhalten oder fortsetzen",
  },
  en: {
    prey: "Prey detected",
    clean: "No prey detected",
    undecidable: "Inconclusive",
    out: "Leaving detected",
    hand: "Hand detected",
    in: "came in",
    left: "went out",
    flap: "Flap",
    by_zeromouse: "recognised by ZeroMOUSE",
    none: "No cat flap match",
    empty: "No events",
    empty_filtered: "No events for this filter",
    error: "Loading failed",
    wrong: "Wrong",
    right: "Right",
    unrate: "Remove rating",
    delete: "Delete",
    cancel: "Cancel",
    confirm_wrong:
      "Report this event as incorrectly classified? Your feedback helps to improve the detection.",
    confirm_delete: "Delete this event permanently?",
    load_more: "Load older",
    loading: "Loading …",
    filters: "Filters",
    filters_desc: "Use filters to narrow down results by event type",
    favorites_only: "Show favorites only",
    favorites_desc: "Shows all favorites, regardless of the other filters.",
    reset: "Reset",
    failed: "Action failed",
    pause: "pause or resume the animation",
  },
};

// Same icons as the app's filter dialog
const ICONS = {
  clean: "mdi:login",
  prey: "mdi:close-octagon-outline",
  undecidable: "mdi:eye-off-outline",
  hand: "mdi:hand-back-right-outline",
  out: "mdi:logout",
};

const COLORS = {
  prey: "var(--error-color, #db4437)",
  clean: "var(--success-color, #43a047)",
  undecidable: "var(--warning-color, #ffa600)",
};

// The app's event groups (the integration sends each event's group); like the
// app, "leaving detected" is only checked by default with hidden events enabled
const FILTER_GROUPS = ["clean", "prey", "undecidable", "hand", "out"];
const DEFAULT_GROUPS = ["clean", "prey", "undecidable", "hand"];

const sameGroups = (a, b) => a.length === b.length && a.every((g) => b.includes(g));

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

function storageGet(key) {
  try {
    return JSON.parse(window.localStorage.getItem(key));
  } catch (err) {
    return null;
  }
}

function storageSet(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch (err) {
    // private mode etc.: filters are just not remembered
  }
}

// Reload when a ZeroMOUSE event or a flap passage changes.
function dataSignature(hass, sources) {
  const parts = [];
  for (const [id, ent] of Object.entries(hass.entities || {})) {
    if (ent.platform === "zeromouse" && id.startsWith("sensor.")) {
      const ev = hass.states[id]?.attributes?.event_id;
      if (ev) parts.push(ev);
    }
  }
  for (const c of sources || []) {
    const st = hass.states[c.entity];
    parts.push(st ? `${st.last_updated}` : "");
  }
  return parts.join("|");
}

function formatTime(hass, language, iso, withSeconds) {
  const tz = hass?.config?.time_zone;
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
  const locale = language === "en" ? "en-GB" : "de-DE";
  return new Intl.DateTimeFormat(locale, opts).format(new Date(iso)).replace(",", "");
}

// Card language: explicit option, else the Home Assistant language
function resolveLanguage(config, hass) {
  if (config?.language && LABELS[config.language]) return config.language;
  const lang = (hass?.locale?.language || hass?.language || navigator.language || "en").toLowerCase();
  return lang.startsWith("de") ? "de" : "en";
}

// Small stable string hash (for storage keys)
function hashString(text) {
  let h = 5381;
  for (let i = 0; i < text.length; i++) h = ((h << 5) + h + text.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

// Config passed to the backend (it ignores display options like icon/color)
function correlateParams(cfg) {
  const params = {};
  if (cfg.correlate?.length) {
    params.correlate = cfg.correlate;
    params.window_before = cfg.window_before;
    params.window_after = cfg.window_after;
  }
  return params;
}

/* ------------------------------------------------------------------------ */
/* Event gallery                                                             */
/* ------------------------------------------------------------------------ */

class ZeroMouseEventsCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._events = [];
    this._cursor = null;
    this._frames = new Map(); // event_id -> frame state, see _frameState
    this._blobs = new Map(); // image url -> object URL
    this._queue = [];
    this._workers = 0;
    this._pending = {}; // event_id -> "confirm-wrong" | "confirm-delete" | "busy"
    this._notice = {}; // event_id -> message
    this._showFilters = false;
    this._loadToken = 0; // bumped on every new list (filter change, reload)
    this._refreshSeq = 0;
    this._appliedRefresh = 0;
  }

  static getStubConfig() {
    return { limit: 10, fps: 2 };
  }

  setConfig(config) {
    this._config = {
      limit: 10,
      fps: 2,
      show_hidden: false,
      show_filter: true,
      show_actions: true,
      remember_filter: true,
      window_before: 60,
      window_after: 180,
      ...config,
      correlate: Array.isArray(config.correlate) ? config.correlate : [],
    };
    this._language = resolveLanguage(this._config, this._hass);
    this._t = LABELS[this._language];
    this._defaultGroups = this._config.show_hidden ? [...DEFAULT_GROUPS, "out"] : DEFAULT_GROUPS;
    const configured = {
      classifications: this._groups(this._config.filter?.classifications),
      favorites_only: !!this._config.filter?.favorites_only,
    };
    this._configuredFilter = configured;
    // Remembered per card: title, configured filter and dashboard path
    this._storageKey =
      "zeromouse-events-card:" +
      (this._config.storage_key ||
        hashString(
          JSON.stringify([this._config.title || "", configured, window.location.pathname])
        ));
    const saved = this._config.remember_filter ? storageGet(this._storageKey) : null;
    this._filter = saved
      ? { classifications: this._groups(saved.classifications), favorites_only: !!saved.favorites_only }
      : configured;
    this._render();
  }

  // Valid groups of a list; nothing (also from older versions) means the default
  _groups(list) {
    const groups = FILTER_GROUPS.filter((g) => (list || []).includes(g));
    return groups.length ? groups : this._defaultGroups;
  }

  _filterActive() {
    return this._filter.favorites_only || !sameGroups(this._filter.classifications, this._defaultGroups);
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    const language = resolveLanguage(this._config, hass);
    if (language !== this._language) {
      this._language = language;
      this._t = LABELS[language];
      this._render();
    }
    const sig = dataSignature(hass, this._config.correlate);
    if (sig !== this._sig) {
      this._sig = sig;
      if (first) this._reload();
      else this._refreshTop();
    }
  }

  getCardSize() {
    return 2 + Math.ceil(this._config.limit / 2) * 5;
  }

  getGridOptions() {
    return { columns: "full" };
  }

  connectedCallback() {
    clearTimeout(this._cleanupTimer);
    const interval = Math.max(100, 1000 / (Number(this._config?.fps) || 2));
    this._timer = setInterval(() => this._tick(), interval);
    this._reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    this._observer = new IntersectionObserver((entries) => this._onVisible(entries), {
      rootMargin: "300px",
    });
    this._observeAll();
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    this._observer?.disconnect();
    this._observer = null;
    // Home Assistant detaches cards temporarily (view changes): free the
    // pictures only if the card stays away for a while
    this._cleanupTimer = setTimeout(() => this._freeImages(), 60000);
  }

  _freeImages() {
    for (const obj of this._blobs.values()) URL.revokeObjectURL(obj);
    this._blobs.clear();
    this._queue = [];
    for (const st of this._frames.values()) {
      st.slots.fill(null);
      st.queued = false;
      clearTimeout(st.evictTimer);
    }
  }

  _params(extra = {}) {
    return {
      type: "zeromouse/events",
      limit: this._config.limit,
      include_hidden: !!this._config.show_hidden,
      classifications: this._filter.classifications,
      favorites_only: this._filter.favorites_only,
      ...correlateParams(this._config),
      ...extra,
    };
  }

  // First page with the current filter (filter changed or first load)
  async _reload() {
    if (!this._hass) return;
    const token = ++this._loadToken;
    this._loading = true;
    this._loadingMore = false;
    this._moreError = null;
    this._render();
    try {
      const result = await this._hass.callWS(this._params());
      if (token !== this._loadToken) return;
      this._setEvents(result.events);
      this._cursor = result.cursor;
      this._error = null;
    } catch (err) {
      if (token !== this._loadToken) return;
      console.error("zeromouse-events-card", err);
      this._error = err.message || String(err);
    }
    this._loading = false;
    this._render();
    if (this._refreshPending) {
      this._refreshPending = false;
      this._refreshTop();
    }
  }

  // New events or passages: merge the newest page into the loaded list
  async _refreshTop() {
    if (!this._hass) return;
    if (this._loading) {
      this._refreshPending = true;
      return;
    }
    const token = this._loadToken;
    const seq = ++this._refreshSeq;
    try {
      // Without a list yet this becomes the list (and needs its cursor)
      const result = await this._hass.callWS(
        this._params({ keep_cursor: !this._events.length })
      );
      if (token !== this._loadToken || seq < this._appliedRefresh) return;
      this._appliedRefresh = seq;
      const byId = new Map(this._events.map((e) => [e.event_id, e]));
      const overlap = result.events.some((e) => byId.has(e.event_id));
      if (this._events.length && !overlap && result.cursor !== null) {
        // More new events than one page (e.g. a sleeping tablet): start over
        this._reload();
        return;
      }
      const fresh = [];
      for (const e of result.events) {
        if (byId.has(e.event_id)) Object.assign(byId.get(e.event_id), e);
        else fresh.push(e);
      }
      if (!this._events.length) this._cursor = result.cursor;
      this._setEvents([...fresh, ...this._events]);
      this._render();
    } catch (err) {
      console.warn("zeromouse-events-card: refresh failed", err);
    }
  }

  async _loadMore() {
    if (!this._cursor || this._loadingMore) return;
    const token = this._loadToken;
    this._loadingMore = true;
    this._moreError = null;
    this._render();
    try {
      const result = await this._hass.callWS(this._params({ cursor: this._cursor }));
      if (token !== this._loadToken) return;
      const known = new Set(this._events.map((e) => e.event_id));
      this._setEvents([...this._events, ...result.events.filter((e) => !known.has(e.event_id))]);
      this._cursor = result.cursor;
    } catch (err) {
      if (token !== this._loadToken) return;
      console.error("zeromouse-events-card", err);
      this._loadingMore = false;
      // An expired list (after a restart) starts over
      if (err.code === "invalid_cursor") {
        this._reload();
        return;
      }
      this._moreError = err.message || String(err);
    }
    this._loadingMore = false;
    this._render();
  }

  _setEvents(events) {
    events.sort((a, b) => (b.time || "").localeCompare(a.time || ""));
    this._events = events;
    const ids = new Set(events.map((e) => e.event_id));
    for (const id of [...this._frames.keys()]) {
      if (!ids.has(id)) this._dropFrames(id);
    }
  }

  _revokeSlots(st) {
    for (const url of st.urls) {
      const obj = this._blobs.get(url);
      if (obj) URL.revokeObjectURL(obj);
      this._blobs.delete(url);
    }
    st.slots.fill(null);
    st.queued = false;
  }

  _dropFrames(id) {
    const st = this._frames.get(id);
    if (st) {
      clearTimeout(st.evictTimer);
      this._revokeSlots(st);
    }
    this._frames.delete(id);
    this._queue = this._queue.filter((job) => job.id !== id);
  }

  _imageUrl(e, idx) {
    return `/api/zeromouse/image/${encodeURIComponent(e.entry_id)}/${encodeURIComponent(
      e.device_id
    )}/${encodeURIComponent(e.event_id)}/${encodeURIComponent(idx)}`;
  }

  _frameState(e) {
    const order = (e.images || []).length
      ? [...e.images]
      : e.title_image != null
        ? [e.title_image]
        : [];
    const key = JSON.stringify([order, e.title_image]);
    let st = this._frames.get(e.event_id);
    if (st && st.key !== key) {
      // The event got more pictures (it was still being uploaded)
      this._revokeSlots(st);
      st = null;
    }
    if (!st) {
      st = {
        key,
        urls: order.map((idx) => this._imageUrl(e, idx)),
        slots: new Array(order.length).fill(null),
        pos: Math.max(0, order.indexOf(e.title_image)),
        paused: !!this._reducedMotion,
        visible: false,
        queued: false,
        retryAt: 0,
        evictTimer: null,
      };
      this._frames.set(e.event_id, st);
    }
    return st;
  }

  _observeAll() {
    if (!this._observer) return;
    this._observer.disconnect();
    for (const box of this.shadowRoot.querySelectorAll(".media")) this._observer.observe(box);
  }

  // Load pictures only for tiles that are (nearly) on screen, free them again
  // when a tile stayed out of view for a minute.
  _onVisible(entries) {
    for (const entry of entries) {
      const id = entry.target.dataset.event;
      const st = this._frames.get(id);
      if (!st) continue;
      st.visible = entry.isIntersecting;
      clearTimeout(st.evictTimer);
      if (st.visible) {
        this._queueFrames(id, st);
      } else {
        st.evictTimer = setTimeout(() => {
          if (!st.visible) this._revokeSlots(st);
        }, 60000);
      }
    }
  }

  _queueFrames(id, st) {
    if (st.queued || Date.now() < st.retryAt) return;
    st.queued = true;
    st.urls.forEach((url, k) => {
      if (st.slots[k]) return;
      // Title picture first, then the rest
      this._queue[k === st.pos ? "unshift" : "push"]({ id, k, url });
    });
    this._pump();
  }

  _pump() {
    while (this._workers < 4 && this._queue.length) {
      const job = this._queue.shift();
      const st = this._frames.get(job.id);
      if (!st || st.urls[job.k] !== job.url || !st.visible || st.slots[job.k]) {
        if (st && !st.visible) st.queued = false;
        continue;
      }
      this._workers++;
      this._fetchBlob(job.url)
        .then((obj) => {
          const current = this._frames.get(job.id);
          if (!current || current.urls[job.k] !== job.url) {
            // The event left the list meanwhile
            URL.revokeObjectURL(obj);
            this._blobs.delete(job.url);
            return;
          }
          current.slots[job.k] = obj;
          if (job.k === current.pos) this._showFrame(job.id);
        })
        .catch(() => {
          // Try the missing pictures again later (cloud hiccup, not uploaded yet)
          const current = this._frames.get(job.id);
          if (current) {
            current.queued = false;
            current.retryAt = Date.now() + 60000;
          }
        })
        .finally(() => {
          this._workers--;
          this._pump();
        });
    }
  }

  async _fetchBlob(url) {
    if (this._blobs.has(url)) return this._blobs.get(url);
    const resp = await this._hass.fetchWithAuth(url);
    if (!resp.ok) throw new Error(`${resp.status}`);
    const obj = URL.createObjectURL(await resp.blob());
    this._blobs.set(url, obj);
    return obj;
  }

  _tick() {
    for (const [id, st] of this._frames) {
      if (!st.visible) continue;
      if (!st.queued && st.slots.some((slot) => !slot) && Date.now() >= st.retryAt) {
        this._queueFrames(id, st);
      }
      if (st.paused || st.slots.filter(Boolean).length < 2) continue;
      do {
        st.pos = (st.pos + 1) % st.slots.length;
      } while (!st.slots[st.pos]);
      this._showFrame(id);
    }
  }

  _showFrame(id) {
    const st = this._frames.get(id);
    const box = this.shadowRoot.querySelector(`.media[data-event="${CSS.escape(id)}"]`);
    const url = st?.slots[st.pos];
    if (!box || !url) return;
    const img = box.querySelector("img");
    if (img.src !== url) img.src = url;
    img.classList.add("ready");
    box.querySelector(".count").textContent = `${st.pos + 1}/${st.slots.length}`;
  }

  async _act(e, action) {
    const t = this._t;
    // Like the app: tapping the active rating again removes it
    const target = { right: "correct", wrong: "incorrect" }[action];
    const rating = target && e.rating === target ? "none" : target;
    const confirm = action === "delete" || (action === "wrong" && rating !== "none");
    if (this._config.confirm !== false && confirm) {
      if (this._pending[e.event_id] !== `confirm-${action}`) {
        this._pending[e.event_id] = `confirm-${action}`;
        this._render();
        return;
      }
    }
    this._pending[e.event_id] = "busy";
    this._render();
    try {
      if (action === "delete") {
        await this._hass.callService("zeromouse", "delete_event", {
          device_id: e.ha_device_id,
          event_id: e.event_id,
        });
        this._setEvents(this._events.filter((x) => x.event_id !== e.event_id));
      } else {
        await this._hass.callService("zeromouse", "rate_event", {
          device_id: e.ha_device_id,
          event_id: e.event_id,
          rating,
        });
        e.rating = rating === "none" ? null : rating;
      }
      delete this._notice[e.event_id];
    } catch (err) {
      console.error("zeromouse-events-card", err);
      this._notice[e.event_id] = `${t.failed}: ${err.message || err}`;
    }
    delete this._pending[e.event_id];
    this._render();
  }

  _setFilter(filter) {
    this._filter = filter;
    if (this._config.remember_filter) storageSet(this._storageKey, filter);
    this._cursor = null;
    // Clear the list so loading and errors of the new filter are visible
    this._setEvents([]);
    this._reload();
  }

  // Key of the focused control, to restore focus after a re-render
  _focusKey() {
    const el = this.shadowRoot.activeElement;
    if (!el) return null;
    if (el.dataset?.group) return `[data-group="${el.dataset.group}"]`;
    if (el.hasAttribute?.("data-favorites")) return "[data-favorites]";
    if (el.dataset?.action && el.dataset?.event)
      return `[data-action="${el.dataset.action}"][data-event="${CSS.escape(el.dataset.event)}"]`;
    if (el.classList?.contains("media")) return `.media[data-event="${CSS.escape(el.dataset.event)}"]`;
    for (const cls of ["more", "reset", "filter-btn", "no", "yes"]) {
      if (el.classList?.contains(cls)) return `.${cls}`;
    }
    return null;
  }

  _render() {
    if (!this._config) return;
    const focus = this._focusKey();
    const t = this._t;
    const cfg = this._config;
    const active = this._filterActive();
    let body;
    if (this._error && !this._events.length) {
      body = `<div class="msg">${esc(t.error)}: ${esc(this._error)}</div>`;
    } else if (this._loading && !this._events.length) {
      body = `<div class="msg">${esc(t.loading)}</div>`;
    } else if (!this._events.length) {
      body = `<div class="msg">${this._hass ? esc(active ? t.empty_filtered : t.empty) : ""}</div>`;
    } else {
      const banner = this._error
        ? `<div class="banner">${esc(t.error)}: ${esc(this._error)}</div>`
        : "";
      const moreLabel = this._loadingMore
        ? t.loading
        : this._moreError
          ? `${t.load_more} – ${t.failed}`
          : t.load_more;
      const more = this._cursor
        ? `<button class="more" ${this._loadingMore ? "disabled" : ""}>
             <ha-icon icon="${this._loadingMore ? "mdi:loading" : "mdi:plus"}"></ha-icon>
             <span>${esc(moreLabel)}</span>
           </button>`
        : "";
      body = `${banner}<div class="grid">${this._events.map((e) => this._renderEvent(e)).join("")}${more}</div>`;
    }
    const header =
      cfg.title || cfg.show_filter
        ? `<div class="header"><span class="name">${esc(cfg.title || "")}</span>${
            cfg.show_filter
              ? `<button class="filter-btn${active ? " active" : ""}" title="${esc(t.filters)}"
                   aria-label="${esc(t.filters)}" aria-expanded="${this._showFilters}">
                   <ha-icon icon="mdi:filter-variant"></ha-icon>${active ? `<span class="badge">${this._filter.favorites_only ? "♥" : this._filter.classifications.length}</span>` : ""}
                 </button>`
              : ""
          }</div>`
        : "";
    const filters = this._showFilters ? this._renderFilters() : "";
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { padding: 16px; }
        .header { display: flex; align-items: center; justify-content: space-between;
                  font-size: 20px; font-weight: 500; margin: 0 0 12px; min-height: 36px; }
        button { font: inherit; color: inherit; }
        .filter-btn { position: relative; border: none; background: none; cursor: pointer;
                      padding: 6px; border-radius: 50%; color: var(--secondary-text-color); }
        .filter-btn.active { color: var(--primary-color); }
        .filter-btn:hover { background: var(--secondary-background-color); }
        .badge { position: absolute; top: 0; right: 0; min-width: 16px; height: 16px;
                 border-radius: 8px; background: var(--primary-color); color: var(--text-primary-color, #fff);
                 font-size: 11px; line-height: 16px; text-align: center; }
        .filters { border: 1px solid var(--divider-color); border-radius: 12px; padding: 12px 16px;
                   margin-bottom: 16px; }
        .filters .desc { color: var(--secondary-text-color); font-size: 14px; text-align: center;
                         margin-bottom: 8px; }
        .frow { display: flex; align-items: center; gap: 12px; padding: 8px 0; cursor: pointer;
                font-size: 16px; }
        .frow span { flex: 1; }
        .frow.muted { opacity: .5; }
        .frow small { display: block; color: var(--secondary-text-color); font-size: 13px; }
        .frow input { width: 20px; height: 20px; accent-color: var(--primary-color); cursor: pointer; }
        .frow ha-icon.prey { color: var(--error-color, #db4437); }
        .filters hr { border: none; border-top: 1px solid var(--divider-color); margin: 8px 0; }
        .reset { width: 100%; margin-top: 8px; padding: 10px; border: none; border-radius: 10px;
                 background: var(--secondary-background-color); font-weight: 600; cursor: pointer; }
        .banner { color: var(--error-color, #db4437); margin-bottom: 12px; font-size: 14px; }
        .grid { display: grid; gap: 16px;
                grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); }
        .ev { border-radius: 16px; overflow: hidden;
              background: var(--secondary-background-color);
              box-shadow: var(--ha-card-box-shadow, none); }
        .media { position: relative; aspect-ratio: 4 / 3; background: #000; cursor: pointer; }
        .media:focus-visible { outline: 3px solid var(--primary-color); outline-offset: -3px; }
        .media img { width: 100%; height: 100%; object-fit: cover; display: block;
                     opacity: 0; transition: opacity .2s; }
        .media img.ready { opacity: 1; }
        .count { position: absolute; right: 8px; bottom: 8px; font-size: 12px;
                 color: #fff; background: rgba(0,0,0,.45); border-radius: 8px;
                 padding: 1px 6px; font-variant-numeric: tabular-nums; }
        .paused .count::after { content: " ❚❚"; }
        .fav { position: absolute; right: 8px; top: 8px; color: #fff;
               filter: drop-shadow(0 0 2px rgba(0,0,0,.6)); }
        .info { padding: 10px 12px 12px; }
        .title { display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 16px; }
        .title ha-icon { --mdc-icon-size: 22px; }
        .meta { color: var(--secondary-text-color); font-size: 13px; margin-top: 2px; }
        .corr { display: flex; align-items: center; gap: 6px; margin-top: 8px; font-size: 13px; }
        .corr.none { color: var(--secondary-text-color); }
        .dot { width: 10px; height: 10px; border-radius: 50%; flex: none; }
        .actions { display: flex; gap: 14px; margin-top: 10px; }
        .act { display: flex; flex-direction: column; align-items: center; gap: 3px; border: none;
               background: none; cursor: pointer; color: var(--secondary-text-color); font-size: 12px; padding: 0; }
        .act .circle { width: 36px; height: 36px; border-radius: 50%; display: flex;
                       align-items: center; justify-content: center;
                       background: var(--card-background-color, #fff); }
        .act.on-wrong .circle { background: var(--error-color, #db4437); color: #fff; }
        .act.on-right .circle { background: var(--success-color, #43a047); color: #fff; }
        .act:disabled { opacity: .5; cursor: default; }
        .confirm { margin-top: 10px; font-size: 13px; }
        .confirm .row { display: flex; gap: 8px; margin-top: 6px; }
        .confirm button { flex: 1; padding: 6px; border-radius: 8px; border: none; cursor: pointer;
                          background: var(--card-background-color, #fff); }
        .confirm button.yes { background: var(--error-color, #db4437); color: #fff; }
        .notice { color: var(--error-color, #db4437); font-size: 12px; margin-top: 6px; }
        .more { display: flex; flex-direction: column; align-items: center; justify-content: center;
                gap: 8px; min-height: 200px; border-radius: 16px; cursor: pointer;
                border: 2px dashed var(--divider-color); background: none;
                color: var(--secondary-text-color); font-size: 15px; }
        .more ha-icon { --mdc-icon-size: 48px; }
        .more:disabled { cursor: progress; }
        .msg { color: var(--secondary-text-color); padding: 8px 0; }
      </style>
      <ha-card>${header}${filters}${body}</ha-card>`;
    this._bind();
    for (const id of this._frames.keys()) this._showFrame(id);
    this._observeAll();
    if (focus) this.shadowRoot.querySelector(focus)?.focus();
  }

  _renderFilters() {
    const t = this._t;
    const selected = this._filter.classifications;
    // At least one group stays checked
    const rows = FILTER_GROUPS.map((g) => {
      const on = selected.includes(g);
      const muted = this._filter.favorites_only ? " muted" : "";
      return `<label class="frow${muted}"><ha-icon class="${g}" icon="${ICONS[g]}"></ha-icon>
        <span>${esc(t[g])}</span>
        <input type="checkbox" data-group="${g}" ${on ? "checked" : ""}
          ${on && selected.length === 1 ? "disabled" : ""}></label>`;
    }).join("");
    return `<div class="filters">
      <div class="desc">${esc(t.filters_desc)}</div>
      ${rows}
      <hr>
      <label class="frow"><span>${esc(t.favorites_only)}<small>${esc(t.favorites_desc)}</small></span>
        <input type="checkbox" data-favorites ${this._filter.favorites_only ? "checked" : ""}></label>
      <button class="reset">${esc(t.reset)}</button>
    </div>`;
  }

  _renderMatch(e) {
    const t = this._t;
    if (!this._config.correlate.length && !e.match) return "";
    const m = e.match;
    if (!m) return `<div class="corr none">${esc(t.none)}</div>`;
    const source = this._config.correlate.find(
      (c) => (m.entity_id && c.entity === m.entity_id) || (c.name || c.entity) === m.name
    );
    const dot = `<span class="dot" style="background:${esc(source?.color || "var(--primary-color)")}"></span>`;
    if (m.method === "zeromouse") {
      return `<div class="corr">${dot}<b>${esc(m.name)}</b> · ${esc(t.by_zeromouse)}</div>`;
    }
    const dir = m.direction === "out" ? ` ${esc(t.left)}` : m.direction === "in" ? ` ${esc(t.in)}` : "";
    const sign = m.delta >= 0 ? "+" : "−";
    return `<div class="corr">${dot}<b>${esc(m.name)}</b>${dir} · ${esc(
      this._config.flap_name || t.flap
    )} ${esc(formatTime(this._hass, this._language, m.time, true))} (${sign}${Math.round(
      Math.abs(m.delta)
    )} s)</div>`;
  }

  _renderActions(e) {
    const t = this._t;
    if (!this._config.show_actions || !e.ha_device_id) return "";
    const pending = this._pending[e.event_id];
    const notice = this._notice[e.event_id]
      ? `<div class="notice">${esc(this._notice[e.event_id])}</div>`
      : "";
    if (pending === "confirm-wrong" || pending === "confirm-delete") {
      const action = pending.slice(8);
      return `<div class="confirm" data-event="${esc(e.event_id)}">
        ${esc(action === "delete" ? t.confirm_delete : t.confirm_wrong)}
        <div class="row"><button class="no">${esc(t.cancel)}</button>
        <button class="yes" data-action="${action}">${esc(action === "delete" ? t.delete : t.wrong)}</button></div>
      </div>${notice}`;
    }
    const busy = pending === "busy" ? "disabled" : "";
    const btn = (action, icon, label, cls, pressed) =>
      `<button class="act ${cls}" data-action="${action}" data-event="${esc(e.event_id)}" ${busy}
         aria-label="${esc(label)}"${pressed === undefined ? "" : ` aria-pressed="${pressed}"`}
         ${pressed ? `title="${esc(t.unrate)}"` : ""}>
         <span class="circle"><ha-icon icon="${icon}"></ha-icon></span>${esc(label)}</button>`;
    return `<div class="actions">
      ${btn("wrong", "mdi:close", t.wrong, e.rating === "incorrect" ? "on-wrong" : "", e.rating === "incorrect")}
      ${btn("right", "mdi:check", t.right, e.rating === "correct" ? "on-right" : "", e.rating === "correct")}
      ${btn("delete", "mdi:delete-outline", t.delete, "")}
    </div>${notice}`;
  }

  _renderEvent(e) {
    const t = this._t;
    // Title like the app: by group ("early" is "No prey detected" there)
    const group = e.group || "undecidable";
    const color = COLORS[group] || "var(--secondary-text-color)";
    const icon = ICONS[group] || "mdi:cat";
    const label = t[group] || group;
    const when = e.time ? formatTime(this._hass, this._language, e.time, false) : "";
    const st = this._frameState(e);
    return `
      <div class="ev">
        <div class="media${st.paused ? " paused" : ""}" data-event="${esc(e.event_id)}"
             role="button" tabindex="0" aria-pressed="${st.paused}"
             aria-label="${esc(`${label}, ${when}: ${t.pause}`)}">
          <img alt="${esc(label)}">
          ${e.is_favorite ? `<ha-icon class="fav" icon="mdi:heart"></ha-icon>` : ""}
          <span class="count"></span>
        </div>
        <div class="info">
          <div class="title"><ha-icon icon="${icon}" style="color:${color}"></ha-icon>
            <span>${esc(label)}</span></div>
          <div class="meta">${esc(e.device_name)} | ${esc(when)}</div>
          ${this._renderMatch(e)}
          ${this._renderActions(e)}
        </div>
      </div>`;
  }

  _bind() {
    const root = this.shadowRoot;
    root.querySelector(".filter-btn")?.addEventListener("click", () => {
      this._showFilters = !this._showFilters;
      this._render();
    });
    for (const box of root.querySelectorAll(".filters input[data-group]")) {
      box.addEventListener("change", () => {
        const groups = [...root.querySelectorAll(".filters input[data-group]:checked")].map(
          (b) => b.dataset.group
        );
        if (groups.length) this._setFilter({ ...this._filter, classifications: groups });
      });
    }
    root.querySelector(".filters input[data-favorites]")?.addEventListener("change", (ev) => {
      this._setFilter({ ...this._filter, favorites_only: ev.target.checked });
    });
    root.querySelector(".filters .reset")?.addEventListener("click", () => {
      this._setFilter({ ...this._configuredFilter });
    });
    root.querySelector(".more")?.addEventListener("click", () => this._loadMore());
    for (const box of root.querySelectorAll(".media")) {
      const toggle = () => {
        const st = this._frames.get(box.dataset.event);
        if (!st) return;
        st.paused = !st.paused;
        box.classList.toggle("paused", st.paused);
        box.setAttribute("aria-pressed", String(st.paused));
      };
      box.addEventListener("click", toggle);
      box.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          toggle();
        }
      });
    }
    const byId = (id) => this._events.find((e) => e.event_id === id);
    for (const btn of root.querySelectorAll(".act")) {
      btn.addEventListener("click", () => {
        const e = byId(btn.dataset.event);
        if (e) this._act(e, btn.dataset.action);
      });
    }
    for (const box of root.querySelectorAll(".confirm")) {
      const e = byId(box.dataset.event);
      if (!e) continue;
      box.querySelector(".no").addEventListener("click", () => {
        delete this._pending[e.event_id];
        this._render();
      });
      box.querySelector(".yes").addEventListener("click", (ev) => {
        this._act(e, ev.currentTarget.dataset.action);
      });
    }
  }
}

/* ------------------------------------------------------------------------ */
/* Timeline                                                                  */
/* ------------------------------------------------------------------------ */

/*
 * type: custom:zeromouse-timeline-card
 * days: 10
 * correlate:
 *   - entity: binary_sensor.tiger
 *     name: Tiger
 *     icon: /local/zeromouse/tiger-{class}.webp   # optional
 * unknown_icon: /local/zeromouse/unknown.webp     # optional
 */
const TL_CLASSES = ["clean", "prey", "undecidable"];
const TL_COLORS = { clean: "#4cae2c", prey: "#e3161b", undecidable: "#f98407" };
const TL_TEXT = {
  de: {
    title: "Wer kam wann – mit oder ohne Beute",
    title_plain: "ZeroMOUSE-Ereignisse – mit oder ohne Beute",
    unknown: "Unbekannt",
    events: "Ereignisse",
    prey: "Beute",
    time: "Uhrzeit",
    loading: "Lade …",
    error: "Fehler beim Laden",
    weekdays: ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"],
    note:
      "Hinweis: Bei „Beute erkannt“ und „Nicht entscheidbar“ sperrt ZeroMOUSE die Klappe – die Katzenklappe " +
      "meldet dann keinen Durchgang. Diese Ereignisse erscheinen deshalb als „Unbekannt“, außer ZeroMOUSE " +
      "erkennt die Katze selbst.",
  },
  en: {
    title: "Who came when – with or without prey",
    title_plain: "ZeroMOUSE events – with or without prey",
    unknown: "Unknown",
    events: "Events",
    prey: "Prey",
    time: "Time of day",
    loading: "Loading …",
    error: "Loading failed",
    weekdays: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
    note:
      "Note: on “Prey detected” and “Inconclusive” ZeroMOUSE blocks the flap, so the cat flap never " +
      "reports a passage. These events are therefore shown as “Unknown” unless ZeroMOUSE recognises " +
      "the cat itself.",
  },
};
const MAX_TIMELINE_EVENTS = 20000;

class ZeroMouseTimelineCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._events = null;
  }

  static getStubConfig() {
    return { days: 10 };
  }

  setConfig(config) {
    this._userConfig = {
      ...config,
      correlate: Array.isArray(config.correlate) ? config.correlate : [],
    };
    this._applyLanguage(resolveLanguage(this._userConfig, this._hass));
    this._render();
  }

  // Language dependent defaults; the user's options always win
  _applyLanguage(language) {
    this._language = language;
    const text = TL_TEXT[language];
    this._t = text;
    this._labels = LABELS[language];
    const hasCats = this._userConfig.correlate.length > 0;
    this._config = {
      days: 10,
      title: hasCats ? text.title : text.title_plain,
      window_before: 60,
      window_after: 180,
      unknown_icon: null,
      unknown_name: hasCats ? text.unknown : text.events,
      night_start: 22,
      night_end: 6,
      note: hasCats ? text.note : "",
      ...this._userConfig,
    };
  }

  set hass(hass) {
    this._hass = hass;
    const language = resolveLanguage(this._userConfig, hass);
    if (language !== this._language) {
      this._applyLanguage(language);
      this._render();
    }
    const sig = dataSignature(hass, this._config.correlate);
    if (sig !== this._sig) {
      this._sig = sig;
      this._load();
    }
  }

  connectedCallback() {
    this._scheduleMidnight();
  }

  disconnectedCallback() {
    clearTimeout(this._midnightTimer);
  }

  // A new day needs a new row (and moves the time window): reload after midnight
  _scheduleMidnight() {
    clearTimeout(this._midnightTimer);
    const p = this._parts(Date.now());
    const msToMidnight = ((24 - p.hour) * 3600 + 5) * 1000;
    this._midnightTimer = setTimeout(() => {
      this._load();
      this._scheduleMidnight();
    }, Math.min(msToMidnight, 24 * 3600 * 1000));
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
        const since = new Date(Date.now() - (cfg.days * 24 + 2) * 3600 * 1000);
        const params = {
          type: "zeromouse/events",
          since: since.toISOString(),
          limit: 1000,
          include_hidden: true,
          ...correlateParams(cfg),
        };
        let events = [];
        let cursor = null;
        do {
          const result = await this._hass.callWS(cursor ? { ...params, cursor } : params);
          events = events.concat(result.events);
          cursor = result.cursor;
        } while (cursor && events.length < MAX_TIMELINE_EVENTS);
        // Grouped like the app, e.g. "early" counts as "no prey detected"
        this._events = events
          .map((e) => ({ ...e, cls: e.group || e.classification }))
          .filter((e) => TL_CLASSES.includes(e.cls) && e.time);
        this._error = null;
      } catch (err) {
        console.error("zeromouse-timeline-card", err);
        this._error = err.message || String(err);
      }
      try {
        this._render();
      } catch (err) {
        console.error("zeromouse-timeline-card", err);
        this._events = null;
        this._error = err.message || String(err);
        this._render();
      }
    })();
    try {
      await this._loading;
    } finally {
      this._loading = null;
      if (this._reloadPending) {
        this._reloadPending = false;
        this._load();
      }
    }
  }

  // Cat config of a match: by entity (flap) or by name (ZeroMOUSE recognition)
  _catOf(match) {
    if (!match) return null;
    return (
      this._config.correlate.find(
        (c) => (match.entity_id && c.entity === match.entity_id) || (c.name || c.entity) === match.name
      ) || null
    );
  }

  // One round marker: picture if configured, otherwise a coloured initial
  _marker(cat, cls, cx, cy, size) {
    const r = size / 2;
    const tpl = cat ? cat.icon : this._config.unknown_icon;
    const o = [];
    if (tpl) {
      o.push(`<image href="${esc(tpl.replace("{class}", cls))}" x="${cx - r}" y="${cy - r}" width="${size}" height="${size}" clip-path="url(#c)"/>`);
      if (!tpl.includes("{class}") && cls) {
        o.push(`<circle cx="${cx}" cy="${cy}" r="${r - 1}" fill="none" stroke="${TL_COLORS[cls]}" stroke-width="3"/>`);
      }
      return o.join("");
    }
    const hasCats = this._config.correlate.length > 0;
    const fill = cat || !hasCats ? TL_COLORS[cls] || "#9b9ea4" : "#9b9ea4";
    o.push(`<circle cx="${cx}" cy="${cy}" r="${r - 1}" fill="${fill}"/>`);
    if (!cat && hasCats && cls) {
      o.push(`<circle cx="${cx}" cy="${cy}" r="${r - 1}" fill="none" stroke="${TL_COLORS[cls]}" stroke-width="3"/>`);
    }
    const letter = cat ? (cat.name || cat.entity).charAt(0).toUpperCase() : hasCats ? "?" : "";
    if (letter) {
      o.push(`<text x="${cx}" y="${cy + size * 0.18}" text-anchor="middle" class="letter" font-size="${size * 0.5}">${esc(letter)}</text>`);
    }
    return o.join("");
  }

  _svg() {
    const cfg = this._config;
    const cats = cfg.correlate;
    const hasCats = cats.length > 0;
    // Rows by calendar date in the HA time zone (DST days have 23 or 25 hours)
    const today = this._parts(Date.now());
    const [ty, tm, td] = today.key.split("-").map(Number);
    const days = [];
    const pad = (n) => String(n).padStart(2, "0");
    for (let i = 0; i < cfg.days; i++) {
      // Pure calendar arithmetic, independent of the browser's time zone
      const d = new Date(Date.UTC(ty, tm - 1, td - i));
      const [y, m, day] = [d.getUTCFullYear(), pad(d.getUTCMonth() + 1), pad(d.getUTCDate())];
      days.push({
        key: `${y}-${m}-${day}`,
        label: `${this._t.weekdays[d.getUTCDay()]} ${day}.${m}.`,
        date: `${day}.${m}.${y}`,
      });
    }
    const rowOf = Object.fromEntries(days.map((d, i) => [d.key, i]));

    // Lanes inside a day row: cats around the centre, unknown in the middle
    const keyOf = (c) => c.entity || c.name;
    const half = Math.ceil(cats.length / 2);
    const order = [...cats.slice(0, half).map(keyOf), null, ...cats.slice(half).map(keyOf)];
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
    const laneY = (entity) => (order.indexOf(entity) - (order.length - 1) / 2) * laneStep;
    const plotW = W - ML - MR;
    const H = MT + days.length * ROW_H + MB;
    const x = (h) => ML + (h / 24) * plotW;

    const counts = { unknown: 0, prey: 0, total: 0 };
    cats.forEach((c) => (counts[keyOf(c)] = 0));
    const marks = [];
    for (const e of this._events || []) {
      const t = Date.parse(e.time);
      const p = this._parts(t);
      const row = rowOf[p.key];
      if (row === undefined) continue;
      const cat = this._catOf(e.match);
      counts[cat ? keyOf(cat) : "unknown"]++;
      counts.total++;
      if (e.cls === "prey") counts.prey++;
      const name = cat ? cat.name || cat.entity : cfg.unknown_name;
      const label = this._labels[e.cls] || e.cls;
      let how = "";
      if (e.match?.method === "flap") {
        how = ` · ${cfg.flap_name || this._labels.flap} ${e.match.delta >= 0 ? "+" : "−"}${Math.round(Math.abs(e.match.delta))} s`;
      } else if (e.match?.method === "zeromouse") {
        how = ` · ${this._labels.by_zeromouse}`;
      }
      marks.push({
        cx: x(p.hour),
        cy: MT + row * ROW_H + ROW_H / 2 + laneY(cat ? keyOf(cat) : null),
        cls: e.cls,
        cat,
        title: `${name} · ${label} · ${p.date} ${p.hm}${how}`,
        t,
      });
    }
    // Draw older first so newer events end up on top
    marks.sort((a, b) => a.t - b.t);

    const o = [];
    o.push(`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(cfg.title)}">`);
    o.push(`<defs><clipPath id="c" clipPathUnits="objectBoundingBox"><circle cx=".5" cy=".5" r=".5"/></clipPath></defs>`);
    const first = days[days.length - 1];
    const last = days[0];
    const summary = hasCats
      ? [
          ...cats.map((c) => `${c.name || c.entity} ${counts[keyOf(c)]}`),
          `${cfg.unknown_name} ${counts.unknown}`,
        ].join(" · ")
      : `${cfg.unknown_name} ${counts.total}`;
    o.push(`<text x="${ML}" y="36" class="ink" font-size="22" font-weight="700">${esc(cfg.title)}</text>`);
    o.push(`<text x="${ML}" y="60" class="ink2" font-size="14">${esc(first.date.slice(0, 6))} – ${esc(last.date)} · ${esc(summary)} · ${esc(this._t.prey)} ${counts.prey}</text>`);
    // Legend: cats, then colours
    let lx = ML;
    const ly = 92;
    if (hasCats) {
      for (const c of [...cats, null]) {
        const name = c ? c.name || c.entity : cfg.unknown_name;
        o.push(this._marker(c, "clean", lx + 12, ly, 24));
        o.push(`<text x="${lx + 30}" y="${ly + 5}" class="ink" font-size="14">${esc(name)}</text>`);
        lx += 30 + name.length * 8 + 26;
      }
      lx += 16;
    }
    for (const cls of TL_CLASSES) {
      o.push(`<circle cx="${lx + 7}" cy="${ly}" r="7" fill="${TL_COLORS[cls]}"/>`);
      o.push(`<text x="${lx + 20}" y="${ly + 5}" class="ink2" font-size="14">${esc(this._labels[cls])}</text>`);
      lx += 20 + this._labels[cls].length * 7.4 + 22;
    }
    noteLines.forEach((line, i) => {
      o.push(`<text x="${ML}" y="${ly + 34 + i * 18}" class="ink2 note" font-size="13">${esc(line)}</text>`);
    });
    days.forEach((d, i) => {
      const y = MT + i * ROW_H;
      o.push(`<rect x="${ML}" y="${y}" width="${plotW}" height="${ROW_H}" class="${i % 2 ? "band" : "surface"}"/>`);
      o.push(`<text x="${ML - 14}" y="${y + ROW_H / 2 + 5}" text-anchor="end" class="ink" font-size="14">${esc(d.label)}</text>`);
    });
    const nightW = (a, b) =>
      `<rect x="${x(a)}" y="${MT}" width="${x(b) - x(a)}" height="${days.length * ROW_H}" class="night"/>`;
    o.push(nightW(0, cfg.night_end), nightW(cfg.night_start, 24));
    for (let h = 0; h <= 24; h += 3) {
      o.push(`<line x1="${x(h)}" x2="${x(h)}" y1="${MT}" y2="${MT + days.length * ROW_H}" class="grid"/>`);
      o.push(`<text x="${x(h)}" y="${MT + days.length * ROW_H + 22}" text-anchor="middle" class="ink2" font-size="13">${String(h).padStart(2, "0")}</text>`);
    }
    o.push(`<text x="${ML + plotW / 2}" y="${H - 6}" text-anchor="middle" class="ink2" font-size="13">${esc(this._t.time)}</text>`);
    for (const m of marks) {
      o.push(`<g class="mark"><title>${esc(m.title)}</title>${this._marker(m.cat, m.cls, m.cx, m.cy, ICON)}</g>`);
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
        .letter { fill: #fff; font-weight: 700; }
        .surface { fill: var(--card-background-color, #fff); }
        .band { fill: var(--secondary-background-color, #f4f3f0); opacity: .6; }
        .night { fill: var(--primary-text-color); opacity: .045; }
        .grid { stroke: var(--divider-color, #e5e4e0); stroke-width: 1; }
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
  name: "ZeroMOUSE events",
  description: "Events like in the app: pictures, filters, rating, load more",
});
window.customCards.push({
  type: "zeromouse-timeline-card",
  name: "ZeroMOUSE timeline",
  description: "Events per day with the cat (cat flap / ZeroMOUSE) and the prey result",
});
