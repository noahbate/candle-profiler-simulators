#!/usr/bin/env python3
"""Dump gen 02a prompts around the mismatch timestamps."""
import json, datetime, sys
from pathlib import Path

gen = json.loads(Path('/Users/hermes/projects/candle-profiler-simulators/web/scenarios/gen_02a_2024-02-06.json').read_text())['scenario']
data = gen['dataset']['data']
ET = datetime.timezone(datetime.timedelta(hours=-5))  # Feb EST

def et(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).astimezone(ET)

# print prompts 10:40-13:10 and 13:50-15:10
for p in gen['prompts']:
    t = et(data[p['triggerCandle']]['time'])
    if t.hour == 11 and 0 <= t.minute <= 5:
        print(f"{t.strftime('%H:%M')} {p['questionText'][:70]} | {p['correctAnswer'][:50]}")
print('---')
for p in gen['prompts']:
    t = et(data[p['triggerCandle']]['time'])
    if (t.hour == 13 and t.minute in (0, 1, 2)) or (t.hour == 12 and t.minute in (59,)):
        print(f"{t.strftime('%H:%M')} {p['questionText'][:70]} | {p['correctAnswer'][:50]}")
print('---')
for p in gen['prompts']:
    t = et(data[p['triggerCandle']]['time'])
    if t.hour == 15 and 0 <= t.minute <= 2:
        print(f"{t.strftime('%H:%M')} {p['questionText'][:70]} | {p['correctAnswer'][:50]}")
print('---')
for p in gen['prompts']:
    t = et(data[p['triggerCandle']]['time'])
    if t.hour == 14 and 48 <= t.minute <= 55:
        print(f"{t.strftime('%H:%M')} {p['questionText'][:70]} | {p['correctAnswer'][:50]}")
print('--- bp below text check ---')
for p in gen['prompts']:
    if 'RTH 0.10% threshold' in p['questionText'] and 'below' in p['questionText']:
        print(repr(p['correctAnswer']))
