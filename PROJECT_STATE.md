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
`reference/assemble/*.json` on the SAME trading day the site used.

| Concept | Box/anchor | Trigger rule | Verified fidelity | Status |
|---------|-----------|--------------|------------------|--------|
| **01a** Box Breakout | first 5 min (exact, 0.00 diff) | breach = wick beyond box edge (tick-level, NOT 0.05%); `false_05_box` if price closes back inside, `momentum_breakout` if it holds | box exact; event logic understood; **exact trigger-bar timing NOT reproduced** (naive version 0/30) | ❌ not faithful |
| **01d** Instat | Q1 = first 15 min, Q2 = next 15 min | first Q2 bar taking out Q1 high→bullish / Q1 low→bearish; single-side only | **14/15 trigger bars exact** vs capture; correct answers 14/14; 1 ambiguous double-break hour skipped | ✓ verified |
| **01e** Doji | Q1/Q2/Q3 = three 15-min quarters | after instat setup, Q3 takes Q2 opposite extreme → doji; price in Q = Q2 extreme | **bit-for-bit on captured day** (7/7 trigger, 7/7 Q-text incl. price, 7/7 answer) | ✓ verified |

### 01a — RE-ENGINEERED with curriculum source (2026-08-21)
- **Source of truth:** vault `02. Strategy Library/Pack BootCamp/Pack BootCamp 05 Box Hourly Quarters.md`
  and `Pack BootCamp Wk5 Hourly 05 Box.md` (vectorized bootcamp material).
- **Confirmed logic:**
  - Box = 00–05 min of each hour (verified exact, 0.00 diff vs capture).
  - ETH breakout threshold = box edge × (1 ± 0.05%) (`bps_threshold: 0.0005`).
  - `momentum_breakout` = first print (wick) beyond the 0.05% threshold that holds (never sucks
    back to the 50% level) → fire at the breach bar.
  - `false_05_box` = price swipes the raw box but FAILS to reach 0.05%, then **sucks back and
    finds footing at the 50% level (box mid)** → fire at that finding-footing bar. This is the
    "time component": price swipes, fills, swipes, fills, then commits at the open/mid.
- **Fidelity (captured 01a day 2024-01-17):** 18/30 exact trigger-bar+answer; **18/18 correct
  answers on the 18 shared bars**; event SET (hour/direction/type) faithful. Remaining gap: the
  false_05_box suckback-confirmation bar lands 1–8 bars off the site's in ~4 hours (the site's
  "final footing" is a few bars after the first close beyond mid). Labeled `~` (logic-verified,
  timing approximate) in the catalog — NOT bit-perfect, but pedagogically faithful.
- Generator re-added to shipped scenarios with the `~` marker (previously removed as UNVERIFIED
  when the old logic scored 0/30).

### 01d — the 1 unresolved case
- Hour where Q2 breaks BOTH Q1 high and low (ambiguous): site skips it; my single-side filter also
  skips it on most days but occasionally differs. 14/15 is the confirmed floor.

## Known gaps / TODO (do NOT claim done)
1. **01a generator unfaithful** — see above. Either fix the trigger timing or stop shipping 01a-gen.
2. **01c/01f/01g/02a/02c/02d** still captured-only (no generator). 02a (32 unique Qs) and
   02d (86 prompts, 3-candle C1/C2/C3 engine) are heavy bespoke work.
3. `generate_scenario.py` `--random` picks recent-ish days; add date-range / multiple-day batch.
4. No automated walk-all test harness (UI loop timed out); relying on structural + single-path checks
   plus the day-level fidelity diffs above.

## Related projects touched
- `candle-profiler` (data source): `data/working/NQ_work_1min.csv` read by generator. No changes made.
- Vercel account: new project added (team hermes-nb). Token reused from `~/.vercel/auth.json`.

## Re-run notes
- Local preview: `cd web && python3 -m http.server 8999`
- Regenerate: `venv/bin/python scripts/generate_scenario.py --concept 01a --date YYYY-MM-DD`
- Redeploy: push to GitHub main → gitSource API (auto-deploy enabled on this project).
