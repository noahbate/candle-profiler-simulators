# Bootcamp Simulators — Reverse-Engineering & Clone Plan

> **Goal:** Clone the Daily Profiler Bootcamp "Practice Builder" simulators as our own
> add-on to the candle-profiler dashboard (local first → GitHub → Vercel when release-ready).

**Captured:** 2026-08-21 · Authenticated CDP session (hermes Chrome, logged in as noahbate@gmail.com)

---

## What the product actually is (verified, not guessed)

The "simulator" is a **runtime-assembled quiz-over-candles player**:

1. `GET /practice/api/simulators` *(auth* — catalog listing, or the page itself)
2. `GET /api/simulators/assemble?concepts=<id>&focus=full` → **one big JSON per session**:
   - `scenario.dataset.data` — **1,380 one-minute NQ OHLC bars** (full Globex day 18:00→17:00)
   - `scenario.dataset.hourlyTPData`, `indicators` (server-computed extras)
   - `scenario.prompts[]` — MC quiz pinned to candle indices:
     `{triggerCandle, type:"multiple_choice", questionText, answerOptions[], correctAnswer, explanation, points, conceptTag}`
   - `scenario.dataPointMarkers[]` — chart pins at each triggerCandle
   - `scenario.passingScore` = 70, `mode` = "IDENTIFY"
3. Player UI: candle chart (vendor charts lib), time-strip (18:00–16:00), "Begin Exercise / Press Space",
   steps through bars; at each `triggerCandle` the prompt renders. Random start (~bar 760/1380) but concept questions reference absolute bars.

**No server-side game state.** The assemble JSON is the whole exercise. Questions/answers ship to the client
in plaintext (answers are IN the payload — client-side grading, honor system).

## The 9 live concepts (captured to `reference/assemble/*.json`)

| ID  | Name | Bars | Prompts |
|-----|------|------|---------|
| 01a | Box Breakout | 1380 | 30 |
| 01c | BP Breach | 1380 | 33 |
| 01d | Instat | 1380 | 15 |
| 01e | Doji | 1380 | 7 |
| 01f | Prev Hour | 1020 | 13 |
| 01g | Sweep+SB | 1020 | 4 |
| 02a | Line/Apex (Framework) | 1380 | 52 |
| 02c | Rolling 3H Structure | 1380 | 19 |
| 02d | 3H Probability Flags | 1380 | 86 |

Coming soon on site: 04 Daily Class, 05a 4-Step Rev (locked).

## Clone architecture

Static, matches candle-profiler-dashboard (vanilla or minimal JS, no build step):

```
candle-profiler-simulators/
├── reference/assemble/*.json      # frozen site captures (source of truth)
├── scenarios/                     # our generated scenarios (same schema)
├── scripts/
│   └── generate_scenario.py       # build scenario JSON from candle-profiler data
├── web/
│   ├── index.html                 # catalog (concept picker)
│   ├── play.html                  # chart player + prompt walker
│   └── assets/{app.js, chart.js, styles.css}
```

### Phase 1 — Local player against captured JSON (this week's win)
- [ ] Chart renderer: canvas candles + pan/zoom (no deps, ~200 lines) — or lightweight-charts CDN
- [ ] Player: start-at-random-bar, Space to begin, walk bars, pop prompt at triggerCandle, grade, final score vs passingScore
- [ ] Catalog page listing 9 concepts from the local JSONs
- [ ] Smoke-test manually; screenshot desktop

### Phase 2 — Scenario generator (the actual clone value)
Generate fresh scenarios from OUR data (`data/working/NQ_work_1min.csv`):
- [ ] Port prompt *templates* per concept tag (question text patterns are fixed per concept — extract recurring ones)
- [ ] Compute triggerCandles from our profiler engine events (box breach, sweep, apex, etc.)
- [ ] Emit schema-identical JSON → drops into Phase 1 player unchanged
- [ ] For concept detection rules we're unsure of: mark TODO + fall back to curated days

### Phase 3 — Ship
- [ ] GitHub repo (private first), gitSource deploy to Vercel (never `vercel deploy` CLI)
- [ ] Add as sub-path / link from candle-profiler-dashboard
- [ ] PROJECT_STATE.md entries (cross-project log rule)

## Flaws / risks in this plan (the review pass)

1. **IP** — these are (c) TDP curriculum questions. Clone the *engine*, don't redistribute their
   question text on a public site. Phase 2 must use our own question wording; reference JSONs stay local/private repo.
2. **hourlyTPData/indicators** — haven't decoded yet; may be needed for correct chart overlays (boxes, hour lines). Check payload fields before Phase 2 scoping.
3. **focus param** — `focus=full` seen; site may support others (random/weak-spots?). Probe before finalizing generator API.
4. **Random start offset** — prompts reference absolute candle indices; verify whether prompts before offset are skipped or shifted. Reproduce faithfully.
5. **Grading** — verify their scoring (points sum, 70% pass) client-side; match.

## Verification gates

- G1: our player renders 01a capture, all 30 prompts fire, score computes.
- G2: generated scenario passes through the same player with zero code changes.
- G3: page loads < 2s from Vercel; no engine/CSV leaks (scenario JSONs only).

---
*Next action: Phase 1 player scaffold.*
