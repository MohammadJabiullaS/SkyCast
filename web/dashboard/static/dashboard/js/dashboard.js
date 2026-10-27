/* SkyCast dashboard: renders weather from the Django proxy of the FastAPI service. */
(() => {
  const { fmt, conv, time, esc, toast, weather, favorites, store } = SkyCast;
  const $ = id => document.getElementById(id);

  const DEFAULT_LOC = { name: 'London', admin1: 'England', country: 'United Kingdom', country_code: 'GB', latitude: 51.5085, longitude: -0.1257 };
  const REFRESH_MS = 10 * 60 * 1000;

  const state = {
    loc: null, data: null, aq: null, favs: [], favTemps: {},
    metric: 'temp', day: null, chart: null, map: null, marker: null, favLayer: null,
    radar: { layers: [], timer: null, idx: 0, control: null },
    climate: null, climateCharts: [],
    activities: [], activity: store.get('activity', 'run'), duration: null, plan: null, planSeq: 0,
  };

  // ---------- Loading ----------
  async function load(loc, { quiet = false } = {}) {
    state.loc = { ...loc, latitude: +loc.latitude, longitude: +loc.longitude };
    store.set('last', state.loc);
    if (!quiet) {
      addRecent(state.loc);
      state.day = null;
      resetClimate();
      document.body.classList.add('loading');
    }
    const params = new URLSearchParams({ lat: state.loc.latitude.toFixed(4), lon: state.loc.longitude.toFixed(4), name: state.loc.name });
    history.replaceState(null, '', `?${params}`);
    $('error').hidden = true;

    const q = { lat: state.loc.latitude, lon: state.loc.longitude };
    const [w, aq] = await Promise.allSettled([weather('weather', q), weather('air-quality', q)]);
    document.body.classList.remove('loading');
    if (w.status === 'rejected') {
      $('error').hidden = false;
      $('error').innerHTML = `<b>Couldn't load weather.</b> ${esc(w.reason.message)}`;
      return;
    }
    state.data = w.value;
    state.aq = aq.status === 'fulfilled' ? aq.value : null;
    renderAll();
    updateMap(!quiet);
    loadPlan();
  }

  function renderAll() {
    if (!state.data) return;
    renderHero();
    renderNowcast();
    renderInsights();
    renderHourly();
    renderDaily();
    renderDetails();
    renderFavorites();
    if (state.climate) renderClimate();
    if (state.plan) renderPlan();
  }

  // ---------- Hero ----------
  function renderHero() {
    const { current: c, daily, location } = state.data;
    const loc = state.loc;
    $('loc-name').textContent = loc.name;
    $('loc-sub').textContent = [SkyCast.flag(loc.country_code), [loc.admin1, loc.country].filter(Boolean).join(', '),
      `${loc.latitude.toFixed(2)}°, ${loc.longitude.toFixed(2)}°`, location.elevation != null ? `${Math.round(location.elevation)} m` : '']
      .filter(Boolean).join('  ·  ');
    $('cur-icon').textContent = c.condition.icon;
    $('cur-temp').textContent = fmt.temp(c.temp);
    $('cur-text').textContent = c.condition.text;
    const today = daily[0];
    $('cur-meta').innerHTML = `
      <span>Feels like <b>${fmt.temp(c.feels_like)}</b></span>
      <span>H <b>${fmt.temp(today.temp_max)}</b> · L <b>${fmt.temp(today.temp_min)}</b></span>
      <span>Rain <b>${today.precip_prob_max ?? 0}%</b></span>
      <span>Wind <b>${fmt.wind(c.wind_speed)}</b></span>`;
    $('updated').textContent = new Date(state.data.fetched_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    document.body.className = document.body.className.replace(/theme-\S+/g, '').trim();
    document.body.classList.add(`theme-${c.condition.theme}-${c.is_day ? 'day' : 'night'}`);
    WeatherFX.set(c.condition.theme, !!c.is_day);

    const fav = findFav(loc);
    $('fav-toggle').textContent = fav ? '★' : '☆';
    $('fav-toggle').setAttribute('aria-pressed', !!fav);
    $('fav-toggle').title = fav ? 'Remove from favorites' : 'Add to favorites';
    document.title = `${fmt.temp(c.temp)} ${loc.name} · SkyCast`;
    tickClock();
  }

  function tickClock() {
    if (!state.data) return;
    const loc = state.data.location;
    const d = time.nowAt(loc.utc_offset_seconds);
    const pad = n => String(n).padStart(2, '0');
    $('loc-clock').textContent = `${['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'][d.getUTCDay()]}, `
      + `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())} ${loc.timezone_abbreviation || ''}`;
  }

  function renderNowcast() {
    const n = state.data.nowcast;
    const max = Math.max(1, ...n.steps.map(s => s.precip));
    $('nowcast-bars').innerHTML = n.steps.map((s, i) => `
      <div class="nowcast-bar" title="${time.hour(s.time)} · ${fmt.precip(s.precip)}">
        <div class="fill" style="height:${Math.max(3, (s.precip / max) * 100)}%;opacity:${s.precip > 0 ? 1 : .25}"></div>
        <span class="t">${i % 2 === 0 ? time.hour(s.time) : ''}</span>
      </div>`).join('');
    $('nowcast-summary').textContent = n.summary;
  }

  function renderInsights() {
    $('insights').innerHTML = state.data.insights.map((ins, i) => `
      <div class="insight ${ins.kind}" style="animation-delay:${i * 60}ms">
        <div class="ico">${ins.icon}</div>
        <div><div class="title">${esc(ins.title)}</div><div class="text">${esc(SkyCast.renderTokens(ins.text))}</div></div>
      </div>`).join('');
  }

  // ---------- Hourly ----------
  function hourlyRows() {
    const { hourly, daily, now_index } = state.data;
    if (state.day != null) {
      const date = daily[state.day].time;
      return hourly.filter(h => h.time.startsWith(date));
    }
    return hourly.slice(now_index, now_index + 48);
  }

  function renderHourly() {
    const rows = hourlyRows();
    const dayMode = state.day != null;
    $('hourly-title').textContent = dayMode
      ? `${state.day === 0 ? 'Today' : time.weekday(rows[0].time)} ${time.dayMonth(rows[0].time)} · hourly`
      : 'Next 48 hours';
    $('reset-day').hidden = !dayMode;
    $('hour-strip').innerHTML = rows.map((h, i) => `
      <div class="hour ${!dayMode && i === 0 ? 'now' : ''}">
        <span class="h">${!dayMode && i === 0 ? 'Now' : time.hour(h.time).startsWith('00') ? time.weekday(h.time) : time.hour(h.time)}</span>
        <span class="i" title="${esc(h.condition.text)}">${h.condition.icon}</span>
        <span class="tp">${fmt.temp(h.temp)}</span>
        <span class="pp">${h.precip_prob >= 10 ? `💧${h.precip_prob}%` : ''}</span>
      </div>`).join('');
    $('hour-strip').scrollLeft = 0;
    renderChart(rows, dayMode);
  }

  function renderChart(rows, dayMode) {
    const labels = rows.map((h, i) => {
      const hr = time.hour(h.time);
      if (!dayMode && i === 0) return 'Now';
      return hr === '00:00' ? `${time.weekday(h.time)} 00:00` : hr;
    });
    const ctx = $('hourly-chart').getContext('2d');
    const gradient = ctx.createLinearGradient(0, 0, 0, 240);
    gradient.addColorStop(0, 'rgba(251,191,36,.45)');
    gradient.addColorStop(1, 'rgba(251,191,36,0)');
    const line = (label, data, color, extra = {}) => ({
      type: 'line', label, data, borderColor: color, backgroundColor: color, tension: .4,
      pointRadius: 0, pointHoverRadius: 5, borderWidth: 2.5, ...extra,
    });

    const m = state.metric;
    let datasets, scales;
    const x = { grid: { display: false }, ticks: { maxRotation: 0, autoSkipPadding: 18 } };
    if (m === 'temp') {
      datasets = [
        line(`Temperature (${fmt.tempLabel()})`, rows.map(h => conv.t(h.temp)), '#fbbf24', { fill: true, backgroundColor: gradient }),
        line('Feels like', rows.map(h => conv.t(h.feels_like)), '#f472b6', { borderDash: [6, 4], borderWidth: 1.5 }),
      ];
      scales = { x, y: { ticks: { callback: v => `${Math.round(v)}°` } } };
    } else if (m === 'precip') {
      datasets = [
        { type: 'bar', label: `Precipitation (${fmt.precipLabel()})`, data: rows.map(h => conv.p(h.precip || 0)), backgroundColor: 'rgba(56,189,248,.7)', borderRadius: 4, yAxisID: 'y' },
        line('Chance (%)', rows.map(h => h.precip_prob), '#a78bfa', { yAxisID: 'y1' }),
      ];
      scales = { x, y: { beginAtZero: true, title: { display: true, text: fmt.precipLabel() } },
        y1: { position: 'right', min: 0, max: 100, grid: { display: false }, ticks: { callback: v => `${v}%` } } };
    } else if (m === 'wind') {
      datasets = [
        line(`Wind (${fmt.windLabel()})`, rows.map(h => conv.w(h.wind_speed)), '#34d399', { fill: true, backgroundColor: 'rgba(52,211,153,.15)' }),
        line('Gusts', rows.map(h => conv.w(h.wind_gusts)), '#94a3b8', { borderDash: [6, 4], borderWidth: 1.5 }),
      ];
      scales = { x, y: { beginAtZero: true } };
    } else if (m === 'humidity') {
      datasets = [
        line('Humidity (%)', rows.map(h => h.humidity), '#38bdf8', { fill: true, backgroundColor: 'rgba(56,189,248,.15)' }),
        line('Cloud cover (%)', rows.map(h => h.cloud_cover), '#cbd5e1', { borderDash: [6, 4], borderWidth: 1.5 }),
      ];
      scales = { x, y: { min: 0, max: 100, ticks: { callback: v => `${v}%` } } };
    } else {
      datasets = [{ type: 'bar', label: 'UV index', data: rows.map(h => h.uv), borderRadius: 4,
        backgroundColor: rows.map(h => uvLevel(h.uv).color) }];
      scales = { x, y: { beginAtZero: true, suggestedMax: 8 } };
    }

    if (state.chart) state.chart.destroy();
    state.chart = new Chart(ctx, {
      data: { labels, datasets },
      options: {
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { labels: { usePointStyle: true, boxWidth: 8 } } },
        scales,
        animation: { duration: 500 },
      },
    });
  }

  // ---------- Daily ----------
  function renderDaily() {
    const { daily, current } = state.data;
    const lo = Math.min(...daily.map(d => d.temp_min));
    const hi = Math.max(...daily.map(d => d.temp_max));
    const pct = v => ((v - lo) / (hi - lo || 1)) * 100;
    $('daily-title').textContent = `${daily.length}-day forecast`;
    $('daily').innerHTML = daily.map((d, i) => `
      <li class="day ${state.day === i ? 'selected' : ''}" data-i="${i}" tabindex="0" title="${esc(d.condition.text)}">
        <span class="dn">${i === 0 ? 'Today' : time.weekday(d.time)}<span class="dd">${time.dayMonth(d.time)}</span></span>
        <span class="di">${d.condition.icon}</span>
        <span class="dp">${d.precip_prob_max >= 10 ? `💧${d.precip_prob_max}%` : ''}</span>
        <span class="lo">${fmt.temp(d.temp_min)}</span>
        <span class="range"><span class="fill" style="left:${pct(d.temp_min)}%;right:${100 - pct(d.temp_max)}%;
          background:linear-gradient(90deg,${SkyCast.tempColor(d.temp_min)},${SkyCast.tempColor(d.temp_max)})"></span>
          ${i === 0 ? `<span class="dot" style="left:${Math.min(100, Math.max(0, pct(current.temp)))}%"></span>` : ''}</span>
        <span class="hi">${fmt.temp(d.temp_max)}</span>
      </li>`).join('');
  }

  function selectDay(i) {
    state.day = state.day === i ? null : i;
    renderDaily();
    renderHourly();
    $('hourly-title').scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  // ---------- Activity planner ----------
  async function initPlanner() {
    try {
      state.activities = (await weather('activities', {})).results;
    } catch (e) {
      $('plan-windows').innerHTML = `<div class="plan-empty">${esc(e.message)}</div>`;
      return;
    }
    if (!state.activities.some(a => a.key === state.activity)) state.activity = state.activities[0].key;
    renderActivityChips();
    $('activity-chips').addEventListener('click', e => {
      const chip = e.target.closest('.chip[data-key]');
      if (!chip || chip.dataset.key === state.activity) return;
      state.activity = chip.dataset.key;
      state.duration = null;
      store.set('activity', state.activity);
      renderActivityChips();
      loadPlan();
    });
    $('plan-duration').addEventListener('change', e => {
      state.duration = e.target.value ? +e.target.value : null;
      loadPlan();
    });
    if (state.data) loadPlan();
  }

  function renderActivityChips() {
    $('activity-chips').innerHTML = state.activities.map(a => `
      <span class="chip ${a.key === state.activity ? 'on' : ''}" data-key="${a.key}" role="button" tabindex="0">
        <span class="ico">${a.icon}</span>${esc(a.label)}</span>`).join('');
    const act = state.activities.find(a => a.key === state.activity);
    $('plan-duration').innerHTML = [1, 2, 3, 4, 5, 6].map(h =>
      `<option value="${h === act.duration ? '' : h}" ${(state.duration || act.duration) === h ? 'selected' : ''}>${h} h</option>`).join('');
  }

  async function loadPlan() {
    if (!state.loc || !state.activities.length) return;
    const seq = ++state.planSeq;
    $('plan-windows').style.opacity = .5;
    const params = { lat: state.loc.latitude, lon: state.loc.longitude, activity: state.activity };
    if (state.duration) params.duration = state.duration;
    try {
      const plan = await weather('plan', params);
      if (seq !== state.planSeq) return;  // a newer request superseded this one
      state.plan = plan;
      renderPlan();
    } catch (e) {
      if (seq === state.planSeq) $('plan-windows').innerHTML = `<div class="plan-empty">${esc(e.message)}</div>`;
    } finally {
      if (seq === state.planSeq) $('plan-windows').style.opacity = 1;
    }
  }

  function dayLabel(date) {
    const days = state.data ? state.data.daily.map(d => d.time) : [];
    if (date === days[0]) return 'Today';
    if (date === days[1]) return 'Tomorrow';
    return `${time.weekday(date)} ${time.dayMonth(date)}`;
  }

  const scoreColor = s => (s <= 0 ? 'rgba(255,255,255,.04)'
    : s < 40 ? `rgba(239,68,68,${0.25 + s / 160})`
    : s < 70 ? `rgba(245,158,11,${0.4 + (s - 40) / 100})`
    : `rgba(34,197,94,${0.45 + (s - 70) / 60})`);

  function ring(score) {
    const c = 2 * Math.PI * 24;
    return `<div class="ring" title="Suitability score ${score}/100"><svg width="58" height="58" viewBox="0 0 58 58">
      <circle cx="29" cy="29" r="24" fill="none" stroke="rgba(255,255,255,.1)" stroke-width="6"/>
      <circle cx="29" cy="29" r="24" fill="none" stroke="${scoreColor(score).replace(/[\d.]+\)$/, '1)')}" stroke-width="6"
        stroke-linecap="round" stroke-dasharray="${(c * score / 100).toFixed(1)} ${c.toFixed(1)}"/></svg>
      <span class="num">${score}</span></div>`;
  }

  function renderVerdict(plan) {
    const v = plan.verdict, act = plan.activity;
    const el = $('plan-verdict');
    if (!v) { el.innerHTML = ''; el.className = 'verdict'; return; }
    const fmtText = t => esc(SkyCast.renderTokens(t));
    const when = w => `${dayLabel(w.start.slice(0, 10))} ${time.hour(w.start)}–${time.hour(w.end)}`;
    const list = items => items.map(fmtText).join(' · ');
    let icon, title, detail;
    if (v.status === 'go') {
      icon = '✅'; title = `Yes, good time to ${act.verb} now`; detail = list(v.pros);
    } else if (v.status === 'caution') {
      icon = '⚠️'; title = `OK to ${act.verb} now, with care`; detail = list(v.cons);
    } else {
      icon = '⛔'; title = `Not a good time to ${act.verb} now`;
      detail = v.blocked ? esc(`Right now ${v.blocked}.`) : list(v.cons);
    }
    const next = v.next
      ? `<div class="verdict-next">${v.status === 'go' ? 'Even better' : 'Best time'}: <b>${when(v.next)}</b> · score ${v.next.score}${
          v.next.confidence ? ` · ${v.next.confidence.level} confidence` : ''}</div>`
      : (v.status === 'go' ? '' : '<div class="verdict-next">No good window in the next 7 days.</div>');
    el.className = `verdict ${v.status}`;
    el.innerHTML = `<div class="verdict-icon">${icon}</div>
      <div class="verdict-body">
        <div class="verdict-title">${esc(title)}</div>
        ${detail ? `<div class="verdict-detail">${detail}</div>` : ''}
        ${next}
      </div>
      ${v.blocked ? '' : ring(v.score)}`;
  }

  function renderPlan() {
    const plan = state.plan;
    const act = plan.activity;
    const fmtText = t => esc(SkyCast.renderTokens(t));
    renderVerdict(plan);

    $('plan-windows').innerHTML = plan.windows.length ? plan.windows.map((w, i) => {
      const conf = w.confidence;
      return `<div class="pwin ${i === 0 ? 'top' : ''}" style="animation-delay:${i * 70}ms">
        <div class="pwin-head">
          <div>
            <div class="pwin-rank">${i === 0 ? '★ Best time' : `Option ${i + 1}`} · ${esc(w.rating)}</div>
            <div class="pwin-day">${w.icon} ${dayLabel(w.start.slice(0, 10))}</div>
            <div class="pwin-time">${time.hour(w.start)}–${time.hour(w.end)}</div>
          </div>
          ${ring(w.score)}
        </div>
        <ul>${w.pros.map(p => `<li class="pro">${fmtText(p)}</li>`).join('')}${w.cons.map(c => `<li class="con">${fmtText(c)}</li>`).join('')}</ul>
        <div class="conf">${conf
          ? `<span class="conf-badge conf-${conf.level}">${conf.level} confidence</span>${fmtText(conf.summary)}`
          : plan.ensemble_available ? 'Too far ahead for confidence data' : 'Confidence unavailable right now'}</div>
      </div>`;
    }).join('') : `<div class="plan-empty">${act.icon} No good ${esc(act.label.toLowerCase())} windows in the next 7 days here. Try a shorter length or another activity.</div>`;

    // Heatmap: one row per day, one cell per hour; today starts at the current hour.
    const picks = new Set();
    plan.windows.forEach(w => {
      const start = time.minutes(w.start);
      for (let m = start; m < start + act.duration * 60; m += 60) picks.add(m);
    });
    let html = '<span></span>' + Array.from({ length: 24 }, (_, h) => `<span class="hd">${h % 3 === 0 ? h : ''}</span>`).join('');
    plan.days.slice(0, 7).forEach(d => {
      const byHour = {};
      d.hours.forEach(x => { byHour[+x.time.slice(11, 13)] = x; });
      html += `<span class="dl">${dayLabel(d.date).replace(/ \d.*/, '')}</span>`;
      for (let h = 0; h < 24; h++) {
        const x = byHour[h];
        html += x
          ? `<span class="cell ${picks.has(time.minutes(x.time)) ? 'pick' : ''}" style="background:${scoreColor(x.score)}"
              title="${dayLabel(d.date)} ${time.hour(x.time)} · ${x.score}/100"></span>`
          : '<span></span>';
      }
    });
    $('plan-heat').innerHTML = html;
  }

  // ---------- Detail tiles ----------
  function uvLevel(uv) {
    if (uv < 3) return { label: 'Low', color: '#22c55e' };
    if (uv < 6) return { label: 'Moderate', color: '#eab308' };
    if (uv < 8) return { label: 'High', color: '#f97316' };
    if (uv < 11) return { label: 'Very high', color: '#ef4444' };
    return { label: 'Extreme', color: '#a855f7' };
  }

  const tile = id => $(id).querySelector('.tile-body');

  function renderDetails() {
    const { current: c, daily, location } = state.data;

    tile('tile-wind').innerHTML = `
      <div class="compass">
        <svg viewBox="0 0 100 100" aria-label="Wind from ${SkyCast.compass(c.wind_dir)}">
          <circle cx="50" cy="50" r="44" fill="none" stroke="rgba(255,255,255,.15)" stroke-width="2"/>
          ${[0, 90, 180, 270].map((a, i) => `<text x="${50 + 36 * Math.sin(a * Math.PI / 180)}" y="${54 - 36 * Math.cos(a * Math.PI / 180)}"
            text-anchor="middle" font-size="10" fill="rgba(255,255,255,.6)">${'NESW'[i]}</text>`).join('')}
          <g class="needle" style="transform:rotate(${(c.wind_dir + 180) % 360}deg)">
            <path d="M50 16 L57 50 L50 44 L43 50 Z" fill="#60a5fa"/><path d="M50 84 L55 50 L45 50 Z" fill="rgba(255,255,255,.35)"/>
          </g>
        </svg>
        <div><div class="val">${fmt.wind(c.wind_speed)}</div>
          <div class="note">From ${SkyCast.compass(c.wind_dir)} (${c.wind_dir}°)<br>Gusts ${fmt.wind(c.wind_gusts)}</div></div>
      </div>`;

    // Sun arc
    const today = daily[0];
    const nowLocal = time.nowAt(location.utc_offset_seconds);
    const nowMin = nowLocal.getUTCHours() * 60 + nowLocal.getUTCMinutes();
    const toMin = s => +s.slice(11, 13) * 60 + +s.slice(14, 16);
    const rise = toMin(today.sunrise), set = toMin(today.sunset);
    const p = Math.min(1, Math.max(0, (nowMin - rise) / (set - rise || 1)));
    const up = nowMin >= rise && nowMin <= set;
    const sx = 100 - 80 * Math.cos(Math.PI * p), sy = 90 - 80 * Math.sin(Math.PI * p);
    tile('tile-sun').innerHTML = `
      <div class="sun-arc"><svg viewBox="0 0 200 100">
        <path d="M20 90 A80 80 0 0 1 180 90" fill="none" stroke="rgba(255,255,255,.2)" stroke-dasharray="4 4" stroke-width="2"/>
        <path d="M20 90 A80 80 0 0 1 ${sx.toFixed(1)} ${sy.toFixed(1)}" fill="none" stroke="#fbbf24" stroke-width="3" opacity="${up ? 1 : .3}"/>
        <line x1="5" y1="90" x2="195" y2="90" stroke="rgba(255,255,255,.25)"/>
        <circle cx="${sx.toFixed(1)}" cy="${sy.toFixed(1)}" r="8" fill="${up ? '#fde047' : '#94a3b8'}"/>
      </svg></div>
      <div class="note">🌅 ${time.hour(today.sunrise)} &nbsp; 🌇 ${time.hour(today.sunset)} · ${time.duration(today.daylight)} daylight</div>`;

    const uv = uvLevel(c.uv ?? 0);
    tile('tile-uv').innerHTML = `
      <div class="val">${(c.uv ?? 0).toFixed(1)} <span class="badge" style="background:${uv.color}">${uv.label}</span></div>
      <div class="gauge uv-gauge"><span class="marker" style="left:${Math.min(100, (c.uv / 11) * 100)}%"></span></div>
      <div class="note">Today's max ${today.uv_max?.toFixed(1) ?? '--'}</div>`;

    const dp = c.dew_point;
    const comfort = dp >= 21 ? 'Oppressive' : dp >= 18 ? 'Muggy' : dp >= 13 ? 'Comfortable' : dp >= 5 ? 'Pleasant & dry' : 'Very dry';
    tile('tile-humidity').innerHTML = `
      <div class="val">${c.humidity}%</div>
      <div class="note">Dew point ${fmt.temp(dp)} · ${comfort}</div>`;

    const pr = c.pressure;
    tile('tile-pressure').innerHTML = `
      <div class="val">${Math.round(pr)} <span class="small muted">hPa</span></div>
      <div class="note">${(pr * 0.02953).toFixed(2)} inHg · ${pr >= 1022 ? 'High — settled weather' : pr <= 1000 ? 'Low — unsettled weather' : 'Normal'}</div>`;

    const vis = c.visibility;
    tile('tile-visibility').innerHTML = `
      <div class="val">${fmt.distance(vis)}</div>
      <div class="note">${vis >= 20000 ? 'Crystal clear' : vis >= 10000 ? 'Clear' : vis >= 4000 ? 'Hazy' : vis >= 1000 ? 'Mist' : 'Fog'}</div>`;

    renderAirQuality();
  }

  function renderAirQuality() {
    const el = tile('tile-aqi');
    if (!state.aq || state.aq.current.us_aqi == null) {
      el.innerHTML = '<div class="note">Air quality data unavailable for this location.</div>';
      return;
    }
    const a = state.aq.current, cat = state.aq.category;
    const pol = [['PM2.5', a.pm2_5], ['PM10', a.pm10], ['O₃', a.ozone], ['NO₂', a.nitrogen_dioxide], ['SO₂', a.sulphur_dioxide], ['CO', a.carbon_monoxide]];
    el.innerHTML = `
      <div class="val">${a.us_aqi} <span class="badge" style="background:${cat.color}">${esc(cat.label)}</span>
        <span class="small muted">US AQI · EU ${a.european_aqi ?? '--'}</span></div>
      <div class="gauge aqi-gauge"><span class="marker" style="left:${Math.min(100, (a.us_aqi / 300) * 100)}%"></span></div>
      <div class="note">${esc(cat.advice)}</div>
      <div class="pollutants">${pol.map(([k, v]) => `<div class="pollutant"><div class="k">${k}</div><div class="v">${v == null ? '--' : Math.round(v)} <span class="small muted">µg/m³</span></div></div>`).join('')}</div>
      ${renderPollen(state.aq.pollen)}`;
  }

  function renderPollen(p) {
    if (!p) return '<div class="pollen-row">🌼 <span class="muted">Pollen forecasts are only available in Europe.</span></div>';
    const name = t => t[0].toUpperCase() + t.slice(1);
    if (p.level === 'None') return '<div class="pollen-row">🌼 Pollen: <b>none right now</b></div>';
    const others = Object.entries(p.types).filter(([t, v]) => v >= 1 && t !== p.top_type)
      .map(([t, v]) => `${name(t)} ${Math.round(v)}`).join(', ');
    return `<div class="pollen-row">🌼 Pollen: <b>${esc(p.level)}</b> · ${name(p.top_type)} ${Math.round(p.top_value)} grains/m³
      ${others ? `<span class="muted">Also: ${others}</span>` : ''}</div>`;
  }

  // ---------- Favorites & recents ----------
  const sameSpot = (a, b) => Math.abs(a.latitude - b.latitude) < 0.01 && Math.abs(a.longitude - b.longitude) < 0.01;
  const findFav = loc => state.favs.find(f => sameSpot(f, loc));

  async function loadFavorites() {
    try {
      state.favs = await favorites.list();
    } catch (e) {
      toast(e.message);
      state.favs = [];
    }
    renderFavorites();
    refreshFavTemps();
  }

  async function refreshFavTemps() {
    if (!state.favs.length) return;
    try {
      const points = state.favs.map(f => `${f.latitude},${f.longitude}`).join(';');
      const data = await weather('compare', { points });
      state.favTemps = {};
      data.results.forEach((r, i) => { state.favTemps[state.favs[i].id] = r.current; });
      renderFavorites();
    } catch { /* temps are optional */ }
  }

  function renderFavorites() {
    const ul = $('favorites');
    if (!state.favs.length) {
      ul.innerHTML = '<li class="muted small">No favorites yet. Tap ☆ next to a city name to save it.</li>';
    } else {
      ul.innerHTML = state.favs.map(f => {
        const cur = state.favTemps[f.id];
        return `<li class="fav-item ${state.loc && sameSpot(f, state.loc) ? 'active' : ''}" data-id="${f.id}" draggable="true">
          <div style="min-width:0"><div class="fav-name">${SkyCast.flag(f.country_code)} ${esc(f.name)}</div>
            <div class="fav-sub">${esc(cur ? cur.condition.text : f.country)}</div></div>
          <span class="fav-temp">${cur ? `${cur.condition.icon} ${fmt.temp(cur.temp)}` : ''}</span>
          <button class="fav-remove" data-remove="${f.id}" title="Remove">✕</button>
        </li>`;
      }).join('');
    }
    if (state.data) {
      const fav = state.loc && findFav(state.loc);
      $('fav-toggle').textContent = fav ? '★' : '☆';
    }
    renderFavMarkers();
  }

  async function toggleFavorite() {
    if (!state.loc) return;
    const fav = findFav(state.loc);
    try {
      if (fav) {
        await favorites.remove(fav.id);
        state.favs = state.favs.filter(f => f.id !== fav.id);
        toast(`Removed ${fav.name} from favorites`);
      } else {
        const created = await favorites.add({ ...state.loc, timezone: state.data?.location.timezone });
        state.favs.push(created);
        if (state.data) state.favTemps[created.id] = state.data.current;
        toast(`⭐ Saved ${created.name}`);
      }
      renderFavorites();
    } catch (e) { toast(e.message); }
  }

  function setupFavDrag() {
    const ul = $('favorites');
    let dragging = null;
    ul.addEventListener('dragstart', e => { dragging = e.target.closest('.fav-item'); dragging?.classList.add('dragging'); });
    ul.addEventListener('dragover', e => {
      e.preventDefault();
      const over = e.target.closest('.fav-item');
      if (!dragging || !over || over === dragging) return;
      const r = over.getBoundingClientRect();
      ul.insertBefore(dragging, e.clientY > r.top + r.height / 2 ? over.nextSibling : over);
    });
    ul.addEventListener('dragend', async () => {
      if (!dragging) return;
      dragging.classList.remove('dragging');
      dragging = null;
      const ids = [...ul.querySelectorAll('.fav-item')].map(li => +li.dataset.id);
      state.favs.sort((a, b) => ids.indexOf(a.id) - ids.indexOf(b.id));
      try { await favorites.reorder(ids); } catch (e) { toast(e.message); }
    });
    ul.addEventListener('click', async e => {
      const rm = e.target.closest('[data-remove]');
      if (rm) {
        e.stopPropagation();
        const id = +rm.dataset.remove;
        try {
          await favorites.remove(id);
          state.favs = state.favs.filter(f => f.id !== id);
          renderFavorites();
        } catch (err) { toast(err.message); }
        return;
      }
      const li = e.target.closest('.fav-item');
      if (li) load(state.favs.find(f => f.id === +li.dataset.id));
    });
  }

  function addRecent(loc) {
    const recent = store.get('recent', []).filter(r => !sameSpot(r, loc));
    recent.unshift(loc);
    store.set('recent', recent.slice(0, 6));
    renderRecent();
  }

  function renderRecent() {
    const recent = store.get('recent', []);
    $('recent').innerHTML = recent.length
      ? recent.map((r, i) => `<li data-i="${i}">${SkyCast.flag(r.country_code)} ${esc(r.name)}${r.country ? `, <span class="muted">${esc(r.country)}</span>` : ''}</li>`).join('')
      : '<li class="muted small" style="cursor:default">Your searches appear here</li>';
  }

  // ---------- Map & radar ----------
  function initMap() {
    if (!window.L) return;
    // Wheel zoom only once the map has focus, so it doesn't trap page scrolling.
    state.map = L.map('map', { worldCopyJump: true, scrollWheelZoom: false }).setView([20, 0], 2);
    state.map.on('focus', () => state.map.scrollWheelZoom.enable());
    state.map.on('blur', () => state.map.scrollWheelZoom.disable());
    // OpenStreetMap refuses tile requests without a Referer, so send our origin explicitly.
    const osm = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19, className: 'basemap', referrerPolicy: 'strict-origin-when-cross-origin',
    });
    const esri = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/';
    const dark = L.layerGroup([
      L.tileLayer(`${esri}World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}`, { maxZoom: 16, attribution: 'Tiles &copy; Esri' }),
      L.tileLayer(`${esri}World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}`, { maxZoom: 16 }),
    ]);
    const basemaps = { Dark: dark, Streets: osm };
    const chosen = basemaps[store.get('basemap', 'Dark')] || dark;
    chosen.addTo(state.map);
    L.control.layers(basemaps, null, { position: 'topright' }).addTo(state.map);
    state.map.on('baselayerchange', e => store.set('basemap', e.name));
    state.favLayer = L.layerGroup().addTo(state.map);
    state.map.on('click', e => {
      const { lat, lng } = e.latlng.wrap();
      load({ name: `${lat.toFixed(3)}°, ${lng.toFixed(3)}°`, latitude: lat, longitude: lng });
    });
  }

  function updateMap(fly) {
    if (!state.map || !state.data) return;
    state.map.invalidateSize();
    const ll = [state.loc.latitude, state.loc.longitude];
    const c = state.data.current;
    const icon = L.divIcon({ className: '', html: `<div style="font-size:30px;filter:drop-shadow(0 2px 6px rgba(0,0,0,.5))">${c.condition.icon}</div>`, iconSize: [36, 36], iconAnchor: [18, 18] });
    if (state.marker) state.marker.setLatLng(ll).setIcon(icon);
    else state.marker = L.marker(ll, { icon }).addTo(state.map);
    state.marker.bindTooltip(`<b>${esc(state.loc.name)}</b><br>${fmt.temp(c.temp)} · ${esc(c.condition.text)}`);
    if (fly) state.map.flyTo(ll, Math.max(state.map.getZoom(), 7), { duration: 1.2 });
  }

  function renderFavMarkers() {
    if (!state.favLayer) return;
    state.favLayer.clearLayers();
    state.favs.forEach(f => {
      const cur = state.favTemps[f.id];
      L.circleMarker([f.latitude, f.longitude], { radius: 6, color: '#fbbf24', fillColor: '#fbbf24', fillOpacity: .8, weight: 2 })
        .bindTooltip(`⭐ ${esc(f.name)}${cur ? ` · ${fmt.temp(cur.temp)}` : ''}`)
        .on('click', ev => { L.DomEvent.stopPropagation(ev); load(f); })
        .addTo(state.favLayer);
    });
  }

  async function toggleRadar(on) {
    const r = state.radar;
    clearInterval(r.timer);
    r.layers.forEach(l => state.map.removeLayer(l));
    r.layers = [];
    if (r.control) { r.control.remove(); r.control = null; }
    if (!on) return;
    try {
      const res = await fetch('https://api.rainviewer.com/public/weather-maps.json');
      const data = await res.json();
      const frames = [...(data.radar.past || []), ...(data.radar.nowcast || [])].slice(-12);
      r.layers = frames.map(f => L.tileLayer(`${data.host}${f.path}/256/{z}/{x}/{y}/2/1_1.png`, {
        opacity: 0, maxNativeZoom: 7, maxZoom: 19, attribution: 'Radar &copy; RainViewer',
      }).addTo(state.map));
      r.control = L.control({ position: 'bottomleft' });
      r.control.onAdd = () => L.DomUtil.create('div', 'radar-time');
      r.control.addTo(state.map);
      r.idx = 0;
      // Radar tiles only go to zoom 7; beyond that they're just upscaled blur.
      if (state.map.getZoom() > 7) state.map.setZoom(6);
      const show = () => {
        r.layers.forEach((l, i) => l.setOpacity(i === r.idx ? .7 : 0));
        const t = new Date(frames[r.idx].time * 1000);
        r.control.getContainer().textContent = `Radar ${t.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
        r.idx = (r.idx + 1) % r.layers.length;
      };
      show();
      r.timer = setInterval(show, 700);
    } catch {
      toast('Radar is unavailable right now');
      $('radar-toggle').checked = false;
    }
  }

  // ---------- Climate ----------
  function resetClimate() {
    state.climate = null;
    state.climateCharts.forEach(c => c.destroy());
    state.climateCharts = [];
    $('climate-body').hidden = true;
    $('climate-load').hidden = false;
    $('climate-load').disabled = false;
    $('climate-load').textContent = 'Load climate history';
  }

  async function loadClimate() {
    const btn = $('climate-load');
    btn.disabled = true;
    btn.textContent = 'Crunching 30 years of data…';
    const q = { lat: state.loc.latitude, lon: state.loc.longitude };
    try {
      const [recent, otd] = await Promise.all([weather('history/recent', { ...q, days: 30 }), weather('history/on-this-day', { ...q, years: 30 })]);
      state.climate = { recent, otd };
      btn.hidden = true;
      $('climate-body').hidden = false;
      renderClimate();
    } catch (e) {
      toast(e.message);
      btn.disabled = false;
      btn.textContent = 'Retry';
    }
  }

  function renderClimate() {
    const { recent, otd } = state.climate;
    const s = otd.stats;
    const todayMax = state.data.daily[0].temp_max;
    const stat = (k, v, sub = '') => `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div><div class="s">${sub}</div></div>`;
    if (s) {
      const diff = todayMax - s.avg_max;
      $('climate-stats').innerHTML = [
        stat('Normal high', fmt.temp(s.avg_max), `${s.count}-year average`),
        stat('Normal low', fmt.temp(s.avg_min)),
        stat('Today vs normal', `${diff >= 0 ? '+' : '−'}${fmt.dtemp(Math.abs(diff))}`, `Forecast high ${fmt.temp(todayMax)}`),
        stat('Record high', fmt.temp(s.record_high.value), `in ${s.record_high.year}`),
        stat('Record low', s.record_low ? fmt.temp(s.record_low.value) : '--', s.record_low ? `in ${s.record_low.year}` : ''),
        stat('Wet on this date', `${s.rain_chance}%`, 'of years with ≥1 mm'),
        stat('Trend', s.trend_per_decade == null ? '--' : `${s.trend_per_decade >= 0 ? '+' : '−'}${fmt.dtemp(Math.abs(s.trend_per_decade))}`, 'per decade (highs)'),
      ].join('');
      const yrs = otd.years;
      $('otd-title').textContent = `On ${time.dayMonth(otd.date)}, ${yrs[0].year}–${yrs[yrs.length - 1].year}`;
    } else {
      $('climate-stats').innerHTML = '<div class="muted">No historical data for this location.</div>';
    }

    state.climateCharts.forEach(c => c.destroy());
    const rd = recent.daily;
    const recentChart = new Chart($('recent-chart'), {
      data: {
        labels: rd.map(d => time.dayMonth(d.time)),
        datasets: [
          { type: 'line', label: 'High', data: rd.map(d => conv.t(d.temp_max)), borderColor: '#fb923c', backgroundColor: 'rgba(251,146,60,.15)', fill: '+1', tension: .35, pointRadius: 0 },
          { type: 'line', label: 'Low', data: rd.map(d => conv.t(d.temp_min)), borderColor: '#60a5fa', tension: .35, pointRadius: 0 },
          { type: 'bar', label: `Precip (${fmt.precipLabel()})`, data: rd.map(d => conv.p(d.precip_sum || 0)), backgroundColor: 'rgba(56,189,248,.45)', yAxisID: 'y1', borderRadius: 3 },
        ],
      },
      options: {
        interaction: { mode: 'index', intersect: false },
        scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } }, y: { ticks: { callback: v => `${Math.round(v)}°` } },
          y1: { position: 'right', beginAtZero: true, grid: { display: false } } },
      },
    });
    const yrs = otd.years;
    const otdChart = new Chart($('otd-chart'), {
      data: {
        labels: yrs.map(y => y.year),
        datasets: [
          { type: 'bar', label: 'High', data: yrs.map(y => conv.t(y.temp_max)), backgroundColor: yrs.map(y => SkyCast.tempColor(y.temp_max)), borderRadius: 3 },
          ...(s ? [{ type: 'line', label: 'Average', data: yrs.map(() => conv.t(s.avg_max)), borderColor: 'rgba(255,255,255,.7)', borderDash: [5, 4], pointRadius: 0, borderWidth: 1.5 }] : []),
        ],
      },
      options: {
        plugins: { legend: { display: false } },
        scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 10 } },
          y: { min: Math.floor(Math.min(...yrs.map(y => conv.t(y.temp_max)))) - 3, ticks: { callback: v => `${Math.round(v)}°` } } },
      },
    });
    state.climateCharts = [recentChart, otdChart];
  }

  // ---------- Geolocation ----------
  function locate() {
    if (!navigator.geolocation) { toast('Geolocation is not supported by this browser'); return; }
    toast('📍 Finding your location…');
    navigator.geolocation.getCurrentPosition(
      pos => load({ name: 'My location', latitude: pos.coords.latitude, longitude: pos.coords.longitude }),
      err => toast(`Location unavailable: ${err.message}`),
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 },
    );
  }

  // ---------- Wiring ----------
  function init() {
    SkyCast.attachSearch(r => load(r));
    initMap();
    setupFavDrag();
    renderRecent();

    $('fav-toggle').addEventListener('click', toggleFavorite);
    $('locate-btn').addEventListener('click', locate);
    $('refresh-btn').addEventListener('click', () => load(state.loc, { quiet: true }).then(() => toast('Updated')));
    $('reset-day').addEventListener('click', () => { state.day = null; renderDaily(); renderHourly(); });
    $('climate-load').addEventListener('click', loadClimate);
    $('radar-toggle').addEventListener('change', e => toggleRadar(e.target.checked));
    $('clear-recent').addEventListener('click', () => { store.set('recent', []); renderRecent(); });
    $('recent').addEventListener('click', e => {
      const li = e.target.closest('li[data-i]');
      if (li) load(store.get('recent', [])[+li.dataset.i]);
    });
    $('daily').addEventListener('click', e => { const li = e.target.closest('.day'); if (li) selectDay(+li.dataset.i); });
    $('daily').addEventListener('keydown', e => { if (e.key === 'Enter') { const li = e.target.closest('.day'); if (li) selectDay(+li.dataset.i); } });
    $('chart-tabs').addEventListener('click', e => {
      const b = e.target.closest('button[data-metric]');
      if (!b) return;
      state.metric = b.dataset.metric;
      $('chart-tabs').querySelectorAll('button').forEach(x => x.classList.toggle('active', x === b));
      renderChart(hourlyRows(), state.day != null);
    });
    SkyCast.onUnitsChange(renderAll);
    initPlanner();

    setInterval(tickClock, 1000);
    setInterval(() => { if (state.loc && !document.hidden) { load(state.loc, { quiet: true }); refreshFavTemps(); } }, REFRESH_MS);

    const p = new URLSearchParams(location.search);
    const fromUrl = p.has('lat') && p.has('lon')
      ? { name: p.get('name') || 'Selected location', latitude: +p.get('lat'), longitude: +p.get('lon') }
      : null;
    loadFavorites().then(() => {
      // Prefer richer stored metadata (country etc.) when the URL points at a known place.
      const known = fromUrl && [...state.favs, ...store.get('recent', [])].find(r => sameSpot(r, fromUrl));
      load(known || fromUrl || store.get('last', null) || DEFAULT_LOC);
    });
  }

  document.addEventListener('DOMContentLoaded', init);
})();
