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
_DF = None  # cached parsed frame for load_day

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

# --- 01c BP Breach: box 00-05, breakout point. Two levels: 0.05% and 0.10%.
# 6 templates extracted verbatim from capture. side in {above, below}.
T_01C = {
    'reject_above': ('BP 0.05% breached above but failed to reach 0.10% — rejection?',
                     '0.05% rejection above — failed continuation'),
    'reject_below': ('BP 0.05% breached below but failed to reach 0.10% — rejection?',
                     '0.05% rejection below — failed continuation'),
    'breach_above': ('BP 0.05% breached above — anticipate continuation to 0.10%',
                     '0.05% breach above — anticipate continuation'),
    'breach_below': ('BP 0.05% breached below — anticipate continuation to 0.10%',
                     '0.05% breach below — anticipate continuation'),
    'mom_above':    ('BP 0.10% breached above — strong bullish momentum confirmed',
                     '0.10% breach above — momentum confirmed, low is set'),
    'mom_below':    ('BP 0.10% breached below — strong bearish momentum confirmed',
                     '0.10% breach below — momentum confirmed, high is set'),
}

# --- 01f Prev Hour: prev hour 50% reclaim (mid_touch) and footprint_test (wick zone reject).
T_01F_MID = ('In Q2 or later, price closed above prev hour 50% ({mid}). What does that confirm?',
             {'bull': 'Confirmed prev hour midpoint reclaim — bullish lean',
              'bear': 'Confirmed prev hour midpoint loss — bearish lean'})
T_01F_FP_BULL = ('Price testing prev hour lower wick zone ({wlow}-{whigh}). Then Q2-or-later broke prev hour 50% ({mid}). What is confirmed?',
            'Confirmed footprint rejection — bullish')
T_01F_FP_BEAR = ('Price testing prev hour upper wick zone ({wlow}-{whigh}). Then Q2-or-later broke prev hour 50% ({mid}). What is confirmed?',
            'Confirmed footprint rejection — bearish')

# --- 01g Sweep+SB: sweep prev hour low/high, suck back, break prev mid in Q2+.
T_01G = {
    'low':  ('Swept prev hour low ({pl}), sucked back into range, now broke prev hour mid ({pm}) in Q2 or later. Bullish — sweep confirmed as manipulation.',
             'Bullish — price wants higher probabilities'),
    'high': ('Swept prev hour high ({ph}), sucked back into range, now broke prev hour mid ({pm}) in Q2 or later. Bearish — sweep confirmed as manipulation.',
             'Bearish — price wants lower probabilities'),
}

