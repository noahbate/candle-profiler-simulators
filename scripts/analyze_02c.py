#!/usr/bin/env python3
"""Analyze 02c capture: per-ET-hour events and H1 signature logic."""
import json, datetime
from pathlib import Path
from collections import defaultdict

base = Path('/Users/hermes/projects/candle-profiler-simulators/reference/assemble')
sc = json.loads((base / '02c.json').read_text())['scenario']
data = sc['dataset']['data']
ET = datetime.timezone(datetime.timedelta(hours=-4))

def et(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).astimezone(ET)

events = defaultdict(list)
for p in sc['prompts']:
    tb = p['triggerCandle']
    t = et(data[tb]['time'])
    md = {m['triggerBarIdx']: m.get('metadata', {}) for m in sc['dataPointMarkers']}.get(tb, {})
    events[t.hour].append((t.minute, md.get('signal_type'), md.get('cycle_role'), p['correctAnswer'][:45]))

print("Per-ET-hour events:")
for h in sorted(events):
    for (mn, sig, role, ans) in events[h]:
        print(f"  ET {h:02d}:{mn:02d} {sig} ({role}) | {ans}")

# For every hour, compute first-15-min extreme formation
bars = []
for i, b in enumerate(data):
    bars.append((i, et(b['time']), b))
hours = defaultdict(list)
for i, tt, b in bars:
    hours[tt.hour].append((i, tt.minute, b))

def classify_first15(seg):
    first15 = seg[:15]
    hi = max(x[2]['high'] for x in first15)
    lo = min(x[2]['low'] for x in first15)
    hi_min = [x[1] for x in first15 if x[2]['high'] == hi][0]
    lo_min = [x[1] for x in first15 if x[2]['low'] == lo][0]
    fhi = max(x[2]['high'] for x in seg)
    flo = min(x[2]['low'] for x in seg)
    hi_is = hi == fhi; lo_is = lo == flo
    if lo_min <= 1 and lo_is: return f"perfect-bull(low@m{lo_min})"
    if hi_min <= 1 and hi_is: return f"perfect-bear(high@m{hi_min})"
    if 2 <= lo_min <= 5 and lo_is: return f"05-bull(low@m{lo_min})"
    if 2 <= hi_min <= 5 and hi_is: return f"05-bear(high@m{hi_min})"
    return f"other(hi@m{hi_min},lo@m{lo_min},hx={hi_is},lx={lo_is})"

print("\nPer-ET-hour first15 classification (hx=hi is hour extreme, lx=lo is hour extreme):")
for h in sorted(hours):
    seg = hours[h]
    if len(seg) < 60: continue
    print(f"  ET {h:02d}: {classify_first15(seg)}")
