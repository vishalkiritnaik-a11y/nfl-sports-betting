"""Tests for model building blocks, storage and API-failure handling (no network)."""
import math
import sqlite3
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from nfledge import db as DB
from nfledge.ingest import weather as W
from nfledge.models import elo
from nfledge.models import td_model as TD


# ------------------------------------------------------------------ elo
def test_elo_expected_symmetric():
    assert abs(elo.expected(0) - 0.5) < 1e-12
    assert abs(elo.expected(100) + elo.expected(-100) - 1) < 1e-12


def test_elo_updates_are_zero_sum_and_leak_free():
    g = pd.DataFrame({
        "game_id": ["a", "b"], "season": [2020, 2020], "gameday": ["2020-09-10", "2020-09-17"],
        "home_team": ["X", "X"], "away_team": ["Y", "Y"], "home_score": [30, np.nan], "away_score": [10, np.nan],
        "location": ["Home", "Home"]})
    pre, now = elo.run(g)
    assert pre.loc[0, "home_elo"] == pre.loc[0, "away_elo"] == elo.MEAN      # pre-game rating unaffected by own result
    assert pre.loc[1, "home_elo"] > pre.loc[1, "away_elo"]                    # second game sees the first result
    assert abs((now["X"] - elo.MEAN) + (now["Y"] - elo.MEAN)) < 1e-9


# ------------------------------------------------------------------ TD model
def _cand(pid, **sh):
    base = {f"sh_{z}": 0.0 for z in TD.ALL_ZONES}
    base.update({f"sh_{k}": v for k, v in sh.items()})
    return {"player_id": pid, **base}


def test_renormalize_redistributes_shares_of_unavailable_players():
    rows = [_cand("rb1", c_i5=0.6, c_out=0.6), _cand("rb2", c_i5=0.3, c_out=0.3), _cand("wr", t_out=0.5)]
    TD.renormalize(rows, {"rb2", "wr"})
    assert rows[0]["adj_c_i5"] == 0.0
    assert abs(rows[1]["adj_c_i5"] - 0.9) < 1e-9            # absorbs rb1's share, capped at team total
    assert abs(rows[2]["adj_t_out"] - 0.5) < 1e-9


def test_lambdas_add_rush_and_receiving_without_double_count():
    rates = {z: 0.1 for z in TD.ALL_ZONES}
    team = {z: 10.0 for z in TD.ALL_ZONES}
    c = _cand("p", c_i5=0.5, t_ez=0.2)
    lr, lc, eo = TD.TDModel.lambdas(c, team, rates, 1.0, 1.0, 1.0, prefix="sh_")
    assert abs(lr - 0.5) < 1e-9 and abs(lc - 0.2) < 1e-9
    assert abs(TD.raw_poisson_p(lr, lc) - (1 - math.exp(-0.7))) < 1e-12


def test_first_td_less_than_anytime():
    lams = [0.8, 0.5, 0.3, 0.1]
    ft = TD.first_td_approx(lams)
    assert abs(sum(ft) - 0.985) < 1e-9
    assert all(f < TD.raw_poisson_p(l, 0) for f, l in zip(ft, lams))


def test_td_calibration_outputs_probabilities():
    rng = np.random.default_rng(0)
    n = 2000
    lam = rng.uniform(0.01, 1.0, n)
    df = pd.DataFrame({"lam_rush": lam * 0.6, "lam_rec": lam * 0.4, "position": rng.choice(TD.POSITIONS, n),
                       "games": rng.integers(0, 12, n)})
    df["y"] = (rng.uniform(size=n) < 1 - np.exp(-lam)).astype(int)
    m = TD.TDModel().fit_calibration(df)
    p = m.prob(df)
    assert ((p > 0) & (p < 1)).all()
    assert np.corrcoef(p, lam)[0, 1] > 0.8


