/* Animated weather backdrop: rain, snow, lightning, stars and fog on a full-screen canvas. */
const WeatherFX = (() => {
  const canvas = document.getElementById('fx');
  const ctx = canvas.getContext('2d');
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let particles = [], mode = 'none', flash = 0, raf = null, w = 0, h = 0;

  function resize() {
    const dpr = window.devicePixelRatio || 1;
    w = window.innerWidth; h = window.innerHeight;
    canvas.width = w * dpr; canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  const rand = (a, b) => a + Math.random() * (b - a);

  function spawn(kind) {
    switch (kind) {
      case 'rain': return { x: rand(0, w), y: rand(-h, h), len: rand(10, 22), v: rand(9, 16), a: rand(.15, .4) };
      case 'drizzle': return { x: rand(0, w), y: rand(-h, h), len: rand(5, 10), v: rand(5, 8), a: rand(.1, .3) };
      case 'snow': return { x: rand(0, w), y: rand(-h, h), r: rand(1, 3.5), v: rand(.5, 1.6), drift: rand(0, Math.PI * 2), a: rand(.4, .9) };
      case 'stars': return { x: rand(0, w), y: rand(0, h * .7), r: rand(.4, 1.4), phase: rand(0, Math.PI * 2), a: rand(.3, .9) };
      case 'fog': return { x: rand(-200, w), y: rand(0, h), r: rand(120, 260), v: rand(.1, .35), a: rand(.03, .07) };
      default: return null;
    }
  }

  function set(theme, isDay) {
    const map = { rain: 'rain', storm: 'rain', drizzle: 'drizzle', snow: 'snow', fog: 'fog' };
    const next = map[theme] || ((theme === 'clear' || theme === 'partly') && !isDay ? 'stars' : 'none');
    const storm = theme === 'storm';
    if (next === mode && storm === set.storm) return;
    mode = next; set.storm = storm;
    const count = { rain: 220, drizzle: 120, snow: 160, stars: 140, fog: 14, none: 0 }[mode];
    particles = Array.from({ length: reduced ? 0 : count }, () => spawn(mode));
    if (!raf && !reduced) raf = requestAnimationFrame(tick);
  }

  function tick(t) {
    ctx.clearRect(0, 0, w, h);
    for (const p of particles) {
      if (mode === 'rain' || mode === 'drizzle') {
        p.y += p.v; p.x -= p.v * .15;
        if (p.y > h) { p.y = -p.len; p.x = rand(0, w * 1.1); }
        ctx.strokeStyle = `rgba(186,230,253,${p.a})`;
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(p.x + p.len * .15, p.y - p.len); ctx.stroke();
      } else if (mode === 'snow') {
        p.drift += .01; p.y += p.v; p.x += Math.sin(p.drift) * .6;
        if (p.y > h) { p.y = -5; p.x = rand(0, w); }
        ctx.fillStyle = `rgba(255,255,255,${p.a})`;
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill();
      } else if (mode === 'stars') {
        const a = p.a * (.6 + .4 * Math.sin(t / 900 + p.phase));
        ctx.fillStyle = `rgba(255,255,255,${a})`;
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill();
      } else if (mode === 'fog') {
        p.x += p.v; if (p.x - p.r > w) p.x = -p.r;
        const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r);
        g.addColorStop(0, `rgba(255,255,255,${p.a})`); g.addColorStop(1, 'rgba(255,255,255,0)');
        ctx.fillStyle = g; ctx.fillRect(p.x - p.r, p.y - p.r, p.r * 2, p.r * 2);
      }
    }
    if (set.storm) {
      if (flash <= 0 && Math.random() < .004) flash = 1;
      if (flash > 0) { ctx.fillStyle = `rgba(255,255,255,${flash * .35})`; ctx.fillRect(0, 0, w, h); flash -= .06; }
    }
    raf = particles.length || set.storm ? requestAnimationFrame(tick) : null;
  }

  window.addEventListener('resize', resize);
  resize();
  return { set };
})();
