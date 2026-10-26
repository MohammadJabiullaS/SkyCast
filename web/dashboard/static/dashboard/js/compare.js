/* Compare page: side-by-side current conditions and 7-day outlook for several places. */
(() => {
  const { fmt, conv, time, esc, toast, weather, favorites, store } = SkyCast;
  const $ = id => document.getElementById(id);
  const COLORS = ['#fbbf24', '#60a5fa', '#f472b6', '#34d399', '#a78bfa', '#fb923c', '#22d3ee', '#f87171', '#a3e635', '#e879f9', '#facc15', '#94a3b8'];
  const MAX = 12;

  const state = { places: [], selected: new Set(), results: [], metric: 'temp_max', chart: null };
  const key = p => `${(+p.latitude).toFixed(2)},${(+p.longitude).toFixed(2)}`;

  function renderPicker() {
    $('compare-picker').innerHTML = state.places.length
      ? state.places.map(p => `<span class="chip ${state.selected.has(key(p)) ? 'on' : ''}" data-k="${key(p)}">
          ${SkyCast.flag(p.country_code)} ${esc(p.name)}${p.extra ? ' <span class="x" data-x>✕</span>' : ''}</span>`).join('')
      : '<span class="muted">No favorites yet — search above to add cities to compare.</span>';
  }

  async function refresh() {
    renderPicker();
    const chosen = state.places.filter(p => state.selected.has(key(p)));
    store.set('compareSelected', [...state.selected]);
    if (!chosen.length) {
      state.results = [];
      render();
      return;
    }
    try {
      const data = await weather('compare', { points: chosen.map(p => `${p.latitude},${p.longitude}`).join(';') });
      state.results = data.results.map((r, i) => ({ ...r, place: chosen[i], color: COLORS[i % COLORS.length] }));
      render();
    } catch (e) { toast(e.message); }
  }

  function render() {
    renderLeaders();
    renderCards();
    renderChart();
  }

  function renderLeaders() {
    const r = state.results;
    if (r.length < 2) { $('leaders').innerHTML = ''; return; }
    const by = (f, dir = 1) => [...r].sort((a, b) => dir * (f(b) - f(a)))[0];
    const items = [
      ['🔥', 'Warmest now', by(x => x.current.temp), x => fmt.temp(x.current.temp)],
      ['🧊', 'Coldest now', by(x => x.current.temp, -1), x => fmt.temp(x.current.temp)],
      ['💨', 'Windiest', by(x => x.current.wind_speed), x => fmt.wind(x.current.wind_speed)],
      ['☔', 'Wettest week', by(x => x.daily.reduce((s, d) => s + (d.precip_prob_max || 0), 0)),
        x => `${Math.round(x.daily.reduce((s, d) => s + (d.precip_prob_max || 0), 0) / x.daily.length)}% avg chance`],
    ];
    $('leaders').innerHTML = items.map(([ico, label, x, val]) => `
      <div class="insight good"><div class="ico">${ico}</div>
        <div><div class="title">${label}</div><div class="text">${esc(x.place.name)} · ${val(x)}</div></div></div>`).join('');
  }

  function renderCards() {
    $('compare-cards').innerHTML = state.results.map(r => {
      const c = r.current;
      const loc = r.place;
      return `<a class="card ccard" href="/?lat=${loc.latitude}&lon=${loc.longitude}&name=${encodeURIComponent(loc.name)}" style="text-decoration:none;color:inherit">
        <div class="cc-top">
          <div><div class="fav-name"><span class="swatch" style="background:${r.color}"></span>${esc(loc.name)}</div>
            <div class="fav-sub">${esc(loc.country || '')} · ${esc(r.location.timezone_abbreviation || '')}</div></div>
          <span class="cc-icon">${c.condition.icon}</span>
        </div>
        <div class="cc-temp">${fmt.temp(c.temp)}</div>
        <div class="muted small">${esc(c.condition.text)} · feels ${fmt.temp(c.feels_like)}</div>
        <div class="muted small">💧 ${c.humidity}% · 💨 ${fmt.wind(c.wind_speed)}</div>
        <div class="cc-week">${r.daily.map(d => `<div><span>${time.weekday(d.time)[0]}</span><span>${d.condition.icon}</span><b>${fmt.temp(d.temp_max)}</b></div>`).join('')}</div>
      </a>`;
    }).join('');
  }

  function renderChart() {
    if (state.chart) state.chart.destroy();
    if (!state.results.length) return;
    const m = state.metric;
    const isTemp = m !== 'precip_prob_max';
    state.chart = new Chart($('compare-chart'), {
      type: 'line',
      data: {
        labels: state.results[0].daily.map((d, i) => (i === 0 ? 'Today' : `${time.weekday(d.time)} ${time.dayMonth(d.time)}`)),
        datasets: state.results.map(r => ({
          label: r.place.name,
          data: r.daily.map(d => (isTemp ? conv.t(d[m]) : d[m])),
          borderColor: r.color, backgroundColor: r.color, tension: .35, borderWidth: 2.5, pointRadius: 3,
        })),
      },
      options: {
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { labels: { usePointStyle: true, boxWidth: 8 } } },
        scales: { x: { grid: { display: false } },
          y: isTemp ? { ticks: { callback: v => `${Math.round(v)}°` } } : { min: 0, max: 100, ticks: { callback: v => `${v}%` } } },
      },
    });
  }

  async function init() {
    let favs = [];
    try { favs = await favorites.list(); } catch (e) { toast(e.message); }
    const extras = store.get('compareExtras', []).map(p => ({ ...p, extra: true }));
    state.places = [...favs, ...extras.filter(e => !favs.some(f => key(f) === key(e)))];
    const saved = store.get('compareSelected', null);
    const valid = new Set(state.places.map(key));
    state.selected = new Set(saved ? saved.filter(k => valid.has(k)) : state.places.slice(0, 4).map(key));
    if (!state.selected.size) state.places.slice(0, 4).forEach(p => state.selected.add(key(p)));

    SkyCast.attachSearch(r => {
      const k = key(r);
      if (!state.places.some(p => key(p) === k)) {
        const place = { ...r, extra: true };
        state.places.push(place);
        store.set('compareExtras', state.places.filter(p => p.extra));
      }
      if (state.selected.size >= MAX) { toast(`Compare up to ${MAX} places`); return; }
      state.selected.add(k);
      refresh();
    });

    $('compare-picker').addEventListener('click', e => {
      const chip = e.target.closest('.chip');
      if (!chip) return;
      const k = chip.dataset.k;
      if (e.target.closest('[data-x]')) {
        state.places = state.places.filter(p => key(p) !== k);
        state.selected.delete(k);
        store.set('compareExtras', state.places.filter(p => p.extra));
      } else if (state.selected.has(k)) {
        state.selected.delete(k);
      } else if (state.selected.size < MAX) {
        state.selected.add(k);
      }
      refresh();
    });
    $('compare-tabs').addEventListener('click', e => {
      const b = e.target.closest('button[data-metric]');
      if (!b) return;
      state.metric = b.dataset.metric;
      $('compare-tabs').querySelectorAll('button').forEach(x => x.classList.toggle('active', x === b));
      renderChart();
    });
    SkyCast.onUnitsChange(render);
    refresh();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
