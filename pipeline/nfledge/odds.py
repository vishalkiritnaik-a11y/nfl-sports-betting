"""Odds math: American <-> decimal, implied probability, vig removal, expected value.

All functions are pure and covered by tests in tests/test_odds.py.
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence


def american_to_implied(odds: float) -> float:
    """Raw implied probability from American odds (includes the book's margin).

    +A  -> 100 / (A + 100)
    -A  -> A / (A + 100)
    """
    if odds is None or (isinstance(odds, float) and math.isnan(odds)):
        raise ValueError("odds is missing")
    if -100 < odds < 100:
        raise ValueError(f"American odds must be <= -100 or >= +100, got {odds}")
    if odds > 0:
        return 100.0 / (odds + 100.0)
    a = -odds
    return a / (a + 100.0)


def american_to_decimal(odds: float) -> float:
    if -100 < odds < 100:
        raise ValueError(f"American odds must be <= -100 or >= +100, got {odds}")
    if odds > 0:
        return 1.0 + odds / 100.0
    return 1.0 + 100.0 / (-odds)


def decimal_to_american(dec: float) -> float:
    if dec <= 1.0:
        raise ValueError("decimal odds must be > 1")
    if dec >= 2.0:
        return round((dec - 1.0) * 100.0, 1)
    return round(-100.0 / (dec - 1.0), 1)


def prob_to_american(p: float) -> float:
    """Fair American odds for a probability (no margin)."""
    if not 0 < p < 1:
        raise ValueError("p must be in (0, 1)")
    return decimal_to_american(1.0 / p)


def overround(implied: Sequence[float]) -> float:
    """Book margin: sum of raw implied probabilities minus 1."""
    return float(sum(implied)) - 1.0


def remove_vig_proportional(implied: Sequence[float]) -> list[float]:
    """Margin-adjusted ("no-vig") probabilities by proportional normalisation."""
    s = float(sum(implied))
    if s <= 0:
        raise ValueError("implied probabilities must sum to > 0")
    return [p / s for p in implied]


def remove_vig_power(implied: Sequence[float], tol: float = 1e-10) -> list[float]:
    """Power method: find k such that sum(p_i ** k) == 1. Shifts more margin
    onto longshots than proportional normalisation (favourite-longshot bias)."""
    lo, hi = 0.5, 5.0
    for _ in range(200):
        k = (lo + hi) / 2
        s = sum(p ** k for p in implied)
        if abs(s - 1) < tol:
            break
        if s > 1:
            lo = k
        else:
            hi = k
    return [p ** k for p in implied]


def expected_profit(p: float, decimal_odds: float) -> float:
    """Expected profit per 1 unit staked: p*(D-1) - (1-p)."""
    if not 0 <= p <= 1:
        raise ValueError("p must be in [0, 1]")
    if decimal_odds <= 1:
        raise ValueError("decimal odds must be > 1")
    return p * (decimal_odds - 1.0) - (1.0 - p)


def roi_pct(p: float, decimal_odds: float) -> float:
    """Expected return on investment, in percent of stake."""
    return 100.0 * expected_profit(p, decimal_odds)


def break_even_prob(decimal_odds: float) -> float:
    return 1.0 / decimal_odds


def kelly_fraction(p: float, decimal_odds: float) -> float:
    """Full-Kelly fraction (shown for reference only, never as a recommendation)."""
    b = decimal_odds - 1.0
    f = (b * p - (1 - p)) / b
    return max(0.0, f)


def value_flag(model_p: float, market_p: float, min_edge_pp: float) -> bool:
    """Positive-value flag: model probability exceeds the (margin-adjusted)
    market probability by at least ``min_edge_pp`` percentage points."""
    return (model_p - market_p) * 100.0 >= min_edge_pp


def evaluate_two_way(model_p_a: float, odds_a: float, odds_b: float) -> dict:
    """Full value breakdown for side A of a two-way market."""
    raw_a, raw_b = american_to_implied(odds_a), american_to_implied(odds_b)
    fair_a, fair_b = remove_vig_proportional([raw_a, raw_b])
    dec_a = american_to_decimal(odds_a)
    return {
        "odds": odds_a,
        "decimal": dec_a,
        "raw_implied": raw_a,
        "no_vig": fair_a,
        "overround": overround([raw_a, raw_b]),
        "edge_pp": (model_p_a - fair_a) * 100.0,
        "edge_vs_raw_pp": (model_p_a - raw_a) * 100.0,
        "ev_per_unit": expected_profit(model_p_a, dec_a),
        "roi_pct": roi_pct(model_p_a, dec_a),
    }


def log_loss(ps: Iterable[float], ys: Iterable[int], eps: float = 1e-12) -> float:
    ps, ys = list(ps), list(ys)
    tot = 0.0
    for p, y in zip(ps, ys):
        p = min(max(p, eps), 1 - eps)
        tot += -(y * math.log(p) + (1 - y) * math.log(1 - p))
    return tot / len(ps)


def brier(ps: Iterable[float], ys: Iterable[int]) -> float:
    ps, ys = list(ps), list(ys)
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ps)
