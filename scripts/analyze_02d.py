#!/usr/bin/env python3
"""Compact 02d view: unique questions, signal types, key metadata per prompt."""
import json, datetime
from pathlib import Path
from collections import Counter, defaultdict

base = Path('/Users/hermes/projects/candle-profiler-simulators/reference/assemble')
sc = json.loads((base / '02d.json').read_text())['scenario']
data = sc['dataset']['data']
ET = datetime.timezone(datetime.timedelta(hours=-4))

def et(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).astimezone(ET)

md_by_idx = {m['triggerBarIdx']: m.get('metadata', {}) for m in sc['dataPointMarkers']}

print("=== Unique question texts (%d) ===" % len(set(p['questionText'] for p in sc['prompts'])))
for q in sorted(set(p['questionText'] for p in sc['prompts'])):
    cnt = sum(1 for p in sc['prompts'] if p['questionText'] == q)
    print(f"  [{cnt:2d}] {q[:150]}")

print("\n=== signal_type distribution ===")
print(dict(Counter(md_by_idx[p['triggerCandle']].get('signal_type') for p in sc['prompts'])))

print("\n=== base_signal_type distribution ===")
print(dict(Counter(md_by_idx[p['triggerCandle']].get('base_signal_type') for p in sc['prompts'])))

print("\n=== per-prompt compact ===")
for i, p in enumerate(sc['prompts']):
    tb = p['triggerCandle']
    t = et(data[tb]['time'])
    md = md_by_idx.get(tb, {})
    st = md.get('signal_type')
    bt = md.get('base_signal_type')
    qf = md.get('question_focus')
    mode = md.get('mode')
    tf = md.get('timeframe')
    eff = md.get('effective_side')
    print(f"{i:2d} {t.strftime('%m-%d %H:%M')} | {st} | base={bt} | qf={qf} | mode={mode} | tf={tf} | eff={eff}")
