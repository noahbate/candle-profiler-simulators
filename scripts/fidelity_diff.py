#!/usr/bin/env python3
"""Fidelity diff: generated scenario vs captured payload, timestamp-based.

Usage: python fidelity_diff.py <concept> [--gen web/scenarios/gen_<c>_<d>.json]
Maps capture triggerCandle -> bar time -> gen bar index (handles 6h/1d offsets).
Reports: shared bars, exact bar+answer matches, unmatched events both ways.
"""
import json, sys, argparse
from pathlib import Path
from collections import Counter

BASE = Path('/Users/hermes/projects/candle-profiler-simulators/reference/assemble')
WEB = Path('/Users/hermes/projects/candle-profiler-simulators/web/scenarios')

def bar_time_index(data):
    return {b['time']: i for i, b in enumerate(data)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('concept')
    ap.add_argument('--gen', default=None, help='path to generated scenario json')
    ap.add_argument('--cap', default=None, help='path to capture json (default reference/assemble/<c>.json)')
    a = ap.parse_args()

    cap = json.loads((a.cap and Path(a.cap) or (BASE / f'{a.concept}.json')).read_text())['scenario']
    cap_data = cap['dataset']['data']
    cap_prompts = cap['prompts']
    cap_t2i = bar_time_index(cap_data)

    if a.gen is None:
        cands = sorted(WEB.glob(f'gen_{a.concept}_*.json'))
        if not cands:
            sys.exit('no gen file and --gen not given')
        a.gen = cands[0]
    gen = json.loads(Path(a.gen).read_text())['scenario']
    gen_data = gen['dataset']['data']
    gen_prompts = gen['prompts']
    gen_t2i = bar_time_index(gen_data)

    print(f"capture: {len(cap_prompts)} prompts, first bar {cap_data[0]['time']} last {cap_data[-1]['time']}")
    print(f"gen:     {len(gen_prompts)} prompts, first bar {gen_data[0]['time']} last {gen_data[-1]['time']}")

    # map capture events to gen bars
    cap_events = []  # (gen_bar_idx, cap_question, cap_answer, cap_sig)
    unmatched_cap = []
    for p in cap_prompts:
        t = cap_data[p['triggerCandle']]['time']
        gi = gen_t2i.get(t)
        if gi is None:
            unmatched_cap.append((t, p['questionText'][:60], p['correctAnswer'][:40]))
        else:
            cap_events.append((gi, t, p['questionText'], p['correctAnswer']))

    # gen events by bar
    gen_by_bar = {}
    for p in gen_prompts:
        tb = p['triggerCandle']
        gen_by_bar.setdefault(tb, []).append((p['questionText'], p['correctAnswer']))

    # match: capture event matches if ANY gen prompt at that bar carries the correct answer
    matched = 0
    match_detail = []
    for gi, t, q, ans in cap_events:
        gs = gen_by_bar.get(gi, [])
        hit = any(gq == q and ga == ans for gq, ga in gs)
        if hit:
            matched += 1
        match_detail.append((hit, t, q[:55], ans[:45], [ga[:40] for _, ga in gs]))
    total_cap = len(cap_prompts)
    print(f"\n=== FIDELITY: {matched}/{total_cap} capture events matched (exact bar + exact answer text) ===")
    print(f"    {len(unmatched_cap)} capture events had NO bar in gen data (timestamp mismatch)")

    if not str(a.gen).endswith('capture'):
        # gen prompts not explained by capture (superset)
        cap_exact = set()
        for gi, t, q, ans in cap_events:
            gs = gen_by_bar.get(gi, [])
            for gq, ga in gs:
                if gq == q and ga == ans:
                    cap_exact.add((gi, gq, ga))
        gen_total = len(gen_prompts)
        gen_explained = len(cap_exact)
        print(f"    gen has {gen_total} prompts; {gen_explained} explained by capture events")

    print("\n--- unmatched capture events (bar present but answer/question differs) ---")
    for hit, t, q, ans, gans in match_detail:
        if not hit:
            print(f"  t={t} Q={q} A={ans} | gen answers: {gans}")
    for t, q, ans in unmatched_cap:
        print(f"  (no gen bar) t={t} Q={q} A={ans}")

    # signature-level: map via capture marker signal_type when available
    md_by_idx = {}
    for m in cap.get('dataPointMarkers', []):
        md_by_idx[m['triggerBarIdx']] = m.get('metadata', {})
    sig_matched = Counter()
    sig_total = Counter()
    for p in cap_prompts:
        md = md_by_idx.get(p['triggerCandle'], {})
        sig = md.get('signal_type', '?')
        sig_total[sig] += 1
        t = cap_data[p['triggerCandle']]['time']
        gi = gen_t2i.get(t)
        if gi is None:
            continue
        gs = gen_by_bar.get(gi, [])
        if any(gq == p['questionText'] and ga == p['correctAnswer'] for gq, ga in gs):
            sig_matched[sig] += 1
    if sig_matched:
        print("\n--- per-signal-type match ---")
        for sig in sorted(sig_total):
            print(f"  {sig:30s} {sig_matched[sig]}/{sig_total[sig]}")

if __name__ == '__main__':
    main()
