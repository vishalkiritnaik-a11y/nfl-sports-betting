-- nfl-edge schema v1. Portable SQL (SQLite default; runs unchanged on PostgreSQL
-- except AUTOINCREMENT -> GENERATED ALWAYS AS IDENTITY).
-- Append-only prediction log: rows are never updated or deleted, so every
-- pre-kickoff projection (including losing ones) stays auditable.

CREATE TABLE IF NOT EXISTS runs (
    run_id          TEXT PRIMARY KEY,           -- ISO timestamp of the pipeline run
    model_version   TEXT NOT NULL,
    season          INTEGER NOT NULL,
    week            INTEGER NOT NULL,
    data_sources    TEXT NOT NULL,              -- JSON: file -> source_updated
    odds_source     TEXT NOT NULL,              -- 'nflverse-consensus' | 'the-odds-api' | 'none'
    weather_source  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS game_predictions (
    run_id          TEXT NOT NULL REFERENCES runs(run_id),
    game_id         TEXT NOT NULL,
    kickoff_utc     TEXT NOT NULL,
    home_team       TEXT NOT NULL,
    away_team       TEXT NOT NULL,
    p_home          REAL NOT NULL,              -- model, conditional on no tie
    exp_margin      REAL NOT NULL,              -- home perspective
    exp_total       REAL NOT NULL,
    market_p_home   REAL,                       -- margin-adjusted moneyline probability
    home_ml         REAL,
    away_ml         REAL,
    spread_line     REAL,
    total_line      REAL,
    confidence      TEXT NOT NULL,
    info            TEXT,                       -- JSON: scenario flags, top factors
    PRIMARY KEY (run_id, game_id)
);

CREATE TABLE IF NOT EXISTS td_predictions (
    run_id          TEXT NOT NULL REFERENCES runs(run_id),
    game_id         TEXT NOT NULL,
    player_id       TEXT NOT NULL,
    player_name     TEXT NOT NULL,
    team            TEXT NOT NULL,
    position        TEXT NOT NULL,
    p_anytime       REAL NOT NULL,
    lam_rush        REAL NOT NULL,
    lam_rec         REAL NOT NULL,
    status          TEXT,                       -- injury designation at prediction time
    market_odds     REAL,
    confidence      TEXT NOT NULL,
    PRIMARY KEY (run_id, game_id, player_id)
);

CREATE TABLE IF NOT EXISTS game_results (
    game_id         TEXT PRIMARY KEY,
    home_score      INTEGER NOT NULL,
    away_score      INTEGER NOT NULL,
    recorded_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS td_results (
    game_id         TEXT NOT NULL,
    player_id       TEXT NOT NULL,
    scored          INTEGER NOT NULL,           -- rushing or receiving TD
    played          INTEGER NOT NULL,           -- took >= 1 offensive snap
    PRIMARY KEY (game_id, player_id)
);

CREATE INDEX IF NOT EXISTS ix_gp_game ON game_predictions(game_id);
CREATE INDEX IF NOT EXISTS ix_tp_game ON td_predictions(game_id);
