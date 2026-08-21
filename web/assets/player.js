/* Profiler Simulators — candle chart player with triggerCandle prompts. */
(() => {
  const params = new URLSearchParams(location.search);
  const conceptId = params.get('concept') || '01a';

  const cv = document.getElementById('chart');
  const ctx = cv.getContext('2d');
  const el = id => document.getElementById(id);

  let scenario, data, promptsByBar = new Map(), markersByBar = new Map();
  let pos = 0;                    // current candle index (exclusive upper bound drawn)
  let playing = false, timer = null, speed = 1;
  let score = 0, maxScore = 0, answered = 0;
  let promptShown = false;        // whether the prompt for current bar is open
  let answeredBars = new Set();

  const SPEEDS = [1, 2, 4, 8, 16];

  init();

  async function init() {
    const r = await fetch(`scenarios/${conceptId}.json`);
    if (!r.ok) { document.body.innerHTML = `<p style="padding:32px">Scenario ${conceptId} not found — <a href="index.html">back</a></p>`; return; }
    const payload = await r.json();
    scenario = payload.scenario;
    data = scenario.dataset.data;

    // map prompts and markers by trigger candle
    for (const p of scenario.prompts) {
      if (!promptsByBar.has(p.triggerCandle)) promptsByBar.set(p.triggerCandle, []);
      promptsByBar.get(p.triggerCandle).push(p);
      maxScore += (p.points || 1);
    }
    for (const m of (scenario.dataPointMarkers || [])) markersByBar.set(m.triggerBarIdx, m);

    el('scenario-name').textContent = `${scenario.name} — ${scenario.prompts.length} prompts · pass ${scenario.passingScore}%`;

    // Start at random ~55% through like the site (or first prompt - small run-up if earlier)
    const firstTrigger = Math.min(...scenario.prompts.map(p => p.triggerCandle));
    const randomStart = Math.floor(data.length * 0.55);
    pos = Math.max(0, Math.min(randomStart, firstTrigger > 200 ? firstTrigger - 120 : randomStart));
    // never start past the last prompt
    const lastTrigger = Math.max(...scenario.prompts.map(p => p.triggerCandle));
    if (pos > lastTrigger - 50) pos = Math.max(0, lastTrigger - 400);

    fitCanvas();
    addEventListener('resize', () => { fitCanvas(); draw(); });
    draw();
    bindControls();
    updateHud();
  }

  function fitCanvas() {
    const wrap = document.getElementById('chartwrap');
    cv.width = wrap.clientWidth - 16;
    cv.height = Math.max(320, innerHeight - 140);
  }

  function bindControls() {
    el('btn-play').onclick = togglePlay;
    el('btn-next').onclick = () => step();
    el('btn-prev').onclick = () => { if (!playing) { pos = Math.max(0, pos - 1); draw(); updateHud(); } };
    el('btn-speed').onclick = () => {
      speed = SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length];
      el('btn-speed').textContent = speed + 'x';
      if (playing) startTimer();
    };
    el('btn-skip').onclick = skipToNextAnswer;
    el('p-next').onclick = closePrompt;
    addEventListener('keydown', e => {
      if (e.code === 'Space') { e.preventDefault(); if (promptShown) closePrompt(); else togglePlay(); }
    });
  }

  function togglePlay() { playing = !playing; el('btn-play').innerHTML = playing ? '&#10074;&#10074; Pause' : '&#9654; Play'; if (playing) startTimer(); else stopTimer(); }
  function startTimer() { stopTimer(); timer = setInterval(tick, Math.max(30, 180 / speed)); }
  function stopTimer() { clearInterval(timer); timer = null; }
  function tick() { for (let i = 0; i < speed; i++) { if (!step()) return; } }

  function step() {
    if (promptShown) return true;               // blocked until prompt answered/continued
    if (pos >= data.length) return finish(), false;
    pos++;
    draw(); updateHud();
    if (promptsByBar.has(pos - 1)) { showPrompts(promptsByBar.get(pos - 1)); if (playing) togglePlay(); }
    return true;
  }

  function skipToNextAnswer() {
    const upcoming = scenario.prompts.map(p => p.triggerCandle).filter(b => b >= pos).sort((a, b) => a - b);
    if (!upcoming.length) return;
    pos = upcoming[0] + 1;  // jump so step() triggers it... actually prompt fires when pos-1 == trigger
    // Set to the trigger bar then call step
    pos = upcoming[0];
    if (!promptShown) step();
    draw(); updateHud();
  }

  /* ---- prompt flow ---- */
  function showPrompts(list) {
    promptShown = true;
    const p = list[0]; // one at a time; multiple at same bar rare
    if (answeredBars.has(p.id)) { promptShown = false; return; }
    answeredBars.add(p.id);
    el('p-tag').textContent = `${p.conceptTag.toUpperCase()} · bar ${p.triggerCandle} · ${p.points} pt`;
    el('p-q').textContent = p.questionText;
    el('p-expl').style.display = 'none';
    el('p-next').style.display = 'none';
    const box = el('p-opts'); box.innerHTML = '';
    for (const opt of p.answerOptions) {
      const b = document.createElement('button');
      b.className = 'opt'; b.textContent = opt;
      b.onclick = () => {
        const correct = opt === p.correctAnswer;
        b.classList.add(correct ? 'correct' : 'wrong');
        if (!correct) box.querySelectorAll('.opt').forEach(o => { if (o.textContent === p.correctAnswer) o.classList.add('correct'); });
        else score += (p.points || 1);
        answered++;
        box.querySelectorAll('.opt').forEach(o => o.onclick = null);
        if (p.explanation) { el('p-expl').textContent = p.explanation; el('p-expl').style.display = 'block'; }
        el('p-next').style.display = 'block';
        updateHud();
      };
      box.appendChild(b);
    }
    el('prompt-panel').style.display = 'block';
  }

  function closePrompt() {
    el('prompt-panel').style.display = 'none';
    promptShown = false;
    if (!playing) togglePlay();
  }

  function finish() {
    stopTimer(); playing = false;
    const pct = maxScore ? Math.round(100 * score / maxScore) : 0;
    const passed = pct >= scenario.passingScore;
    el('f-title').innerHTML = passed ? 'Passed' : 'Not passed';
    el('f-detail').innerHTML = `Score <b>${score}</b> / ${maxScore} (${pct}%) · answered ${answered}/${scenario.prompts.length}`;
    el('final').classList.add('show');
  }

  function updateHud() {
    el('progress').textContent = `bar ${pos}/${data.length}`;
    el('scorebox').innerHTML = `Score <b>${score}</b>/${maxScore}`;
  }

  /* ---- candle renderer ---- */
  function draw() {
    const W = cv.width, H = cv.height;
    ctx.fillStyle = '#0f172a'; ctx.fillRect(0, 0, W, H);
    const PAD = { l: 56, r: 12, t: 12, b: 26 };
    const plotW = W - PAD.l - PAD.r, plotH = H - PAD.t - PAD.b;

    const VISIBLE = 320;                        // candles on screen
    const end = pos, start = Math.max(0, end - VISIBLE);
    if (end - start < 2) return;
    const slice = data.slice(start, end);
    let hi = -Infinity, lo = Infinity;
    for (const c of slice) { if (c.high > hi) hi = c.high; if (c.low < lo) lo = c.low; }
    // include box levels + thresholds from upcoming/recent markers so lines stay visible
    for (let i = start; i < end; i++) {
      const m = markersByBar.get(i);
      if (m && m.metadata) { ['box_high', 'box_low', 'threshold_price'].forEach(k => { const v = m.metadata[k]; if (v != null) { hi = Math.max(hi, v); lo = Math.min(lo, v); } }); }
    }
    const pad = (hi - lo) * 0.06 || 1; hi += pad; lo -= pad;
    const y = v => PAD.t + (hi - v) / (hi - lo) * plotH;
    const bw = plotW / slice.length;
    const cw = Math.max(2, bw * 0.7), ox = PAD.l + (bw - cw) / 2;

    // horizontal price grid
    ctx.strokeStyle = '#ffffff10'; ctx.fillStyle = '#64748b'; ctx.font = '11px JetBrains Mono, monospace'; ctx.textAlign = 'right';
    const ticks = 8;
    for (let i = 0; i <= ticks; i++) {
      const v = hi - (hi - lo) * i / ticks, yy = y(v);
      ctx.beginPath(); ctx.moveTo(PAD.l, yy); ctx.lineTo(W - PAD.r, yy); ctx.stroke();
      ctx.fillText(v.toFixed(1), PAD.l - 6, yy + 4);
    }

    // candles
    for (let i = 0; i < slice.length; i++) {
      const c = slice[i], x = ox + i * bw;
      const up = c.close >= c.open;
      ctx.strokeStyle = up ? '#22c55e' : '#ef4444';
      ctx.fillStyle = up ? '#22c55e33' : '#ef444433';
      // wick
      ctx.beginPath(); ctx.moveTo(x + cw / 2, y(c.high)); ctx.lineTo(x + cw / 2, y(c.low)); ctx.stroke();
      // body
      const yO = y(c.open), yC = y(c.close), top = Math.min(yO, yC), hgt = Math.max(1, Math.abs(yC - yO));
      ctx.fillRect(x, top, cw, hgt);
      ctx.strokeRect(x, top, cw, hgt);
    }

    // markers: box lines + threshold (draw across visible width once encountered)
    const drawnBoxes = new Set();
    for (let i = start; i < end; i++) {
      const m = markersByBar.get(i);
      if (!m) continue;
      const md = m.metadata || {};
      const key = `${md.box_high}-${md.box_low}`;
      if (drawnBoxes.has(key)) continue;
      drawnBoxes.add(key);
      if (md.box_high != null && md.box_low != null) {
        ctx.fillStyle = 'rgba(34,211,238,0.06)';
        ctx.fillRect(PAD.l, y(md.box_high), plotW, y(md.box_low) - y(md.box_high));
        ctx.strokeStyle = 'rgba(34,211,238,0.6)'; ctx.setLineDash([4, 4]);
        ctx.beginPath(); ctx.moveTo(PAD.l, y(md.box_high)); ctx.lineTo(W - PAD.r, y(md.box_high)); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(PAD.l, y(md.box_mid)); ctx.lineTo(W - PAD.r, y(md.box_mid)); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(PAD.l, y(md.box_low)); ctx.lineTo(W - PAD.r, y(md.box_low)); ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = '#67e8f9'; ctx.textAlign = 'left';
        ctx.fillText('0-5 box', PAD.l + 4, y(md.box_high) - 4);
      }
      if (md.threshold_price != null) {
        ctx.strokeStyle = 'rgba(245,158,11,0.7)'; ctx.setLineDash([2, 3]);
        ctx.beginPath(); ctx.moveTo(PAD.l, y(md.threshold_price)); ctx.lineTo(W - PAD.r, y(md.threshold_price)); ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = '#fbbf24'; ctx.textAlign = 'left';
        ctx.fillText('0.05% threshold', PAD.l + 4, y(md.threshold_price) + 12);
      }
    }

    // prompt pins
    for (let i = start; i < end; i++) {
      if (!promptsByBar.has(i)) continue;
      const x = ox + (i - start) * bw + cw / 2;
      const answeredOrPending = [...promptsByBar.get(i)].some(p => answeredBars.has(p.id));
      ctx.fillStyle = answeredOrPending ? '#22d3ee' : '#f59e0b';
      ctx.beginPath(); ctx.arc(x, PAD.t + 8, 4, 0, Math.PI * 2); ctx.fill();
    }

    // time axis: hour labels
    ctx.fillStyle = '#64748b'; ctx.textAlign = 'center';
    for (let i = start; i < end; i++) {
      const c = data[i], d = new Date(c.time * 1000);
      if (d.getMinutes() === 0) {
        const x = ox + (i - start) * bw + cw / 2;
        ctx.fillText(d.getHours().toString().padStart(2, '0') + ':00', x, H - 8);
        ctx.strokeStyle = '#ffffff08';
        ctx.beginPath(); ctx.moveTo(x, PAD.t); ctx.lineTo(x, H - PAD.b); ctx.stroke();
      }
    }
  }
})();
