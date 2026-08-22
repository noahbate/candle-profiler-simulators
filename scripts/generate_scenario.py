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
from zoneinfo import ZoneInfo

import pandas as pd

DATA = Path('/Users/hermes/projects/candle-profiler/data/working/NQ_work_1min.csv')
OUT = Path(__file__).resolve().parent.parent / 'web' / 'scenarios'
_DF = None  # cached parsed frame for load_day
_ETZ = ZoneInfo('America/New_York')

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
T_01F_MID_ABOVE = ('In Q2 or later, price closed above prev hour 50% ({mid}). What does that confirm?',
             'Confirmed prev hour midpoint reclaim — bullish lean')
T_01F_MID_BELOW = ('In Q2 or later, price closed below prev hour 50% ({mid}). What does that confirm?',
             'Confirmed prev hour midpoint loss — bearish lean')
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

def _et(ts):
    """ET (America/New_York) datetime for an epoch timestamp (DST-safe)."""
    return datetime.fromtimestamp(ts, tz=_ETZ)

def _et_hour(ts):
    return _et(ts).hour

# --- 02c Rolling 3-Hour Cycle ---
T_02C_RESET = ('Session just opened — {bnd} (0{bh}:00 ET). What just happened to the rolling cycle?',
               'Cycle force-resets — this hour becomes the new H1 regardless of where we were.')
T_02C_RESET_A = 'Cycle force-resets — this hour becomes the new H1 regardless of where we were.'
T_02C_APEX_BULL = ('An apex just fired in H2. What pattern is it?',
                  'Q2 Break — Q2 continued past Q1, Q3 broke Q2 opposite side. Mid-hour reversal.')
T_02C_APEX_BEAR = ('An apex just fired in H2. What pattern is it?',
                  'Q2 Break — Q2 continued past Q1, Q3 broke Q2 opposite side. Mid-hour reversal.')
T_02C_FLIP_BULL = ('H2 just took H1\'s high without an apex. What does this tell you about the cycle?',
                  'Direction flips for the cycle — now bull. H3 should target H2\'s high.')
T_02C_FLIP_BEAR = ('H2 just took H1\'s low without an apex. What does this tell you about the cycle?',
                  'Direction flips for the cycle — now bear. H3 should target H2\'s low.')
T_02C_H3_COMPLETE = ('The 3-hour line just completed. What happens to the cycle now?',
                    'H3 becomes the new H1 — cycle resets immediately.')
T_02C_H3_COMPLETE_A = 'H3 becomes the new H1 — cycle resets immediately.'
T_02C_H3_NOCOMP = ('H3 closed without completing the line and is NOT inside H2. What happens to the cycle?',
                   'Cycle expires — the next hour becomes new H1 by fallback.')
T_02C_H3_NOCOMP_A = 'Cycle expires — the next hour becomes new H1 by fallback.'
T_02C_TEXTBOOK = ('H3 just completed the line — and H1 was a Perfect Line. What\'s the conviction on this cycle?',
                  'Highest — textbook cycle. Perfect line H1 + H3 completion is the cleanest setup.')
T_02C_TEXTBOOK_A = 'Highest — textbook cycle. Perfect line H1 + H3 completion is the cleanest setup.'
T_02C_H1_SIG = 'H1\'s first 15 minutes are complete. What line signature is this?'

# --- 02a Three-Hour Line & Apex: block engine over RTH1 (9:00) and RTH2 (12:00) ---
T_02A_POOL = [
    ('concept_apex_hour', 'An apex shows its hand in which hour of the three-hour block?',
     'Hour 2', ['Hour 1', 'Hour 3', 'All three equally']),
    ('concept_signature_count', 'How many three-hour line signatures are there?',
     '4', ['1', '2', '6']),
    ('concept_respect_rule', 'Complete the rule: \'Apexes respect ___, lines respect ___\'',
     'extremes / midpoints', ['midpoints / extremes', 'the open / the close', 'volume / time']),
]
T_02A_INSTAT_LOW = ('Q2 has taken out Q1\'s high. What is the instat classification?',
                    'Instat low — bullish. Q1 set the LOW, expect Q4 high')
T_02A_INSTAT_HIGH = ('Q2 has taken out Q1\'s low. What is the instat classification?',
                     'Instat high — bearish. Q1 set the HIGH, expect Q4 low')
T_02A_BP_ABOVE = ('Price broke above the 0-5 box by the RTH 0.10% threshold. What does this imply for the hour?',
                  'Hour\'s LOW is likely set — bullish momentum confirmed')
T_02A_BP_BELOW = ('Price broke below the 0-5 box by the RTH 0.10% threshold. What does this imply for the hour?',
                  'Hour\'s HIGH is likely set — bearish momentum confirmed')
T_02A_DOJI_BULL = ('Bullish instat already fired. Q3 just broke Q2\'s low. What does this mean?',
                   'Doji alert — structure weakening, reduce expansion expectations')
T_02A_FAILED_DOJI = ('After the doji alert, price has recovered past Q3\'s high. What now?',
                     'Failed doji — structure recovered, healthy candle expected')
T_02A_FALSE_O5_DN = ('Price first broke ABOVE the 0-5 box then confirmed in Q2 or later by closing back BELOW the box bottom. What does this pattern mean?',
                     'Real direction is down — the fake break planted the high')
T_02A_FALSE_O5_UP = ('Price first broke BELOW the 0-5 box then confirmed in Q2 or later by closing back ABOVE the box top. What does this pattern mean?',
                     'Real direction is up — the fake break planted the low')
T_02A_FAILED_FALSE_O5 = ('After the false break down, price broke ABOVE the 0-5 box again. What now?',
                         'Initial bullish intent reasserted — false break itself failed')
T_02A_PREV_MID_DN = ('In Q2 or later, price closed below prev hour midpoint coming from above. What does losing the mid suggest?',
                     'Lost prev hour midpoint — downside bias for this hour')
T_02A_SWEEP_HIGH = ('Price swept prev hour high and has now confirmed in Q2 or later below prev hour mid. What pattern?',
                    'Sweep + suck back — bearish reversal pattern, expect downside')
T_02A_FAILED_SWEEP = ('After the sweep + suck back, price pushed back above prev hour high. What now?',
                      'Sweep reversal failed — original bullish intent reasserted')
T_02A_H3_COUNTER_BEAR = ('H1+H2 set up a bullish line, but H3 just broke its 0-5 box low. In the line/apex framework, what is this?',
                         'Third-hour effect retrace — line may exhaust before close; watch for return to block midpoint or open zone')
T_02A_FAILED_COUNTER = ('After the counter-direction break, price closed back above H3\'s midpoint. What now?',
                        'Failed counter break — bullish thesis reasserted')


