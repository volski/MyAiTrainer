/**
 * AI Trainer — Home Assistant sidebar panel.
 *
 * A dependency-free web component. It talks to the integration's REST API
 * using the signed-in user's access token and renders a Hebrew RTL admin UI.
 */

const AI_TRAINER_CSS = `
:host {
  display: block;
  min-height: 100%;
  background: var(--primary-background-color, #f4f6fb);
  color: var(--primary-text-color, #0f172a);
}
* { box-sizing: border-box; }
#app {
  max-width: 1280px;
  margin: 0 auto;
  padding: 24px 20px 90px;
  font-family: var(--paper-font-body1_-_font-family, "Heebo", "Assistant", "Segoe UI", system-ui, sans-serif);
  transition: opacity .15s ease;
}
#app.busy { opacity: .55; pointer-events: none; }
.topbar {
  display: flex; align-items: center; justify-content: space-between;
  gap: 16px; flex-wrap: wrap; margin-bottom: 18px;
}
.brand { display: flex; align-items: center; gap: 14px; }
.logo {
  width: 54px; height: 54px; border-radius: 17px;
  background: linear-gradient(135deg, #10b981, #0ea5e9 65%, #6366f1);
  display: grid; place-items: center; font-size: 27px;
  box-shadow: 0 10px 26px rgba(14, 165, 233, .35);
}
h1 { font-size: 22px; margin: 0; letter-spacing: -.2px; }
.sub { color: var(--secondary-text-color, #64748b); font-size: 13px; margin-top: 3px; }
.chips { display: flex; gap: 8px; flex-wrap: wrap; }
.chip {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 7px 12px; border-radius: 999px; font-size: 12px; font-weight: 600;
  background: var(--card-background-color, #fff);
  border: 1px solid var(--divider-color, rgba(148, 163, 184, .3));
}
.chip .dot { width: 8px; height: 8px; border-radius: 50%; background: #94a3b8; }
.chip .dot.on { background: #10b981; box-shadow: 0 0 0 3px rgba(16, 185, 129, .18); }
.chip .dot.off { background: #ef4444; box-shadow: 0 0 0 3px rgba(239, 68, 68, .15); }
.chip .dot.warn { background: #f59e0b; }
.tabs {
  display: inline-flex; gap: 5px; padding: 5px; margin-bottom: 20px;
  background: var(--card-background-color, #fff); border-radius: 14px;
  border: 1px solid var(--divider-color, rgba(148, 163, 184, .2));
  box-shadow: 0 2px 10px rgba(15, 23, 42, .05);
  flex-wrap: wrap;
}
.tabs button {
  border: 0; background: transparent; color: var(--secondary-text-color, #64748b);
  padding: 9px 16px; border-radius: 10px; cursor: pointer;
  font: inherit; font-weight: 700; font-size: 13px; transition: .15s;
}
.tabs button:hover { background: rgba(148, 163, 184, .12); }
.tabs button.active { background: var(--primary-color, #0ea5e9); color: #fff; }
.grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 16px; }
.card {
  background: var(--card-background-color, #fff);
  border: 1px solid var(--divider-color, rgba(148, 163, 184, .2));
  border-radius: 18px; padding: 18px;
  box-shadow: 0 3px 16px rgba(15, 23, 42, .06);
}
.span-4 { grid-column: span 4; }
.span-6 { grid-column: span 6; }
.span-8 { grid-column: span 8; }
.span-12 { grid-column: span 12; }
.card h2, .card h3 { margin: 0 0 4px; font-size: 15px; }
.card .hint { color: var(--secondary-text-color, #64748b); font-size: 12px; line-height: 1.5; }
.card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 12px; }
.hero {
  grid-column: span 12; position: relative; overflow: hidden;
  background: linear-gradient(120deg, #047857 0%, #0284c7 55%, #4f46e5 100%);
  color: #fff; border: 0; padding: 26px;
}
.hero::after {
  content: ""; position: absolute; width: 380px; height: 380px; border-radius: 50%;
  background: radial-gradient(circle, rgba(255,255,255,.22), transparent 65%);
  top: -170px; left: -110px; pointer-events: none;
}
.hero h2 { font-size: 24px; margin: 0 0 6px; color: #fff; }
.hero p { margin: 0; opacity: .9; font-size: 13px; }
.hero-stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 22px; }
.hero-stat {
  background: rgba(255, 255, 255, .14); border: 1px solid rgba(255,255,255,.22);
  border-radius: 14px; padding: 12px 14px; backdrop-filter: blur(4px);
}
.hero-stat b { display: block; font-size: 24px; line-height: 1.1; }
.hero-stat span { font-size: 11px; opacity: .88; }
.stat-line { display: flex; align-items: baseline; gap: 8px; }
.stat-line b { font-size: 26px; line-height: 1; }
.stat-line span { color: var(--secondary-text-color, #64748b); font-size: 12px; }
.kv { display: flex; justify-content: space-between; gap: 10px; padding: 7px 0; font-size: 13px; border-bottom: 1px dashed var(--divider-color, rgba(148,163,184,.25)); }
.kv:last-child { border-bottom: 0; }
.kv span { color: var(--secondary-text-color, #64748b); }
.kv b { font-weight: 700; text-align: left; }
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  border: 1px solid transparent; border-radius: 10px; padding: 9px 14px;
  font: inherit; font-weight: 700; font-size: 13px; cursor: pointer;
  background: rgba(148, 163, 184, .15); color: var(--primary-text-color, #0f172a);
  transition: .15s; text-decoration: none;
}
.btn:hover { filter: brightness(1.04); transform: translateY(-1px); }
.btn.primary { background: var(--primary-color, #0ea5e9); color: #fff; box-shadow: 0 6px 16px rgba(14, 165, 233, .3); }
.btn.green { background: #059669; color: #fff; }
.btn.ghost { background: transparent; border-color: var(--divider-color, rgba(148,163,184,.4)); }
.btn.danger { background: rgba(239, 68, 68, .12); color: #dc2626; }
.btn.small { padding: 6px 10px; font-size: 12px; border-radius: 8px; }
.btn[disabled] { opacity: .5; pointer-events: none; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 14px; }
.toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 14px; }
.toolbar .grow { flex: 1 1 220px; }
input, select, textarea {
  width: 100%; padding: 11px 12px; border-radius: 10px;
  border: 1px solid var(--divider-color, rgba(148, 163, 184, .55));
  background: var(--secondary-background-color, #f8fafc);
  color: var(--primary-text-color, #0f172a); font: inherit; font-size: 13px;
  outline: none; transition: border-color .15s, box-shadow .15s;
}
input:focus, select:focus, textarea:focus {
  border-color: var(--primary-color, #0ea5e9);
  box-shadow: 0 0 0 3px rgba(14, 165, 233, .16);
}
textarea { resize: vertical; min-height: 74px; }
label.field { display: block; margin-bottom: 12px; }
label.field > span {
  display: block; font-size: 11px; font-weight: 700; letter-spacing: .2px;
  color: var(--secondary-text-color, #64748b); margin-bottom: 6px;
}
label.check { display: flex; align-items: center; gap: 9px; font-size: 13px; margin: 8px 0; cursor: pointer; }
label.check input { width: auto; accent-color: var(--primary-color, #0ea5e9); }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 14px; }
.form-grid .full { grid-column: 1 / -1; }
.section-title { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 800; margin: 4px 0 12px; }
.section-title .ico { font-size: 16px; }
.table-wrap { overflow-x: auto; border-radius: 14px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th {
  text-align: right; padding: 10px 10px; font-size: 11px; letter-spacing: .2px;
  color: var(--secondary-text-color, #64748b); font-weight: 800;
  border-bottom: 1px solid var(--divider-color, rgba(148, 163, 184, .3));
  white-space: nowrap;
}
td { padding: 12px 10px; border-bottom: 1px solid var(--divider-color, rgba(148, 163, 184, .18)); vertical-align: middle; }
tbody tr { cursor: pointer; transition: background .12s; }
tbody tr:hover { background: rgba(14, 165, 233, .06); }
tbody tr:last-child td { border-bottom: 0; }
.person { display: flex; align-items: center; gap: 10px; }
.avatar {
  width: 36px; height: 36px; border-radius: 50%; flex: 0 0 36px;
  display: grid; place-items: center; font-weight: 800; font-size: 13px;
  background: rgba(14, 165, 233, .14); color: #0284c7;
}
.person .who { font-weight: 700; line-height: 1.2; }
.person .phone { color: var(--secondary-text-color, #64748b); font-size: 11px; direction: ltr; text-align: right; }
.badge {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 4px 9px; border-radius: 999px; font-size: 11px; font-weight: 800;
  background: rgba(148, 163, 184, .16); color: var(--secondary-text-color, #475569);
  white-space: nowrap;
}
.badge.green { background: rgba(16, 185, 129, .14); color: #047857; }
.badge.amber { background: rgba(245, 158, 11, .16); color: #b45309; }
.badge.red { background: rgba(239, 68, 68, .13); color: #b91c1c; }
.badge.blue { background: rgba(14, 165, 233, .14); color: #0369a1; }
.badge.gray { background: rgba(148, 163, 184, .16); color: #475569; }
.mini-bar { width: 88px; height: 7px; border-radius: 99px; background: rgba(148, 163, 184, .25); overflow: hidden; }
.mini-bar > i { display: block; height: 100%; border-radius: 99px; background: linear-gradient(90deg, #0ea5e9, #10b981); }
.muted { color: var(--secondary-text-color, #64748b); }
.small { font-size: 12px; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; direction: ltr; unicode-bidi: embed; }
.empty { text-align: center; padding: 34px 14px; color: var(--secondary-text-color, #64748b); }
.empty .big { font-size: 34px; display: block; margin-bottom: 8px; }
.log-list { display: flex; flex-direction: column; gap: 2px; }
.log-item { display: flex; gap: 10px; align-items: flex-start; padding: 9px 4px; border-bottom: 1px dashed var(--divider-color, rgba(148,163,184,.22)); font-size: 12px; }
.log-item:last-child { border-bottom: 0; }
.log-item .ldot { width: 8px; height: 8px; border-radius: 50%; margin-top: 5px; flex: 0 0 8px; background: #0ea5e9; }
.log-item.warning .ldot { background: #f59e0b; }
.log-item.error .ldot { background: #ef4444; }
.log-item .lbody { flex: 1; min-width: 0; }
.log-item .lbody b { font-weight: 700; }
.log-item time { color: var(--secondary-text-color, #64748b); font-size: 10px; white-space: nowrap; }
.skeleton { border-radius: 14px; height: 96px; background: linear-gradient(90deg, rgba(148,163,184,.12), rgba(148,163,184,.24), rgba(148,163,184,.12)); background-size: 200% 100%; animation: shimmer 1.3s infinite; margin-bottom: 14px; }
@keyframes shimmer { to { background-position: -200% 0; } }
.error-card { border: 1px solid rgba(239, 68, 68, .35); background: rgba(239, 68, 68, .07); }
.error-card h2 { color: #b91c1c; }
.modal-backdrop { position: fixed; inset: 0; background: rgba(2, 6, 23, .55); backdrop-filter: blur(3px); z-index: 20; }
.modal-card {
  position: fixed; z-index: 21; top: 50%; left: 50%; transform: translate(-50%, -50%);
  width: min(940px, 94vw); max-height: 89vh; overflow: auto;
  background: var(--card-background-color, #fff); color: var(--primary-text-color, #0f172a);
  border-radius: 20px; padding: 20px; box-shadow: 0 30px 90px rgba(2, 6, 23, .5);
  outline: none;
}
.modal-card.small { width: min(480px, 94vw); }
.modal-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
.modal-head h2 { margin: 0; font-size: 19px; }
.modal-head .sub { margin-top: 4px; }
.x {
  border: 0; background: rgba(148, 163, 184, .16); color: inherit; width: 34px; height: 34px;
  border-radius: 50%; cursor: pointer; font-size: 18px; line-height: 1; flex: 0 0 34px;
}
.seg { display: inline-flex; gap: 4px; padding: 4px; border-radius: 11px; background: rgba(148, 163, 184, .12); margin-bottom: 16px; flex-wrap: wrap; }
.seg button { border: 0; background: transparent; color: var(--secondary-text-color, #64748b); padding: 7px 13px; border-radius: 8px; font: inherit; font-weight: 700; font-size: 12px; cursor: pointer; }
.seg button.active { background: var(--card-background-color, #fff); color: var(--primary-text-color, #0f172a); box-shadow: 0 2px 8px rgba(15,23,42,.1); }
.metric-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; margin-bottom: 16px; }
.metric { background: var(--secondary-background-color, #f8fafc); border-radius: 12px; padding: 10px 12px; border: 1px solid var(--divider-color, rgba(148,163,184,.2)); }
.metric b { display: block; font-size: 16px; line-height: 1.2; }
.metric span { color: var(--secondary-text-color, #64748b); font-size: 10px; }
.meals { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.meal { background: var(--secondary-background-color, #f8fafc); border-radius: 12px; padding: 11px 13px; border: 1px solid var(--divider-color, rgba(148,163,184,.2)); }
.meal .mh { display: flex; justify-content: space-between; gap: 8px; font-weight: 800; font-size: 12px; margin-bottom: 5px; }
.meal .mh span { color: var(--secondary-text-color, #64748b); font-weight: 600; }
.meal ul { margin: 0; padding-inline-start: 16px; color: var(--secondary-text-color, #475569); font-size: 12px; line-height: 1.55; }
.plan-text { white-space: pre-wrap; font-family: inherit; font-size: 12px; line-height: 1.65; background: var(--secondary-background-color, #f8fafc); border-radius: 12px; padding: 14px; border: 1px solid var(--divider-color, rgba(148,163,184,.25)); }
details summary { cursor: pointer; font-weight: 700; font-size: 12px; color: var(--primary-color, #0ea5e9); margin: 12px 0 8px; }
.chat { display: flex; flex-direction: column; gap: 4px; max-height: 340px; overflow-y: auto; padding: 6px 4px; }
.msg { max-width: 84%; padding: 9px 12px; border-radius: 14px; font-size: 12.5px; line-height: 1.55; white-space: pre-wrap; word-break: break-word; }
.msg.assistant { background: rgba(14, 165, 233, .1); border: 1px solid rgba(14, 165, 233, .16); margin-inline-end: auto; }
.msg.user { background: rgba(16, 185, 129, .1); border: 1px solid rgba(16, 185, 129, .18); margin-inline-start: auto; }
.msg time { display: block; font-size: 9px; color: var(--secondary-text-color, #64748b); margin-top: 4px; }
.danger-zone { border: 1px dashed rgba(239, 68, 68, .45); border-radius: 14px; padding: 13px; margin-top: 18px; }
.danger-zone h3 { color: #b91c1c; }
.notice { padding: 11px 13px; border-radius: 12px; background: rgba(245, 158, 11, .1); border: 1px solid rgba(245, 158, 11, .3); font-size: 12px; line-height: 1.55; }
.sticky-save { position: sticky; bottom: 0; background: linear-gradient(180deg, transparent, var(--primary-background-color, #f4f6fb) 35%); padding: 18px 0 4px; display: flex; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }
.divider { height: 1px; background: var(--divider-color, rgba(148,163,184,.25)); margin: 14px 0; }
#busy { position: fixed; inset-inline: 0; top: 0; height: 3px; z-index: 40; opacity: 0; transition: opacity .15s; }
#busy.on { opacity: 1; background: linear-gradient(90deg, transparent, var(--primary-color, #0ea5e9), #10b981, transparent); background-size: 50% 100%; animation: busy 1s linear infinite; }
@keyframes busy { from { background-position: -50% 0; } to { background-position: 150% 0; } }
.toast {
  position: fixed; bottom: 24px; left: 50%; transform: translate(-50%, 18px);
  background: #0f172a; color: #fff; padding: 12px 18px; border-radius: 12px;
  font-size: 13px; font-weight: 600; max-width: min(560px, 90vw);
  box-shadow: 0 14px 40px rgba(2,6,23,.35); z-index: 50;
  opacity: 0; pointer-events: none; transition: .22s ease; text-align: center;
  font-family: var(--paper-font-body1_-_font-family, "Heebo", "Segoe UI", system-ui, sans-serif);
}
.toast.show { opacity: 1; transform: translate(-50%, 0); }
.toast.error { background: #b91c1c; }
.toast.success { background: #047857; }
@media (max-width: 960px) {
  .span-4, .span-6, .span-8 { grid-column: 1 / -1; }
  .hero-stats { grid-template-columns: 1fr 1fr; }
  .metric-grid { grid-template-columns: repeat(3, 1fr); }
  .meals { grid-template-columns: 1fr; }
}
@media (max-width: 640px) {
  #app { padding: 16px 12px 80px; }
  .form-grid { grid-template-columns: 1fr; }
  .hero h2 { font-size: 20px; }
  .hide-sm { display: none; }
  .tabs { width: 100%; }
  .tabs button { flex: 1; padding: 9px 8px; }
  .metric-grid { grid-template-columns: repeat(2, 1fr); }
  .modal-card { padding: 16px; }
}
`;

