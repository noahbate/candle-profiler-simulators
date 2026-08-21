#!/usr/bin/env python3
"""Generate schema-identical simulator scenarios from candle-profiler working data.

Supports: 01a (Box Breakout) fully; other concepts scaffolded with template prompts.

Usage:
  python generate_scenario.py --concept 01a --date 2025-01-21
  python generate_scenario.py --concept 01a --random
"""
import argparse, json, random, sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DATA = Path('/Users/hermes/projects/candle-profiler/data/working/NQ_work_1min.csv')
OUT = Path(__file__).resolve().parent.parent / 'web' / 'scenarios'

# --- question templates per concept (extracted from site captures) ---
T_01A_BREACH = [
    ('Price breached the ETH 0.05% threshold {side} the 0-5 box. What does this tell you?',
     {'above': 'Momentum is strong — expect continuation higher',
      'below': 'Momentum is strong — expect continuation lower'}),
    ('Price breached the 0.05% threshold {side} the 0-5 box with authority. What is the read?',
     {'above': 'Continued strength — the hour favors longs',
      'below': 'Continued weakness — the hour favors shorts'}),
]
T_01A_FALSE = [
    ('Price failed to continue past 0.05% {side} the 0-5 box and confirmed the suckback in Q2 or later. What do you expect?',
     {'above': 'False 0-5 box — the high is set for the hour',
      'below': 'False 0-5 box — the low is set for the hour'}),
]

def load_day(date_str):
    """Return 1-min NQ bars for one trading day (18:00 prev day -> 17:00 day of).
    CSV timestamps are US/Eastern naive: YYYY-MM-DD HH:MM (or MM/DD/YYYY HH:MM)."""
    df = pd.read_csv(DATA)
    tcol = 'timestamp' if 'timestamp' in df.columns else 'time'
    ts = df[tcol]
    # handle both ISO and MM/DD/YYYY formats
    df['ts'] = pd.to_datetime(ts, format='mixed')
    # assume already US/Eastern clock time
    df['ts'] = df['ts'].dt.tz_localize('US/Eastern')
    d = pd.Timestamp(date_str).date()
    from datetime import timedelta
    prev = d - timedelta(days=1)
    s = pd.Timestamp(datetime(prev.year, prev.month, prev.day, 18, 0), tz='US/Eastern')
    e = pd.Timestamp(datetime(d.year, d.month, d.day, 17, 0), tz='US/Eastern')
    m = df[(df['ts'] >= s) & (df['ts'] < e)]
    rows = [{
        'time': int(r.ts.tz_convert('UTC').timestamp()),
        'open': float(r.open), 'high': float(r.high),
        'low': float(r.low), 'close': float(r.close),
    } for r in m.itertuples()]
    return rows

