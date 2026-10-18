"""Financial health score (0–100) and letter grade.

Each component scores 0–100. Components without data are dropped and their weight is
shared proportionally by the rest (and reported as missing).
"""

from __future__ import annotations

from dataclasses import dataclass

from networth.analysis.credit import CreditResult
from networth.analysis.percentile import PercentileResult
from networth.analysis.projections import TrendFit
from networth.analysis.state_compare import StateComparison
from networth.analysis.totals import Totals
from networth.constants import SAVINGS_BENCHMARK_RATE

WEIGHTS = {
    "age_percentile": 30,
    "trend": 20,
    "debt": 20,
    "emergency_fund": 10,
    "credit": 10,
    "state_adjusted": 10,
}
LABELS = {
    "age_percentile": "Rank for your age",
    "trend": "Net worth trend",
    "debt": "Debt load",
    "emergency_fund": "Emergency fund",
    "credit": "Credit score",
    "state_adjusted": "Rank adjusted for cost of living",
}
GRADES = ((90, "A"), (80, "B"), (65, "C"), (50, "D"), (0, "F"))


@dataclass(frozen=True)
class Component:
    key: str
    label: str
    base_weight: float          # % before redistribution
    weight: float               # % actually used (0 if missing)
    score: float | None         # 0–100, None = no data
    detail: str

    @property
    def points(self) -> float:
        return (self.score or 0.0) * self.weight / 100


@dataclass(frozen=True)
class HealthScore:
    score: float
    grade: str
    components: tuple[Component, ...]
    missing: tuple[str, ...]    # labels of components without data


def piecewise(x: float, points: list[tuple[float, float]]) -> float:
    """Linear interpolation through (x, y) points, flat beyond the ends."""
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def grade_for(score: float) -> str:
    return next(g for floor, g in GRADES if score >= floor)


def trend_score(trend: TrendFit | None, typical_income: float) -> tuple[float | None, str]:
    """Full marks for growing by 15% of a typical income for your age each year; 25 for flat."""
    if trend is None:
        return None, "needs at least 2 history points over 6+ months"
    benchmark = SAVINGS_BENCHMARK_RATE * typical_income
    s = trend.slope_per_year / benchmark if benchmark else 0.0
    score = 100.0 if s >= 1 else 25 + 75 * s if s >= 0 else max(0.0, 25 + 25 * s)
    return score, f"${trend.slope_per_year:,.0f}/year vs. a ${benchmark:,.0f}/year benchmark"


def debt_score(t: Totals) -> tuple[float, str]:
    if t.total_debts == 0:
        return 100.0, "no debt"
    if t.total_assets == 0:
        return 0.0, "debt with no assets"
    ratio = t.debt_to_asset or 0.0
    base = piecewise(ratio, [(0.1, 100), (1.0, 0)])
    penalty = min(50.0, t.high_interest_debt / t.total_assets * 200)
    return max(0.0, base - penalty), f"debts are {ratio:.0%} of assets; ${t.high_interest_debt:,.0f} high-interest"


def emergency_score(t: Totals) -> tuple[float | None, str]:
    if t.cash == 0:
        return 0.0, "no cash listed"
    if t.emergency_fund_months is None:
        return None, "needs monthly expenses"
    m = t.emergency_fund_months
    return piecewise(m, [(0, 0), (1, 25), (3, 70), (6, 100)]), f"{m:.1f} months of expenses in cash"


def credit_score_points(score: int) -> float:
    return piecewise(score, [(300, 0), (580, 20), (670, 50), (740, 80), (800, 100)])


def health_score(totals: Totals, trend: TrendFit | None, age_rank: PercentileResult,
                 state: StateComparison, credit: CreditResult) -> HealthScore:
    raw: dict[str, tuple[float | None, str]] = {
        "age_percentile": (age_rank.standard.percentile,
                           f"{age_rank.standard.phrase} for ages {age_rank.standard.bracket.label.lower()}"),
        "trend": trend_score(trend, age_rank.standard.bracket.median_income),
        "debt": debt_score(totals),
        "emergency_fund": emergency_score(totals),
        "credit": (credit_score_points(credit.scoring_score), f"score {credit.scoring_score}"),
        "state_adjusted": (state.adjusted_age_rank.standard.percentile,
                           f"{state.adjusted_age_rank.standard.phrase} at {state.name} prices"),
    }
    available = sum(WEIGHTS[k] for k, (s, _) in raw.items() if s is not None)
    components = tuple(
        Component(k, LABELS[k], WEIGHTS[k],
                  WEIGHTS[k] * 100 / available if s is not None else 0.0, s, detail)
        for k, (s, detail) in raw.items()
    )
    total = sum(c.points for c in components)
    return HealthScore(
        score=total, grade=grade_for(total), components=components,
        missing=tuple(c.label for c in components if c.score is None),
    )
