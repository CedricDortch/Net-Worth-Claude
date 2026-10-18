"""Where the household ranks among households of the same age (SCF 2025)."""

from __future__ import annotations

from dataclasses import dataclass

from networth.constants import PERCENTILE_TIERS
from networth.models import NetWorthProfile
from networth.reference_data import AgeBracket, AgeData


def estimate_percentile(value: float, percentiles: dict[int, float]) -> float:
    """Linear interpolation between breakpoints. Clamped to 0.5 / 99.5 outside the 1st-99th."""
    points = sorted(percentiles.items())
    if value < points[0][1]:
        return 0.5
    if value >= points[-1][1]:
        return 99.5
    for (p_lo, v_lo), (p_hi, v_hi) in zip(points, points[1:]):
        if v_lo <= value < v_hi:
            return p_lo + (p_hi - p_lo) * (value - v_lo) / (v_hi - v_lo)
    return 99.5  # unreachable: covered by the bounds above


def rank_phrase(percentile: float) -> str:
    """62.3 -> 'top 38%' · 12.0 -> 'bottom 12%'."""
    if percentile >= 50:
        return f"top {max(1, round(100 - percentile))}%"
    return f"bottom {max(1, round(percentile))}%"


@dataclass(frozen=True)
class Tier:
    percentile: int
    value: float
    gap: float           # dollars needed to reach it (≤ 0 if already there)


@dataclass(frozen=True)
class BracketRank:
    bracket: AgeBracket
    net_worth: float
    percentile: float
    phrase: str
    gap_to_median: float           # positive = below the median by this much
    next_tier: Tier | None         # the first tier above the user; None at the top
    tiers: tuple[Tier, ...]


@dataclass(frozen=True)
class PercentileResult:
    reference_age: int             # the user's age, or the older partner's
    standard: BracketRank          # headline ranking (Fed's standard bracket)
    fine: BracketRank | None       # under-35 sub-bracket, smaller sample
    all_households: BracketRank
    dollars: str                   # "2025 dollars"


def rank_in(bracket: AgeBracket, net_worth: float) -> BracketRank:
    pct = estimate_percentile(net_worth, bracket.percentiles)
    tiers = tuple(Tier(t, bracket.percentiles[t], bracket.percentiles[t] - net_worth)
                  for t in PERCENTILE_TIERS if t in bracket.percentiles)
    next_tier = next((t for t in tiers if t.gap > 0), None)
    return BracketRank(bracket, net_worth, pct, rank_phrase(pct), bracket.median - net_worth, next_tier, tiers)


def rank_by_age(profile: NetWorthProfile, age_data: AgeData, net_worth: float | None = None) -> PercentileResult:
    """Rank `net_worth` (default: the profile's) among households whose head is the same age.

    Couples use the older partner's age; the SCF groups households by the head's age.
    """
    value = profile.net_worth if net_worth is None else net_worth
    age = max(p.age for p in profile.people)
    fine = age_data.fine_bracket_for(age)
    return PercentileResult(
        reference_age=age,
        standard=rank_in(age_data.bracket_for(age), value),
        fine=rank_in(fine, value) if fine else None,
        all_households=rank_in(age_data.all_households, value),
        dollars=age_data.dollars,
    )
