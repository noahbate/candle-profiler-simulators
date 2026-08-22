#!/usr/bin/env python3
"""02a stats: unique questions, variants, per-block sequence."""
import json, datetime
from pathlib import Path
from collections import Counter, defaultdict

base = Path('/Users/hermes/projects/candle-profiler-simulators/reference/assemble')
sc = json.loads((base / '02a.json').read_text())['scenario']
data = sc['dataset']['data']
ET = datetime.timezone(datetime.timedelta(hours=-4))

def et(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).astimezone(ET)

md_by_idx = {m['triggerBarIdx']: m.get('metadata', {}) for m in sc['dataPointMarkers']}

qs = [(p['questionText'], md_by_idx[p['triggerCandle']].get('variant')) for p in sc['prompts']]
uniq = set(q for q, v in qs)
print("unique questions:", len(uniq))
for q in sorted(uniq):
    print(f"  [{sum(1 for qq,_ in qs if qq==q)}] {q[:120]}")

print("\nvariants:")
vc = Counter(v for _, v in qs)
for v, c in sorted(vc.items()):
    print(f"  {c:2d} {v}")

# Per block: list (bar_local, variant) sorted
print("\nPer-block sequence (bar local = idx - block_start):")
blocks = defaultdict(list)
for p in sc['prompts']:
    tb = p['triggerCandle']
    md = md_by_idx[tb]
    bh = md.get('block_hour')
    if bh is None:
        continue
    # block start = first bar with ET hour == bh and minute == 0
    blocks[bh].append((tb, md.get('variant'), p['questionText'][:60]))
for bh in sorted(blocks):
    # find block start bar
    start = None
    for i, b in enumerate(data):
        t = et(b['time'])
        if t.hour == bh and t.minute == 0:
            start = i
            break
    print(f"\n=== block {bh}:00 ET (start bar {start}) ===")
    for tb, v, q in sorted(blocks[bh]):
        print(f"  +{tb-start:3d} (idx {tb}) {v} | {q}")
