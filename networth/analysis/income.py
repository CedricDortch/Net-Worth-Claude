"""Income growth and savings rate (only when income history is given)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from networth.models import NetWorthProfile


@dataclass(frozen=True)
class IncomeAnalysis:
    years: tuple[int, ...]
    income: dict[int, float]
    income_cagr: float | None                 # %/year
    net_worth_change: dict[int, float]        # year -> change in year-end net worth
    savings_rate: dict[int, float]            # year -> Δ net worth ÷ income, %
    average_savings_rate: float | None        # Σ Δ net worth ÷ Σ income over matched years, %
    spent_the_raise: tuple[int, ...]          # years income rose but net worth fell


def _year_end_values(history: dict[dt.date, float]) -> dict[int, float]:
    """The last net worth value recorded in each calendar year."""
    out: dict[int, float] = {}
    for d in sorted(history):
        out[d.year] = history[d]
    return out


def analyze_income(profile: NetWorthProfile) -> IncomeAnalysis | None:
    income = profile.income_history
    if not income:
        return None
    years = tuple(sorted(income))
    positive = [y for y in years if income[y] > 0]
    cagr = None
    if len(positive) >= 2 and positive[-1] > positive[0]:
        cagr = ((income[positive[-1]] / income[positive[0]]) ** (1 / (positive[-1] - positive[0])) - 1) * 100

    year_end = _year_end_values(profile.net_worth_history)
    change = {y: year_end[y] - year_end[y - 1] for y in years if y in year_end and y - 1 in year_end}
    rates = {y: change[y] / income[y] * 100 for y in change if income[y] > 0}
    matched_income = sum(income[y] for y in rates)
    average = sum(change[y] for y in rates) / matched_income * 100 if matched_income else None

    spent = tuple(y for y in change if y - 1 in income and income[y] > income[y - 1] and change[y] < 0)
    return IncomeAnalysis(years, dict(income), cagr, change, rates, average, spent)
