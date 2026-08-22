#!/usr/bin/env python3
"""Dump full prompt detail for 02a/02c/02d to text files for reverse-engineering."""
import json, datetime
from pathlib import Path

base = Path('/Users/hermes/projects/candle-profiler-simulators/reference/assemble')
outdir = Path('/Users/hermes/projects/candle-profiler-simulators/scripts/capture_dumps')
outdir.mkdir(parents=True, exist_ok=True)

def utc(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc)

for c in ['02a', '02c', '02d']:
    sc = json.loads((base / f'{c}.json').read_text())['scenario']
    data = sc['dataset']['data']
    prompts = sc['prompts']
    markers = {m['triggerBarIdx']: m for m in sc.get('dataPointMarkers', [])}
    lines = []
    lines.append(f'# {c} — {sc.get("name")} | {len(prompts)} prompts | first bar {utc(data[0]["time"])} | last bar {utc(data[-1]["time"])}')
    for i, p in enumerate(prompts):
        tb = p['triggerCandle']
        t = utc(data[tb]['time'])
        bar = data[tb]
        lines.append('')
        lines.append(f'--- prompt {i} | id={p["id"][:8]} | trigger idx={tb} | time={t.isoformat()} (UTC {t.hour:02d}:{t.minute:02d}) | nyHour={t.hour-4}')
        lines.append(f'    bar: o={bar["open"]} h={bar["high"]} l={bar["low"]} c={bar["close"]}')
        lines.append(f'    Q: {p["questionText"]}')
        lines.append(f'    options: {json.dumps(p["answerOptions"])}')
        lines.append(f'    correct: {p["correctAnswer"]!r}')
        m = markers.get(tb)
        if m:
            lines.append(f'    marker: {json.dumps(m.get("metadata", {}), indent=2)}')
    (outdir / f'{c}_prompts.txt').write_text('\n'.join(lines))
    print(c, 'dumped', len(prompts), 'prompts ->', outdir / f'{c}_prompts.txt')