# ------------------------------------------------------------------ storage
def test_migrations_and_append_only_log(tmp_path):
    con = DB.connect(tmp_path / "t.sqlite")
    assert DB.migrate(con) == []                                           # idempotent
    DB.log_run(con, "2026-10-01T00:00:00Z", "v", 2026, 5, {}, "x", "y")
    DB.log_run(con, "2026-10-02T00:00:00Z", "v", 2026, 5, {}, "x", "y")
    rec = {"game_id": "g1", "kickoff_utc": "2026-10-03T17:00:00Z", "home_team": "A", "away_team": "B",
           "p_home": 0.6, "exp_margin": 3, "exp_total": 44, "confidence": "Medium"}
    DB.log_game(con, "2026-10-01T00:00:00Z", rec)
    DB.log_game(con, "2026-10-02T00:00:00Z", {**rec, "p_home": 0.55})
    DB.log_game(con, "2026-10-04T00:00:00Z", {**rec, "p_home": 0.99})    # after kickoff: never graded
    DB.record_results(con, pd.DataFrame({"game_id": ["g1"], "home_score": [20], "away_score": [17]}))
    last = DB.last_pregame_games(con)
    assert len(last) == 1 and last[0]["p_home"] == 0.55 and last[0]["home_score"] == 20
    assert len(DB.history_for_game(con, "g1")) == 3


# ------------------------------------------------------------------ weather / API failures
def test_kickoff_times_are_eastern():
    ko = W.kickoff_utc("2026-10-11", "13:00")
    assert ko.hour == 17 and ko.tzinfo == timezone.utc               # EDT = UTC-4
    assert W.kickoff_utc("2026-12-06", "13:00").hour == 18           # EST = UTC-5


def test_weather_failure_reports_unavailable(monkeypatch):
    import requests

    def boom(*a, **k):
        raise requests.ConnectionError("no route")
    monkeypatch.setattr(W.requests, "get", boom)
    monkeypatch.setattr(W.time, "sleep", lambda s: None)
    now = datetime(2026, 10, 9, tzinfo=timezone.utc)
    out = W.forecast(40.0, -74.0, datetime(2026, 10, 11, 17, tzinfo=timezone.utc), now)
    assert out["status"] == "unavailable"
    far = W.forecast(40.0, -74.0, datetime(2026, 12, 1, tzinfo=timezone.utc), now)
    assert far["status"] == "beyond_forecast_range"


def test_weather_parses_game_window(monkeypatch):
    times = [f"2026-10-11T{h:02d}:00" for h in range(24)]
    payload = {"hourly": {"time": times, "temperature_2m": [50] * 24, "relative_humidity_2m": [60] * 24,
                          "precipitation_probability": [0] * 17 + [70] + [0] * 6, "precipitation": [0.0] * 24,
                          "snowfall": [0.0] * 24, "wind_speed_10m": [5] * 18 + [22] + [5] * 5,
                          "wind_gusts_10m": [9] * 24, "weather_code": [1] * 24}}

    class R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return payload
    monkeypatch.setattr(W.requests, "get", lambda *a, **k: R())
    monkeypatch.setattr(W, "_ensemble", lambda *a: {})
    out = W.forecast(40, -74, datetime(2026, 10, 11, 17, tzinfo=timezone.utc), datetime(2026, 10, 10, tzinfo=timezone.utc))
    assert out["status"] == "forecast"
    assert out["wind_mph"] == 22 and out["precip_prob_pct"] == 70   # max over kickoff + 3h window


def test_odds_api_disabled_without_key(monkeypatch):
    from nfledge.ingest import odds_api
    monkeypatch.setattr(odds_api, "ODDS_API_KEY", "")
    assert odds_api.enabled() is False
    assert odds_api.game_odds() == {}


# ------------------------------------------------------------------ confidence tiers
def test_tiers_follow_probability_and_downgrade_on_risk():
    from nfledge import tiers as TR
    assert TR.assess(0.10, TR.TD_CUTS, None, [])["label"] == "Low"        # low chance is never High
    assert TR.assess(0.35, TR.TD_CUTS, None, [])["label"] == "Medium"
    assert TR.assess(0.50, TR.TD_CUTS, None, [])["label"] == "High"
    a = TR.assess(0.50, TR.TD_CUTS, None, ["listed Questionable"])
    assert a["label"] == "Medium" and a["base"] == "High"
    assert TR.assess(0.20, TR.TD_CUTS, None, ["x"])["label"] == "Low"     # floor
    assert TR.assess(0.72, TR.GAME_CUTS, None, [])["label"] == "High"


