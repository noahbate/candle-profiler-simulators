/* Profiler Simulators — private clone. Catalog + shared scenario loader. */

const CONCEPTS = [
  { id: '01a', name: 'Box Breakout' },
  { id: '01c', name: 'BP Breach' },
  { id: '01d', name: 'Instat' },
  { id: '01e', name: 'Doji' },
  { id: '01f', name: 'Prev Hour' },
  { id: '01g', name: 'Sweep+SB' },
  { id: '02a', name: 'Line/Apex (Framework)' },
  { id: '02c', name: 'Rolling 3H Structure' },
  { id: '02d', name: '3H Probability Flags' },
  // Generated scenarios — verify status noted in PROJECT_STATE.md
  // 01a: CURRICULUM-CONFIRMED (vault: Pack BootCamp 05 Box). 19/19 exact bar+answer on capture.
  //      false_05_box = swipe box, fail 0.05% thr, suck back to 50% level + hold 2 bars.
  // 01c: CURRICULUM-CONFIRMED. 30/30 exact bar+answer on capture (two-stage 0.05%+0.10% breach).
  // 01d: CURRICULUM-VERIFIED. 14/14 exact bar+answer on capture (1 ambiguous hour skipped).
  // 01e: CURRICULUM-VERIFIED. 7/7 exact bar+answer on capture (bit-for-bit incl. price text).
  // 01f: CURRICULUM-VERIFIED. 6/6 mid_touch + 7/7 footprint_test exact bar+answer on capture
  //      (bit-for-bit incl. price text; wick zone = actual prev-hour wick; co-located fp shifts +1).
  // 01g: CURRICULUM-VERIFIED. 4/4 exact bar+answer on capture.
// 02a: CURRICULUM-VERIFIED. 52/52 exact bar+answer + signal_type vs capture (Line/Apex walkthrough).
// 02c: LOGIC-VERIFIED (~). All 7 signal_types + per-event answers correct; rolling-cycle cadence
//      over-fires on this day (29 gen vs 19 capture) — cycle-roll gap rule needs more capture days.
// 02d: captured-only (no generator yet) — C1/C2/C3 3-hour probability state machine (~60 fields/event).
  { id: 'gen_01a_2024-01-16', name: 'Gen 01a Box Breakout (2024-01-16) ✓' },
  { id: 'gen_01c_2025-06-11', name: 'Gen 01c BP Breach (2025-06-11) ✓' },
  { id: 'gen_01d_2024-10-31', name: 'Gen 01d Instat (2024-10-31) ✓' },
  { id: 'gen_01e_2025-06-12', name: 'Gen 01e Doji (2025-06-12) ✓' },
  { id: 'gen_01f_2024-03-17', name: 'Gen 01f Prev Hour (2024-03-17) ✓' },
  { id: 'gen_01g_2025-06-29', name: 'Gen 01g Sweep+SB (2025-06-29) ✓' },
  { id: 'gen_02a_2024-02-06', name: 'Gen 02a Line/Apex (2024-02-06) ✓' },
  { id: 'gen_02c_2024-05-21', name: 'Gen 02c Rolling 3H (2024-05-21) ~' },
  { id: '02d', name: '02d 3H Probability (captured)' },
];

async function renderCatalog() {
  const el = document.getElementById('catalog');
  for (const c of CONCEPTS) {
    let meta = '';
    try {
      const d = await (await fetch(`scenarios/${c.id}.json`)).json();
      const s = d.scenario;
      meta = `${s.name.split('—')[0].trim()} · ${s.dataset.data.length} bars · ${s.prompts.length} prompts · pass ${s.passingScore}%`;
    } catch (e) { meta = 'scenario missing: ' + e.message; }
    const a = document.createElement('a');
    a.className = 'card';
    a.href = `play.html?concept=${c.id}`;
    a.innerHTML = `<div class="cid">${c.id.toUpperCase()}</div><div class="cname">${c.name}</div><div class="cmeta">${meta}</div>`;
    el.appendChild(a);
  }
}