def gen_02a(bars, date_str):
    """Three-Hour Line & Apex (02a): processes the 9:00-12:00 and 12:00-15:00 ET blocks.

    The site schedules AT MOST ONE prompt per bar: signal events (module_01/shared)
    are queued at their detection bars, then the fixed line/apex milestone sequence
    runs at its scheduled bars; any collision bumps the later event to the next
    free bar. The milestone pairs (H1-close cluster, H3-open pair, strong/drawable,
    final/3HE pair) are emitted in a per-block shuffled order (parity alternates).
    """
    prompts, markers, pid = [], [], 0
    queue = []  # (scheduled_bar, priority, q, correct, opts, md)

    def mkid():
        nonlocal pid; pid += 1; return f'gen-{date_str}-{pid:03d}'

    def emit(trigger, q, correct, opts, md):
        markers.append({'concept': '02a', 'triggerBarIdx': trigger,
                        'triggerTime': bars[trigger]['time'],
                        'nyHour': _et_hour(bars[trigger]['time']),
                        'question': q, 'metadata': md})
        o = list(opts)
        random.shuffle(o)
        prompts.append({'id': mkid(), 'triggerCandle': trigger, 'type': 'multiple_choice',
                        'questionText': q, 'correctAnswer': correct, 'explanation': '',
                        'points': 10, 'answerOptions': o, 'conceptTag': '02a'})

    def quarter_rng(h0, ql=15):
        seg = bars[h0:h0 + ql]
        if len(seg) < ql:
            return None, None
        return max(b['high'] for b in seg), min(b['low'] for b in seg)

    def hour_signal_pass(h0, hour_no, block_ctx, prio):
        """module_01/shared signals within one hour; appended to queue with priority prio."""
        if h0 + 60 > len(bars):
            return
        box = bars[h0:h0 + 5]
        bh = max(b['high'] for b in box); bl = min(b['low'] for b in box)
        thr_up = bh * 1.0010
        thr_dn = bl * 0.9990
        hour_end = min(h0 + 60, len(bars))
        base_md = {'block_hour': block_ctx['block_hour'], 'concept_focus': 'module_01',
                   'final_classification': block_ctx.get('final_classification', 'other')}
        prev = bars[h0 - 60:h0] if h0 - 60 >= 0 else None
        prev_mid = prev_high = prev_low = None
        if prev is not None and len(prev) >= 60:
            prev_high = max(b['high'] for b in prev); prev_low = min(b['low'] for b in prev)
            prev_mid = (prev_high + prev_low) / 2
        # instat: FIRST Q2 bar taking Q1 high or low
        q1h, q1l = quarter_rng(h0)
        instat = None
        for k in range(h0 + 15, h0 + 30):
            if bars[k]['high'] > q1h:
                instat = ('low', k); break
            if bars[k]['low'] < q1l:
                instat = ('high', k); break
        if instat:
            side, k = instat
            q, correct = T_02A_INSTAT_LOW if side == 'low' else T_02A_INSTAT_HIGH
            decoys = ['Instat high — bearish. Q1 set the HIGH, expect Q4 low',
                      'No instat — Q2 stayed within Q1 range'] if side == 'low' else \
                     ['Instat low — bullish. Q1 set the LOW, expect Q4 high',
                      'No instat — Q2 stayed within Q1 range']
            md = dict(base_md, variant='instat_' + side, signal_type='instat_' + side,
                      concept_focus='shared', q1_high=q1h, q1_low=q1l,
                      direction='bullish' if side == 'low' else 'bearish')
            queue.append((k, prio + 0, q, correct, decoys, md))
            # doji: Q3 breaks Q2 opposite extreme (bullish instat -> Q2 low)
            if side == 'low':
                q2h, q2l = quarter_rng(h0 + 15)
                for k3 in range(h0 + 30, h0 + 45):
                    if bars[k3]['low'] < q2l:
                        q, correct = T_02A_DOJI_BULL
                        md = dict(base_md, variant='doji_violation_bull', signal_type='doji_violation_bull',
                                  concept_focus='shared', q2_low=q2l, q2_high=q2h,
                                  q3_high_at_alert=bars[k3]['high'])
                        queue.append((k3, prio + 1, q, correct, ['Normal pullback, thesis holds'], md))
                        for k4 in range(k3 + 1, hour_end):
                            if bars[k4]['close'] > bars[k3]['high']:
                                q, correct = T_02A_FAILED_DOJI
                                md = dict(base_md, variant='failed_doji_bull', signal_type='failed_doji_bull',
                                          concept_focus='shared', origin_bar_idx=k3,
                                          origin_signal_type='doji_violation_bull')
                                queue.append((k4, prio + 1, q, correct, ['Doji confirmed'], md))
                                break
                        break
        # bp_breach (RTH 0.10%) — fires ONLY when the 0.10% crossing lands in Q1+Q2
        # (bars 5-29 of the hour). Crossings after bar 29 (Q3+) are ignored by the site
        # (validated: 18:31/18:55/18:56 crossings past bar 29 produce NO capture event).
        for side in ('above', 'below'):
            thr = thr_up if side == 'above' else thr_dn
            for k in range(h0 + 5, min(h0 + 30, hour_end)):
                hit = (bars[k]['high'] > thr) if side == 'above' else (bars[k]['low'] < thr)
                if hit:
                    q, correct = T_02A_BP_ABOVE if side == 'above' else T_02A_BP_BELOW
                    decoys = ['Hour\'s HIGH is likely set — bearish momentum confirmed', 'False breakout — price will reverse'] if side == 'above' else \
                             ['Hour\'s LOW is likely set — bullish momentum confirmed', 'False breakout — price will reverse']
                    md = dict(base_md, variant='bp_breach_' + side, signal_type='bp_breach_' + side,
                              box_high=bh, box_low=bl, breach_level=round(thr, 2),
                              breach_price=bars[k]['high'] if side == 'above' else bars[k]['low'],
                              threshold_session='RTH')
                    queue.append((k, prio + 2, q, correct, decoys, md))
                    break
        # false O5 break (break must occur in bars 5-14 of the hour) + failed variant
        for side in ('down', 'up'):
            break_edge = bh if side == 'down' else bl
            rev_edge = bl if side == 'down' else bh
            broke = None
            for k in range(h0 + 5, min(h0 + 15, hour_end)):
                hit = (bars[k]['high'] > break_edge) if side == 'down' else (bars[k]['low'] < break_edge)
                if hit:
                    broke = k
                    break
            if broke is None:
                continue
            for k in range(max(broke + 1, h0 + 15), hour_end):
                hit = (bars[k]['close'] < rev_edge) if side == 'down' else (bars[k]['close'] > rev_edge)
                if hit:
                    q, correct = T_02A_FALSE_O5_DN if side == 'down' else T_02A_FALSE_O5_UP
                    decoys = ['Continuation higher', 'Neutral — wait for more info'] if side == 'down' else \
                             ['Continuation lower', 'Neutral — wait for more info']
                    md = dict(base_md, variant='false_o5_break_' + side, signal_type='false_o5_break_' + side,
                              box_high=bh, box_low=bl, break_bar_local=broke - h0,
                              reversal_bar_local=k - h0)
                    queue.append((k, prio + 3, q, correct, decoys, md))
                    for k2 in range(k + 1, hour_end):
                        hit2 = (bars[k2]['close'] >= break_edge) if side == 'down' else (bars[k2]['close'] <= break_edge)
                        if hit2:
                            q, correct = T_02A_FAILED_FALSE_O5
                            md = dict(base_md, variant='failed_false_o5_break_down', signal_type='failed_false_o5_break_down',
                                      origin_bar_idx=k, origin_signal_type='false_o5_break_' + side)
                            queue.append((k2, prio + 3, q, correct, ['Bearish thesis still holds'], md))
                            break
                    break
        # prev-mid cross down + sweep+suckback + failed sweep
        if prev_mid is not None:
            o = bars[h0]['open']
            if o > prev_mid:
                for k in range(h0 + 15, hour_end):
                    if bars[k]['close'] < prev_mid:
                        q, correct = T_02A_PREV_MID_DN
                        md = dict(base_md, variant='prev_mid_cross_down', signal_type='prev_mid_cross_down',
                                  prev_hour_high=round(prev_high, 2), prev_hour_low=round(prev_low, 2),
                                  prev_hour_mid=round(prev_mid, 2))
                        queue.append((k, prio + 4, q, correct, ['Breakout confirmed'], md))
                        break
            swept_high = None
            for k in range(h0, h0 + 15):
                if bars[k]['high'] > prev_high:
                    swept_high = k
                    break
            if swept_high is not None:
                for k in range(h0 + 15, hour_end):
                    if bars[k]['close'] < prev_mid:
                        q, correct = T_02A_SWEEP_HIGH
                        md = dict(base_md, variant='prev_high_sweep_suckback', signal_type='prev_high_sweep_suckback',
                                  prev_hour_high=round(prev_high, 2), prev_hour_mid=round(prev_mid, 2),
                                  sweep_bar_local=swept_high - h0)
                        queue.append((k, prio + 5, q, correct, ['Bullish continuation'], md))
                        for k2 in range(k + 1, hour_end):
                            if bars[k2]['close'] > prev_high:
                                q, correct = T_02A_FAILED_SWEEP
                                md = dict(base_md, variant='failed_prev_high_sweep', signal_type='failed_prev_high_sweep',
                                          origin_bar_idx=k, origin_signal_type='prev_high_sweep_suckback')
                                queue.append((k2, prio + 5, q, correct, ['Bearish thesis still holds'], md))
                                break
                        break
        # H3 counter break (bear) when H1+H2 = bullish line, + failed variant
        if hour_no == 2 and block_ctx.get('h1h2_line') == 'bull':
            box3 = bars[h0:h0 + 5]
            b3l = min(b['low'] for b in box3)
            b3h = max(b['high'] for b in box3)
            for k in range(h0 + 5, hour_end):
                if bars[k]['low'] < b3l:
                    q, correct = T_02A_H3_COUNTER_BEAR
                    md = dict(base_md, variant='h3_counter_break_bear', signal_type='h3_counter_break_bear',
                              concept_focus='shared', box_high=b3h, box_low=b3l,
                              classification=block_ctx.get('final_classification', 'bullish_line'))
                    queue.append((k, prio + 6, q, correct,
                                  ['Normal pullback — bullish line continues, H3 closes near the high'], md))
                    mid3 = (b3h + b3l) / 2
                    for k2 in range(k + 1, hour_end):
                        if bars[k2]['close'] > mid3:
                            q, correct = T_02A_FAILED_COUNTER
                            md = dict(base_md, variant='failed_h3_counter_bear', signal_type='failed_h3_counter_bear',
                                      concept_focus='shared', origin_bar_idx=k,
                                      origin_signal_type='h3_counter_break_bear')
                            queue.append((k2, prio + 6, q, correct, ['Counter break still valid'], md))
                            break
                    break

    i = 0
    block_no = 0
    while i + 180 < len(bars):
        t = _et(bars[i]['time'])
        if t.minute != 0 or t.hour not in (9, 12):
            i += 1
            continue
        bh = t.hour
        parity = block_no % 2
        block = bars[i:i + 180]
        h1 = block[0:60]; h2 = block[60:120]; h3 = block[120:180]
        h1h = max(b['high'] for b in h1); h1l = min(b['low'] for b in h1)
        h2h = max(b['high'] for b in h2); h2l = min(b['low'] for b in h2)
        h3h = max(b['high'] for b in h3); h3l = min(b['low'] for b in h3)
        box1 = block[0:5]; b1h = max(b['high'] for b in box1); b1l = min(b['low'] for b in box1)

        def quarter_of(bar_idx):
            for qn in range(4):
                if i + qn * 15 <= bar_idx < i + (qn + 1) * 15:
                    return qn + 1
            return 4
        hi_bar = max(range(60), key=lambda k: h1[k]['high'])
        lo_bar = min(range(60), key=lambda k: h1[k]['low'])
        hq = quarter_of(i + hi_bar); lq = quarter_of(i + lo_bar)
        twos_threes = hq in (2, 3) or lq in (2, 3)
        broke_both = (h1h > b1h) and (h1l < b1l)
        if broke_both:
            h1_sig = 'false_o5'
        else:
            first15 = h1[0:15]
            f15l = min(b['low'] for b in first15); f15h = max(b['high'] for b in first15)
            f15l_min = min(range(15), key=lambda k: first15[k]['low'])
            f15h_min = min(range(15), key=lambda k: -first15[k]['high'])
            if (h1l == f15l and f15l_min <= 1) or (h1h == f15h and f15h_min <= 1):
                h1_sig = 'perfect'
            elif (h1l == f15l and f15l_min <= 5) or (h1h == f15h and f15h_min <= 5):
                h1_sig = 'first05'
            else:
                h1_sig = 'none'
        prog_up = (h1h < h2h < h3h) and (h1l < h2l < h3l)
        prog_dn = (h1h > h2h > h3h) and (h1l > h2l > h3l)
        block_open = block[0]['open']; block_close = block[-1]['close']
        drift = (block_close - block_open) / block_open * 100
        if prog_up:
            final_cls = 'bullish_line'
        elif prog_dn:
            final_cls = 'bearish_line'
        elif twos_threes and abs(drift) < 0.05:
            final_cls = ('bullish_apex' if block_close > block_open else 'bearish_apex')
        else:
            final_cls = 'other'
        ctx = {'block_hour': bh, 'final_classification': final_cls,
               'h1h2_line': 'bull' if prog_up else ('bear' if prog_dn else None)}
        base = {'block_hour': bh, 'final_classification': final_cls, 'concept_focus': 'line_apex'}
        # pool questions at +5/+6 (cycle [0,1],[2,0],[1,2],...)
        for off, pi in ((5, (2 * block_no) % 3), (6, (2 * block_no + 1) % 3)):
            variant, q, correct, decoys = T_02A_POOL[pi]
            md = dict(base, source='Apex.md', variant=variant, pool_index=pi, signal_type=variant)
            queue.append((i + off, 10, q, correct, decoys, md))
        # signal events
        for hn in range(3):
            hour_signal_pass(i + hn * 60, hn, ctx, prio=0)
        # ---- milestone sequence (scheduled bars; parity decides pair order) ----
        sig_ans = {'false_o5': 'False O5 break — fake direction reversed into a line',
                   'perfect': 'Perfect line — minute 1 planted the extreme',
                   'first05': 'First five-minute line — 0-5 box planted the extreme',
                   'none': 'No clear line signature — apex more likely'}[h1_sig]
        sig_opts = ['Perfect line — minute 1 planted the extreme', 'First five-minute line — 0-5 box planted the extreme',
                    'False O5 break — fake direction reversed into a line', 'No clear line signature — apex more likely']
        # H1-close cluster: parity 0 [sig@59, qr@60], parity 1 [qr@59, sig@60] (bumping resolves)
        sig_ev = (i + (59 if parity == 0 else 60), 20,
                  'Hour 1 just closed. Which three-hour-line signature (if any) appeared during this hour?',
                  sig_ans, sig_opts, dict(base, source='Three-Hour-Line.md/Line-Signatures', variant='h1_signature_check',
                                          signal_type='h1_signature_check'))
        if twos_threes:
            q4r = 'Apex — Q2 or Q3 planted an extreme (twos-and-threes); fade extremes'
        elif (hq, lq) == (4, 1):
            q4r = 'Bullish line — high in Q4, low in Q1 (4-1): Q1 planted the LOW, Q4 targeted the high'
        elif (hq, lq) == (1, 4):
            q4r = 'Bearish line — high in Q1, low in Q4 (1-4): Q1 planted the HIGH, Q4 targeted the low'
        else:
            q4r = 'Mixed — extremes don\'t follow a clean fours-and-ones or twos-and-threes pattern'
        qr_opts = ['Bullish line — high in Q4, low in Q1 (4-1): Q1 planted the LOW, Q4 targeted the high',
                   'Bearish line — high in Q1, low in Q4 (1-4): Q1 planted the HIGH, Q4 targeted the low',
                   'Apex — Q2 or Q3 planted an extreme (twos-and-threes); fade extremes',
                   'Mixed — extremes don\'t follow a clean fours-and-ones or twos-and-threes pattern']
        qr_ev = (i + (60 if parity == 0 else 59), 20,
                 'Hour 1 just closed. Where did H1 plant its HIGH and LOW? What does that say about line vs apex?',
                 q4r, qr_opts, dict(base, source='Quarters.md/Fours-and-Ones/Twos-and-Threes', variant='h1_quarter_read',
                                    signal_type='h1_quarter_read', high_quarter=hq, low_quarter=lq,
                                    quarter_signature=f'{hq}-{lq}'))
        queue.append(sig_ev if parity == 0 else qr_ev)
        queue.append(qr_ev if parity == 0 else sig_ev)
        # quadrant + apex watch: H2-quadrant at +61, H3-quadrant at +120/+121 (parity), apex watch at +62
        h2_open = block[60]['open']
        quad_events = []
        for k, label, prev_hi, prev_lo in ((i + 61, 'H1', h1h, h1l), (i + 121, 'H2', h2h, h2l)):
            prev_mid2 = (prev_hi + prev_lo) / 2
            rng = prev_hi - prev_lo
            open_price = (h3[0]['open'] if k == i + 121 else h2_open)
            if open_price >= prev_hi - rng * 0.1:
                quad = 'upper'
            elif open_price <= prev_lo + rng * 0.1:
                quad = 'lower'
            elif open_price > prev_mid2:
                quad = 'upper-mid'
            else:
                quad = 'lower-mid'
            qn = 'H2 just opened. Where in H1\'s range did the open land, and what does this open suggest?' if label == 'H1' else \
                 'H3 just opened. Where in H2\'s range did the open land, and what does this open suggest?'
            ans = {'upper': f'Near {label} high — higher probability of upside continuation or sweep + reversal',
                   'upper-mid': f'Above {label} midpoint — slight bullish lean, watch 0-5 box for confirmation',
                   'lower-mid': f'Below {label} midpoint — slight bearish lean, watch 0-5 box for confirmation',
                   'lower': f'Near {label} low — higher probability of downside continuation or sweep + reversal'}[quad]
            opts_q = [f'Near {label} high — higher probability of upside continuation or sweep + reversal',
                      f'Above {label} midpoint — slight bullish lean, watch 0-5 box for confirmation',
                      f'Below {label} midpoint — slight bearish lean, watch 0-5 box for confirmation',
                      f'Near {label} low — higher probability of downside continuation or sweep + reversal']
            st = 'h2_open_quadrant' if k == i + 61 else 'h3_open_quadrant'
            quad_events.append((k, 21, qn, ans, opts_q,
                                dict(base, variant=st, signal_type=st, quadrant=quad, open_price=open_price,
                                     prev_high=prev_hi, prev_low=prev_lo, concept_focus='shared')))
        queue.append(quad_events[0])  # H2 quadrant at +61 (bumps if occupied)
        queue.append((i + 62, 22, 'Hour 2 just opened. The apex shows its hand in H2. Which two signatures should you watch for to confirm an apex?',
                      'Sweeper of H1 extreme + Q2 or Q3 quarter break (the two apex signatures)',
                      ['Perfect line + first-five-minute line', 'Doji + instat', 'Footprint rejection + 0-5 box breach'],
                      dict(base, source='Apex.md/Two-Primary-Apex-Signatures', variant='h2_open_apex_watch',
                           signal_type='h2_open_apex_watch')))
        he_ev = (i + 120, 25, 'Hour 3 just opened. What\'s the \'third-hour effect\' (3HE) — what should you watch for now?',
                 'Either the line extends OR the third-hour effect retraces toward the block-open / 9:30 area — depends on H1+H2 setup',
                 ['H3 always continues the H2 direction — no other outcome', 'H3 always reverses against H2 — that\'s what 3HE means',
                  'H3 has no diagnostic value once H2 closes'],
                 dict(base, source='RE-2026-02-20', variant='h3_open_3he_watch', signal_type='h3_open_3he_watch'))
        h3_quad_ev = (i + (120 if parity == 1 else 121), 21, quad_events[1][2], quad_events[1][3], quad_events[1][4], quad_events[1][5])
        # H3-open pair: parity 0 [3he@120, quad@121], parity 1 [quad@120, 3he@121]
        he_ev = (i + (120 if parity == 0 else 121), 25, he_ev_q, he_ev_ans, he_ev_opts, he_ev_md) if False else he_ev
        if parity == 0:
            queue.append(he_ev)
            queue.append(h3_quad_ev)
        else:
            queue.append(h3_quad_ev)
            queue.append(he_ev)
        # 6-quarter trend: total return over Q1 open -> Q6 close; threshold 0.05%
        q6c = block[89]['close']
        ret_pct = (q6c - block[0]['open']) / block[0]['open'] * 100
        if ret_pct > 0.05:
            trend = 'UP'
        elif ret_pct < -0.05:
            trend = 'DOWN'
        else:
            trend = None
        if trend:
            opp = 'DOWNWARD' if trend == 'UP' else 'UPWARD'
            queue.append((i + 90, 23,
                          f'Six quarters into the block, the trend has been {trend}. Q3 of H2 is now starting. What would put us on APEX ALERT here?',
                          f'Apex ALERT triggers IF Q3 or Q4 breaks {opp} (opposite of the 6-quarter trend); confirmation comes later if price breaks the block opening',
                          [f'Apex ALERT triggers IF Q3 or Q4 breaks {"UPWARD" if trend == "DOWN" else "DOWNWARD"} (opposite of the 6-quarter trend); confirmation comes later if price breaks the block opening',
                           'Line continues — Q3/Q4 break just adds momentum', 'Doji alert — wait for H3 to confirm'],
                          dict(base, source='Apex.md/Quarter-Break-In-Hour-Two', variant='h2_quarter_break_apex_watch',
                               signal_type='h2_quarter_break_apex_watch', six_quarter_trend=trend.lower())))
            down_ans = ('Q4 must break DOWN below the running quarterly lows to trigger the apex alert (opposite of the 7-quarter trend)'
                        if trend == 'UP' else
                        'Q4 must break UP above the running quarterly highs to trigger the apex alert (opposite of the 7-quarter trend)')
            down_opts = ['Q4 must break DOWN below the running quarterly lows to trigger the apex alert (opposite of the 7-quarter trend)',
                         'Q4 must break UP above the running quarterly highs to trigger the apex alert (opposite of the 7-quarter trend)',
                         'Q4 just continues the line — no apex possible after Q3', 'Q4 has no diagnostic value']
            queue.append((i + 105, 23,
                          f'Q3 of H2 didn\'t break the {trend} trend. Q4 of H2 just started. What\'s the late-apex ALERT criterion?',
                          down_ans, down_opts,
                          dict(base, source='Apex.md/Quarter-Break-In-Hour-Two', variant='h2_q4_late_break_watch',
                               signal_type='h2_q4_late_break_watch', seven_quarter_trend=trend.lower())))
        # H2 close commit (+119)
        if twos_threes:
            h1_setup = 'apex_likely'
            commit_ans = 'Apex forming — H1 quarter pattern was twos-and-threes'
        elif h1_sig in ('perfect', 'first05', 'false_o5'):
            h1_setup = 'line_likely'
            commit_ans = ('Bullish line forming — H1 line signature + H2 continuation up' if h2[-1]['close'] > h1[-1]['close']
                          else 'Bearish line forming — H1 line signature + H2 continuation down')
        else:
            h1_setup = 'ambiguous'
            commit_ans = 'Ambiguous — wait for H3 to commit'
        queue.append((i + 119, 24, 'Hours 1 and 2 are complete. Based ONLY on what\'s happened so far (no H3 yet), what\'s the most likely classification?',
                      commit_ans,
                      ['Bullish line forming — H1 line signature + H2 continuation up', 'Bearish line forming — H1 line signature + H2 continuation down',
                       'Apex forming — H2 swept both H1 sides (sweeper signature)', 'Apex forming — H1 quarter pattern was twos-and-threes',
                       'Ambiguous — wait for H3 to commit'],
                      dict(base, source='Three-Hour-Line.md/Apex.md', variant='h2_close_commit', h1_setup=h1_setup,
                           signal_type='h2_close_commit')))
        # Q4 resolution (+165)
        queue.append((i + 165, 26, 'Q4 of H3 is starting. Based on the line/apex framework, how does Q4 typically resolve?',
                      'In a line: Q4 targets the opposite of Q1\'s extreme (fours-and-ones). In an apex: Q4 mean reverts toward the H3 midpoint.',
                      ['Q4 always extends past Q3\'s extreme regardless of classification', 'Q4 always closes flat — it is a \'doji quarter\'',
                       'Q4 has no predictable behavior — random'],
                      dict(base, source='Three-Hour-Line.md/Q1-plants-Q4-targets', variant='h3_q4_resolution_watch',
                           signal_type='h3_q4_resolution_watch')))
        # drawable + strong at +170/+171: parity 0 [drawable, strong], parity 1 [strong, drawable]
        # drawable is gated on H1's quarter signature: twos-and-threes (apex) => NOT drawable,
        # regardless of later progression (validated: 19:51 block-2 progress but answer = No/apex)
        if twos_threes:
            drawable_ans = 'No — structure broken; this is an apex'
        elif prog_up:
            drawable_ans = 'Yes — bullish line is drawable (progressive higher highs, no violations)'
        elif prog_dn:
            drawable_ans = 'Yes — bearish line is drawable (progressive lower lows, no violations)'
        else:
            drawable_ans = 'No — structure broken; this is an apex'
        draw_opts = ['Yes — bullish line is drawable (progressive higher highs, no violations)',
                     'Yes — bearish line is drawable (progressive lower lows, no violations)',
                     'No — structure broken; this is an apex']
        draw_ev = (i + 170, 27, 'We\'re 50 bars into H3. Can you \'draw a line\' through the three hourly candles?',
                   drawable_ans, draw_opts,
                   dict(base, source='BLUF/If-you-can-draw-a-line', variant='h3_drawable_line', signal_type='h3_drawable_line'))
        h2_mid = (h2h + h2l) / 2
        strong_ev = None
        if all(bars[j]['close'] > h2_mid for j in range(i + 120, i + 171)):
            strong_ev = (i + 170, 27, 'Through bar 50 of H3, every close has stayed above H2\'s midpoint with no retrace. What does this signal?',
                         'Strong bullish line — no retrace through H2 mid; expect H3 close at or near the extreme',
                         ['Apex coiling — break is imminent in either direction', 'Random walk — no diagnostic value', 'Doji hour — close near open expected'],
                         dict(base, h2_mid=round(h2_mid, 2), source='Three-Hour-Line.md/Hours-two-and-three-continue',
                              variant='h3_strong_line_no_pullback', direction='bullish',
                              signal_type='h3_strong_line_no_pullback'))
        if parity == 0:
            queue.append(draw_ev)
            if strong_ev:
                queue.append(strong_ev)
        else:
            if strong_ev:
                queue.append(strong_ev)
            queue.append(draw_ev)
        # final classification + 3HE resolution at +179/+180: parity 0 [final@179, 3he@180],
        # parity 1 [3he@179, final@180] — SWAP the scheduled bars, not just the append order
        cls_ans = {'bullish_line': 'Bullish line', 'bearish_line': 'Bearish line',
                   'bullish_apex': 'Bullish apex', 'bearish_apex': 'Bearish apex',
                   'other': 'Other — does not match a clean line or apex'}[final_cls]
        final_ev = (i + (179 if parity == 0 else 180), 28, f'Is this {bh}:00-{bh + 3}:00 three-hour block a Line or Apex? Bullish or bearish?',
                    cls_ans, ['Bullish line', 'Bearish line', 'Bullish apex', 'Bearish apex',
                              'Other — does not match a clean line or apex'],
                    dict(base, variant='final_classification', signal_type='final_classification',
                         classification=final_cls, final_classification=final_cls))
        if drift > 0.02:
            he_ans = '3HE played out as EXTENSION — close significantly above block open (line-like)'
        elif drift < -0.02:
            he_ans = '3HE played out as EXTENSION — close significantly below block open (line-like)'
        else:
            he_ans = '3HE played out as MEAN REVERSION — close near block open (apex-like)'
        he_res_ev = (i + (180 if parity == 0 else 179), 28, 'Block close. Did the third-hour effect play out as expected — extension away from block open, or retrace back to it?',
                     he_ans,
                     ['3HE played out as MEAN REVERSION — close near block open (apex-like)',
                      '3HE played out as EXTENSION — close significantly above block open (line-like)',
                      '3HE played out as EXTENSION — close significantly below block open (line-like)'],
                     dict(base, source='RE-2026-02-20+01-29+03-04', variant='h3_close_3he_resolution',
                          h3_close=block_close, drift_pct=round(drift, 3), block_open=block_open,
                          signal_type='h3_close_3he_resolution'))
        if parity == 0:
            queue.append(final_ev)
            queue.append(he_res_ev)
        else:
            queue.append(he_res_ev)
            queue.append(final_ev)
        i += 180
        block_no += 1
    # resolve collisions: sort by (scheduled_bar, priority); assign to first free bar >= scheduled
    queue.sort(key=lambda e: (e[0], e[1]))
    occupied = set()
    for sched, prio, q, correct, opts, md in queue:
        bar = sched
        while bar in occupied:
            bar += 1
        occupied.add(bar)
        emit(bar, q, correct, opts, md)
    return prompts, markers


