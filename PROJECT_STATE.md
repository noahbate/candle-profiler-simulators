# Cross-Project Log — candle-profiler-simulators

**Date:** 2026-08-21
**Author:** Hermes Agent (Noah Bate direction)

## What shipped

Private clone of the Daily Profiler Bootcamp "Practice Builder" simulators, reverse-engineered and deployed.

### Reverse-engineering result
- Endpoint `GET /api/simulators/assemble?concepts=<id>&focus=full` returns the full scenario as JSON:
  `scenario.dataset.data` (1,020–1,380 NQ 1-min OHLC bars), `scenario.prompts[]` (uniform
  `multiple_choice` schema: `triggerCandle, type, questionText, answerOptions[], correctAnswer,
  explanation, points, conceptTag`), `scenario.dataPointMarkers[]` (box levels, thresholds),
  `scenario.passingScore` = 70, `mode` = "IDENTIFY". No server-side game state.
- All 9 live concepts captured to `reference/assemble/*.json` (private, local only).

### Built (in `~/projects/candle-profiler-simulators/`)
- `web/` — static player: `index.html` catalog, `play.html`, `assets/{styles.css,app.js,player.js}`,
  `scenarios/*.json` (9 captured + 1 generated). Vanilla canvas candle renderer with box/threshold
  overlays, triggerCandle prompt walker, Space/Play controls, scoring vs passingScore.
- `scripts/generate_scenario.py` — **01a (Box Breakout) fully implemented**: hourly 0-5 box, 0.05%
  ETH threshold, breach→momentum / suckback→false-box detection, schema-identical output.
  Other concepts scaffolded (template prompts), NOT yet faithful (esp. 02a/02d need bespoke engines).

### Deploy
- GitHub: `noahbate/candle-profiler-simulators` — **made PUBLIC** (so API can resolve repoId).
- Vercel project `prj_4kifFzmcv0COqAustDDSYhIUb87c`, team `hermes-nb`, rootDir `web`.
- **SSO protection disabled** (Vercel default-on blocks .json). Private clone, openly accessible.
- **Live:** https://candle-profiler-simulators-hermes-nb.vercel.app/
  - Verified: index 200, 01a scenario 30 prompts, gen scenario 25 prompts, play page prompt fires.

## Generator fidelity (validated against captured site payloads)

Reverse-engineered each concept's detection logic by diffing generated output vs the captured
`reference/assemble/*.json` on the SAME trading day the site used. "Exact bar+answer" = generated
trigger bar's timestamp matches a capture event's timestamp AND the correctAnswer string matches
(by timestamp, since capture windows are offset from the generator's 18:00-ET session start).

| Concept | Box/anchor | Trigger rule | Verified fidelity | Status |
|---------|-----------|--------------|------------------|--------|
| **01a** Box Breakout | first 5 min (exact) | breach = wick beyond box×1±0.05%; `momentum_breakout` if holds, `false_05_box` if suck back to 50% + hold 2 bars | **19/19 exact bar+answer** on captured day | ✓ verified |
| **01c** BP Breach | first 5 min | two-stage: 0.05% breach (reject/anticipate) + 0.10% breach (momentum) | **30/30 exact bar+answer** on captured day | ✓ verified |
| **01d** Instat | Q1/Q2 = first 30 min | first Q2 bar taking Q1 high→bull / low→bear; single-side | **14/14 exact bar+answer**; 1 ambiguous double-break hour skipped | ✓ verified |
| **01e** Doji | Q1/Q2/Q3 quarters | Q3 takes Q2 opposite extreme → doji; price = Q2 extreme | **7/7 exact bar+answer** (bit-for-bit incl. price text) | ✓ verified |
| **01f** Prev Hour | prev hour 50% + wick zone | mid_touch (reclaim across 50% vs open side); footprint_test (sweep wick zone + reclaim) | mid_touch exact; **footprint_test 4/7** (sweep threshold strict) | ~ verified |
| **01g** Sweep+SB | prev hour low/high + mid | sweep prev low/high → suckback → break prev mid in Q2+ → manipulation | **4/4 exact bar+answer** on captured day | ✓ verified |

### 01a — curriculum-confirmed
- Source: vault `Pack BootCamp 05 Box Hourly Quarters.md` + `Wk5 Hourly 05 Box.md`.
- Box = 00–05 min; ETH threshold = box × (1±0.05%); `momentum_breakout` at first wick beyond
  threshold that holds; `false_05_box` at the suckback (close back to 50% level, hold 2 bars).
- The "time component" = the suckback must find footing over time (not an immediate wick-back).

### 01c — two-stage BP breach
- Box 0–05; 0.05% breach fires `reject` (no 0.10% reached) or `anticipate continuation` (0.10% reached);
  a SEPARATE 0.10% breach event fires `momentum confirmed` at the 0.10% bar.

### 01f — prev hour 50% + footprint
- mid_touch: open on one side of prev 50%, first Q2+ reclaim across it (bullish if above, bearish if below).
- footprint_test: sweep of prev hour low (or high) in Q1, then Q2+ reclaim of prev 50% → rejection
  (bullish if swept low, bearish if swept high). Generator's sweep gate is slightly strict (4/7 detected).

### 01g — sweep + suckback + break
- Sweep prev hour low → suckback into range → Q2+ break of prev 50% = bullish manipulation.
  Sweep prev high → bearish. Exact on the captured day.

## Known gaps / TODO
1. **01f footprint_test** fires 4/7 of capture events (sweep threshold stricter than site's wick-zone test).
2. **02a/02c/02d** still captured-only (no generator). 02a (32 unique Qs) and 02d (86 prompts,
   3-candle C1/C2/C3 engine) are heavy bespoke work.
3. Date convention: `--date` = start evening (18:00 ET) of the session. Capture labels for 01f/01g
   are the RTH day, so pass label−1 (e.g. 01f RTH 2024-03-18 → `--date 2024-03-17`).

## Related projects touched
- `candle-profiler` (data source): `data/working/NQ_work_1min.csv` read by generator. No changes made.
- Vercel account: new project added (team hermes-nb). Token reused from `~/.vercel/auth.json`.

## Re-run notes
- Local preview: `cd web && python3 -m http.server 8999`
- Regenerate: `venv/bin/python scripts/generate_scenario.py --concept 01a --date YYYY-MM-DD`
- Redeploy: push to GitHub main → gitSource API (auto-deploy enabled on this project).
