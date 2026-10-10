import math

import pytest

from nfledge import odds as o


def approx(a, b, tol=1e-9):
    return abs(a - b) < tol


def test_implied_positive():
    assert approx(o.american_to_implied(150), 100 / 250)
    assert approx(o.american_to_implied(100), 0.5)


def test_implied_negative():
    assert approx(o.american_to_implied(-150), 150 / 250)
    assert approx(o.american_to_implied(-110), 110 / 210)


def test_invalid_odds():
    with pytest.raises(ValueError):
        o.american_to_implied(50)
    with pytest.raises(ValueError):
        o.american_to_decimal(-99)


def test_decimal_conversion_roundtrip():
    for a in [-400, -200, -110, 100, 120, 250, 900]:
        d = o.american_to_decimal(a)
        assert approx(o.decimal_to_american(d), a, 0.11)
    assert approx(o.american_to_decimal(-110), 1 + 100 / 110)
    assert approx(o.american_to_decimal(250), 3.5)


def test_implied_equals_inverse_decimal():
    for a in [-300, -110, 140, 500]:
        assert approx(o.american_to_implied(a), 1 / o.american_to_decimal(a))


def test_vig_removal_sums_to_one():
    raw = [o.american_to_implied(-110), o.american_to_implied(-110)]
    assert approx(o.overround(raw), 2 * 110 / 210 - 1)
    fair = o.remove_vig_proportional(raw)
    assert approx(sum(fair), 1.0)
    assert approx(fair[0], 0.5)
    pw = o.remove_vig_power([o.american_to_implied(-300), o.american_to_implied(240)])
    assert abs(sum(pw) - 1) < 1e-8


def test_power_method_favours_favourite():
    raw = [o.american_to_implied(-300), o.american_to_implied(240)]
    prop = o.remove_vig_proportional(raw)
    pw = o.remove_vig_power(raw)
    assert pw[0] > prop[0]  # more margin removed from longshot


def test_expected_profit_formula():
    # p*(D-1) - (1-p)
    assert approx(o.expected_profit(0.5, 2.0), 0.0)
    assert approx(o.expected_profit(0.55, 1 + 100 / 110), 0.55 * (100 / 110) - 0.45)
    assert approx(o.expected_profit(0.25, 5.0), 0.25 * 4 - 0.75)
    assert approx(o.roi_pct(0.25, 5.0), 25.0)


def test_break_even_equals_zero_ev():
    for a in [-200, -110, 150, 400]:
        d = o.american_to_decimal(a)
        assert abs(o.expected_profit(o.break_even_prob(d), d)) < 1e-12


def test_value_flag_threshold():
    assert o.value_flag(0.56, 0.52, 3.0)
    assert not o.value_flag(0.54, 0.52, 3.0)


def test_evaluate_two_way():
    r = o.evaluate_two_way(0.60, -120, 100)
    assert approx(r["raw_implied"], 120 / 220)
    assert approx(r["no_vig"], (120 / 220) / (120 / 220 + 0.5))
    assert approx(r["ev_per_unit"], 0.6 * (100 / 120) - 0.4)


def test_kelly_nonnegative():
    assert o.kelly_fraction(0.4, 2.0) == 0
    assert approx(o.kelly_fraction(0.6, 2.0), 0.2)


def test_scoring_rules():
    assert approx(o.brier([1.0, 0.0], [1, 0]), 0)
    assert approx(o.log_loss([0.5, 0.5], [1, 0]), math.log(2))
