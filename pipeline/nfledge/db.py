"""SQLite storage with ordered SQL migrations and an append-only prediction log."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .config import DB_PATH

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    migrate(con)
    return con


def migrate(con: sqlite3.Connection) -> list[str]:
    con.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    done = {r[0] for r in con.execute("SELECT name FROM schema_migrations")}
    applied = []
    for f in sorted(MIGRATIONS.glob("*.sql")):
        if f.name in done:
            continue
        con.executescript(f.read_text())
        con.execute("INSERT INTO schema_migrations(name) VALUES (?)", (f.name,))
        applied.append(f.name)
    con.commit()
    return applied


def log_run(con, run_id, model_version, season, week, sources, odds_source, weather_source):
    con.execute("INSERT OR IGNORE INTO runs VALUES (?,?,?,?,?,?,?)",
                (run_id, model_version, season, week, json.dumps(sources), odds_source, weather_source))


def log_game(con, run_id: str, rec: dict):
    con.execute("INSERT OR IGNORE INTO game_predictions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
        run_id, rec["game_id"], rec["kickoff_utc"], rec["home_team"], rec["away_team"], rec["p_home"],
        rec["exp_margin"], rec["exp_total"], rec.get("market_p_home"), rec.get("home_ml"), rec.get("away_ml"),
        rec.get("spread_line"), rec.get("total_line"), rec["confidence"], json.dumps(rec.get("info", {}))))


def log_td(con, run_id: str, rec: dict):
    con.execute("INSERT OR IGNORE INTO td_predictions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
        run_id, rec["game_id"], rec["player_id"], rec["player_name"], rec["team"], rec["position"],
        rec["p_anytime"], rec["lam_rush"], rec["lam_rec"], rec.get("status"), rec.get("market_odds"),
        rec["confidence"]))


def record_results(con, games_df, td_df=None):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    for r in games_df.itertuples(index=False):
        con.execute("INSERT OR IGNORE INTO game_results VALUES (?,?,?,?)",
                    (r.game_id, int(r.home_score), int(r.away_score), now))
    if td_df is not None:
        con.executemany("INSERT OR IGNORE INTO td_results VALUES (?,?,?,?)",
                        [(r.game_id, r.player_id, int(r.scored), int(r.played)) for r in td_df.itertuples(index=False)])


def last_pregame_games(con) -> list[dict]:
    """Latest prediction made before kickoff for every game, joined to its result."""
    q = """
    SELECT gp.*, r.run_id AS rid, gr.home_score, gr.away_score FROM game_predictions gp
    JOIN runs r ON r.run_id = gp.run_id
    LEFT JOIN game_results gr ON gr.game_id = gp.game_id
    WHERE gp.run_id < gp.kickoff_utc
      AND gp.run_id = (SELECT MAX(g2.run_id) FROM game_predictions g2 WHERE g2.game_id = gp.game_id AND g2.run_id < g2.kickoff_utc)
    """
    return [dict(r) for r in con.execute(q)]


def last_pregame_tds(con) -> list[dict]:
    q = """
    SELECT tp.*, gp.kickoff_utc, tr.scored, tr.played FROM td_predictions tp
    JOIN game_predictions gp ON gp.run_id = tp.run_id AND gp.game_id = tp.game_id
    LEFT JOIN td_results tr ON tr.game_id = tp.game_id AND tr.player_id = tp.player_id
    WHERE tp.run_id < gp.kickoff_utc
      AND tp.run_id = (SELECT MAX(t2.run_id) FROM td_predictions t2 JOIN game_predictions g2
                         ON g2.run_id = t2.run_id AND g2.game_id = t2.game_id
                       WHERE t2.game_id = tp.game_id AND t2.player_id = tp.player_id AND t2.run_id < g2.kickoff_utc)
    """
    return [dict(r) for r in con.execute(q)]


def history_for_game(con, game_id: str) -> list[dict]:
    q = "SELECT run_id, p_home, exp_margin, exp_total, market_p_home FROM game_predictions WHERE game_id=? ORDER BY run_id"
    return [dict(r) for r in con.execute(q, (game_id,))]
