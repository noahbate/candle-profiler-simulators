#!/usr/bin/env python3
"""Splice _gen02a.py (the gen_02a function) into generate_scenario.py before 'def gen_01f'."""
from pathlib import Path

base = Path('/Users/hermes/projects/candle-profiler-simulators/scripts')
main = (base / 'generate_scenario.py').read_text()
frag = (base / '_gen02a.py').read_text()

marker = 'def gen_01f(bars, date_str):'
idx = main.index(marker)
new = main[:idx] + frag.rstrip() + '\n\n\n' + main[idx:]
(base / 'generate_scenario.py').write_text(new)
print('spliced; total lines:', len(new.split('\n')))
