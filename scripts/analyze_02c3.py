#!/usr/bin/env python3
"""02c: inspect hours 6,7,8 takeout bars."""
import json, datetime
from pathlib import Path

base = Path('/Users/hermes/projects/candle-profiler-simulators/reference/assemble')
sc = json.loads((base / '02c.json').read_text())['scenario']
data = sc['dataset']['data']
ET = datetime.timezone(datetime.timedelta(hours=-4))

def et(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).astimezone(ET)

# hour 6: from 06:26 (idx 746) to 06:59; hour 7 full; hour 8 full
print("Hour 6 bars from idx 746 (06:26):")
for i in range(746, 780):
    b = data[i]
    t = et(b['time'])
    print(f"  {i} {t.strftime('%H:%M')} o={b['open']} h={b['high']} l={b['low']} c={b['close']}")

h6_high_after = max(b['high'] for b in data[746:780])
print("\nh6 high from 06:26->06:59:", h6_high_after)

print("\nHour 7 bars where high > 18782.5 or low < 18755:")
for i in range(780, 840):
    b = data[i]
    t = et(b['time'])
    if b['high'] > 18782.5 or b['low'] < 18755:
        print(f"  {i} {t.strftime('%H:%M')} o={b['open']} h={b['high']} l={b['low']} c={b['close']}  <-- takeout")
print("hour 7 full: o=18775.25 hi=18811.5 lo=18774.75 c=18792.5")
print("hour 6 full: hi=18782.5 lo=18755")

# Also verify hour 5's flip takeout: H1=4 low=18786, first bar in hour 5 with low < 18786
print("\nHour 5 first bars with low < 18786:")
for i in range(720, 780):
    b = data[i]
    t = et(b['time'])
    if b['low'] < 18786:
        print(f"  {i} {t.strftime('%H:%M')} o={b['open']} h={b['high']} l={b['low']} c={b['close']}")

# hour 23 flip: H1=22 low=18808.75, first bar in hour 23 with low < 18808.75
print("\nHour 23 first bars with low < 18808.75:")
for i in range(300, 360):
    b = data[i]
    t = et(b['time'])
    if b['low'] < 18808.75:
        print(f"  {i} {t.strftime('%H:%M')} o={b['open']} h={b['high']} l={b['low']} c={b['close']}")

# hour 2: H1=1 high 18820.5 — did hour 2 take it?
print("\nHour 2 bars with high > 18820.5 or low < 18809.25 (H1=1 range):")
for i in range(60, 120):
    b = data[i]
    t = et(b['time'])
    if b['high'] > 18820.5 or b['low'] < 18809.25:
        print(f"  {i} {t.strftime('%H:%M')} o={b['open']} h={b['high']} l={b['low']} c={b['close']}")
