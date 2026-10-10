"""Confidence tiers.

Confidence answers "how likely is this pick to hit, and can I trust that number?"
1. The base tier comes from the probability band. Each band's hit rate is measured
   on walk-forward backtests and published, so the labels are checkable.
2. The tier drops one level for conditions that make the probability itself
   uncertain: a questionable/doubtful tag (the projection assumes he plays), an
   uncertain starting QB, high wind, or a large model-vs-market disagreement.
Data-stability signals (thin history, swinging snap share) were tested and did not
predict miscalibration in 2022-25 backtests, so they are shown as notes only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TD_CUTS = [(0.40, "High"), (0.25, "Medium"), (0.0, "Low")]
GAME_CUTS = [(0.70, "High"), (0.60, "Medium"), (0.0, "Low")]
ORDER = ["Low", "Medium", "High"]


def base_tier(p: float, cuts) -> str:
    for lo, lab in cuts:
        if p >= lo:
            return lab
    return cuts[-1][1]


def downgrade(label: str) -> str:
    return ORDER[max(0, ORDER.index(label) - 1)]


def band_text(label: str, cuts) -> str:
    i = [l for _, l in cuts].index(label)
    lo = cuts[i][0]
    hi = cuts[i - 1][0] if i > 0 else None
    if hi is None:
        return f"{lo:.0%}+"
    if lo == 0:
        return f"under {hi:.0%}"
    return f"{lo:.0%}–{hi:.0%}"


def tier_stats(p: np.ndarray, y: np.ndarray, cuts) -> dict:
    """Backtest hit rate per tier: {label: {n, pred, hit, band}}."""
    labs = np.array([base_tier(x, cuts) for x in p])
    out = {}
    for _, lab in cuts:
        m = labs == lab
        out[lab] = {"n": int(m.sum()), "pred": float(p[m].mean()) if m.any() else None,
                    "hit": float(y[m].mean()) if m.any() else None, "band": band_text(lab, cuts)}
    return out


def assess(p: float, cuts, stats: dict | None, risks: list[str], notes: list[str] | None = None,
           what: str = "to score") -> dict:
    """Return {label, base, reasons} for a probability and its risk flags."""
    base = base_tier(p, cuts)
    label = base
    reasons = []
    st = (stats or {}).get(base)
    if st and st.get("hit") is not None:
        reasons.append(f"{p:.0%} {what}: {base} tier ({st['band']}). Backtest picks in this tier hit {st['hit']:.0%} of the time (n={st['n']:,})")
    else:
        reasons.append(f"{p:.0%} {what}: {base} tier ({band_text(base, cuts)})")
    if risks:
        label = downgrade(base)
        reasons += [f"Lowered one tier: {r}" for r in risks] if label != base else risks
    reasons += notes or []
    return {"label": label, "base": base, "reasons": reasons}
