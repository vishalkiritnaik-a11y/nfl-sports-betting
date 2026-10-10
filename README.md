# NFL Edge Board

A weekly NFL analytics dashboard that estimates **team win probabilities** and **anytime-touchdown probabilities**, compares them with market prices, explains every projection, and keeps an append-only record of its own pre-kickoff predictions.

It runs on **GitHub Pages + GitHub Actions**. A Python pipeline runs on a schedule, pulls public data, trains and evaluates the models, writes JSON for the dashboard, and commits the prediction log. A static React app reads the JSON. There's no server to run and nothing to pay for unless you add a paid odds plan.

> An analytical and educational tool, not betting advice. In walk-forward backtests the closing market was more accurate than this model, and flat-betting the model's "edges" at closing prices lost money. The dashboard shows both facts.

---

## What's live, what isn't

| Feature | Status | Source |
|---|---|---|
| Schedule, scores, rest days, stadium, roof, surface | **Live** | nflverse `schedules/games.csv` |
| Moneyline / spread / total (with prices) | **Live**, consensus line | nflverse schedule (lines collected by nflverse) |
| Multi-book best prices, live snapshots | Optional: set `ODDS_API_KEY` | The Odds API |
| Anytime-TD sportsbook odds, TD edge/EV | Optional: needs a paid odds plan + `ODDS_API_TD_PROPS=1` | The Odds API `player_anytime_td` |
| Play-by-play, EPA, success rate, red zone, pressure | **Live** | nflverse play-by-play |
| Official injury report + practice participation | **Live** | nflverse injuries |
| Snap counts, weekly rosters, depth charts | **Live** | nflverse (PFR / ESPN) |
| Play action, motion, blitz, box counts | **Live** | FTN charting via nflverse |
| Weather forecasts at kickoff + ensemble range | **Live** (in Actions) | Open-Meteo forecast + GFS ensemble |
| Man/zone coverage, single-high vs two-high, route participation, personnel | **Unavailable** (licensed data). Shown as unavailable, never inferred | — |
| Historical anytime-TD odds (to backtest TD betting) | **Unavailable** | — |

Nothing is filled in by hand. When a source is missing, the UI says so.

---

## Repository layout

```
pipeline/                    Python package `nfledge`
  nfledge/ingest/            nflverse downloads (+Last-Modified freshness), Open-Meteo, The Odds API
  nfledge/features.py        team-game stats from play-by-play, leak-free blended ratings, travel/rest context
  nfledge/models/elo.py      margin-aware Elo baseline
  nfledge/models/game_model.py   ridge margin + logistic winner + ridge total, contributions, distributions
  nfledge/models/td_model.py     opportunity x rate anytime-TD model with calibration layer
  nfledge/matchups.py        measured scheme tendencies (offense vs defense)
  nfledge/odds.py            implied probability, vig removal, EV (fully unit tested)
  nfledge/evaluate.py        backtests, calibration, market comparison, betting simulation, prospective log
  nfledge/db.py + migrations/   SQLite schema (portable SQL), append-only prediction log
  nfledge/build.py           end-to-end orchestration -> web/public/data/*.json
  tests/                     pytest: odds math, EV, Elo, TD model, storage, API failure handling
web/                         Vite + React + TypeScript + Tailwind + Recharts dashboard (HashRouter for Pages)
data/nfledge.sqlite          prediction log, committed by the workflow
.github/workflows/refresh.yml   scheduled pipeline + Pages deploy
docs/DATA_CONTRACTS.md       JSON contracts between pipeline and UI
```

## Deploy (GitHub Pages)

1. Create a new GitHub repository and push this folder to `main`.
2. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
3. **Settings → Actions → General → Workflow permissions: Read and write.** The workflow commits `data/nfledge.sqlite`.
4. Optional, **Settings → Secrets and variables → Actions**:
   - Secret `ODDS_API_KEY`: from https://the-odds-api.com (free tier is enough for moneyline/spread/total, ~3 credits per run).
   - Variables `ODDS_API_TD_PROPS=1` (paid plan), `ODDS_API_REGIONS`, `NFLEDGE_MIN_EDGE_PP`.
5. **Actions → Refresh data and deploy → Run workflow.** The first run takes ~10 minutes because it downloads 2016+ play-by-play and builds the TD training rows. Later runs reuse the cache and take ~3–4 minutes.

The schedule refreshes daily, after Wednesday–Friday practice reports, Friday evening (final game statuses), ~90 minutes before Sunday 1pm kickoffs (inactives), and before late and night games. Edit the cron lines in `refresh.yml` to change it.

