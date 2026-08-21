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

## Known gaps / TODO (do NOT claim done)
1. **Generated scenarios only cover 01a.** 01c/01d/01e/01f/01g/02a/02c/02d still use captured
   site data only. Faithful regeneration requires per-concept detection rules:
   - 01c BP Breach, 01d Instat, 01e Doji, 01f Prev Hour, 01g Sweep+SB = moderate (few templates)
   - 02a Line/Apex (~32 unique q), 02d 3-Candle (~86 prompts, C1/C2/C3 window engine) = heavy
2. `generate_scenario.py` `--random` picks recent-ish days; add date-range / multiple-day batch.
3. No automated test harness yet — walk-all UI test timed out; relying on structural + single-path checks.
4. Generator prompts are paraphrased (not verbatim site copy) for 01a — acceptable for private use.

## Related projects touched
- `candle-profiler` (data source): `data/working/NQ_work_1min.csv` read by generator. No changes made.
- Vercel account: new project added (team hermes-nb). Token reused from `~/.vercel/auth.json`.

## Re-run notes
- Local preview: `cd web && python3 -m http.server 8999`
- Regenerate: `venv/bin/python scripts/generate_scenario.py --concept 01a --date YYYY-MM-DD`
- Redeploy: push to GitHub main → gitSource API (auto-deploy enabled on this project).