def test_tier_stats_hit_rates():
    from nfledge import tiers as TR
    p = np.array([0.05, 0.1, 0.35, 0.4, 0.5, 0.6])
    y = np.array([0, 0, 1, 0, 1, 1])
    st = TR.tier_stats(p, y, TR.TD_CUTS)
    assert st["Low"]["n"] == 2 and st["Low"]["hit"] == 0
    assert st["Medium"]["hit"] == 0.5 and st["High"]["hit"] == 1.0


def test_td_score_out_of_ten():
    from nfledge import tiers as TR
    assert TR.td_score(0.0) == 1 and TR.td_score(0.059) == 1 and TR.td_score(0.06) == 2
    assert TR.td_score(0.50) == 9 and TR.td_score(0.95) == 10
    a = TR.assess_td(0.55, None, None, ["listed Questionable"])
    assert a["base_score"] == 10 and a["score"] == 9 and a["label"] == "High"
    b = TR.assess_td(0.50, None, None, ["listed Questionable", "QB uncertain"])
    assert b["score"] == 7 and b["label"] == "Medium"
    assert TR.assess_td(0.02, None, None, ["x"])["score"] == 1


# ------------------------------------------------------------------ pre-kickoff gate
def test_gate_fires_once_about_an_hour_before_kickoff():
    from nfledge import gate as G
    csvtext = ("game_id,gameday,gametime,home_score\n"
               "g1,2026-10-11,13:00,\n"           # 17:00Z
               "g2,2026-10-11,13:00,\n"
               "g3,2026-10-11,16:25,\n"           # 20:25Z
               "g0,2026-10-08,20:15,24\n")        # already played
    t = lambda s: datetime.strptime(s, G.ISO).replace(tzinfo=timezone.utc)
    ks = G.kickoffs(csvtext, t("2026-10-11T15:00:00Z"))
    assert len(ks) == 2                                                  # same-time games share one slot
    assert G.decide(ks, t("2026-10-11T15:50:00Z"), set()) is None        # 70 min out: too early
    assert G.decide(ks, t("2026-10-11T16:00:00Z"), set()) == "2026-10-11T17:00:00Z"   # 60 min out
    assert G.decide(ks, t("2026-10-11T16:20:00Z"), set()) == "2026-10-11T17:00:00Z"   # delayed tick still in window
    assert G.decide(ks, t("2026-10-11T16:10:00Z"), {"2026-10-11T17:00:00Z"}) is None  # already refreshed
    assert G.decide(ks, t("2026-10-11T19:25:00Z"), {"2026-10-11T17:00:00Z"}) == "2026-10-11T20:25:00Z"



def test_weather_retries_then_succeeds(monkeypatch):
    import requests
    calls = {"n": 0}
    times = [f"2026-10-11T{h:02d}:00" for h in range(24)]
    payload = {"hourly": {"time": times, **{k: [5] * 24 for k in ("temperature_2m", "relative_humidity_2m", "precipitation_probability",
               "precipitation", "snowfall", "wind_speed_10m", "wind_gusts_10m", "weather_code")}}}

    class R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return payload

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.ReadTimeout("slow")
        return R()
    monkeypatch.setattr(W.requests, "get", flaky)
    monkeypatch.setattr(W.time, "sleep", lambda s: None)
    monkeypatch.setattr(W, "_ensemble", lambda *a: {})
    out = W.forecast(40, -74, datetime(2026, 10, 11, 17, tzinfo=timezone.utc), datetime(2026, 10, 10, tzinfo=timezone.utc))
    assert out["status"] == "forecast" and calls["n"] == 3


