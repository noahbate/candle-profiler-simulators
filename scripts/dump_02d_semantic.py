#!/usr/bin/env python3
"""02d compact semantic dump: per prompt, question key + answer + key metadata."""
import json, datetime
from pathlib import Path

base = Path('/Users/hermes/projects/candle-profiler-simulators/reference/assemble')
sc = json.loads((base / '02d.json').read_text())['scenario']
data = sc['dataset']['data']
ET = datetime.timezone(datetime.timedelta(hours=-4))

def et(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).astimezone(ET)

md_by_idx = {m['triggerBarIdx']: m.get('metadata', {}) for m in sc['dataPointMarkers']}

KEY = ['signal_type','mode','timeframe','block_start_hour','target_hour','live_phase',
       'c1_start_hour','c2_start_hour','c3_start_hour','c1_end_hour','c2_end_hour','c3_end_hour',
       'first_takeout_side','takeout_side','base_side','effective_side','rule_bias_side',
       'c1_open','c1_close','c1_high','c1_low','c2_open','c2_close','c2_high','c2_low',
       'c3_open','c3_close','c3_high','c3_low','mid_price','alert_mid_price',
       'focus_open_price','focus_open_source','context_open_price','active_open_price',
       'close_side_vs_open','close_through_open','open_hold_confirmed','open_touched',
       'c2_took_c1_high','c2_took_c1_low','c3_took_c2_high','c3_took_c2_low',
       'c3_close_side_vs_c2_high','c3_close_side_vs_c2_low','c3_close_side_vs_c2_open','c3_close_through_c2_open',
       'c3_breached_c2_open_wick','alert_mid_breached','mid_touched','confirmation_open_breached_wick',
       'confirmation_open_breached_close','provisional','reason_codes','state_seq',
       'window_start_ts_utc','window_end_ts_utc','view_start_bar','view_id',
       'actual_trigger_bar_idx','actual_trigger_time']

lines = []
for i, p in enumerate(sc['prompts']):
    tb = p['triggerCandle']
    t = et(data[tb]['time'])
    md = md_by_idx.get(tb, {})
    q = p['questionText']
    # compress question: keep it but truncate to 130
    lines.append(f"== {i} | {t.strftime('%m-%d %H:%M')} | idx {tb} | {md.get('signal_type')}")
    lines.append(f"  Q: {q}")
    lines.append(f"  A: {p['correctAnswer']}")
    # key metadata one-liners
    for k in KEY:
        if k in md and md[k] is not None:
            v = md[k]
            if isinstance(v, float):
                v = round(v, 4)
            lines.append(f"    {k}: {v}")
    lines.append('')
Path('/Users/hermes/projects/candle-profiler-simulators/scripts/capture_dumps/02d_semantic.txt').write_text('\n'.join(lines))
print("written", len(lines), "lines")
