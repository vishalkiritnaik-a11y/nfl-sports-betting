# Data contracts

The pipeline writes static JSON to `web/public/data/`. TypeScript definitions live in `web/src/types.ts`, which is the source of truth for field names. All probabilities are 0–1, all edges are percentage points, and all timestamps are UTC ISO-8601 (`YYYY-MM-DDTHH:MM:SSZ`).

## `meta.json`
`generated`, `season`, `current_week`, `model_version`, `weeks[]` (`season, week, file, games, kind: current|past|lookahead, label`),
`teams{abbr: name, colours, logo}`, `default_min_edge_pp`, `odds_source` (`nflverse-consensus` | `the-odds-api`), `odds_error`,
`td_market_available`, `weather_enabled`, `sources[]` (`file, url, source_updated, fetched`), `features.live[]`, `features.unavailable[]`,
`methodology.game` (training span, sigmas, coefficients), `methodology.td` (rates per opportunity, calibration coefficients, team-opportunity model).

## `weeks/{season}_{week}.json`
`games[]`:
- identity and timing: `game_id, season, week, game_type, gameday, weekday, gametime_et, kickoff_utc, location, div_game, venue{stadium, surface, roof, roof_type, lat, lon, elevation_m}`
- `home`/`away`: `team, record (entering), elo, qb{id,name,epa_db,dropbacks,changed}, rest_days, travel_km, tz_shift`; for full records also `season{}` (raw season-to-date), `blended{}` (model inputs), `form{last3,last5,last10}`, `injuries[]`
- `prediction`: `p_home, p_away` (sum to 1, ties excluded), `p_margin_model, p_logit_model, elo_prob, exp_margin` (home perspective), `exp_total, home_pts, away_pts, distribution{margin_hist[], margin_p10_p90, total_p10_p90, p_home_cover, p_over}, contributions[]` (points of margin; sum + `baseline_margin` = `exp_margin`), `total_contributions[], trained_on, backtest`
- `market`: lines + `home_raw_implied, home_no_vig, overround, source, snapshot`. nflverse convention: `spread_line` is the expected **home margin** (positive = home favoured).
- `values[]`: per selection `model_p, odds, decimal, raw_implied, no_vig, edge_pp` (vs no-vig), `edge_vs_raw_pp, ev_per_unit, roi_pct`
- `confidence{label, score, reasons[]}`, `factors{home[], away[], risks[]}`, `scenarios[]`, `weather{status: forecast|observed|indoor|unavailable|beyond_forecast_range, ...}`, `h2h[]`, `matchups{home_off[], away_off[], unavailable[]}`, `history[]` (logged runs), `result{}` when final, `td_ruled_out[]`

`td[]`: `player_id, name, team, opp, position, game_id, status, p` (uncertain players active), `p_if_uncertain_out` (null = player sits),
`lam_rush, lam_rec, p_first_td_approx, exp_opps{zone}, shares{}, usage{}, season{}, recent{last3,last5,last10, inside-5/10 carries, RZ/EZ targets}`,
`snap_pct_last3[], opp_vs_pos{td_pg, rank}, finishing_mult, opp_mult{rush,rec}, team_exp_points, team_exp_margin, confidence{}, why, market{}`.
Backtest rows carry `backtest: true` and `scored`.

## `performance.json`
`game{overall, by_season[], current_season_by_week[], segments[], calibration[] (with 90% Wilson intervals), MAE vs market, betting[] (simulated at closing prices)}`,
`td{overall, calibration[], by_position[], by_season[], top_picks[]}`, `prospective{games_logged, games_graded, game_scores, market_scores, td_scores, recent[]}`.