# ------------------------------------------------------------------ market anchoring
def test_anchor_collapses_to_market_when_model_is_noise():
    from nfledge import anchor as AN
    rng = np.random.default_rng(1)
    n = 4000
    mp = rng.uniform(0.3, 0.7, n)
    y = (rng.uniform(size=n) < mp).astype(int)                 # outcomes follow the market
    p = np.clip(mp + rng.normal(0, 0.08, n), 0.05, 0.95)        # model = market + noise
    coef = AN.fit(pd.DataFrame({"market": "spread", "p": p, "mp": mp, "win": y, "season": 2024}))
    assert abs(coef["spread"]["b"]) < 0.25
    assert abs(AN.anchored(coef, "spread", 0.62, 0.50) - 0.50) < 0.04   # a 12-pt raw edge mostly disappears


def test_anchor_keeps_real_signal():
    from nfledge import anchor as AN
    rng = np.random.default_rng(2)
    n = 4000
    truth = rng.uniform(0.3, 0.7, n)
    y = (rng.uniform(size=n) < truth).astype(int)
    mp = np.full(n, 0.5)                                         # market knows nothing
    coef = AN.fit(pd.DataFrame({"market": "total", "p": truth, "mp": mp, "win": y, "season": 2024}))
    assert coef["total"]["b"] > 0.7
    assert AN.anchored(None, "total", 0.6, 0.5) == 0.5


def _rec_game(model_home_cover=0.60, nv_home=0.50, ev=-0.02):
    vals = []
    for team, p, nv in (("H", model_home_cover, nv_home), ("A", 1 - model_home_cover, 1 - nv_home)):
        vals.append({"market": "spread", "selection": f"{team} -3", "team": team, "model_p": p, "no_vig": nv,
                     "odds": -110.0, "ev_per_unit": ev, "anchored_p": nv})
    return {"home": {"team": "H"}, "away": {"team": "A"}, "values": vals,
            "market": {"spread_line": 3.0, "home_no_vig": 0.6, "total_line": 44.0}}


def test_recs_model_alone_caps_at_lean():
    from nfledge import recs as RC
    r = RC.recommend(_rec_game(0.70), None, None)["markets"]["spread"]
    assert r["side"] == "H" and r["score"] == 6 and r["verdict"] == "Lean"


def test_recs_bet_needs_agreeing_signal():
    from nfledge import recs as RC
    opening = {"spread_line": 2.0}           # line moved 1 pt toward home
    r = RC.recommend(_rec_game(0.70), opening, None)["markets"]["spread"]
    assert r["score"] == 7 and r["verdict"] == "Bet"
    notes = {"adjust": [{"market": "all", "side": "A", "points": 1.5, "reason": "x"}]}
    r2 = RC.recommend(_rec_game(0.70), opening, notes)["markets"]["spread"]
    assert r2["verdict"] != "Bet"


def test_anchor_never_fades_model():
    from nfledge import anchor as AN
    coef = {"spread": {"c": 0.0, "a": 1.0, "b": -0.3}}
    assert abs(AN.anchored(coef, "spread", 0.6, 0.5) - 0.5) < 1e-9


def test_last_completed_week_is_prefix():
    import pandas as pd
    from nfledge.retrain import last_completed_week
    g = pd.DataFrame({"season": [2026] * 4, "week": [1, 1, 2, 3], "game_id": list("abcd"), "home_score": [1, 2, None, 3]})
    pbp = pd.DataFrame({"game_id": list("abcd")})
    assert last_completed_week(g, pbp, 2026) == 1          # week 2 unfinished, so week 3 doesn't count
    assert last_completed_week(g, pd.DataFrame({"game_id": ["a"]}), 2026) is None   # pbp missing a game


def test_recency_weighting_runs():
    import numpy as np
    import pandas as pd
    from nfledge.models.game_model import MARGIN_FEATURES, TOTAL_FEATURES, GameModel
    rng = np.random.default_rng(0)
    cols = sorted(set(MARGIN_FEATURES) | set(TOTAL_FEATURES))
    X = pd.DataFrame(rng.normal(size=(200, len(cols))), columns=cols)
    X["season"] = np.repeat([2024, 2025], 100); X["week"] = 5
    m = GameModel(half_life=2.0).fit(X, rng.normal(0, 13, 200), rng.normal(44, 13, 200))
    assert m.predict(X.head(3)).shape[0] == 3