def gen_02c(bars, date_str):
    """Rolling 3-Hour Cycle (02c): H1 -> H2 -> H3 cycles.

    Cycle model (from capture metadata): each cycle is 3 consecutive hours
    (H1, H2, H3). On h3_line_complete the H3 hour becomes the new H1 (immediate
    roll). On h3_no_completion the next hour becomes new H1 by fallback. Forced
    resets at Globex open (18:00 ET) and RTH open (09:00 ET).

    Events: cycle_reset_session_boundary, h1_line_signature, h2_apex,
    h2_direction_flip, h3_line_complete, h3_no_completion, setup_textbook_perfect.
    """
    prompts, markers, pid = [], [], 0
    def mkid():
        nonlocal pid; pid += 1; return f'gen-{date_str}-{pid:03d}'
    def emit(bar, q, correct, opts, md):
        if bar < 0 or bar >= n:
            return
        md = dict(md)
        markers.append({'concept': '02c', 'triggerBarIdx': bar,
                        'triggerTime': bars[bar]['time'],
                        'nyHour': _et_hour(bars[bar]['time']),
                        'question': q, 'metadata': md})
        o = list(opts); random.shuffle(o)
        prompts.append({'id': mkid(), 'triggerCandle': bar, 'type': 'multiple_choice',
                        'questionText': q, 'correctAnswer': correct, 'explanation': '',
                        'points': 10, 'answerOptions': o, 'conceptTag': '02c'})

    n = len(bars)
    starts = [(i, _et_hour(bars[i]['time'])) for i in range(0, n - 60, 60)
              if _et(bars[i]['time']).minute == 0]
    resets = {i for i, h in starts if h in (18, 9)}

    h1 = None   # bar index of current cycle's H1
    for h0, h in starts:
        if h0 in resets:
            h1 = h0
            emit(h0, T_02C_RESET[0].format(bnd='Globex open' if h == 18 else 'RTH open', bh=h),
                 T_02C_RESET[1], ['Cycle continues — H2 becomes H1', 'Cycle pauses until next session'],
                 {'signal_type': 'cycle_reset_session_boundary', 'cycle_role': 'H1',
                  'boundary': 'globex_open' if h == 18 else 'rth_open', 'h1_hour': h, 'h2_hour': None})
            # H1 line signature at +15
            sig, ans = _h1_signature(bars, h0)
            emit(h0 + 15, sig, ans,
                 ['No clear line signature — apex more likely', 'Perfect Bear — H1 high formed in minute 0-1. Strongest bear.'],
                 {'signal_type': 'h1_line_signature', 'cycle_role': 'H1', 'line_sig': 'perfect-bull' if ans.startswith('Perfect Bull') else 'perfect-bear',
                  'cycle_direction': 'bull' if ans.startswith('Perfect Bull') else 'bear', 'h1_hour': h, 'h2_hour': None})
            continue
        if h1 is None:
            h1 = h0
            emit(h0, T_02C_RESET[0].format(bnd='fallback', bh=h), T_02C_RESET[1],
                 ['Cycle continues — H2 becomes H1', 'Cycle pauses until next session'],
                 {'signal_type': 'cycle_reset_session_boundary', 'cycle_role': 'H1', 'boundary': 'fallback', 'h1_hour': h, 'h2_hour': None})
            sig, ans = _h1_signature(bars, h0)
            emit(h0 + 15, sig, ans,
                 ['No clear line signature — apex more likely', 'Perfect Bear — H1 high formed in minute 0-1. Strongest bear.'],
                 {'signal_type': 'h1_line_signature', 'cycle_role': 'H1',
                  'line_sig': 'perfect-bull' if ans.startswith('Perfect Bull') else 'perfect-bear',
                  'cycle_direction': 'bull' if ans.startswith('Perfect Bull') else 'bear', 'h1_hour': h, 'h2_hour': None})
            continue
        h1h = _et_hour(bars[h1]['time'])
        delta = (h - h1h) % 24
        if delta == 0:
            # rolled: this hour is the new H1 (H3 of prev cycle became H1)
            h1 = h0
            emit(h0, T_02C_RESET[0].format(bnd='roll', bh=h), T_02C_RESET[1],
                 ['Cycle continues — H2 becomes H1', 'Cycle pauses until next session'],
                 {'signal_type': 'cycle_reset_session_boundary', 'cycle_role': 'H1', 'boundary': 'roll', 'h1_hour': h, 'h2_hour': None})
            sig, ans = _h1_signature(bars, h0)
            emit(h0 + 15, sig, ans,
                 ['No clear line signature — apex more likely', 'Perfect Bear — H1 high formed in minute 0-1. Strongest bear.'],
                 {'signal_type': 'h1_line_signature', 'cycle_role': 'H1',
                  'line_sig': 'perfect-bull' if ans.startswith('Perfect Bull') else 'perfect-bear',
                  'cycle_direction': 'bull' if ans.startswith('Perfect Bull') else 'bear', 'h1_hour': h, 'h2_hour': None})
            continue
        if delta == 1:
            # H2
            h1_bars = bars[h1:h1 + 60]; h2_bars = bars[h0:h0 + 60]
            h1_lo = min(b['low'] for b in h1_bars); h1_hi = max(b['high'] for b in h1_bars)
            took_low = any(b['low'] < h1_lo for b in h2_bars)
            took_high = any(b['high'] > h1_hi for b in h2_bars)
            apex = _h2_apex(h2_bars)
            if apex:
                q, a = (T_02C_APEX_BULL if apex == 'bull' else T_02C_APEX_BEAR)
                emit(h0 + 44, q, a, ['Q1 Break — Q1 extended, Q3 failed', 'No apex — clean line'],
                     {'signal_type': 'h2_apex', 'cycle_role': 'H2', 'cycle_direction': apex,
                      'h1_hour': h1h, 'h2_hour': h, 'apex_kind': 'q2break'})
            elif took_low or took_high:
                flip = 'bear' if took_low else 'bull'
                bar = h0 + 30
                for k in range(h0, h0 + 60):
                    if (took_low and bars[k]['low'] < h1_lo) or (took_high and bars[k]['high'] > h1_hi):
                        bar = k; break
                q, a = (T_02C_FLIP_BEAR if flip == 'bear' else T_02C_FLIP_BULL)
                emit(bar, q, a, ['Direction holds', 'Cycle expires'],
                     {'signal_type': 'h2_direction_flip', 'cycle_role': 'H2', 'cycle_direction': flip,
                      'h1_hour': h1h, 'h2_hour': h})
        elif delta == 2:
            # H3
            h1_bars = bars[h1:h1 + 60]; h2_bars = bars[h1 + 60:h1 + 120]; h3_bars = bars[h0:h0 + 60]
            h1_lo = min(b['low'] for b in h1_bars); h1_hi = max(b['high'] for b in h1_bars)
            h2_lo = min(b['low'] for b in h2_bars); h2_hi = max(b['high'] for b in h2_bars)
            h3_lo = min(b['low'] for b in h3_bars); h3_hi = max(b['high'] for b in h3_bars)
            completed = h3_hi > h2_hi or h3_lo < h2_lo
            inside_h2 = h3_lo >= h2_lo and h3_hi <= h2_hi
            if completed:
                emit(h0 + 59, T_02C_H3_COMPLETE, T_02C_H3_COMPLETE_A,
                     ['Cycle expires — next hour is new H1 by fallback', 'Direction flips'],
                     {'signal_type': 'h3_line_complete', 'cycle_role': 'H3',
                      'cycle_direction': 'bull' if h3_hi > h2_hi else 'bear', 'h1_hour': h1h, 'h2_hour': h1h + 1})
                if _is_perfect(bars, h1):
                    emit(h0 + 60, T_02C_TEXTBOOK, T_02C_TEXTBOOK_A,
                         ['Moderate — decent but not textbook', 'Low — incomplete cycle'],
                         {'signal_type': 'setup_textbook_perfect', 'cycle_role': 'H3', 'h1_hour': h1h, 'h2_hour': h1h + 1})
                h1 = h0  # H3 becomes new H1
            elif not inside_h2:
                emit(h0 + 59, T_02C_H3_NOCOMP, T_02C_H3_NOCOMP_A,
                     ['Line completes — H3 becomes new H1', 'Direction flips'],
                     {'signal_type': 'h3_no_completion', 'cycle_role': 'H3',
                      'cycle_direction': 'bull' if h3_hi > h2_hi else 'bear', 'h1_hour': h1h, 'h2_hour': h1h + 1})
                h1 = None  # fallback: next hour new H1
            else:
                h1 = None
    return prompts, markers


