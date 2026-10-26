/* Shared helpers: unit preferences, API access, search box, formatting. */
const SkyCast = (() => {
  const store = {
    get(key, fallback) {
      try { const v = localStorage.getItem('skycast.' + key); return v === null ? fallback : JSON.parse(v); }
      catch { return fallback; }
    },
    set(key, value) {
      try { localStorage.setItem('skycast.' + key, JSON.stringify(value)); } catch { /* private mode */ }
    },
  };

  // ---- Units (API data is always metric) ----
  const prefs = Object.assign({ temp: 'c', wind: 'kmh' }, store.get('prefs', {}));
  const listeners = [];
  const WIND = {
    kmh: { f: 1, label: 'km/h' }, mph: { f: 0.621371, label: 'mph' },
    ms: { f: 1 / 3.6, label: 'm/s' }, kn: { f: 0.539957, label: 'kn' },
  };
  const imperial = () => prefs.temp === 'f';
  const conv = {
    t: v => (imperial() ? v * 9 / 5 + 32 : v),
    dt: v => (imperial() ? v * 9 / 5 : v),
    w: v => v * WIND[prefs.wind].f,
    p: v => (imperial() ? v / 25.4 : v),
  };
  const fmt = {
    temp: v => (v == null ? '--' : `${Math.round(conv.t(v))}°`),
    dtemp: v => `${Math.round(conv.dt(v) * 10) / 10}°`,
    wind: v => (v == null ? '--' : `${Math.round(conv.w(v))} ${WIND[prefs.wind].label}`),
    precip: v => (imperial() ? `${(v / 25.4).toFixed(2)} in` : `${(+v).toFixed(1)} mm`),
    distance: m => (m == null ? '--' : imperial() ? `${(m / 1609.34).toFixed(1)} mi` : m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`),
    windLabel: () => WIND[prefs.wind].label,
    tempLabel: () => (imperial() ? '°F' : '°C'),
    precipLabel: () => (imperial() ? 'in' : 'mm'),
  };

  /* Insight text carries tokens like {{t:21.5}} that we format client side. */
  function renderTokens(text) {
    return text.replace(/\{\{(t|dt|w|p):(-?[\d.]+)\}\}/g, (_, k, v) => {
      v = parseFloat(v);
      return { t: fmt.temp, dt: fmt.dtemp, w: fmt.wind, p: fmt.precip }[k](v);
    });
  }

  function setPref(key, value) {
    prefs[key] = value;
    store.set('prefs', prefs);
    syncUnitControls();
    listeners.forEach(fn => fn());
  }
  function onUnitsChange(fn) { listeners.push(fn); }

  function syncUnitControls() {
    document.querySelectorAll('#temp-unit button').forEach(b => b.classList.toggle('active', b.dataset.value === prefs.temp));
    const ws = document.getElementById('wind-unit');
    if (ws) ws.value = prefs.wind;
  }

  // ---- Time helpers. API times are local wall-clock strings like 2026-10-26T14:00 ----
  const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const parseLocal = s => {
    const [d, t = '00:00'] = s.split('T');
    const [y, m, day] = d.split('-').map(Number);
    const [hh, mm] = t.split(':').map(Number);
    return new Date(Date.UTC(y, m - 1, day, hh, mm));
  };
  const time = {
    hour: s => s.slice(11, 16),
    weekday: s => DAYS[parseLocal(s).getUTCDay()],
    dayMonth: s => { const d = parseLocal(s); return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`; },
    minutes: s => parseLocal(s).getTime() / 60000,
    /* Current wall-clock time at a UTC offset, as a Date whose UTC fields are local. */
    nowAt: offsetSeconds => new Date(Date.now() + offsetSeconds * 1000),
    duration: seconds => `${Math.floor(seconds / 3600)}h ${Math.round((seconds % 3600) / 60)}m`,
  };

  const COMPASS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
  const compass = deg => COMPASS[Math.round(((deg % 360) / 22.5)) % 16];
  const flag = cc => (cc && cc.length === 2
    ? String.fromCodePoint(...[...cc.toUpperCase()].map(c => 127397 + c.charCodeAt(0)))
    : '🌐');

  /* Colour for a temperature in °C, used by range bars and charts. */
  function tempColor(c) {
    const stops = [[-20, [129, 140, 248]], [0, [56, 189, 248]], [12, [52, 211, 153]], [22, [250, 204, 21]], [30, [249, 115, 22]], [40, [239, 68, 68]]];
    if (c <= stops[0][0]) return `rgb(${stops[0][1]})`;
    for (let i = 1; i < stops.length; i++) {
      if (c <= stops[i][0]) {
        const [t0, c0] = stops[i - 1], [t1, c1] = stops[i];
        const k = (c - t0) / (t1 - t0);
        return `rgb(${c0.map((v, j) => Math.round(v + (c1[j] - v) * k)).join(',')})`;
      }
    }
    return `rgb(${stops[stops.length - 1][1]})`;
  }

  // ---- HTTP ----
  function cookie(name) {
    const m = document.cookie.match('(^|;)\\s*' + name + '=([^;]+)');
    return m ? decodeURIComponent(m[2]) : '';
  }
  async function request(url, opts = {}) {
    const headers = { Accept: 'application/json', ...(opts.headers || {}) };
    if (opts.body) { headers['Content-Type'] = 'application/json'; headers['X-CSRFToken'] = cookie('csrftoken'); }
    if (opts.method && opts.method !== 'GET') headers['X-CSRFToken'] = cookie('csrftoken');
    const res = await fetch(url, { ...opts, headers, body: opts.body ? JSON.stringify(opts.body) : undefined });
    if (res.status === 204) return null;
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = Array.isArray(data.detail) ? data.detail.map(d => d.msg).join('; ') : data.detail;
      throw new Error(detail || `Request failed (${res.status})`);
    }
    return data;
  }
  const weather = (endpoint, params) => request(`/api/weather/${endpoint}?${new URLSearchParams(params)}`);
  const favorites = {
    list: () => request('/api/favorites/').then(d => d.results),
    add: loc => request('/api/favorites/', { method: 'POST', body: loc }),
    remove: id => request(`/api/favorites/${id}/`, { method: 'DELETE' }),
    reorder: ids => request('/api/favorites/reorder/', { method: 'POST', body: { order: ids } }),
  };

  // ---- UI bits ----
  let toastTimer;
  function toast(msg, ms = 2600) {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, ms);
  }
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

  /* Autocomplete search bound to the top bar. onSelect receives a geocoding result. */
  function attachSearch(onSelect) {
    const input = document.getElementById('search-input');
    const list = document.getElementById('search-results');
    let results = [], active = -1, seq = 0;

    const close = () => { list.hidden = true; input.setAttribute('aria-expanded', 'false'); active = -1; };
    const highlight = () => [...list.children].forEach((li, i) => li.setAttribute('aria-selected', i === active));
    const choose = i => { const r = results[i]; if (!r) return; close(); input.value = ''; input.blur(); onSelect(r); };

    const run = debounce(async q => {
      const mine = ++seq;
      if (q.length < 2) { close(); return; }
      try {
        const data = await weather('geocode', { q, count: 8 });
        if (mine !== seq) return;
        results = data.results;
        list.innerHTML = results.length
          ? results.map((r, i) => `<li role="option" data-i="${i}"><span class="flag">${flag(r.country_code)}</span>
              <span><div>${esc(r.name)}</div><div class="sub">${esc([r.admin1, r.country].filter(Boolean).join(', '))}</div></span></li>`).join('')
          : '<li class="muted">No places found</li>';
        list.hidden = false;
        input.setAttribute('aria-expanded', 'true');
        active = results.length ? 0 : -1;
        highlight();
      } catch (e) { toast(e.message); }
    }, 220);

    input.addEventListener('input', () => run(input.value.trim()));
    input.addEventListener('keydown', e => {
      if (list.hidden) return;
      if (e.key === 'ArrowDown') { active = Math.min(active + 1, results.length - 1); highlight(); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { active = Math.max(active - 1, 0); highlight(); e.preventDefault(); }
      else if (e.key === 'Enter') { choose(active); e.preventDefault(); }
      else if (e.key === 'Escape') close();
    });
    list.addEventListener('mousedown', e => {
      const li = e.target.closest('li[data-i]');
      if (li) { e.preventDefault(); choose(+li.dataset.i); }
    });
    input.addEventListener('blur', () => setTimeout(close, 120));
    document.addEventListener('keydown', e => {
      if (e.key === '/' && document.activeElement !== input && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
        e.preventDefault(); input.focus();
      }
    });
  }

  function chartDefaults() {
    if (!window.Chart) return;
    Chart.defaults.color = 'rgba(226,232,240,.75)';
    Chart.defaults.font.family = 'Inter, system-ui, sans-serif';
    Chart.defaults.borderColor = 'rgba(255,255,255,.08)';
    Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(15,23,42,.92)';
    Chart.defaults.plugins.tooltip.padding = 10;
    Chart.defaults.plugins.tooltip.cornerRadius = 10;
    Chart.defaults.maintainAspectRatio = false;
  }

  document.addEventListener('DOMContentLoaded', () => {
    chartDefaults();
    syncUnitControls();
    document.querySelectorAll('#temp-unit button').forEach(b => b.addEventListener('click', () => setPref('temp', b.dataset.value)));
    document.getElementById('wind-unit').addEventListener('change', e => setPref('wind', e.target.value));
  });

  return {
    store, prefs, conv, fmt, renderTokens, onUnitsChange, time, compass, flag, tempColor,
    weather, favorites, toast, esc, attachSearch,
  };
})();