def load_day(date_str):
    """Return 1-min NQ bars for one trading session: 18:00 ET on `date` -> 17:00 ET next day.
    `date_str` is the calendar date of the START evening (e.g. '2025-06-11' = session beginning
    2025-06-11 18:00 ET). This matches the capture-file labeling convention.
    Parsed frame is cached to disk as parquet so the 267MB mixed-format parse runs once."""
    global _DF
    if _DF is None:
        cache = DATA.with_suffix('.parquet')
        if cache.exists():
            _DF = pd.read_parquet(cache)
        else:
            df = pd.read_csv(DATA)
            tcol = 'timestamp' if 'timestamp' in df.columns else 'time'
            ts = df[tcol]
            df['ts'] = pd.to_datetime(ts, format='mixed').dt.tz_localize('US/Eastern')
            df = df[['ts', 'open', 'high', 'low', 'close']]
            df.to_parquet(cache, index=False)
            _DF = df
    df = _DF
    d = pd.Timestamp(date_str).date()
    s = pd.Timestamp(datetime(d.year, d.month, d.day, 18, 0), tz='US/Eastern')
    e = pd.Timestamp(datetime(d.year, d.month, d.day, 17, 0), tz='US/Eastern') + pd.Timedelta(days=1)
    m = df[(df['ts'] >= s) & (df['ts'] < e)]
    rows = [{
        'time': int(r.ts.value // 10**9),
        'open': float(r.open), 'high': float(r.high),
        'low': float(r.low), 'close': float(r.close),
    } for r in m.itertuples()]
    return rows

def gen_01a(bars, date_str):
    """Box Breakout (01a) — curriculum-confirmed logic (vault: Pack BootCamp 05 Box Hourly Quarters).

    Box = first 5 min of each hour (00-05). Breakout threshold = box edge x (1 +/- 0.05%) (ETH).
    - momentum_breakout: price prints (wick) beyond the 0.05% threshold and NEVER sucks back to
      the 50% level (box mid) -> fire at the first breach bar.
    - false_05_box: price swipes the raw box but FAILS to reach the 0.05% threshold, then sucks
      back and finds footing at the 50% level (box mid) -> fire at the first close beyond mid
      AFTER the box swipe (the 'confirmation' / finding-footing bar). This is the time component:
      price swipes, fills, swipes, fills, then commits at the open/mid.
    """
    BPS = 0.0005
    prompts, markers, pid = [], [], 0
    def mkid():
        nonlocal pid
        pid += 1
        return f'gen-{date_str}-{pid:03d}'
    i = 0
    while i + 60 < len(bars):
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
        fired = set()
        for side in ('above', 'below'):
            if side in fired:
                continue
            thr = thr_up if side == 'above' else thr_dn
            # find first wick beyond raw box (the 'swipe')
            swipe = None
            for j in range(i + 5, hour_end):
                if side == 'above' and bars[j]['high'] > bh:
                    swipe = j; break
                if side == 'below' and bars[j]['low'] < bl:
                    swipe = j; break
            if swipe is None:
                continue
            # resolve: does it reach the 0.05% threshold (momentum) or suck back to mid (false)?
            res = None
            HOLD = 2  # footing must commit: close beyond 50% level for HOLD consecutive bars
            for k in range(swipe, hour_end):
                c = bars[k]['close']
                hit_thr = (bars[k]['high'] > thr) if side == 'above' else (bars[k]['low'] < thr)
                if hit_thr:
                    res = ('momentum_breakout', k)  # hold; fire at breach bar
                    break
                # suckback confirmed: close beyond the 50% level (box mid) and it holds
                beyond_mid = (c > bm) if side == 'below' else (c < bm)
                if beyond_mid:
                    cnt = 0
                    for j in range(k, min(k + HOLD, hour_end)):
                        cc = bars[j]['close']
                        if (cc > bm) if side == 'below' else (cc < bm):
                            cnt += 1
                        else:
                            break
                    if cnt >= HOLD:
                        res = ('false_05_box', k)  # fire at the finding-footing bar
                        break
            if res is None:
                # never resolved within hour -> treat as momentum (held)
                res = ('momentum_breakout', swipe)
            md_event, trigger = res
            fired.add(side)
            if md_event == 'momentum_breakout':
                md = {'event': md_event, 'box_high': bh, 'box_mid': bm, 'box_low': bl,
                      'bps_threshold': BPS, 'breakout_side': side,
                      'breach_bar': trigger - i, 'breach_price': bars[trigger]['high'] if side == 'above' else bars[trigger]['low'],
                      'threshold_price': thr, 'threshold_session': 'ETH'}
                q, ans_map = T_01A_BREACH[0]
                decoys = ['False breakout — expect suckback into the box', 'Neutral — wait for the next hour']
            else:
                md = {'event': md_event, 'box_high': bh, 'box_mid': bm, 'box_low': bl,
                      'bps_threshold': BPS, 'breakout_side': side,
                      'suckback_bar': trigger - i, 'suckback_close': bars[trigger]['close'],
                      'threshold_price': thr, 'threshold_session': 'ETH'}
                q, ans_map = T_01A_FALSE[0]
                decoys = ['Temporary pullback — expect another attempt', 'Range-bound hour — no directional read']
            markers.append({'concept': '01a', 'triggerBarIdx': trigger,
                            'triggerTime': bars[trigger]['time'],
                            'nyHour': datetime.fromtimestamp(bars[trigger]['time'], tz=timezone.utc).hour,
                            'question': q.format(side=side), 'metadata': md})
            correct = ans_map[side]
            opts = [correct] + decoys
            random.shuffle(opts)
            prompts.append({'id': mkid(), 'triggerCandle': trigger, 'type': 'multiple_choice',
                            'questionText': q.format(side=side), 'correctAnswer': correct,
                            'explanation': '', 'points': 10, 'answerOptions': opts,
                            'conceptTag': '01a'})
        i += 60
    return prompts, markers

def gen_01c(bars, date_str):
    """BP Breach (01c): hourly 0-5 box; breakout point (BP) beyond box x (1 +/- 0.05%).
    If price also reaches the 0.10% level -> continuation/momentum confirmed; otherwise the
    0.05% breach is a 'rejection' (failed continuation). Two sides, per hour."""
    BPS = 0.0005
    BPS10 = 0.0010
    prompts, markers, pid = [], [], 0
    def mkid():
        nonlocal pid; pid += 1; return f'gen-{date_str}-{pid:03d}'
    i = 0
    while i + 60 < len(bars):
        t = datetime.fromtimestamp(bars[i]['time'], tz=timezone.utc)
        if t.minute != 0:
            i += 1; continue
        box = bars[i:i+5]
        if len(box) < 5: break
        bh = max(b['high'] for b in box); bl = min(b['low'] for b in box)
        thr05_up = bh * (1 + BPS); thr05_dn = bl * (1 - BPS)
        thr10_up = bh * (1 + BPS10); thr10_dn = bl * (1 - BPS10)
        hour_end = min(i + 60, len(bars))
        for side in ('above', 'below'):
            thr05 = thr05_up if side == 'above' else thr05_dn
            thr10 = thr10_up if side == 'above' else thr10_dn
            breach05 = None; breach10 = None
            for j in range(i + 5, hour_end):
                if breach05 is None:
                    hit = (bars[j]['high'] > thr05) if side == 'above' else (bars[j]['low'] < thr05)
                    if hit: breach05 = j
                if breach10 is None:
                    hit = (bars[j]['high'] > thr10) if side == 'above' else (bars[j]['low'] < thr10)
                    if hit: breach10 = j
                if breach05 is not None and breach10 is not None:
                    break
            if breach05 is None:
                continue
            reached10 = breach10 is not None
            # Event 1: 0.05% breach (fired at first 0.05% bar)
            if reached10:
                key = 'breach_above' if side == 'above' else 'breach_below'
            else:
                key = 'reject_above' if side == 'above' else 'reject_below'
            q, correct = T_01C[key]
            md = {'side': side, 'box_high': bh, 'box_low': bl, 'threshold': '0.05%',
                  'reached_10': reached10, 'breach_level': thr05,
                  'breach_price': bars[breach05]['high'] if side == 'above' else bars[breach05]['low']}
            markers.append({'concept': '01c', 'triggerBarIdx': breach05,
                            'triggerTime': bars[breach05]['time'],
                            'nyHour': datetime.fromtimestamp(bars[breach05]['time'], tz=timezone.utc).hour,
                            'question': q, 'metadata': md})
            decoy_pool = [T_01C['breach_above'][1], T_01C['breach_below'][1],
                          T_01C['reject_above'][1], T_01C['reject_below'][1],
                          T_01C['mom_above'][1], T_01C['mom_below'][1]]
            decoys = [d for d in decoy_pool if d != correct][:2]
            opts = [correct] + decoys; random.shuffle(opts)
            prompts.append({'id': mkid(), 'triggerCandle': breach05, 'type': 'multiple_choice',
                            'questionText': q, 'correctAnswer': correct, 'explanation': '',
                            'points': 10, 'answerOptions': opts, 'conceptTag': '01c'})
            # Event 2: 0.10% breach (fired at first 0.10% bar) -> momentum confirmed
            if breach10 is not None:
                key2 = 'mom_above' if side == 'above' else 'mom_below'
                q2, correct2 = T_01C[key2]
                md2 = {'side': side, 'box_high': bh, 'box_low': bl, 'threshold': '0.10%',
                       'reached_10': True, 'breach_level': thr10,
                       'breach_price': bars[breach10]['high'] if side == 'above' else bars[breach10]['low']}
                markers.append({'concept': '01c', 'triggerBarIdx': breach10,
                                'triggerTime': bars[breach10]['time'],
                                'nyHour': datetime.fromtimestamp(bars[breach10]['time'], tz=timezone.utc).hour,
                                'question': q2, 'metadata': md2})
                decoys2 = [d for d in decoy_pool if d != correct2][:2]
                opts2 = [correct2] + decoys2; random.shuffle(opts2)
                prompts.append({'id': mkid(), 'triggerCandle': breach10, 'type': 'multiple_choice',
                                'questionText': q2, 'correctAnswer': correct2, 'explanation': '',
                                'points': 10, 'answerOptions': opts2, 'conceptTag': '01c'})
        i += 60
    return prompts, markers

def gen_01f(bars, date_str):
    """Prev Hour (01f): prev hour 50% (mid) reclaim in Q2 or later -> bullish lean.
    Also footprint_test: price tests prev hour lower wick zone, then Q2+ breaks prev mid -> bullish."""
    prompts, markers, pid = [], [], 0
    def mkid():
        nonlocal pid; pid += 1; return f'gen-{date_str}-{pid:03d}'
    i = 60  # need a prior hour
    while i + 60 < len(bars):
        t = datetime.fromtimestamp(bars[i]['time'], tz=timezone.utc)
        if t.minute != 0:
            i += 1; continue
        prev = bars[i-60:i]
        if len(prev) < 60:
            i += 60; continue
        ph_high = max(b['high'] for b in prev); ph_low = min(b['low'] for b in prev)
        ph_mid = (ph_high + ph_low) / 2
        ph_open = prev[0]['open']; ph_close = prev[-1]['close']
        o = bars[i]['open']
        hour_end = min(i + 60, len(bars))
        # footprint_test: genuine sweep BELOW prev hour low (or ABOVE prev high) in Q1 (bars 0-14),
        # then Q2+ reclaim of prev 50% -> rejection. swept_low -> bullish, swept_high -> bearish.
        swept_low = any(bars[k]['low'] < ph_low for k in range(i, i + 15))
        swept_high = any(bars[k]['high'] > ph_high for k in range(i, i + 15))
        # mid_touch: open on one side of prev 50%, first Q2+ (bar i+15+) reclaim across it
        mt = None; mt_side = None
        if o < ph_mid:
            for k in range(i + 15, hour_end):
                if bars[k]['close'] > ph_mid:
                    mt = k; mt_side = 'above'; break
        elif o > ph_mid:
            for k in range(i + 15, hour_end):
                if bars[k]['close'] < ph_mid:
                    mt = k; mt_side = 'below'; break
        if mt is not None:
            # mid_touch event
            q, ans_map = T_01F_MID
            correct = ans_map['bull'] if mt_side == 'above' else ans_map['bear']
            md = {'above_mid': mt_side == 'above', 'bar_close': round(bars[mt]['close'], 2),
                  'sub_concept': 'mid_touch', 'prev_hour_low': round(ph_low, 2),
                  'prev_hour_mid': round(ph_mid, 2), 'prev_hour_high': round(ph_high, 2),
                  'confirmation_bar': mt - i}
            markers.append({'concept': '01f', 'triggerBarIdx': mt,
                            'triggerTime': bars[mt]['time'],
                            'nyHour': datetime.fromtimestamp(bars[mt]['time'], tz=timezone.utc).hour,
                            'question': q.format(mid=f'{ph_mid:.2f}'), 'metadata': md})
            decoys = [ans_map['bear'] if mt_side == 'above' else ans_map['bull']]
            opts = [correct] + decoys; random.shuffle(opts)
            prompts.append({'id': mkid(), 'triggerCandle': mt, 'type': 'multiple_choice',
                            'questionText': q.format(mid=f'{ph_mid:.2f}'), 'correctAnswer': correct,
                            'explanation': '', 'points': 10, 'answerOptions': opts, 'conceptTag': '01f'})
        # footprint_test (fires at the reclaim bar, +1 to separate from mid_touch when both present)
        if swept_low or swept_high:
            fp_side = 'bull' if swept_low else 'bear'
            q2, correct2 = T_01F_FP_BULL if fp_side == 'bull' else T_01F_FP_BEAR
            wick_bottom = round(ph_low, 2); wick_top = round(ph_low + (ph_high - ph_low) * 0.2, 2)
            fp_bar = mt + 1 if (mt is not None and mt + 1 < hour_end) else (mt if mt is not None else None)
            if fp_bar is not None:
                md2 = {'rejected': True, 'wick_top': wick_top, 'bar_close': round(bars[fp_bar]['close'], 2),
                       'sub_concept': 'footprint_test', 'wick_bottom': wick_bottom,
                       'footprint_bar': 0, 'prev_hour_low': round(ph_low, 2),
                       'prev_hour_mid': round(ph_mid, 2), 'prev_hour_high': round(ph_high, 2),
                       'prev_hour_color': 'red' if ph_close < ph_open else 'green',
                       'confirmation_bar': fp_bar - i}
                markers.append({'concept': '01f', 'triggerBarIdx': fp_bar,
                                'triggerTime': bars[fp_bar]['time'],
                                'nyHour': datetime.fromtimestamp(bars[fp_bar]['time'], tz=timezone.utc).hour,
                                'question': q2.format(wlow=f'{wick_bottom:.2f}', whigh=f'{wick_top:.2f}', mid=f'{ph_mid:.2f}'),
                                'metadata': md2})
                decoy2 = 'Accepted wick zone — bearish continuation' if fp_side == 'bull' else 'Accepted wick zone — bullish continuation'
                opts2 = [correct2, decoy2]; random.shuffle(opts2)
                prompts.append({'id': mkid(), 'triggerCandle': fp_bar, 'type': 'multiple_choice',
                                'questionText': q2.format(wlow=f'{wick_bottom:.2f}', whigh=f'{wick_top:.2f}', mid=f'{ph_mid:.2f}'),
                                'correctAnswer': correct2, 'explanation': '', 'points': 10,
                                'answerOptions': opts2, 'conceptTag': '01f'})
        i += 60
    return prompts, markers

def gen_01g(bars, date_str):
    """Sweep+SB (01g): sweep prev hour low/high, suck back into range, then break prev mid in Q2+.
    Swept low -> bullish manipulation; swept high -> bearish manipulation."""
    prompts, markers, pid = [], [], 0
    def mkid():
        nonlocal pid; pid += 1; return f'gen-{date_str}-{pid:03d}'
    i = 60
    while i + 60 < len(bars):
        t = datetime.fromtimestamp(bars[i]['time'], tz=timezone.utc)
        if t.minute != 0:
            i += 1; continue
        prev = bars[i-60:i]
        if len(prev) < 60:
            i += 60; continue
        ph_high = max(b['high'] for b in prev if False or True) if False else max(b['high'] for b in prev)
        ph_low = min(b['low'] for b in prev); ph_mid = (max(b['high'] for b in prev) + ph_low) / 2
        hour_end = min(i + 60, len(bars))
        # detect sweep of prev low or high within this hour's early part, then suckback, then mid break in Q2+
        for sweep_type, edge in (('low', ph_low), ('high', ph_high)):
            swept = None; suck = None
            for k in range(i, hour_end):
                if sweep_type == 'low' and bars[k]['low'] < edge: swept = k
                if sweep_type == 'high' and bars[k]['high'] > edge: swept = k
                if swept is not None and k > swept:
                    # suckback: back inside prev range
                    if ph_low <= bars[k]['close'] <= ph_high:
                        suck = k; break
            if swept is not None and suck is not None:
                # break prev mid in Q2 or later
                break_mid = None
                for k in range(max(suck, i + 15), hour_end):
                    if (sweep_type == 'low' and bars[k]['close'] > ph_mid) or \
                       (sweep_type == 'high' and bars[k]['close'] < ph_mid):
                        break_mid = k; break
                if break_mid is not None:
                    q, correct = T_01G[sweep_type]
                    md = {'prev_low': round(ph_low, 2), 'prev_high': round(ph_high, 2),
                          'prev_mid': round(ph_mid, 2), 'sweep_type': sweep_type,
                          'sweep_price': round(edge, 2), 'trigger_close': round(bars[break_mid]['close'], 2),
                          'sweep_bar_local': swept - i, 'confirmation_bar': break_mid - i,
                          'trigger_bar_local': break_mid - i, 'suckback_bar_local': suck - i}
                    markers.append({'concept': '01g', 'triggerBarIdx': break_mid,
                                    'triggerTime': bars[break_mid]['time'],
                                    'nyHour': datetime.fromtimestamp(bars[break_mid]['time'], tz=timezone.utc).hour,
                                    'question': q.format(pl=f'{ph_low:.2f}', ph=f'{ph_high:.2f}', pm=f'{ph_mid:.2f}'),
                                    'metadata': md})
                    decoy = 'Bearish — sweep was real breakdown' if sweep_type == 'low' else 'Bullish — sweep was real breakout'
                    opts = [correct, decoy]; random.shuffle(opts)
                    prompts.append({'id': mkid(), 'triggerCandle': break_mid, 'type': 'multiple_choice',
                                    'questionText': q.format(pl=f'{ph_low:.2f}', ph=f'{ph_high:.2f}', pm=f'{ph_mid:.2f}'),
                                    'correctAnswer': correct, 'explanation': '', 'points': 10,
                                    'answerOptions': opts, 'conceptTag': '01g'})
                    break  # one sweep event per hour
        i += 60
    return prompts, markers

def _quarter_range(bars, q_start, q_len=15):
    """Return (high, low) of a 15-min quarter starting at bar index q_start."""
    seg = bars[q_start:q_start + q_len]
    if len(seg) < q_len:
        return None, None
    return max(b['high'] for b in seg), min(b['low'] for b in seg)

def gen_01d(bars, date_str):
    """Instat (01d): per hour, the FIRST bar in Q2 that takes out Q1's high OR low is the
    instat signal. Bullish (Q1 set the LOW) if Q2 takes Q1 high; bearish (Q1 set the HIGH)
    if Q2 takes Q1 low. Site fires exactly at that first breakout bar. Skip ambiguous hours
    where Q2 breaks BOTH sides (verified: site emits 14/15 matched hours on the reference
    capture; the remaining 1 is a site-specific filter not yet reproduced)."""
    prompts, markers, pid = [], [], 0
    def mkid():
        nonlocal pid; pid += 1; return f'gen-{date_str}-{pid:03d}'
    Q = 15  # quarter length in bars
    i = Q  # skip first quarter (no prior)
    while i + 3 * Q < len(bars):
        if datetime.fromtimestamp(bars[i]['time'], tz=timezone.utc).minute != 0:
            i += 1; continue
        q1h, q1l = _quarter_range(bars, i)
        # find FIRST breakout bar in Q2 (single side only)
        trigger = None; instat = None
        bull = bear = False
        for k in range(i + Q, i + 2 * Q):
            if bars[k]['high'] > q1h: bull = True
            if bars[k]['low'] < q1l: bear = True
        if bull and not bear:
            instat = 'low';  # bullish
            for k in range(i + Q, i + 2 * Q):
                if bars[k]['high'] > q1h:
                    trigger = k; break
        elif bear and not bull:
            instat = 'high'  # bearish
            for k in range(i + Q, i + 2 * Q):
                if bars[k]['low'] < q1l:
                    trigger = k; break
        if instat and trigger is not None:
            if instat == 'low':
                q = 'Q2 has taken out Q1\'s high. What is the instat classification?'
                correct = 'Instat low — bullish for the hour. Q1 set the LOW, expect Q4 high.'
                decoys = ['Instat high — bearish for the hour. Q1 set the HIGH, expect Q4 low.',
                          'No instat — Q2 stayed within Q1 range.']
                direction = 'bullish'
            else:
                q = 'Q2 has taken out Q1\'s low. What is the instat classification?'
                correct = 'Instat high — bearish for the hour. Q1 set the HIGH, expect Q4 low.'
                decoys = ['Instat low — bullish for the hour. Q1 set the LOW, expect Q4 high.',
                          'No instat — Q2 stayed within Q1 range.']
                direction = 'bearish'
            md = {'event': 'instat', 'instat_type': instat, 'instat_direction': direction,
                  'q1_high': q1h, 'q1_low': q1l, 'trigger_bar_local': trigger, 'trigger_price': bars[trigger]['close']}
            markers.append({'concept': '01d', 'triggerBarIdx': trigger,
                            'triggerTime': bars[trigger]['time'],
                            'nyHour': datetime.fromtimestamp(bars[trigger]['time'], tz=timezone.utc).hour,
                            'question': q, 'metadata': md})
            opts = [correct] + decoys; random.shuffle(opts)
            prompts.append({'id': mkid(), 'triggerCandle': trigger, 'type': 'multiple_choice',
                            'questionText': q, 'correctAnswer': correct, 'explanation': '',
                            'points': 10, 'answerOptions': opts, 'conceptTag': '01d'})
        i += 60
    return prompts, markers

def gen_01e(bars, date_str):
    """Doji (01e): after an instat setup (Q2 takes out Q1 high/low), Q3 takes out Q2's opposite
    extreme -> doji reversal alert. Fire at the Q3 breakout bar."""
    prompts, markers, pid = [], [], 0
    def mkid():
        nonlocal pid; pid += 1; return f'gen-{date_str}-{pid:03d}'
    Q = 15
    i = Q
    while i + 3 * Q < len(bars):
        if datetime.fromtimestamp(bars[i]['time'], tz=timezone.utc).minute != 0:
            i += 1; continue
        q1h, q1l = _quarter_range(bars, i)
        q2h, q2l = _quarter_range(bars, i + Q)
        q3h, q3l = _quarter_range(bars, i + 2 * Q)
        if None in (q1h, q2h, q3h):
            break
        instat = 'LOW' if q2h > q1h else ('HIGH' if q2l < q1l else None)
        if not instat:
            i += 60; continue
        if instat == 'LOW':  # bullish instat; doji if Q3 takes out Q2 low
            if q3l < q2l:
                direction = 'bullish'; broke = 'low'; correct = 'Doji — bullish thesis reversed, Q3 broke Q2 low'
                decoy = 'No doji — bullish continues'
            else:
                i += 60; continue
        else:  # bearish instat; doji if Q3 takes out Q2 high
            if q3h > q2h:
                direction = 'bearish'; broke = 'high'; correct = 'Doji — bearish thesis reversed, Q3 broke Q2 high'
                decoy = 'No doji — bearish continues'
            else:
                i += 60; continue
        # find the first bar inside Q3 that breaks Q2 extreme
        trigger = None
        for k in range(i + 2 * Q, i + 3 * Q):
            if broke == 'low' and bars[k]['low'] < q2l:
                trigger = k; break
            if broke == 'high' and bars[k]['high'] > q2h:
                trigger = k; break
        if trigger is None:
            trigger = i + 2 * Q
        q = (f'Instat {instat} ({direction}) — Q2 broke Q1\'s {"high" if instat=="LOW" else "low"}. '
             f'Now Q3 broke Q2\'s {broke} ({q2l if broke=="low" else q2h:.2f}). Doji alert!')
        md = {'event': 'doji', 'instat': instat, 'instat_direction': direction,
              'q2_high': q2h, 'q2_low': q2l, 'doji_bar_local': trigger,
              'doji_price': q2l if broke == 'low' else q2h}
        markers.append({'concept': '01e', 'triggerBarIdx': trigger,
                        'triggerTime': bars[trigger]['time'],
                        'nyHour': datetime.fromtimestamp(bars[trigger]['time'], tz=timezone.utc).hour,
                        'question': q, 'metadata': md})
        opts = [correct, decoy]; random.shuffle(opts)
        prompts.append({'id': mkid(), 'triggerCandle': trigger, 'type': 'multiple_choice',
                        'questionText': q, 'correctAnswer': correct, 'explanation': '',
                        'points': 10, 'answerOptions': opts, 'conceptTag': '01e'})
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
    elif a.concept == '01d':
        prompts, markers = gen_01d(bars, a.date)
    elif a.concept == '01e':
        prompts, markers = gen_01e(bars, a.date)
    elif a.concept == '01c':
        prompts, markers = gen_01c(bars, a.date)
    elif a.concept == '01f':
        prompts, markers = gen_01f(bars, a.date)
    elif a.concept == '01g':
        prompts, markers = gen_01g(bars, a.date)
    else:
        sys.exit(f'concept {a.concept} not implemented yet')
    sc = build_scenario(a.concept, a.date, bars, prompts, markers)
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f'gen_{a.concept}_{a.date}.json'
    out.write_text(json.dumps(sc))
    print(f'{out}: {len(bars)} bars, {len(prompts)} prompts, {sum(p["points"] for p in prompts)} max pts')

if __name__ == '__main__':
    main()