def _h1_signature(bars, h0):
    """Return (question, answer) for H1 line signature at h0 (first 15 min)."""
    seg = bars[h0:h0 + 15]
    if len(seg) < 15:
        return T_02C_H1_SIG, 'No clear line signature — apex more likely'
    lo_plant = min(range(15), key=lambda i: seg[i]['low'])
    hi_plant = min(range(15), key=lambda i: seg[i]['high'])
    if lo_plant <= 1:
        return T_02C_H1_SIG, 'Perfect Bull — H1 low formed in minute 0-1. Strongest bull. H3 expected higher high.'
    if hi_plant <= 1:
        return T_02C_H1_SIG, 'Perfect Bear — H1 high formed in minute 0-1. Strongest bear. H3 expected lower low.'
    return T_02C_H1_SIG, 'No clear line signature — apex more likely'


def _h2_apex(h2_bars):
    """Detect Q2-break apex in H2: Q2 takes Q1 extreme, Q3 breaks opposite."""
    if len(h2_bars) < 45:
        return None
    q1h = max(b['high'] for b in h2_bars[:15]); q1l = min(b['low'] for b in h2_bars[:15])
    for k in range(15, 30):
        if h2_bars[k]['high'] > q1h:
            for k3 in range(30, 45):
                if h2_bars[k3]['low'] < h2_bars[k]['low']:
                    return 'bull'
            break
        if h2_bars[k]['low'] < q1l:
            for k3 in range(30, 45):
                if h2_bars[k3]['high'] > h2_bars[k]['high']:
                    return 'bear'
            break
    return None

