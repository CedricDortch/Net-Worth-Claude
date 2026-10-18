"""How the household compares with its state, raw and adjusted for cost of living.

Two numbers, two different questions:
- In-state percentile: raw net worth vs. the state's household distribution (Census SIPP,
  all ages): "Among households in Ohio, where do you fall?"
- Cost-of-living adjusted: net worth × 100 / RPP (what it's worth at national prices), used
  for the age ranking that feeds the health score, so a dollar in a cheap state counts more.
"""

from __future__ import annotations

from dataclasses import dataclass

from networth.analysis.percentile import PercentileResult, rank_by_age
from networth.models import NetWorthProfile
from networth.reference_data import ReferenceData, StateInfo


@dataclass(frozen=True)
class DistributionRank:
    percentile: float
    bound: str          # "exact" | "upper" (true percentile is at most this) | "lower" (at least this)

    @property
    def phrase(self) -> str:
        p = self.percentile
        if self.bound == "upper":
            return f"bottom {max(1, round(p))}%"
        if self.bound == "lower":
            return f"top {max(1, round(100 - p))}% or higher"
        return f"top {max(1, round(100 - p))}%" if p >= 50 else f"bottom {max(1, round(p))}%"


@dataclass(frozen=True)
class StateComparison:
    code: str
    name: str
    rpp: float
    net_worth: float
    adjusted_net_worth: float              # in national prices
    state_median: float                    # Census median (national × RPP/100 if suppressed)
    national_median: float                 # Census national median
    vs_state_median: float                 # net_worth ÷ state_median
    in_state: DistributionRank | None      # None if the distribution is unavailable
    adjusted_age_rank: PercentileResult    # SCF age ranking of the adjusted net worth
    median_household_income: float
    income_year: int
    latest_income: float | None
    income_vs_state: float | None          # latest income ÷ state median household income
    used_national_fallback: bool
    notes: tuple[str, ...]


def rank_in_distribution(value: float, distribution: dict[float, float]) -> DistributionRank:
    """Interpolate the cumulative distribution {dollar bound: % of households below it}."""
    bounds = sorted(distribution)
    if value <= 0:
        return DistributionRank(distribution[0.0], "upper")
    if value >= bounds[-1]:
        return DistributionRank(distribution[bounds[-1]], "lower")
    for lo, hi in zip(bounds, bounds[1:]):
        if lo < value <= hi:
            share = distribution[lo] + (distribution[hi] - distribution[lo]) * (value - lo) / (hi - lo)
            return DistributionRank(share, "exact")
    return DistributionRank(distribution[bounds[-1]], "lower")


def _scaled(national: StateInfo, rpp: float) -> dict[float, float] | None:
    """National distribution with dollar bounds scaled by the state's price level."""
    if national.distribution is None:
        return None
    return {b * rpp / 100: v for b, v in national.distribution.items()}


def compare_state(profile: NetWorthProfile, ref: ReferenceData) -> StateComparison:
    state = ref.states.get(profile.state)
    national = ref.states.national
    nw = profile.net_worth
    notes: list[str] = []

    fallback = state.median_net_worth is None or state.distribution is None
    if fallback:
        notes.append(f"The Census Bureau doesn't publish wealth figures for {state.name} (too few survey "
                     "responses), so national figures adjusted for its cost of living are used instead.")
    median = state.median_net_worth if state.median_net_worth is not None \
        else national.median_net_worth * state.rpp / 100
    distribution = state.distribution if state.distribution is not None else _scaled(national, state.rpp)
    notes.append("State figures cover households of all ages, so younger households usually rank lower "
                 "here than they do against their own age group.")

    adjusted = nw * 100 / state.rpp
    latest_income = profile.income_history[max(profile.income_history)] if profile.income_history else None

    return StateComparison(
        code=state.code, name=state.name, rpp=state.rpp,
        net_worth=nw, adjusted_net_worth=adjusted,
        state_median=median, national_median=national.median_net_worth,
        vs_state_median=nw / median if median else 0.0,
        in_state=rank_in_distribution(nw, distribution) if distribution else None,
        adjusted_age_rank=rank_by_age(profile, ref.age, adjusted),
        median_household_income=state.median_household_income,
        income_year=state.income_year,
        latest_income=latest_income,
        income_vs_state=(latest_income / state.median_household_income) if latest_income else None,
        used_national_fallback=fallback,
        notes=tuple(notes),
    )
