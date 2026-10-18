"""Net worth projections for 5, 10, 15, 20 years (three scenarios).

Model (simulated month by month from the current snapshot):
- Investments and retirement grow at the scenario return; cash at `cash_rate`;
  real estate at `home_appreciation`; vehicles lose `vehicle_depreciation`; "other" is flat.
- Debts accrue their own interest rate (0% if none given).
- A monthly contribution (savings) pays debts highest-rate first, then is invested.
  A negative contribution (spending more than you earn) drains cash, then investments,
  then becomes new debt. Nothing is clamped at zero.

Where the contribution comes from (first that applies):
1. `--contribution` / file assumption.
2. History trend: the linear trend in net worth ($/year) minus the market growth the
   assumptions would explain over that period = implied savings. We never extrapolate
   the historical growth *percentage* (CAGR): compounding a fast start from a small base
   is fantasy. CAGR is still reported as a fact about the past.
3. Income × DEFAULT_SAVINGS_RATE if only income is known; otherwise $0.

Contributions grow each year by income growth (assumption, else income history capped
at MAX_DERIVED_INCOME_GROWTH, else 0).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np

from networth.constants import (
    CONTRIBUTION_SPREAD, DEFAULT_SAVINGS_RATE, MAX_DERIVED_INCOME_GROWTH, MIN_TREND_YEARS,
    PROJECTION_YEARS,
)
from networth.models import Assumptions, NetWorthProfile

HORIZON = max(PROJECTION_YEARS)


@dataclass(frozen=True)
class TrendFit:
    start: dt.date
    end: dt.date
    points: int
    span_years: float
    change_total: float
    slope_per_year: float            # linear fit, dollars per year
    r2_linear: float
    cagr: float | None               # %/year from an exponential fit; None if any value <= 0
    r2_exponential: float | None

    @property
    def better_fit(self) -> str:
        if self.r2_exponential is not None and self.r2_exponential > self.r2_linear:
            return "exponential"
        return "linear"


@dataclass(frozen=True)
class Scenario:
    name: str                        # "conservative" | "expected" | "optimistic" | "default"
    investment_return: float         # %
    annual_contribution: float       # first-year contribution, dollars
    nominal: tuple[float, ...]       # net worth at year 0..HORIZON
    real: tuple[float, ...]          # same, in today's dollars

    def at(self, year: int, real: bool = False) -> float:
        return (self.real if real else self.nominal)[year]


@dataclass(frozen=True)
class Projections:
    start_date: dt.date
    start_net_worth: float
    trend: TrendFit | None
    contribution_source: str         # "assumption" | "history" | "income" | "none"
    annual_contribution: float       # expected scenario, first year
    market_growth_per_year: float | None   # part of the historical trend explained by returns
    contribution_growth: float       # %/year
    scenarios: dict[str, Scenario]
    default_expected: Scenario | None      # expected path at default assumptions, if the user changed any
    ages_at: dict[int, tuple[int, ...]]    # year offset -> ages of each person
    notes: tuple[str, ...] = field(default_factory=tuple)

    def at(self, year: int, scenario: str = "expected", real: bool = False) -> float:
        return self.scenarios[scenario].at(year, real)


# ---------------------------------------------------------------------------
# Trend
# ---------------------------------------------------------------------------

def _years_between(a: dt.date, b: dt.date) -> float:
    return (b - a).days / 365.25


def _r2(y: np.ndarray, predicted: np.ndarray) -> float:
    total = float(((y - y.mean()) ** 2).sum())
    return 1.0 - float(((y - predicted) ** 2).sum()) / total if total else 1.0


def fit_trend(history: dict[dt.date, float]) -> TrendFit | None:
    """Linear and exponential fits of net worth over time. None if too little history."""
    if len(history) < 2:
        return None
    dates = sorted(history)
    span = _years_between(dates[0], dates[-1])
    if span < MIN_TREND_YEARS:
        return None
    x = np.array([_years_between(dates[0], d) for d in dates])
    y = np.array([history[d] for d in dates], dtype=float)

    slope, intercept = np.polyfit(x, y, 1)
    r2_lin = _r2(y, slope * x + intercept)

    cagr = r2_exp = None
    if (y > 0).all():
        b, a = np.polyfit(x, np.log(y), 1)
        cagr = (float(np.exp(b)) - 1) * 100
        r2_exp = _r2(y, np.exp(a + b * x))

    return TrendFit(dates[0], dates[-1], len(dates), span, float(y[-1] - y[0]),
                    float(slope), r2_lin, cagr, r2_exp)


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def _monthly(rate_pct: float) -> float:
    return (1 + rate_pct / 100) ** (1 / 12) - 1


@dataclass
class _Book:
    cash: float
    growth: float          # investments + retirement
    real_estate: float
    vehicles: float
    other: float
    debts: list[list[float]]   # [balance, annual rate %], sorted highest rate first

    @classmethod
    def from_profile(cls, p: NetWorthProfile) -> _Book:
        by = lambda *cats: sum(i.value for i in p.assets if i.category in cats)  # noqa: E731
        debts = sorted(([d.value, d.interest_rate or 0.0] for d in p.debts), key=lambda d: -d[1])
        return cls(by("cash"), by("investments", "retirement"), by("real_estate"),
                   by("vehicles"), by("other"), debts)

    @property
    def net_worth(self) -> float:
        return (self.cash + self.growth + self.real_estate + self.vehicles + self.other
                - sum(d[0] for d in self.debts))

    def step(self, a: Assumptions, ret: float, contribution: float) -> None:
        self.cash *= 1 + _monthly(a.cash_rate)
        self.growth *= 1 + _monthly(ret)
        self.real_estate *= 1 + _monthly(a.home_appreciation)
        self.vehicles *= (1 - a.vehicle_depreciation / 100) ** (1 / 12)
        for d in self.debts:
            d[0] *= 1 + _monthly(d[1])

        if contribution >= 0:
            for d in self.debts:
                pay = min(d[0], contribution)
                d[0] -= pay
                contribution -= pay
            self.growth += contribution
        else:
            need = -contribution
            for attr in ("cash", "growth"):
                take = min(max(getattr(self, attr), 0.0), need)
                setattr(self, attr, getattr(self, attr) - take)
                need -= take
            if need > 0:
                self.debts.append([need, 0.0])


def _simulate(p: NetWorthProfile, a: Assumptions, ret: float, annual_contribution: float,
              contribution_growth: float, name: str) -> Scenario:
    book = _Book.from_profile(p)
    nominal = [book.net_worth]
    monthly = annual_contribution / 12
    for year in range(1, HORIZON + 1):
        for _ in range(12):
            book.step(a, ret, monthly)
        nominal.append(book.net_worth)
        monthly *= 1 + contribution_growth / 100
    real = [v / (1 + a.inflation / 100) ** y for y, v in enumerate(nominal)]
    return Scenario(name, ret, annual_contribution, tuple(nominal), tuple(real))


def _annual_market_growth(p: NetWorthProfile, a: Assumptions) -> float:
    """Dollars per year the current balances earn (or lose) at the expected assumptions."""
    b = _Book.from_profile(p)
    return (b.cash * a.cash_rate + b.growth * a.investment_return + b.real_estate * a.home_appreciation
            - b.vehicles * a.vehicle_depreciation - sum(d[0] * d[1] for d in b.debts)) / 100


def _income_cagr(income: dict[int, float]) -> float | None:
    years = sorted(y for y, v in income.items() if v > 0)
    if len(years) < 2:
        return None
    first, last = income[years[0]], income[years[-1]]
    return ((last / first) ** (1 / (years[-1] - years[0])) - 1) * 100


def _contribution_growth(profile: NetWorthProfile, a: Assumptions, notes: list[str]) -> float:
    if a.income_growth is not None:
        return a.income_growth
    derived = _income_cagr(profile.income_history)
    if derived is None:
        return 0.0
    if derived > MAX_DERIVED_INCOME_GROWTH:
        notes.append(f"Your income grew {derived:.1f}%/year; projections cap savings growth at "
                     f"{MAX_DERIVED_INCOME_GROWTH:g}%/year because fast raises rarely last 20 years.")
    return min(derived, MAX_DERIVED_INCOME_GROWTH)


def _contribution(profile: NetWorthProfile, a: Assumptions, trend: TrendFit | None,
                  notes: list[str]) -> tuple[float, str, float | None]:
    """(annual contribution, source, market growth per year explained by returns)."""
    if a.monthly_contribution is not None:
        return a.monthly_contribution * 12, "assumption", None
    if trend is not None:
        market_now = _annual_market_growth(profile, a)
        history_mean = max(float(np.mean(list(profile.net_worth_history.values()))), 0.0)
        # Scale today's market growth down to the average balance over the history period.
        market = market_now * (history_mean / profile.net_worth) if profile.net_worth > 0 else market_now
        return trend.slope_per_year - market, "history", market
    if profile.income_history:
        latest = profile.income_history[max(profile.income_history)]
        notes.append(f"No usable net worth history, so savings are assumed to be "
                     f"{DEFAULT_SAVINGS_RATE:g}% of your latest income.")
        return latest * DEFAULT_SAVINGS_RATE / 100, "income", None
    notes.append("No history, income, or contribution given, so projections assume you save $0 "
                 "from here on. Pass --contribution with your monthly savings for a real forecast.")
    return 0.0, "none", None


def project(profile: NetWorthProfile, today: dt.date | None = None) -> Projections:
    a = profile.assumptions
    notes: list[str] = []
    start = profile.as_of or today or dt.date.today()
    trend = fit_trend(profile.net_worth_history)
    growth = _contribution_growth(profile, a, notes)
    contribution, source, market_growth = _contribution(profile, a, trend, notes)

    if any(d.interest_rate is None for d in profile.debts):
        notes.append("Debts without an interest rate are projected at 0% interest.")

    spread = abs(contribution) * CONTRIBUTION_SPREAD
    scenarios = {
        "conservative": _simulate(profile, a, a.investment_return - a.scenario_spread,
                                  contribution - spread, growth, "conservative"),
        "expected": _simulate(profile, a, a.investment_return, contribution, growth, "expected"),
        "optimistic": _simulate(profile, a, a.investment_return + a.scenario_spread,
                                contribution + spread, growth, "optimistic"),
    }

    # The same projection at default assumptions, for "your vs default" comparisons.
    default_expected = None
    if any(s != "default" for s in a.source.values()):
        d = Assumptions()
        d_contribution, _, _ = _contribution(profile, d, trend, [])
        default_expected = _simulate(profile, d, d.investment_return, d_contribution,
                                     _contribution_growth(profile, d, []), "default")

    ages_at = {y: tuple(p.age + y for p in profile.people) for y in range(HORIZON + 1)}
    return Projections(start, profile.net_worth, trend, source, contribution, market_growth,
                       growth, scenarios, default_expected, ages_at, tuple(notes))
