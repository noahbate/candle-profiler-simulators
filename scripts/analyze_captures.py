#!/usr/bin/env python3
"""Summarize 02a/02c/02d captures: names, dates, prompts, question texts, answers."""
import json, datetime, sys
from collections import Counter
from pathlib import Path

base = Path('/Users/hermes/projects/candle-profiler-simulators/reference/assemble')

def load(c):
    return json.loads((base / f'{c}.json').read_text())

def utc(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc)

for c in ['02a', '02c', '02d']:
    sc = load(c)['scenario']
    ds = sc['dataset']
    data = ds['data']
    prompts = sc['prompts']
    markers = sc.get('dataPointMarkers', [])
    print('='*90)
    print(c, '| name:', sc.get('name'), '| id:', sc.get('id'), '| desc:', sc.get('description'))
    print('  mode:', sc.get('mode'), '| passingScore:', sc.get('passingScore'), '| contentStatus:', sc.get('contentStatus'))
    print('  dataset name:', ds.get('name'), '| ticker:', ds.get('ticker'), '| timeframe:', ds.get('timeframe'), '| candles:', ds.get('candleCount'), len(data))
    print('  first bar:', utc(data[0]['time']).isoformat(), '| last bar:', utc(data[-1]['time']).isoformat())
    print('  prompts:', len(prompts), '| markers:', len(markers))
    print('  conceptTags:', dict(Counter(p.get('conceptTag') for p in prompts)))
    print('  points dist:', dict(Counter(p.get('points') for p in prompts)))
    # id pattern
    ids = [p.get('id') for p in prompts]
    print('  sample ids:', ids[:3], '... unique:', len(set(ids)))
    # explanation presence
    exp = sum(1 for p in prompts if p.get('explanation'))
    print('  prompts with explanation:', exp)
    # marker metadata keys
    if markers:
        m0 = markers[0]
        print('  marker keys:', sorted(m0.keys()))
        print('  marker metadata keys:', sorted(m0.get('metadata', {}).keys()) if isinstance(m0.get('metadata'), dict) else type(m0.get('metadata')))
    # trigger hour distribution
    hours = Counter(utc(data[p['triggerCandle']]['time']).hour for p in prompts)
    print('  trigger hour UTC dist:', dict(sorted(hours.items())))
