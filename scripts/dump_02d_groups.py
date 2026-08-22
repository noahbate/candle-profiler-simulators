#!/usr/bin/env python3
"""02d: per-signal-type templates: question, all answers, key varying fields."""
import json, re
from pathlib import Path
from collections import defaultdict

base = Path('/Users/hermes/projects/candle-profiler-simulators/reference/assemble')
sc = json.loads((base / '02d.json').read_text())['scenario']
data = sc['dataset']['data']
ET_OFF = -4

def et(t):
    import datetime
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).astimezone(
        datetime.timezone(datetime.timedelta(hours=ET_OFF)))

md_by_idx = {m['triggerBarIdx']: m.get('metadata', {}) for m in sc['dataPointMarkers']}

groups = defaultdict(list)
for p in sc['prompts']:
    md = md_by_idx[p['triggerCandle']]
    groups[md.get('signal_type')].append((p, md))

def money(s):
    return re.sub(r'\d{4,6}\.\d{2}', 'PRICE', s)

for st, items in sorted(groups.items()):
    print('='*100)
    print(f"### {st} ({len(items)})")
    qs = defaultdict(list)
    for p, md in items:
        qs[money(p['questionText'])].append((p['questionText'], p['correctAnswer']))
    for k, v in qs.items():
        print(f"  Q: {v[0][0]}")
        seen = set()
        for qt, ans in v:
            if ans not in seen:
                print(f"    -> {ans}")
                seen.add(ans)
    allmd = [md for p, md in items]
    for f in ['takeout_side','first_takeout_side','base_side','effective_side','rule_bias_side',
              'focus_open_source','focus_open_price','context_open_price','active_open_price',
              'close_side_vs_open','close_through_open','open_hold_confirmed','alert_mid_breached',
              'c2_took_c1_high','c2_took_c1_low','c3_took_c2_high','c3_took_c2_low',
              'c3_close_side_vs_c2_high','c3_close_side_vs_c2_low','c3_close_side_vs_c2_open','c3_close_through_c2_open',
              'c3_breached_c2_open_wick','mid_touched','block_start_hour','target_hour']:
        vals = sorted(set(str(md.get(f)) for md in allmd))
        if len(vals) <= 5:
            print(f"    {f}: {vals}")
    print(f"  triggers: {[(et(data[p['triggerCandle']]['time']).strftime('%m-%d %H:%M'), p['triggerCandle']) for p, md in items]}")
