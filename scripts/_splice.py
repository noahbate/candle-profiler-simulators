#!/usr/bin/env python3
"""Remove the current gen_02a body (from 'def gen_02a(' up to 'def gen_01f('), leaving a marker."""
from pathlib import Path
p = Path('/Users/hermes/projects/candle-profiler-simulators/scripts/generate_scenario.py')
lines = p.read_text().split('\n')
start = next(i for i, l in enumerate(lines) if l.startswith('def gen_02a('))
end = next(i for i, l in enumerate(lines) if l.startswith('def gen_01f('))
print('removing lines', start + 1, '..', end, f'({end - start} lines)')
new = lines[:start] + lines[end:]
p.write_text('\n'.join(new))
print('done, total lines:', len(new))
