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
  { id: 'gen_01a_2025-01-21', name: '★ Gen 01a Box Breakout (2025-01-21)' },
  { id: 'gen_01a_2025-03-14', name: '★ Gen 01a Box Breakout (2025-03-14)' },
  { id: 'gen_01a_2025-06-09', name: '★ Gen 01a Box Breakout (2025-06-09)' },
  { id: 'gen_01d_2025-01-21', name: '★ Gen 01d Instat (2025-01-21)' },
  { id: 'gen_01d_2025-03-14', name: '★ Gen 01d Instat (2025-03-14)' },
  { id: 'gen_01d_2025-06-09', name: '★ Gen 01d Instat (2025-06-09)' },
  { id: 'gen_01e_2025-01-21', name: '★ Gen 01e Doji (2025-01-21)' },
  { id: 'gen_01e_2025-03-14', name: '★ Gen 01e Doji (2025-03-14)' },
  { id: 'gen_01e_2025-06-09', name: '★ Gen 01e Doji (2025-06-09)' },
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