def gen_01a(bars, date_str):
    """Box Breakout detector: hourly 0-5 box (first 5 min of each hour),
    0.05% threshold, breach -> momentum_breakout; breach then suckback -> false_05_box."""
    BPS = 0.0005
    prompts, markers, pid = [], [], 0
    def mkid():
        nonlocal pid
        pid += 1
        return f'gen-{date_str}-{pid:03d}'
    i = 0
    while i + 60 < len(bars):
        # bar i starts an hour if its minute == 0
        t = datetime.fromtimestamp(bars[i]['time'], tz=timezone.utc)
        if t.minute != 0:
            i += 1
            continue
        box_bars = bars[i:i+5]
        if len(box_bars) < 5:
            break
        bh = max(b['high'] for b in box_bars)
        bl = min(b['low'] for b in box_bars)
        bm = (bh + bl) / 2
        thr_up = bh * (1 + BPS)
        thr_dn = bl * (1 - BPS)
        hour_end = min(i + 60, len(bars))
        # scan the hour — at most one event per side per hour
        fired = set()
        for j in range(i + 5, hour_end):
            b = bars[j]
            for side, thr in (('above', thr_up), ('below', thr_dn)):
                if side in fired:
                    continue
                broke = b['high'] > thr if side == 'above' else b['low'] < thr
                if broke:
                    fired.add(side)
                    # suckback = a later close back inside [bl, bh]
                    suck = None
                    for k in range(j + 1, hour_end):
                        c = bars[k]['close']
                        if bl <= c <= bh:
                            suck = k
                            break
                    q, ans_map = (T_01A_FALSE[0] if suck else T_01A_BREACH[0])
                    md_event = 'false_05_box' if suck else 'momentum_breakout'
                    md = {'event': md_event, 'box_high': bh, 'box_mid': bm, 'box_low': bl,
                          'bps_threshold': BPS, 'breakout_side': side,
                          'threshold_price': thr, 'threshold_session': 'ETH'}
                    if suck:
                        md.update({'suckback_bar': suck, 'suckback_close': bars[suck]['close']})
                    else:
                        md.update({'breach_bar': j, 'breach_price': b['high'] if side == 'above' else b['low']})
                    markers.append({'concept': '01a', 'triggerBarIdx': j,
                                    'triggerTime': bars[j]['time'],
                                    'nyHour': datetime.fromtimestamp(bars[j]['time'], tz=timezone.utc).hour,
                                    'question': q.format(side=side), 'metadata': md})
                    correct = ans_map[side]
                    decoys = ['Temporary pullback — expect another attempt',
                              'Range-bound hour — no directional read'] \
                        if suck else ['False breakout — expect suckback into the box',
                                      'Neutral — wait for the next hour']
                    opts = [correct] + decoys
                    random.shuffle(opts)
                    prompts.append({'id': mkid(), 'triggerCandle': j, 'type': 'multiple_choice',
                                    'questionText': q.format(side=side), 'correctAnswer': correct,
                                    'explanation': '', 'points': 10, 'answerOptions': opts,
                                    'conceptTag': '01a'})
                    break  # one event per hour-direction
        i += 60
    return prompts, markers

def build_scenario(concept, date_str, bars, prompts, markers):
    return {'scenario': {
        'id': f'gen-{concept}-{date_str}',
        'name': f'{date_str} — {concept}',
        'description': f'Runtime-generated from {len(prompts)} data points',
        'datasetId': f'gen-{concept}-{date_str}',
        'dataset': {'id': f'gen-{concept}-{date_str}', 'name': date_str, 'ticker': 'NQ',
                    'timeframe': 'M1', 'data': bars, 'candleCount': len(bars),
                    'startDate': '', 'endDate': '', 'indicators': [], 'hourlyTPData': {},
                    'createdBy': 'generator', 'createdAt': datetime.now(timezone.utc).isoformat(),
                    'updatedAt': datetime.now(timezone.utc).isoformat()},
        'annotations': [], 'prompts': prompts, 'entries': [],
        'mode': 'IDENTIFY', 'passingScore': 70, 'contentStatus': 'PUBLISHED',
        'createdBy': 'generator', 'createdAt': datetime.now(timezone.utc).isoformat(),
        'updatedAt': datetime.now(timezone.utc).isoformat(),
        'dataPointMarkers': markers}}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--concept', required=True)
    ap.add_argument('--date')
    ap.add_argument('--random', action='store_true')
    a = ap.parse_args()
    if a.random:
        import pandas as pd
        df = pd.read_csv('/Users/hermes/projects/candle-profiler/data/working/NQ_work_1min.csv',
                         usecols=[0])
        col = df.columns[0]
        days = sorted({pd.to_datetime(t, format='mixed').date().isoformat() for t in df[col].sample(3000)})
        a.date = random.choice(days[-400:])  # recent-ish
    if not a.date:
        ap.error('need --date or --random')
    bars = load_day(a.date)
    if len(bars) < 300:
        sys.exit(f'too few bars for {a.date} ({len(bars)})')
    if a.concept == '01a':
        prompts, markers = gen_01a(bars, a.date)
    else:
        sys.exit(f'concept {a.concept} not implemented yet (01a only in v1)')
    sc = build_scenario(a.concept, a.date, bars, prompts, markers)
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f'gen_{a.concept}_{a.date}.json'
    out.write_text(json.dumps(sc))
    print(f'{out}: {len(bars)} bars, {len(prompts)} prompts, {sum(p["points"] for p in prompts)} max pts')

if __name__ == '__main__':
    main()