const GOAL_LABELS = {
  lose_weight: "ירידה במשקל",
  build_muscle: "בניית שריר",
  maintain: "שמירה על המשקל",
  health: "אורח חיים בריא",
};
const STATUS_LABELS = {
  active: "פעיל",
  paused: "מושהה",
  onboarding: "בהיכרות",
};
const STATUS_BADGE = { active: "green", paused: "amber", onboarding: "blue" };

function esc(value) {
  return String(value === null || value === undefined ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function fmt(value, digits) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return number.toLocaleString("he-IL", {
    maximumFractionDigits: digits === undefined ? 1 : digits,
  });
}

function fmtDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("he-IL", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function dash(value) {
  const text = String(value === null || value === undefined ? "" : value).trim();
  return text ? esc(text) : "—";
}

class AITrainerPanel extends HTMLElement {
  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
    this._hass = null;
    this._loaded = false;
    this._loading = false;
    this._busy = false;
    this._error = "";
    this._tab = "dashboard";
    this._config = null;
    this._users = [];
    this._logs = [];
    this._search = "";
    this._selectedId = null;
    this._selectedUser = null;
    this._userTab = "profile";
    this._addUserOpen = false;
    this._toastTimer = null;
    this._boundClick = this._onClick.bind(this);
    this._boundSubmit = this._onSubmit.bind(this);
    this._boundInput = this._onInput.bind(this);
    this._boundKey = this._onKeyDown.bind(this);
  }

  connectedCallback() {
    if (!this._root.getElementById("app")) {
      this._root.innerHTML =
        '<style>' + AI_TRAINER_CSS + '</style>' +
        '<div id="busy"></div>' +
        '<div id="app"></div>' +
        '<div id="toast" class="toast"></div>';
      this._app = this._root.getElementById("app");
      this._busyEl = this._root.getElementById("busy");
      this._toastEl = this._root.getElementById("toast");
      this._root.addEventListener("click", this._boundClick);
      this._root.addEventListener("submit", this._boundSubmit);
      this._root.addEventListener("input", this._boundInput);
      this._root.addEventListener("change", this._boundInput);
      document.addEventListener("keydown", this._boundKey);
    }
    this._render();
    if (this._hass && !this._loaded) this._loadAll();
  }

  disconnectedCallback() {
    document.removeEventListener("keydown", this._boundKey);
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first && this.isConnected && !this._loaded) {
      this._loadAll();
    }
  }

  get hass() {
    return this._hass;
  }

  set narrow(value) {
    this._narrow = value;
  }

  // ------------------------------------------------------------------
  // API
  // ------------------------------------------------------------------
  _token() {
    return this._hass && this._hass.auth && this._hass.auth.data
      ? this._hass.auth.data.access_token
      : (this._hass && this._hass.auth ? this._hass.auth.accessToken : null);
  }

  async _fetchResponse(path, options) {
    const opts = Object.assign({}, options || {});
    const headers = Object.assign(
      { "Content-Type": "application/json" },
      opts.headers || {}
    );
    const url = "/api/ai_trainer" + path;

    // 1. Preferred: Home Assistant's official fetchWithAuth.
    // Handles access token lifecycle, automatic refresh before expiry, and retry.
    // This prevents sending expired bearer tokens that cause HA to ban the IP into ip_bans.yaml.
    if (this._hass && typeof this._hass.fetchWithAuth === "function") {
      opts.headers = headers;
      return await this._hass.fetchWithAuth(url, opts);
    }

    // 2. Fallback: refresh access token manually if expired before dispatching native fetch.
    if (this._hass && this._hass.auth) {
      const auth = this._hass.auth;
      if (auth.expired && typeof auth.refreshAccessToken === "function") {
        try {
          await auth.refreshAccessToken();
        } catch (err) {
          console.warn("[ai-trainer] Token refresh failed:", err);
        }
      }
      const token =
        (auth.data && auth.data.access_token) || auth.accessToken || this._token();
      if (token) {
        headers["Authorization"] = "Bearer " + token;
      }
    } else {
      const staticToken = this._token();
      if (staticToken) {
        headers["Authorization"] = "Bearer " + staticToken;
      }
    }

    opts.headers = headers;
    return await fetch(url, opts);
  }

  async _api(path, options) {
    let response;
    try {
      response = await this._fetchResponse(path, options);
    } catch (err) {
      throw new Error(err && err.message ? err.message : "שגיאת תקשורת עם השרת.");
    }

    // Critical security & ban protection:
    // If Home Assistant returns 401 (Unauthorized) or 403 (Forbidden), immediately
    // stop the auto-refresh interval timer. This guarantees that background loops never
    // repeatedly send unauthenticated requests and trigger Home Assistant's ip_bans.yaml brute-force ban!
    if (response.status === 401) {
      throw new Error("פג תוקף החיבור למערכת (401). יש לרענן את העמוד.");
    }

    if (response.status === 403) {
      throw new Error("נדרשת הרשאת מנהל כדי לנהל את המאמן.");
    }

    let data = {};
    try {
      data = await response.json();
    } catch (err) {
      data = {};
    }
    if (!response.ok) {
      throw new Error(data && data.error ? data.error : "שגיאה " + response.status);
    }
    return data;
  }

  async _loadAll() {
    if (this._loading) return;
    this._loading = true;
    this._error = "";
    this._render();
    try {
      // Execute sequentially to prevent blasting multiple requests if auth fails
      const config = await this._api("/config");
      const users = await this._api("/users");
      const logs = await this._api("/logs?limit=80");
      this._config = config;
      this._users = (users && users.users) || [];
      this._logs = (logs && logs.logs) || [];
      this._loaded = true;
    } catch (err) {
      this._error = err && err.message ? err.message : "שגיאה בטעינה";
    } finally {
      this._loading = false;
      this._render();
    }
  }

  async _reloadUsers() {
    const data = await this._api("/users");
    this._users = (data && data.users) || [];
  }

  async _refreshLogs() {
    const data = await this._api("/logs?limit=100");
    this._logs = (data && data.logs) || [];
    if (this._tab === "logs") this._render();
  }

  async _openUser(id) {
    this._selectedId = id;
    this._selectedUser = null;
    this._userTab = "profile";
    this._render();
    try {
      const data = await this._api("/users/" + encodeURIComponent(id));
      this._selectedUser = data.user;
      this._render();
    } catch (err) {
      this._selectedId = null;
      this._toast(err.message || "לא ניתן לטעון את המשתמש", "error");
      this._render();
    }
  }

  async _reloadSelected() {
    if (!this._selectedId) return;
    const data = await this._api("/users/" + encodeURIComponent(this._selectedId));
    this._selectedUser = data.user;
    this._render();
  }

  // ------------------------------------------------------------------
  // Rendering
  // ------------------------------------------------------------------
  _render() {
    if (!this._app) return;
    this._app.innerHTML = this._view();
    this._syncProviderUi();
    this._applySearch();
  }

  _view() {
    if (this._loading && !this._config) return this._viewLoading();
    if (this._error && !this._config) return this._viewError();
    return (
      this._viewTopbar() +
      this._viewTabs() +
      '<main>' + this._viewMain() + "</main>" +
      this._viewModal()
    );
  }

  _viewLoading() {
    return (
      '<div class="topbar"><div class="brand"><div class="logo">🤖</div>' +
      '<div><h1>מאמן AI</h1><div class="sub">טוען נתונים…</div></div></div></div>' +
      '<div class="skeleton" style="height:150px"></div>' +
      '<div class="grid"><div class="skeleton span-4"></div>' +
      '<div class="skeleton span-4"></div><div class="skeleton span-4"></div></div>'
    );
  }

  _viewError() {
    return (
      '<div class="topbar"><div class="brand"><div class="logo">🤖</div>' +
      '<div><h1>מאמן AI</h1><div class="sub">לוח ניהול</div></div></div></div>' +
      '<div class="card error-card"><h2>לא ניתן לטעון את הנתונים</h2>' +
      '<p class="hint">' + esc(this._error) + '</p>' +
      '<div class="actions"><button class="btn primary" data-action="refresh">נסה שוב</button>' +
      '<button class="btn ghost" data-action="go-settings">בדיקת הגדרות</button></div></div>'
    );
  }

  _viewTopbar() {
    const cfg = this._config || {};
    const stats = cfg.stats || {};
    const settings = cfg.settings || {};
    const providerLabel = settings.provider_label || settings.provider || "ספק AI";
    const providerOn = !!stats.provider_ready;
    const waOn = !!stats.whatsapp_available;
    return (
      '<div class="topbar">' +
      '<div class="brand"><div class="logo">🤖</div><div>' +
      '<h1>מאמן AI</h1><div class="sub">מאמן תזונה, שתייה ואימונים בוואטסאפ · עברית</div>' +
      "</div></div>" +
      '<div class="chips">' +
      '<span class="chip"><i class="dot ' + (providerOn ? "on" : "warn") + '"></i>' +
      esc(providerLabel) + "</span>" +
      '<span class="chip"><i class="dot ' + (waOn ? "on" : "off") + '"></i>וואטסאפ</span>' +
      '<span class="chip"><i class="dot on"></i>' + esc(stats.users || 0) + " משתמשים</span>" +
      "</div></div>"
    );
  }

  _viewTabs() {
    const tabs = [
      ["dashboard", "סקירה"],
      ["users", "משתמשים"],
      ["settings", "הגדרות"],
      ["logs", "יומן"],
    ];
    return (
      '<div class="tabs">' +
      tabs
        .map(
          (tab) =>
            '<button data-action="tab" data-tab="' + tab[0] + '"' +
            (this._tab === tab[0] ? ' class="active"' : "") +
            ">" + tab[1] + "</button>"
        )
        .join("") +
      "</div>"
    );
  }

  _viewMain() {
    if (this._tab === "users") return this._viewUsers();
    if (this._tab === "settings") return this._viewSettings();
    if (this._tab === "logs") return this._viewLogs();
    return this._viewDashboard();
  }

  _viewDashboard() {
    const cfg = this._config || {};
    const stats = cfg.stats || {};
    const settings = cfg.settings || {};
    const providerOn = !!stats.provider_ready;
    const waOn = !!stats.whatsapp_available;
    const today = new Intl.DateTimeFormat("he-IL", {
      weekday: "long",
      day: "numeric",
      month: "long",
    }).format(new Date());
    const logs = (this._logs || []).slice(0, 6);

    return (
      '<section class="grid">' +
      '<div class="card hero"><h2>שלום 👋</h2>' +
      '<p>היום ' + esc(today) + " · המערכת מוכנה לשלוח תוכניות בעברית.</p>" +
      '<div class="hero-stats">' +
      this._heroStat(stats.users || 0, "סה״כ משתמשים") +
      this._heroStat(stats.active || 0, "פעילים") +
      this._heroStat(stats.onboarding || 0, "בתהליך היכרות") +
      this._heroStat(stats.messages_today || 0, "הודעות היום") +
      "</div></div>" +

      '<div class="card span-4"><div class="card-head"><div><h2>ספק AI</h2>' +
      '<div class="hint">' + esc(settings.effective_model || "לא נבחר מודל") + "</div></div>" +
      '<span class="badge ' + (providerOn ? "green" : "amber") + '">' +
      (providerOn ? "מוכן" : "לא מוגדר") + "</span></div>" +
      '<div class="kv"><span>ספק</span><b>' + esc(settings.provider_label || "—") + "</b></div>" +
      '<div class="kv"><span>מפתח API</span><b>' +
      (settings.api_key_set ? "שמור " + esc(settings.api_key_hint || "") : "לא הוגדר") +
      "</b></div>" +
      '<div class="kv"><span>טמפרטורה</span><b>' + fmt(settings.temperature, 1) + "</b></div>" +
      '<div class="actions"><button class="btn small primary" data-action="test-ai">בדוק חיבור</button>' +
      '<button class="btn small ghost" data-action="go-settings">הגדרות</button></div></div>' +

      '<div class="card span-4"><div class="card-head"><div><h2>וואטסאפ</h2>' +
      '<div class="hint">' + esc(settings.whatsapp_service || "whatsapp.send_message") + "</div></div>" +
      '<span class="badge ' + (waOn ? "green" : "red") + '">' +
      (waOn ? "מחובר" : "לא זמין") + "</span></div>" +
      '<div class="kv"><span>חשבון</span><b>' +
      esc(this._accountLabel(settings.whatsapp_account) || "ברירת מחדל") + "</b></div>" +
      '<div class="kv"><span>קבוצות</span><b>' +
      (settings.allow_groups ? "מאופשר" : "כבוי") + "</b></div>" +
      '<div class="kv"><span>תוכנית אחרונה</span><b>' + dash(stats.last_plan_date) + "</b></div>" +
      '<div class="actions"><button class="btn small ghost" data-action="test-whatsapp-first">שלח בדיקה</button>' +
      '<button class="btn small ghost" data-action="refresh">רענן</button></div></div>' +

      '<div class="card span-4"><div class="card-head"><div><h2>לוח זמנים</h2>' +
      '<div class="hint">לפי אזור הזמן של Home Assistant</div></div>' +
      '<span class="badge blue">יומי</span></div>' +
      '<div class="kv"><span>תוכנית יומית</span><b>' +
      (settings.enable_daily ? esc(settings.daily_time) : "כבוי") + "</b></div>" +
      '<div class="kv"><span>תזכורות מים</span><b>' +
      (settings.enable_water ? esc((settings.water_times || []).join(", ") || "—") : "כבוי") +
      "</b></div>" +
      '<div class="kv"><span>תזכורת אימון</span><b>' +
      (settings.enable_workout ? esc(settings.workout_time) : "כבוי") + "</b></div>" +
      '<div class="actions"><button class="btn small ghost" data-action="go-settings">ערוך לוח זמנים</button></div></div>' +

      '<div class="card span-12"><div class="card-head"><div><h2>פעילות אחרונה</h2>' +
      '<div class="hint">אירועים מהבוט, מהמתזמן ומה-API</div></div>' +
      '<button class="btn small ghost" data-action="tab" data-tab="logs">כל היומן</button></div>' +
      this._logList(logs, true) +
      "</div></section>"
    );
  }

  _heroStat(value, label) {
    return '<div class="hero-stat"><b>' + esc(value) + "</b><span>" + esc(label) + "</span></div>";
  }

  _accountLabel(account) {
    if (!account) return "";
    const cfg = this._config || {};
    const accounts = (cfg.whatsapp && cfg.whatsapp.accounts) || [];
    const found = accounts.find((item) => item.entry_id === account);
    return found ? found.title : account;
  }

  _viewUsers() {
    const users = this._users || [];
    const rows = users
      .map((user) => {
        const name = user.name || "ללא שם";
        const initial = name.trim().charAt(0) || "?";
        const goal = user.goal_text || user.goal_label || "—";
        const waterPercent = Math.max(0, Math.min(100, user.water_percent || 0));
        return (
          '<tr data-action="open-user" data-id="' + esc(user.id) + '" data-search="' +
          esc((name + " " + (user.phone || "") + " " + goal).toLowerCase()) + '">' +
          '<td><div class="person"><div class="avatar">' + esc(initial) + "</div><div>" +
          '<div class="who">' + esc(name) + '</div><div class="phone">' + esc(user.phone || "") +
          "</div></div></div></td>" +
          '<td><span class="badge ' + (STATUS_BADGE[user.status] || "gray") + '">' +
          esc(STATUS_LABELS[user.status] || user.status) + "</span></td>" +
          '<td>' + esc(goal) + "</td>" +
          '<td class="hide-sm">' + fmt(user.weight_kg) + ' ק״ג · ' + fmt(user.height_cm, 0) + " ס״מ</td>" +
          '<td class="hide-sm">' + (user.bmi ? esc(user.bmi) + ' <span class="muted small">' + esc(user.bmi_category || "") + "</span>" : "—") + "</td>" +
          '<td><div class="mini-bar" title="' + waterPercent + '%"><i style="width:' + waterPercent + '%"></i></div>' +
          '<div class="muted small">' + fmt(user.water_done_ml / 1000, 1) + "/" + fmt(user.water_target_ml / 1000, 1) + " ל׳</div></td>" +
          '<td>' + (user.streak ? "🔥 " + esc(user.streak) : "—") + "</td>" +
          '<td class="hide-sm">' + esc(fmtDate(user.updated_at)) + "</td>" +
          "</tr>"
        );
      })
      .join("");

    return (
      '<div class="card"><div class="toolbar">' +
      '<div class="grow"><input id="user-search" type="search" placeholder="חיפוש לפי שם, טלפון או מטרה…" value="' + esc(this._search) + '"></div>' +
      '<button class="btn primary" data-action="add-user">+ משתמש חדש</button>' +
      '<button class="btn ghost" data-action="refresh">רענן</button></div>' +
      (users.length
        ? '<div class="table-wrap"><table><thead><tr><th>משתמש</th><th>סטטוס</th><th>מטרה</th>' +
          '<th class="hide-sm">משקל / גובה</th><th class="hide-sm">BMI</th><th>מים היום</th><th>רצף</th>' +
          '<th class="hide-sm">עודכן</th></tr></thead><tbody>' + rows + "</tbody></table></div>" +
          '<div id="no-results" class="empty" style="display:none"><span class="big">🔍</span>לא נמצאו משתמשים תואמים.</div>'
        : '<div class="empty"><span class="big">👥</span>אין משתמשים עדיין.<br>' +
          '<span class="small">שלחו הודעה לבוט בוואטסאפ, או הוסיפו משתמש ידנית.</span></div>') +
      "</div>"
    );
  }

  _viewSettings() {
    const cfg = this._config || {};
    const s = cfg.settings || {};
    const providers = cfg.providers || [];
    const accounts = (cfg.whatsapp && cfg.whatsapp.accounts) || [];
    const accountValue = s.whatsapp_account || "";
    let accountField;
    if (accounts.length) {
      const options = accounts
        .map(
          (account) =>
            '<option value="' + esc(account.entry_id) + '"' +
            (accountValue === account.entry_id ? " selected" : "") + ">" +
            esc((account.title || account.entry_id) + (account.number ? " (" + account.number + ")" : "")) +
            "</option>"
        )
        .join("");
      const extra = accountValue && !accounts.some((a) => a.entry_id === accountValue)
        ? '<option value="' + esc(accountValue) + '" selected>' + esc(accountValue) + " (לא מחובר)</option>"
        : "";
      accountField =
        '<select name="whatsapp_account"><option value="">ברירת מחדל</option>' + extra + options + "</select>";
    } else {
      accountField =
        '<input name="whatsapp_account" value="' + esc(accountValue) + '" placeholder="entry_id או מספר (אופציונלי)">';
    }

    return (
      '<form id="settings-form">' +
      '<div class="grid">' +

      '<div class="card span-6"><div class="section-title"><span class="ico">🧠</span>ספק AI</div>' +
      '<div class="form-grid">' +
      '<label class="field full"><span>ספק</span><select name="provider">' +
      providers
        .map(
          (provider) =>
            '<option value="' + esc(provider.id) + '"' +
            (s.provider === provider.id ? " selected" : "") + ">" + esc(provider.label) + "</option>"
        )
        .join("") +
      "</select></label>" +
      '<label class="field"><span>מודל</span>' +
      '<div style="display:flex;gap:6px;align-items:center;">' +
      '<input name="model" list="models-datalist" value="' + esc(s.model || "") + '" placeholder="ברירת מחדל של הספק" style="flex:1">' +
      '<button type="button" class="btn small ghost" data-action="fetch-models" title="טען רשימת מודלים מהספק" style="white-space:nowrap;padding:7px 10px;font-size:12px">🔄 רענן מודלים</button>' +
      '</div><datalist id="models-datalist"></datalist></label>' +
      '<label class="field"><span>מפתח API</span><input name="api_key" type="password" autocomplete="new-password" placeholder="' +
      (s.api_key_set ? "שמור " + esc(s.api_key_hint || "") + " — מלאו כדי להחליף" : "הדביקו מפתח API") + '"></label>' +
      '<div class="full"><p class="hint" data-provider-hint></p></div>' +
      '<label class="field full" data-field="base_url"><span>כתובת בסיס (Ollama / תואם OpenAI)</span>' +
      '<input name="base_url" value="' + esc(s.base_url || "") + '" placeholder="http://homeassistant.local:11434"></label>' +
      '<label class="field"><span>טמפרטורה</span><input name="temperature" type="number" min="0" max="2" step="0.1" value="' + esc(s.temperature) + '"></label>' +
      '<label class="field"><span>מקסימום טוקנים</span><input name="max_tokens" type="number" min="64" max="4000" step="1" value="' + esc(s.max_tokens) + '"></label>' +
      '<label class="check full"><input type="checkbox" name="clear_api_key"> מחק את המפתח השמור</label>' +
      "</div></div>" +

      '<div class="card span-6"><div class="section-title"><span class="ico">💬</span>וואטסאפ</div>' +
      '<label class="field"><span>שירות שליחה</span><input name="whatsapp_service" value="' + esc(s.whatsapp_service || "whatsapp.send_message") + '"></label>' +
      '<label class="field"><span>חשבון</span>' + accountField + "</label>" +
      '<label class="check"><input type="checkbox" name="allow_groups"' + (s.allow_groups ? " checked" : "") + "> אפשר הודעות מקבוצות</label>" +
      '<label class="field"><span>מספרים מורשים (ריק = כולם)</span><textarea name="allowed_numbers" placeholder="972501234567, 972521234567">' +
      esc((s.allowed_numbers || []).join(", ")) + "</textarea></label>" +
      '<div class="notice">הבוט משתמש בשירות <span class="mono">whatsapp.send_message</span> של FaserF/ha-whatsapp. ' +
      "אם הוואטסאפ לא מחובר, ההודעות ייכשלו והאירוע יופיע ביומן.</div>" +
      '<div class="actions"><input id="test-phone" placeholder="מספר לבדיקה (עם קידומת)" style="max-width:220px">' +
      '<button type="button" class="btn small ghost" data-action="test-whatsapp">שלח בדיקה</button></div></div>' +

      '<div class="card span-6"><div class="section-title"><span class="ico">🗓️</span>לוח זמנים</div>' +
      '<div class="form-grid">' +
      '<label class="check full"><input type="checkbox" name="enable_daily"' + (s.enable_daily ? " checked" : "") + "> שלח תוכנית יומית</label>" +
      '<label class="field"><span>שעת תוכנית</span><input name="daily_time" value="' + esc(s.daily_time || "08:00") + '" placeholder="08:00"></label>' +
      '<label class="field"><span>שעת אימון</span><input name="workout_time" value="' + esc(s.workout_time || "18:00") + '" placeholder="18:00"></label>' +
      '<label class="check full"><input type="checkbox" name="enable_water"' + (s.enable_water ? " checked" : "") + "> שלח תזכורות שתייה</label>" +
      '<label class="field full"><span>שעות תזכורת מים (מופרד בפסיקים)</span><input name="water_times" value="' +
      esc((s.water_times || []).join(", ")) + '" placeholder="10:00, 13:00, 16:00, 19:00"></label>' +
      '<label class="check full"><input type="checkbox" name="enable_workout"' + (s.enable_workout ? " checked" : "") + "> שלח תזכורת אימון</label>" +
      "</div></div>" +

      '<div class="card span-6"><div class="section-title"><span class="ico">🛡️</span>מגבלות ואופי</div>' +
      '<div class="form-grid">' +
      '<label class="field"><span>מקסימום משתמשים</span><input name="max_users" type="number" min="1" max="500" value="' + esc(s.max_users) + '"></label>' +
      '<label class="field"><span>השהיה בין קריאות AI (שניות)</span><input name="min_ai_interval" type="number" min="0" max="30" step="0.5" value="' + esc(s.min_ai_interval) + '"></label>' +
      '<label class="field full"><span>שם המאמן</span><input name="coach_name" value="' + esc(s.coach_name || "המאמן") + '"></label>' +
      '<label class="field full"><span>הנחיות נוספות למאמן</span><textarea name="system_prompt_extra" placeholder="למשל: העדף אוכל ים־תיכוני, קצר יותר, בלי אימוג׳ים">' +
      esc(s.system_prompt_extra || "") + "</textarea></label>" +
      "</div></div>" +

      '<div class="span-12 sticky-save">' +
      '<button type="button" class="btn ghost" data-action="test-ai">בדוק חיבור AI</button>' +
      '<button type="submit" class="btn primary">שמור הגדרות</button></div>' +
      "</div></form>"
    );
  }

  _viewLogs() {
    return (
      '<div class="card"><div class="toolbar"><div class="toolbar grow"><h2 style="margin:0">יומן פעילות</h2>' +
      '<div class="hint">100 האירועים האחרונים</div></div>' +
      '<button class="btn ghost" data-action="refresh-logs">רענן</button></div>' +
      this._logList(this._logs || [], false) + "</div>"
    );
  }

  _logList(logs, compact) {
    if (!logs || !logs.length) {
      return '<div class="empty"><span class="big">🗒️</span>אין אירועים עדיין.</div>';
    }
    return (
      '<div class="log-list">' +
      logs
        .map(
          (log) =>
            '<div class="log-item ' + esc(log.level || "info") + '"><i class="ldot"></i><div class="lbody">' +
            '<b>' + esc(log.event || "") + "</b> · " + esc(log.message || "") +
            (log.user ? ' <span class="muted small">(' + esc(log.user) + ")</span>" : "") +
            "</div><time>" + esc(fmtDate(log.ts)) + "</time></div>"
        )
        .join("") +
      "</div>" + (compact ? "" : "")
    );
  }

  _viewModal() {
    if (this._addUserOpen) return this._viewAddUserModal();
    if (!this._selectedId) return "";
    if (!this._selectedUser) {
      return (
        '<div class="modal-backdrop" data-action="close-modal"></div>' +
        '<div class="modal-card" role="dialog" aria-modal="true" tabindex="-1"><div class="skeleton"></div>' +
        '<div class="skeleton" style="height:220px"></div></div>'
      );
    }
    return this._viewUserModal(this._selectedUser);
  }

  _viewAddUserModal() {
    return (
      '<div class="modal-backdrop" data-action="close-modal"></div>' +
      '<div class="modal-card small" role="dialog" aria-modal="true" tabindex="-1">' +
      '<div class="modal-head"><div><h2>משתמש חדש</h2>' +
      '<div class="sub">המשתמש ייכנס לתהליך היכרות בעברית</div></div>' +
      '<button class="x" data-action="close-modal" aria-label="סגור">×</button></div>' +
      '<form id="add-user-form">' +
      '<label class="field"><span>שם</span><input name="name" placeholder="דנה"></label>' +
      '<label class="field"><span>מספר טלפון (עם קידומת מדינה)</span><input name="phone" required placeholder="972501234567" inputmode="tel"></label>' +
      '<label class="check"><input type="checkbox" name="send_greeting" checked> שלח הודעת פתיחה בוואטסאפ</label>' +
      '<div class="actions"><button type="submit" class="btn primary">צור משתמש</button>' +
      '<button type="button" class="btn ghost" data-action="close-modal">ביטול</button></div>' +
      "</form></div>"
    );
  }

  _viewUserModal(user) {
    const name = user.name || "ללא שם";
    const status = user.status || "unknown";
    const tabs = [
      ["profile", "פרופיל"],
      ["plan", "תוכנית"],
      ["chat", "שיחה"],
    ];
    let body = "";
    if (this._userTab === "plan") body = this._viewUserPlan(user);
    else if (this._userTab === "chat") body = this._viewUserChat(user);
    else body = this._viewUserProfile(user);

    return (
      '<div class="modal-backdrop" data-action="close-modal"></div>' +
      '<div class="modal-card" role="dialog" aria-modal="true" tabindex="-1">' +
      '<div class="modal-head"><div><h2>' + esc(name) + "</h2>" +
      '<div class="sub"><span class="mono">' + esc(user.phone || "") + "</span> · " +
      '<span class="badge ' + (STATUS_BADGE[status] || "gray") + '">' +
      esc(STATUS_LABELS[status] || status) + "</span>" +
      (user.created_at ? " · נוצר " + esc(fmtDate(user.created_at)) : "") +
      "</div></div>" +
      '<div class="actions" style="margin:0">' +
      '<button class="btn small ghost" data-action="toggle-status">' +
      (status === "paused" ? "▶️ הפעל" : "⏸️ השהה") + "</button>" +
      '<button class="x" data-action="close-modal" aria-label="סגור">×</button></div></div>' +

      '<div class="metric-grid">' +
      this._metric(user.goal_text || user.goal_label || "—", "מטרה") +
      this._metric(user.bmi || "—", "BMI") +
      this._metric(user.calories ? fmt(user.calories, 0) : "—", "קק״ל יעד") +
      this._metric(user.water_l ? fmt(user.water_l, 1) + " ל׳" : "—", "מים") +
      this._metric(user.streak || 0, "רצף ימים") +
      this._metric((user.workouts_week || 0) + "/" + (user.weekly_workouts || 0), "אימונים השבוע") +
      "</div>" +

      '<div class="seg">' +
      tabs
        .map(
          (tab) =>
            '<button type="button" data-action="user-tab" data-utab="' + tab[0] + '"' +
            (this._userTab === tab[0] ? ' class="active"' : "") + ">" + tab[1] + "</button>"
        )
        .join("") +
      "</div>" + body + "</div>"
    );
  }

  _metric(value, label) {
    return '<div class="metric"><b>' + esc(value) + "</b><span>" + esc(label) + "</span></div>";
  }

  _viewUserProfile(user) {
    const p = user.profile || {};
    const goalOptions = Object.keys(GOAL_LABELS)
      .map(
        (key) =>
          '<option value="' + key + '"' + (p.goal === key ? " selected" : "") + ">" +
          esc(GOAL_LABELS[key]) + "</option>"
      )
      .join("");
    return (
      '<form id="profile-form"><div class="form-grid">' +
      '<label class="field"><span>שם</span><input name="name" value="' + esc(user.name || "") + '"></label>' +
      '<label class="field"><span>מטרה</span><select name="goal">' + goalOptions + "</select></label>" +
      '<label class="field full"><span>תיאור מטרה חופשי</span><input name="goal_text" value="' + esc(p.goal_text || "") + '" placeholder="למשל: לרדת 5 קילו עד הקיץ"></label>' +
      '<label class="field"><span>משקל (ק״ג)</span><input name="weight_kg" type="number" min="25" max="350" step="0.1" value="' + esc(p.weight_kg || "") + '"></label>' +
      '<label class="field"><span>גובה (ס״מ)</span><input name="height_cm" type="number" min="100" max="250" step="1" value="' + esc(p.height_cm || "") + '"></label>' +
      '<label class="field"><span>גיל</span><input name="age" type="number" min="12" max="100" step="1" value="' + esc(p.age || "") + '"></label>' +
      '<label class="field"><span>מין</span><select name="sex">' +
      '<option value="unspecified"' + (p.sex === "unspecified" ? " selected" : "") + ">לא צוין</option>" +
      '<option value="male"' + (p.sex === "male" ? " selected" : "") + ">זכר</option>" +
      '<option value="female"' + (p.sex === "female" ? " selected" : "") + ">נקבה</option></select></label>" +
      '<label class="field"><span>רמת פעילות</span><select name="activity_level">' +
      '<option value="low"' + (p.activity_level === "low" ? " selected" : "") + ">נמוכה</option>" +
      '<option value="moderate"' + (p.activity_level === "moderate" ? " selected" : "") + ">בינונית</option>" +
      '<option value="high"' + (p.activity_level === "high" ? " selected" : "") + ">גבוהה</option></select></label>" +
      '<label class="field"><span>משקל יעד (ק״ג)</span><input name="target_weight_kg" type="number" min="25" max="350" step="0.1" value="' + esc(p.target_weight_kg || "") + '"></label>' +
      '<label class="field full"><span>העדפות / רגישויות / מגבלות</span><textarea name="restrictions" placeholder="למשל: צמחוני, אלרגיה לאגוזים">' + esc(p.restrictions || "") + "</textarea></label>" +
      '<label class="field full"><span>הערות פנימיות</span><textarea name="notes" placeholder="הערות שלא נשלחות למשתמש">' + esc(user.notes || "") + "</textarea></label>" +
      "</div><div class=\"actions\"><button type=\"submit\" class=\"btn primary\">שמור פרופיל</button>" +
      '<button type="button" class="btn ghost" data-action="user-tab" data-utab="plan">לתוכנית היומית</button></div></form>' +
      '<div class="danger-zone"><h3>אזור מסוכן</h3><p class="hint">איפוס מוחק פרופיל והתקדמות ומתחיל היכרות מחדש. מחיקה מסירה את המשתמש לצמיתות.</p>' +
      '<div class="actions"><button class="btn small ghost" data-action="reset-user">אפס משתמש</button>' +
      '<button class="btn small danger" data-action="delete-user">מחק משתמש</button></div></div>'
    );
  }

  _viewUserPlan(user) {
    const plan = user.plan;
    const sourceBadge = plan && plan.source === "ai"
      ? '<span class="badge blue">נוצר על ידי AI</span>'
      : '<span class="badge gray">תוכנית בסיס</span>';
    let content = '<div class="empty"><span class="big">📋</span>עוד לא נוצרה תוכנית ליום הזה.</div>';
    if (plan) {
      const meals = (plan.meals || [])
        .map(
          (meal) =>
            '<div class="meal"><div class="mh"><div>' + esc(meal.name || "ארוחה") +
            '</div><span>' + esc(meal.time || "") + (meal.kcal ? " · " + esc(meal.kcal) + ' קק״ל' : "") + "</span></div>" +
            "<ul>" + (meal.items || []).map((item) => "<li>" + esc(item) + "</li>").join("") + "</ul></div>"
        )
        .join("");
      const workout = plan.workout || {};
      const exercises = (workout.exercises || [])
        .map(
          (ex) =>
            "<li>" + esc(ex.name || "") +
            (ex.sets || ex.reps ? ' — <span class="muted">' + esc([ex.sets, ex.reps].filter(Boolean).join(" × ")) + "</span>" : "") +
            "</li>"
        )
        .join("");
      const tips = (plan.tips || []).map((tip) => "<li>" + esc(tip) + "</li>").join("");
      content =
        '<div class="card-head"><div><h3>' + esc(plan.focus || "התוכנית היומית") + "</h3>" +
        '<div class="hint">' + esc(plan.date || "") + " · " + esc(plan.water_l || "—") + ' ליטר מים</div></div>' + sourceBadge + "</div>" +
        '<div class="meals">' + meals + "</div>" +
        (workout.title
          ? '<div class="divider"></div><h3>🏋️ ' + esc(workout.title) +
            (workout.duration_min ? ' <span class="muted small">(' + esc(workout.duration_min) + " דק׳)</span>" : "") +
            "</h3><ul class=\"hint\">" + exercises + "</ul>"
          : "") +
        (tips ? '<div class="divider"></div><h3>💡 טיפים</h3><ul class="hint">' + tips + "</ul>" : "") +
        (user.plan_text
          ? '<details><summary>הצג את הודעת הוואטסאפ המלאה</summary><pre class="plan-text">' + esc(user.plan_text) + "</pre></details>"
          : "");
    }
    return (
      '<div class="actions" style="margin-top:0;margin-bottom:14px">' +
      '<button class="btn primary" data-action="plan-generate" data-send="1">צור ושלח עכשיו</button>' +
      '<button class="btn ghost" data-action="plan-generate" data-send="0">צור ללא שליחה</button>' +
      (user.plan_text ? '<button class="btn ghost" data-action="send-plan">שלח את התוכנית הקיימת</button>' : "") +
      "</div>" + content
    );
  }

  _viewUserChat(user) {
    const history = (user.history || [])
      .map(
        (entry) =>
          '<div class="msg ' + (entry.role === "user" ? "user" : "assistant") + '" dir="auto">' +
          esc(entry.content) + "<time>" + esc(fmtDate(entry.ts)) + "</time></div>"
      )
      .join("");
    return (
      '<div class="chat">' + (history || '<div class="empty">אין הודעות עדיין.</div>') + "</div>" +
      '<div class="divider"></div>' +
      '<form id="message-form"><label class="field"><span>שליחת הודעה ידנית (לא עוברת ב-AI)</span>' +
      '<textarea name="message" placeholder="הודעה ללקוח…" required></textarea></label>' +
      '<div class="actions"><button type="submit" class="btn primary">שלח בוואטסאפ</button></div></form>' +
      '<div class="divider"></div>' +
      '<form id="simulate-form"><label class="field"><span>סימולציית הודעת משתמש (הבוט יענה בוואטסאפ)</span>' +
      '<textarea name="text" placeholder="למשל: אכלתי שניצל וסלט" required></textarea></label>' +
      '<div class="actions"><button type="submit" class="btn ghost">הרץ סימולציה</button></div></form>'
    );
  }

  // ------------------------------------------------------------------
  // UI helpers
  // ------------------------------------------------------------------
  _syncProviderUi() {
    const form = this._app && this._app.querySelector("#settings-form");
    if (!form) return;
    const select = form.elements.namedItem("provider");
    if (!select) return;
    const chosen = select.value;
    const catalogue = (this._config && this._config.providers) || [];
    const meta = catalogue.find((item) => item.id === chosen) || {};
    const modelInput = form.elements.namedItem("model");
    if (modelInput) {
      modelInput.placeholder = meta.default_model
        ? "ברירת מחדל: " + meta.default_model
        : "שם מודל";
    }
    const baseRow = form.querySelector('[data-field="base_url"]');
    if (baseRow) baseRow.style.display = meta.supports_base_url ? "" : "none";
    const baseInput = form.elements.namedItem("base_url");
    if (baseInput) {
      baseInput.placeholder = meta.base_url || "http://homeassistant.local:11434";
    }
    const hint = form.querySelector("[data-provider-hint]");
    if (hint) {
      const keyNote = meta.requires_key ? "נדרש מפתח API." : "לא נדרש מפתח API.";
      hint.textContent = meta.label
        ? meta.label + " · " + keyNote + (meta.supports_base_url ? " ניתן להגדיר כתובת בסיס." : "")
        : "";
    }
    this._fetchModels(false);
  }

  async _fetchModels(notify = true) {
    const form = this._app && this._app.querySelector("#settings-form");
    if (!form) return;
    const providerSelect = form.elements.namedItem("provider");
    const provider = providerSelect ? providerSelect.value : "";
    const apiKeyInput = form.elements.namedItem("api_key");
    const apiKey = apiKeyInput ? apiKeyInput.value.trim() : "";
    const baseUrlInput = form.elements.namedItem("base_url");
    const baseUrl = baseUrlInput ? baseUrlInput.value.trim() : "";

    const datalist = form.querySelector("#models-datalist");
    if (!datalist) return;

    try {
      const res = await this._api("/models", {
        method: "POST",
        body: JSON.stringify({
          provider,
          api_key: apiKey,
          base_url: baseUrl,
        }),
      });
      const models = (res && res.models) || [];
      if (models.length) {
        datalist.innerHTML = models
          .map(
            (m) =>
              '<option value="' + esc(m.id) + '">' + esc(m.name || m.id) + "</option>"
          )
          .join("");
        if (notify) {
          const catalogue = (this._config && this._config.providers) || [];
          const meta = catalogue.find((item) => item.id === provider) || {};
          this._toast("נטענו " + models.length + " מודלים מ-" + (meta.label || provider), "success");
        }
      } else if (notify) {
        this._toast("לא נמצאו מודלים מהספק", "info");
      }
    } catch (err) {
      if (notify) {
        this._toast("שגיאה בטעינת מודלים: " + (err.message || err), "error");
      }
    }
  }

  _applySearch() {
    if (!this._app) return;
    const query = (this._search || "").trim().toLowerCase();
    const rows = this._app.querySelectorAll("tr[data-user]");
    if (!rows.length) return;
    let visible = 0;
    rows.forEach((row) => {
      const haystack = row.getAttribute("data-search") || "";
      const show = !query || haystack.indexOf(query) !== -1;
      row.style.display = show ? "" : "none";
      if (show) visible += 1;
    });
    const empty = this._app.querySelector("#no-results");
    if (empty) empty.style.display = visible ? "none" : "";
  }

  _setBusy(value) {
    this._busy = !!value;
    if (this._busyEl) this._busyEl.classList.toggle("on", this._busy);
    if (this._app) this._app.classList.toggle("busy", this._busy);
  }

  _toast(message, type) {
    if (!this._toastEl) return;
    this._toastEl.textContent = String(message || "");
    this._toastEl.className = "toast show " + (type || "info");
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => {
      if (this._toastEl) this._toastEl.className = "toast";
    }, 4200);
  }

  _value(form, name) {
    const field = form.elements.namedItem(name);
    if (!field) return "";
    return String(field.value || "").trim();
  }

  _checked(form, name) {
    const field = form.elements.namedItem(name);
    return !!(field && field.checked);
  }

  _numOrNull(value) {
    const text = String(value === undefined || value === null ? "" : value).trim();
    if (!text) return null;
    const number = Number(text);
    return Number.isFinite(number) ? number : null;
  }

  // ------------------------------------------------------------------
  // Events
  // ------------------------------------------------------------------
  _onClick(event) {
    const target = event.target && event.target.closest ? event.target.closest("[data-action]") : null;
    if (!target) return;
    const action = target.getAttribute("data-action");
    if (!action) return;
    event.preventDefault();
    this._handleAction(action, target).catch((err) => {
      this._toast((err && err.message) || "שגיאה", "error");
    });
  }

  async _handleAction(action, target) {
    if (action === "tab") {
      this._tab = target.getAttribute("data-tab") || "dashboard";
      this._render();
      return;
    }
    if (action === "go-settings") {
      this._tab = "settings";
      this._render();
      return;
    }
    if (action === "refresh") {
      await this._loadAll();
      return;
    }
    if (action === "fetch-models") {
      await this._withBusy(async () => {
        await this._fetchModels(true);
      });
      return;
    }
    if (action === "refresh-logs") {
      await this._withBusy(() => this._refreshLogs());
      return;
    }
    if (action === "open-user") {
      await this._openUser(target.getAttribute("data-id"));
      return;
    }
    if (action === "add-user") {
      this._addUserOpen = true;
      this._render();
      return;
    }
    if (action === "close-modal") {
      this._addUserOpen = false;
      this._selectedId = null;
      this._selectedUser = null;
      this._render();
      return;
    }
    if (action === "user-tab") {
      this._userTab = target.getAttribute("data-utab") || "profile";
      this._render();
      return;
    }
    if (action === "test-ai") {
      await this._withBusy(async () => {
        const result = await this._api("/test", {
          method: "POST",
          body: JSON.stringify({ kind: "ai" }),
        });
        this._toast(
          "AI עובד · " + (result.model || "") + " · " + (result.latency_ms || 0) + "ms",
          "success"
        );
      });
      return;
    }
    if (action === "test-whatsapp" || action === "test-whatsapp-first") {
      let phone = "";
      if (action === "test-whatsapp") {
        const input = this._app.querySelector("#test-phone");
        phone = input ? input.value : "";
      }
      if (!phone && this._users.length && this._users[0].phone) phone = this._users[0].phone;
      if (!phone) {
        this._toast("צריך מספר טלפון לבדיקה", "error");
        return;
      }
      await this._withBusy(async () => {
        await this._api("/test", {
          method: "POST",
          body: JSON.stringify({ kind: "whatsapp", phone }),
        });
        this._toast("הודעת בדיקה נשלחה", "success");
      });
      return;
    }
    if (action === "plan-generate") {
      const send = target.getAttribute("data-send") === "1";
      await this._generatePlan(send);
      return;
    }
    if (action === "send-plan") {
      await this._withBusy(async () => {
        const user = this._selectedUser;
        if (!user || !user.plan_text) return;
        await this._api("/users/" + encodeURIComponent(user.id) + "/message", {
          method: "POST",
          body: JSON.stringify({ message: user.plan_text }),
        });
        await this._reloadSelected();
        await this._reloadUsers();
        this._toast("התוכנית נשלחה", "success");
      });
      return;
    }
    if (action === "toggle-status") {
      await this._withBusy(async () => {
        const user = this._selectedUser;
        if (!user) return;
        const next = user.status === "paused" ? "active" : "paused";
        const data = await this._api("/users/" + encodeURIComponent(user.id), {
          method: "PATCH",
          body: JSON.stringify({ status: next }),
        });
        this._selectedUser = data.user;
        await this._reloadUsers();
        this._render();
        this._toast(next === "paused" ? "התזכורות הושהו" : "התזכורות הופעלו", "success");
      });
      return;
    }
    if (action === "reset-user") {
      const user = this._selectedUser;
      if (!user) return;
      if (!window.confirm("לאפס את " + (user.name || user.phone) + " ולהתחיל היכרות מחדש?")) return;
      await this._withBusy(async () => {
        const data = await this._api("/users/" + encodeURIComponent(user.id) + "/reset", {
          method: "POST",
          body: "{}",
        });
        this._selectedUser = data.user;
        await this._reloadUsers();
        this._render();
        this._toast("המשתמש אופס", "success");
      });
      return;
    }
    if (action === "delete-user") {
      const user = this._selectedUser;
      if (!user) return;
      if (!window.confirm("למחוק את " + (user.name || user.phone) + " לצמיתות?")) return;
      await this._withBusy(async () => {
        await this._api("/users/" + encodeURIComponent(user.id), { method: "DELETE" });
        this._selectedId = null;
        this._selectedUser = null;
        await this._reloadUsers();
        this._render();
        this._toast("המשתמש נמחק", "success");
      });
      return;
    }
  }

  async _onSubmit(event) {
    const form = event.target;
    if (!form || !form.id) return;
    event.preventDefault();
    const id = form.id;
    if (id === "settings-form") return this._saveSettings(form);
    if (id === "add-user-form") return this._addUser(form);
    if (id === "profile-form") return this._saveProfile(form);
    if (id === "message-form") return this._sendMessage(form);
    if (id === "simulate-form") return this._simulate(form);
    return undefined;
  }

  _onInput(event) {
    const target = event.target;
    if (!target) return;
    if (target.id === "user-search") {
      this._search = target.value || "";
      this._applySearch();
      return;
    }
    if (target.name === "provider") {
      this._syncProviderUi();
    }
  }

  _onKeyDown(event) {
    if (event.key === "Escape" && (this._selectedId || this._addUserOpen)) {
      this._addUserOpen = false;
      this._selectedId = null;
      this._selectedUser = null;
      this._render();
    }
  }

  async _withBusy(fn) {
    this._setBusy(true);
    try {
      return await fn();
    } finally {
      this._setBusy(false);
    }
  }

  // ------------------------------------------------------------------
  // Actions
  // ------------------------------------------------------------------
  async _saveSettings(form) {
    await this._withBusy(async () => {
      const payload = {
        provider: this._value(form, "provider"),
        model: this._value(form, "model"),
        base_url: this._value(form, "base_url"),
        temperature: Number(this._value(form, "temperature") || 0.7),
        max_tokens: Number(this._value(form, "max_tokens") || 700),
        whatsapp_service: this._value(form, "whatsapp_service"),
        whatsapp_account: this._value(form, "whatsapp_account"),
        allow_groups: this._checked(form, "allow_groups"),
        allowed_numbers: this._value(form, "allowed_numbers"),
        daily_time: this._value(form, "daily_time"),
        workout_time: this._value(form, "workout_time"),
        water_times: this._value(form, "water_times"),
        enable_daily: this._checked(form, "enable_daily"),
        enable_water: this._checked(form, "enable_water"),
        enable_workout: this._checked(form, "enable_workout"),
        max_users: Number(this._value(form, "max_users") || 25),
        min_ai_interval: Number(this._value(form, "min_ai_interval") || 2),
        coach_name: this._value(form, "coach_name"),
        system_prompt_extra: this._value(form, "system_prompt_extra"),
        clear_api_key: this._checked(form, "clear_api_key"),
      };
      const apiKey = this._value(form, "api_key");
      if (apiKey) payload.api_key = apiKey;

      const data = await this._api("/config", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      this._config = Object.assign({}, this._config, {
        settings: data.settings,
        stats: data.stats || this._config.stats,
      });
      this._render();
      this._toast("ההגדרות נשמרו", "success");
    });
  }

  async _addUser(form) {
    await this._withBusy(async () => {
      const phone = this._value(form, "phone");
      const data = await this._api("/users", {
        method: "POST",
        body: JSON.stringify({
          phone,
          name: this._value(form, "name"),
          send_greeting: this._checked(form, "send_greeting"),
        }),
      });
      this._addUserOpen = false;
      this._selectedId = data.user.id;
      this._selectedUser = data.user;
      this._userTab = "profile";
      await this._reloadUsers();
      this._render();
      this._toast("המשתמש נוצר", "success");
    });
  }

  async _saveProfile(form) {
    const user = this._selectedUser;
    if (!user) return;
    await this._withBusy(async () => {
      const body = {
        name: this._value(form, "name"),
        notes: this._value(form, "notes"),
        profile: {
          goal: this._value(form, "goal"),
          goal_text: this._value(form, "goal_text"),
          weight_kg: this._numOrNull(this._value(form, "weight_kg")),
          height_cm: this._numOrNull(this._value(form, "height_cm")),
          age: this._numOrNull(this._value(form, "age")),
          sex: this._value(form, "sex"),
          activity_level: this._value(form, "activity_level"),
          target_weight_kg: this._numOrNull(this._value(form, "target_weight_kg")),
          restrictions: this._value(form, "restrictions"),
        },
      };
      if (body.profile.age === null) delete body.profile.age;
      const data = await this._api("/users/" + encodeURIComponent(user.id), {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      this._selectedUser = data.user;
      await this._reloadUsers();
      this._render();
      this._toast("הפרופיל נשמר", "success");
    });
  }

  async _generatePlan(send) {
    const user = this._selectedUser;
    if (!user) return;
    await this._withBusy(async () => {
      const data = await this._api("/users/" + encodeURIComponent(user.id) + "/plan", {
        method: "POST",
        body: JSON.stringify({ send, force: true }),
      });
      this._selectedUser = data.user;
      await this._reloadUsers();
      this._render();
      this._toast(send ? "התוכנית נוצרה ונשלחה" : "התוכנית נוצרה", "success");
    });
  }

  async _sendMessage(form) {
    const user = this._selectedUser;
    if (!user) return;
    await this._withBusy(async () => {
      await this._api("/users/" + encodeURIComponent(user.id) + "/message", {
        method: "POST",
        body: JSON.stringify({ message: this._value(form, "message") }),
      });
      form.reset();
      await this._reloadSelected();
      this._toast("ההודעה נשלחה", "success");
    });
  }

  async _simulate(form) {
    const user = this._selectedUser;
    if (!user) return;
    await this._withBusy(async () => {
      const data = await this._api("/users/" + encodeURIComponent(user.id) + "/simulate", {
        method: "POST",
        body: JSON.stringify({ text: this._value(form, "text") }),
      });
      this._selectedUser = data.user;
      form.reset();
      await this._reloadUsers();
      this._render();
      this._toast("הסימולציה הורצה", "success");
    });
  }
}

if (!customElements.get("ai-trainer-panel")) {
  customElements.define("ai-trainer-panel", AITrainerPanel);
}
