#!/usr/bin/env python3
"""02c deep dive: cycle state transitions for the mystery windows."""
import json, datetime
from pathlib import Path
from collections import defaultdict

base = Path('/Users/hermes/projects/candle-profiler-simulators/reference/assemble')
sc = json.loads((base / '02c.json').read_text())['scenario']
data = sc['dataset']['data']
ET = datetime.timezone(datetime.timedelta(hours=-4))

def et(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).astimezone(ET)

# hour OHLC
hours = defaultdict(list)
for i, b in enumerate(data):
    hours[et(b['time']).hour].append((i, b))

def hour_ohlc(h):
    seg = hours[h]
    o = seg[0][1]['open']; c = seg[-1][1]['close']
    hi = max(b['high'] for _, b in seg); lo = min(b['low'] for _, b in seg)
    return o, hi, lo, c

def fmt(h, label):
    o, hi, lo, c = hour_ohlc(h)
    print(f"  {label} h{h}: o={o} hi={hi} lo={lo} c={c}")

print("Window A: apex at 19:44, then 20/21, sig at 22:15")
for h in (18, 19, 20, 21, 22):
    fmt(h, '')
o19, hi19, lo19, c19 = hour_ohlc(19)
o20, hi20, lo20, c20 = hour_ohlc(20)
o21, hi21, lo21, c21 = hour_ohlc(21)
print(f"  H2=20 took H1=19 high? {hi20 > hi19} | low? {lo20 < lo19}")
print(f"  H3=21 took H2=20 high? {hi21 > hi20} | low? {lo21 < lo20}")
print(f"  H3=21 inside H2=20? {lo20 <= lo21 and hi21 <= hi20}")
print(f"  H3=21 inside H1=19? {lo19 <= lo21 and hi21 <= hi19}")

print("\nWindow B: completion at 11:05, then 12/13, sig at 14:15")
for h in (9, 10, 11, 12, 13, 14):
    fmt(h, '')
o11, hi11, lo11, c11 = hour_ohlc(11)
o12, hi12, lo12, c12 = hour_ohlc(12)
o13, hi13, lo13, c13 = hour_ohlc(13)
print(f"  H2=12 took H1=11 high? {hi12 > hi11} | low? {lo12 < lo11}")
print(f"  H3=13 took H2=12 high? {hi13 > hi12} | low? {lo13 < lo12}")
print(f"  H3=13 inside H2=12? {lo12 <= lo13 and hi13 <= hi12}")
print(f"  H3=13 inside H1=11? {lo11 <= lo13 and hi13 <= hi11}")

print("\nWindow C: completion at 06:26, then 7/8, RTH reset at 09:00 (no sig at 09:15)")
for h in (4, 5, 6, 7, 8, 9):
    fmt(h, '')
o6, hi6, lo6, c6 = hour_ohlc(6)
o7, hi7, lo7, c7 = hour_ohlc(7)
o8, hi8, lo8, c8 = hour_ohlc(8)
print(f"  H2=7 took H1=6 high? {hi7 > hi6} | low? {lo7 < lo6}")
print(f"  H3=8 took H2=7 high? {hi8 > hi7} | low? {lo8 < lo7}")
print(f"  H3=8 inside H2=7? {lo7 <= lo8 and hi8 <= hi7}")

print("\nWindow D: expiry 00:59 -> sig at 01:15; expiry 03:59 -> sig at 04:15")
o22, hi22, lo22, c22 = hour_ohlc(22)
o23, hi23, lo23, c23 = hour_ohlc(23)
for h in (22, 23, 0, 1):
    fmt(h, '')
o0, hi0, lo0, c0 = hour_ohlc(0)
o1, hi1, lo1, c1 = hour_ohlc(1)
print(f"  H3=0 inside H2=23? {lo23 <= lo0 and hi0 <= hi23}")

# hour 9 first-15: low/high minute
seg9 = hours[9][:15]
print("\nHour 9 first-15 bars (idx,min,o,h,l,c):")
for i, b in seg9:
    t = et(b['time'])
    print(f"  {i} m{t.minute}: o={b['open']} h={b['high']} l={b['low']} c={b['close']}")
