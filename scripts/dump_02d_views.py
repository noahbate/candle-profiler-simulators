#!/usr/bin/env python3
"""02d: view schedule per prompt (c1/c2/c3 start hours + window_start/end + actual bar)."""
import json, datetime
from pathlib import Path

base = Path('/Users/hermes/projects/candle-profiler-simulators/reference/assemble')
sc = json.loads((base / '02d.json').read_text())['scenario']
data = sc['dataset']['data']

def et(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).astimezone(
        datetime.timezone(datetime.timedelta(hours=-4)))

md_by_idx = {m['triggerBarIdx']: m.get('metadata', {}) for m in sc['dataPointMarkers']}

for i, p in enumerate(sc['prompts']):
    tb = p['triggerCandle']
    md = md_by_idx[tb]
    t = et(data[tb]['time'])
    ws = md.get('window_start_ts_utc'); we = md.get('window_end_ts_utc')
    wsl = et(ws).strftime('%H:%M') if ws else '?'
    wel = et(we).strftime('%H:%M') if we else '?'
    print(f"{i:2d} {t.strftime('%H:%M')} | {md.get('signal_type'):28s} | view C1={md.get('c1_start_hour')} C2={md.get('c2_start_hour')} C3={md.get('c3_start_hour')} | win {wsl}-{wel} | block={md.get('block_start_hour')} tgt={md.get('target_hour')} | view_start={md.get('view_start_bar')} | state={md.get('state_seq')}")