API keys only exist inside GitHub Actions. The browser receives finished JSON and never sees a key.

## Run locally

```bash
# pipeline (Python 3.11+)
cd pipeline
pip install -r requirements.txt
python -m pytest -q tests
python -m nfledge.build              # add --no-weather offline, --rebuild to rebuild cached TD rows
# dashboard
cd ../web
npm ci
npx vitest run
npm run dev                           # http://localhost:5173
npm run build                         # static site in web/dist
```

Environment variables are documented in `.env.example`.

## Database

SQLite at `data/nfledge.sqlite`, created and migrated automatically (`pipeline/migrations/*.sql`, tracked in `schema_migrations`). Tables:

- `runs`: one row per pipeline run (model version, source timestamps, odds/weather source)
- `game_predictions`, `td_predictions`: every pre-kickoff projection, **insert-only**
- `game_results`, `td_results`: outcomes recorded after games

The track-record page grades the **last prediction made before kickoff** for each game and player, including the losing ones. The SQL is portable. To move to PostgreSQL, point a connection at the same migrations and change `AUTOINCREMENT` if you add identity columns.

## Models (short version; full detail on the "Data & method" page)

**Game model.** Leak-free features computed only from games before kickoff: Elo, opponent-adjusted EPA/success matchups (pass/rush split), special teams, turnovers, pressure, red zone, starting-QB EPA per dropback (decayed, shrunk to replacement level), rest, travel, time zones, altitude, division games. Ratings blend this season with last season so small samples don't dominate. A ridge regression predicts margin, which is converted to win probability with a normal distribution (σ ≈ 13). A logistic regression predicts the winner. The published probability averages the two, and their disagreement lowers confidence. A separate ridge model predicts the total, using observed wind and cold at outdoor venues historically and the forecast for upcoming games. Ties are excluded, so probabilities are conditional on a decisive result.

**Anytime-TD model.** Opportunities × rates, not TD totals. Team opportunities by zone (carries inside 5, 6–10, 11–20, outside 20; end-zone, red-zone and other targets) come from projected team points and game script. They're multiplied by hierarchically shrunk player shares, the league TD rate per opportunity, and shrunk finishing and opponent multipliers. Rushing and receiving intensities add, since each play has one ball carrier or target. A calibration layer fit on later seasons maps intensity to P(≥1 TD). Ruled-out players' shares are redistributed to teammates. Questionable and doubtful players get both scenarios.

**Validation (walk-forward, retrain each season on earlier seasons only):**

| | Log loss | Brier | Winners |
|---|---|---|---|
| Game model 2021–26 | 0.632 | 0.221 | 64.4% |
| Elo baseline | 0.640 | 0.224 | 63.3% |
| Closing market (no-vig) | **0.613** | **0.213** | 66.4% |
| TD model 2022–26 (29k player-games) | 0.395 (base rate 0.446) | 0.122 | AUC 0.74 |

TD probabilities are well calibrated by position (see the Track record page). Flat-betting model edges ≥ 3 pts at closing consensus prices returned about −5% on moneylines, −5% on spreads and −2% on totals. That is the honest baseline any future improvement has to beat.

## Tests

- `pipeline/tests/test_odds.py`: American→implied (+A and −A formulas), decimal conversion, vig removal (proportional and power), EV `p(D−1)−(1−p)`, break-even, value threshold, scoring rules.
- `pipeline/tests/test_models.py`: Elo is leak-free and zero-sum, TD share redistribution, no double counting across pathways, first-TD < anytime, calibration output, migrations + append-only log grading, Eastern kickoff conversion, weather API failure → "unavailable", odds API disabled without a key.
- `web/src/lib/odds.test.ts`: the same odds math on the client (used for the live threshold slider).

## Roadmap

1. **Odds history.** Snapshot The Odds API lines every run into a new `odds_snapshots` table, so the dashboard can show line movement and closing-line value for logged predictions.
2. **Anytime-TD market backtest.** Once a season of TD prices is logged, evaluate TD edge and ROI prospectively.
3. **Weekly walk-forward backtests.** Backtests currently retrain once per season; the live model already refits on every completed game each run.
4. **Licensed charting** (coverage shells, route participation) behind optional keys, feeding the matchup table and TD target shares.
5. **More team-level injury effects.** Quantify OL/CB absences from historical with/without splits, as was done for QBs.
6. **Player props beyond anytime TD** (yards, receptions) reusing the opportunity model.
7. **Optional FastAPI + Postgres backend** if the dashboard needs on-demand recomputation (the pipeline modules are already separated for this).
