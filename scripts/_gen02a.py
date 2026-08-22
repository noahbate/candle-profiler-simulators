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
        # bp_breach (RTH 0.10%)
        for side in ('above', 'below'):
            thr = thr_up if side == 'above' else thr_dn
            for k in range(h0 + 5, hour_end):
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
        sig_ev = (i + 59, 20, 'Hour 1 just closed. Which three-hour-line signature (if any) appeared during this hour?',
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
        qr_ev = (i + 60, 20, 'Hour 1 just closed. Where did H1 plant its HIGH and LOW? What does that say about line vs apex?',
                 q4r, qr_opts, dict(base, source='Quarters.md/Fours-and-Ones/Twos-and-Threes', variant='h1_quarter_read',
                                    signal_type='h1_quarter_read', high_quarter=hq, low_quarter=lq,
                                    quarter_signature=f'{hq}-{lq}'))
        # H1-close cluster order: parity 0 [sig, qr], parity 1 [qr, sig]
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
        h3_quad_ev = (quad_events[1][0], 21, quad_events[1][1], quad_events[1][2], quad_events[1][3], quad_events[1][4])
        # H3-open pair: parity 0 [3he@120, quad@121], parity 1 [quad@120, 3he@121]
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
        # H3 open pair at +120/+121: parity 0 [3he, quadrant], parity 1 [quadrant, 3he]
        he_ev = (i + 120, 25, 'Hour 3 just opened. What\'s the \'third-hour effect\' (3HE) — what should you watch for now?',
                 'Either the line extends OR the third-hour effect retraces toward the block-open / 9:30 area — depends on H1+H2 setup',
                 ['H3 always continues the H2 direction — no other outcome', 'H3 always reverses against H2 — that\'s what 3HE means',
                  'H3 has no diagnostic value once H2 closes'],
                 dict(base, source='RE-2026-02-20', variant='h3_open_3he_watch', signal_type='h3_open_3he_watch'))
        # the H3 quadrant is queued at +121 (its own slot)
        # queue.append(he_ev if parity == 0 else quad_ev) -- quad already queued above; handle ordering below
        queue.append(he_ev)
        # Q4 resolution (+165)
        queue.append((i + 165, 26, 'Q4 of H3 is starting. Based on the line/apex framework, how does Q4 typically resolve?',
                      'In a line: Q4 targets the opposite of Q1\'s extreme (fours-and-ones). In an apex: Q4 mean reverts toward the H3 midpoint.',
                      ['Q4 always extends past Q3\'s extreme regardless of classification', 'Q4 always closes flat — it is a \'doji quarter\'',
                       'Q4 has no predictable behavior — random'],
                      dict(base, source='Three-Hour-Line.md/Q1-plants-Q4-targets', variant='h3_q4_resolution_watch',
                           signal_type='h3_q4_resolution_watch')))
        # drawable + strong at +170/+171: parity 0 [drawable, strong], parity 1 [strong, drawable]
        drawable_ans = ('Yes — bullish line is drawable (progressive higher highs, no violations)' if prog_up else
                        'Yes — bearish line is drawable (progressive lower lows, no violations)' if prog_dn else
                        'No — structure broken; this is an apex')
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
        # final classification + 3HE resolution at +179/+180: parity 0 [final, 3he], parity 1 [3he, final]
        cls_ans = {'bullish_line': 'Bullish line', 'bearish_line': 'Bearish line',
                   'bullish_apex': 'Bullish apex', 'bearish_apex': 'Bearish apex',
                   'other': 'Other — does not match a clean line or apex'}[final_cls]
        final_ev = (i + 179, 28, f'Is this {bh}:00-{bh + 3}:00 three-hour block a Line or Apex? Bullish or bearish?',
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
        he_res_ev = (i + 180, 28, 'Block close. Did the third-hour effect play out as expected — extension away from block open, or retrace back to it?',
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