def _is_perfect(bars, h0):
    """Perfect line: H1 extreme (low for bull / high for bear) planted in minute 0-1."""
    seg = bars[h0:h0 + 15]
    if len(seg) < 15:
        return False
    lo_plant = min(range(15), key=lambda i: seg[i]['low'])
    hi_plant = min(range(15), key=lambda i: seg[i]['high'])
    return lo_plant <= 1 or hi_plant <= 1

def gen_01f(bars, date_str):
    """Prev Hour (01f): prev hour 50% (mid) reclaim in Q2+ and footprint_test (wick zone reject).

    Rules validated 7/7 fp + 6/6 mt vs capture reference/assemble/01f.json (2024-03-18):
    - prev hour = the 60 bars before the current hour's first bar.
    - wick zone = the prev hour candle's ACTUAL wick:
        red   (close<open): lower wick zone = [low, close]
        green (close>open): upper wick zone = [close, high]
    - footprint gate: some Q1 bar (off 0-14) ENTERS the wick zone from outside:
        red:   bar.low <= ph_close AND bar.high > ph_close
        green: bar.high >= ph_close AND bar.low < ph_close
      footprint_bar = offset of the FIRST such Q1 bar.
    - footprint_test fires at the first Q2+ (off 15+) close beyond prev mid in the
      reclaim direction (red -> above/bullish, green -> below/bearish), break >= 0.25.
    - mid_touch fires (only in footprint-gate hours) at the first Q2+ close beyond mid
      in the direction OPPOSITE to Q1's last close (Q1 close < mid -> above; > mid -> below).
    - Co-location: if mt and fp reclaim the SAME bar, fp trigger shifts +1 (mt at N, fp at N+1).
    """
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
        red = ph_close < ph_open
        wick_bottom = round(ph_low if red else ph_close, 2)
        wick_top = round(ph_close if red else ph_high, 2)
        hour_end = min(i + 60, len(bars))
        # footprint gate: first Q1 bar entering the wick zone from outside
        fp_test = None
        for off in range(15):
            b = bars[i + off]
            if red and b['low'] <= ph_close and b['high'] > ph_close:
                fp_test = off; break
            if (not red) and b['high'] >= ph_close and b['low'] < ph_close:
                fp_test = off; break
        # mid_touch: only in footprint-gate hours; direction opposite Q1's last close
        mt = None; mt_side = None
        if fp_test is not None:
            q1c = bars[i + 14]['close']
            if q1c < ph_mid:
                mt_side = 'above'
                for k in range(i + 15, hour_end):
                    if bars[k]['close'] > ph_mid and bars[k]['close'] - ph_mid >= 0.25:
                        mt = k; break
            elif q1c > ph_mid:
                mt_side = 'below'
                for k in range(i + 15, hour_end):
                    if bars[k]['close'] < ph_mid and ph_mid - bars[k]['close'] >= 0.25:
                        mt = k; break
        if mt is not None:
            q, correct = (T_01F_MID_ABOVE if mt_side == 'above' else T_01F_MID_BELOW)
            md = {'above_mid': mt_side == 'above', 'bar_close': round(bars[mt]['close'], 2),
                  'sub_concept': 'mid_touch', 'prev_hour_low': round(ph_low, 2),
                  'prev_hour_mid': round(ph_mid, 2), 'prev_hour_high': round(ph_high, 2),
                  'confirmation_bar': mt - i}
            markers.append({'concept': '01f', 'triggerBarIdx': mt,
                            'triggerTime': bars[mt]['time'],
                            'nyHour': datetime.fromtimestamp(bars[mt]['time'], tz=timezone.utc).hour,
                            'question': q.format(mid=f'{ph_mid:.2f}'), 'metadata': md})
            decoy = 'Confirmed prev hour midpoint loss — bearish lean' if mt_side == 'above' else 'Confirmed prev hour midpoint reclaim — bullish lean'
            opts = [correct, decoy]; random.shuffle(opts)
            prompts.append({'id': mkid(), 'triggerCandle': mt, 'type': 'multiple_choice',
                            'questionText': q.format(mid=f'{ph_mid:.2f}'), 'correctAnswer': correct,
                            'explanation': '', 'points': 10, 'answerOptions': opts, 'conceptTag': '01f'})
        # footprint_test
        if fp_test is not None:
            fp_side = 'above' if red else 'below'   # reclaim direction
            fp = None
            for k in range(i + 15, hour_end):
                if fp_side == 'above' and bars[k]['close'] > ph_mid and bars[k]['close'] - ph_mid >= 0.25:
                    fp = k; break
                if fp_side == 'below' and bars[k]['close'] < ph_mid and ph_mid - bars[k]['close'] >= 0.25:
                    fp = k; break
            if fp is not None:
                trig = fp + 1 if (mt is not None and mt == fp) else fp  # co-location shift
                q2, correct2 = T_01F_FP_BULL if fp_side == 'above' else T_01F_FP_BEAR
                md2 = {'rejected': True, 'wick_top': wick_top, 'bar_close': round(bars[fp]['close'], 2),
                       'sub_concept': 'footprint_test', 'wick_bottom': wick_bottom,
                       'footprint_bar': fp_test, 'prev_hour_low': round(ph_low, 2),
                       'prev_hour_mid': round(ph_mid, 2), 'prev_hour_high': round(ph_high, 2),
                       'prev_hour_color': 'red' if red else 'green',
                       'confirmation_bar': fp - i}
                markers.append({'concept': '01f', 'triggerBarIdx': trig,
                                'triggerTime': bars[trig]['time'],
                                'nyHour': datetime.fromtimestamp(bars[trig]['time'], tz=timezone.utc).hour,
                                'question': q2.format(wlow=f'{wick_bottom:.2f}', whigh=f'{wick_top:.2f}', mid=f'{ph_mid:.2f}'),
                                'metadata': md2})
                decoy2 = 'Accepted wick zone — bearish continuation' if fp_side == 'above' else 'Accepted wick zone — bullish continuation'
                opts2 = [correct2, decoy2]; random.shuffle(opts2)
                prompts.append({'id': mkid(), 'triggerCandle': trig, 'type': 'multiple_choice',
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
    elif a.concept == '02a':
        prompts, markers = gen_02a(bars, a.date)
    elif a.concept == '02c':
        prompts, markers = gen_02c(bars, a.date)
    else:
        sys.exit(f'concept {a.concept} not implemented yet')
    sc = build_scenario(a.concept, a.date, bars, prompts, markers)
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f'gen_{a.concept}_{a.date}.json'
    out.write_text(json.dumps(sc))
    print(f'{out}: {len(bars)} bars, {len(prompts)} prompts, {sum(p["points"] for p in prompts)} max pts')

if __name__ == '__main__':
    main()
