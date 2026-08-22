#!/usr/bin/env python3
"""Debug 02a detection details against the 2024-02-06 session data."""
import json, sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path('/Users/hermes/projects/candle-profiler-simulators/scripts')))
import generate_scenario as gs

bars = gs.load_day('2024-02-06')
ETZ = ZoneInfo('America/New_York')

def et(i):
    import datetime
    return datetime.datetime.fromtimestamp(bars[i]['time'], tz=ETZ)

# block 9 start = 09:00 ET -> find idx
b9 = next(i for i, b in enumerate(bars) if et(i).hour == 9 and et(i).minute == 0)
b12 = next(i for i, b in enumerate(bars) if et(i).hour == 12 and et(i).minute == 0)
print("block9 start", b9, "block12 start", b12)

# --- instat block 12 H1 (h0=b12): Q1 = 12:00-12:15, Q2 = 12:15-12:30 ---
h0 = b12
q1h = max(bars[k]['high'] for k in range(h0, h0+15))
q1l = min(bars[k]['low'] for k in range(h0, h0+15))
print("\nB12 H1: q1h", q1h, "q1l", q1l)
bull_bars = [k for k in range(h0+15, h0+30) if bars[k]['high'] > q1h]
bear_bars = [k for k in range(h0+15, h0+30) if bars[k]['low'] < q1l]
print("  bull takeout bars:", [(k, et(k).strftime('%H:%M'), bars[k]['high']) for k in bull_bars])
print("  bear takeout bars:", [(k, et(k).strftime('%H:%M'), bars[k]['low']) for k in bear_bars])

# capture fired instat_low at 12:17 (idx 1097). What does the capture consider q1?
# capture metadata: q1_high 17852, q1_low 17824.5
print("  capture q1_high=17852 q1_low=17824.5")
# check bar 1097
print("  bar 1097:", et(1097).strftime('%H:%M'), bars[1097])

# --- sweep block 9 H1 (h0=b9): prev hour 08:00-09:00 ---
h0 = b9
prev = bars[h0-60:h0]
ph_high = max(b['high'] for b in prev); ph_low = min(b['low'] for b in prev)
ph_mid = (ph_high + ph_low) / 2
print("\nB9 H1 prev hour: high", ph_high, "low", ph_low, "mid", ph_mid)
print("  capture prev_hour_high=17746.5 prev_hour_low=17705.5 prev_hour_mid=17726")
sweeps = [k for k in range(h0, h0+15) if bars[k]['high'] > ph_high]
print("  sweep bars:", [(k, et(k).strftime('%H:%M'), bars[k]['high']) for k in sweeps])
closes_below = [k for k in range(h0+15, h0+60) if bars[k]['close'] < ph_mid]
print("  first closes below mid:", [(k, et(k).strftime('%H:%M'), bars[k]['close']) for k in closes_below[:5]])
print("  hour open:", bars[h0]['open'])

# --- prog_up block 12 ---
h1 = bars[b12:b12+60]; h2 = bars[b12+60:b12+120]; h3 = bars[b12+120:b12+180]
h1h = max(b['high'] for b in h1); h1l = min(b['low'] for b in h1)
h2h = max(b['high'] for b in h2); h2l = min(b['low'] for b in h2)
h3h = max(b['high'] for b in h3); h3l = min(b['low'] for b in h3)
print("\nB12: H1(h,l)=", h1h, h1l, "H2(h,l)=", h2h, h2l, "H3(h,l)=", h3h, h3l)
print("  prog_up:", h1h < h2h < h3h, h1l > h2l > h3l)
# H3 box
box3 = bars[b12+120:b12+125]
b3l = min(b['low'] for b in box3); b3h = max(b['high'] for b in box3)
print("  H3 box:", b3h, b3l, "(capture box_low 17841.25)")
breaks = [k for k in range(b12+125, b12+180) if bars[k]['low'] < b3l]
print("  H3 box-low breaks:", [(k, et(k).strftime('%H:%M'), bars[k]['low']) for k in breaks[:5]])

# --- 6-quarter trend ---
for label, bs in (('B9', b9), ('B12', b12)):
    q1o = bars[bs]['open']
    q6c = bars[bs+89]['close']
    # quarter closes
    qcloses = [bars[bs + q*15 + 14]['close'] for q in range(6)]
    up = sum(1 for i, c in enumerate(qcloses) if c > qcloses[i-1] if i > 0)
    dn = sum(1 for i, c in enumerate(qcloses) if c < qcloses[i-1] if i > 0)
    print(f"\n{label} trend: q1o={q1o} q6c={q6c} q6c>q1o={q6c > q1o}")
    print(f"  quarter closes: {[round(c,2) for c in qcloses]}, up={up} dn={dn}")
    # running quarterly high/low at Q6
    qhighs = [max(bars[bs+q*15:bs+q*15+15][k]['high'] for k in range(15)) for q in range(6)]
    qlows = [min(bars[bs+q*15:bs+q*15+15][k]['low'] for k in range(15)) for q in range(6)]
    print(f"  qhighs: {[round(x,2) for x in qhighs]}")
    print(f"  qlows:  {[round(x,2) for x in qlows]}")
    print(f"  Q6 high > Q1 high: {qhighs[5] > qhighs[0]}, Q6 low < Q1 low: {qlows[5] < qlows[0]}")
