"""Core data model. Change this first, then update dependents and .claude/rules/architecture.md."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

ASSET_CATEGORIES = ("cash", "investments", "retirement", "real_estate", "vehicles", "other")
DEBT_CATEGORIES = ("mortgage", "auto", "student", "credit_card", "personal", "other")
OWNERS = ("partner1", "partner2", "joint")


@dataclass(frozen=True)
class Item:
    label: str              # "Bank Account 1"
    value: float            # 30000.0
    category: str           # "cash"
    interest_rate: float | None = None   # debts only, percent (5.5 = 5.5%)
    owner: str = "joint"    # "partner1" | "partner2" | "joint" (couples only)


@dataclass(frozen=True)
class Person:
    age: int
    credit_score: int


@dataclass(frozen=True)
class Assumptions:
    investment_return: float = 7.0      # % per year, expected scenario
    scenario_spread: float = 3.0        # ± points for conservative / optimistic
    inflation: float = 3.0
    cash_rate: float = 2.0
    home_appreciation: float = 3.0
    vehicle_depreciation: float = 15.0
    monthly_contribution: float | None = None   # None = use the trend
    income_growth: float | None = None          # None = use income history
    source: dict[str, str] = field(default_factory=dict)  # field -> "default" | "file" | "cli"


@dataclass(frozen=True)
class NetWorthProfile:
    household_type: str     # "single" | "couple"
    people: tuple[Person, ...]   # 1 for single, 2 for couple
    state: str              # normalized 2-letter code
    assets: tuple[Item, ...]
    debts: tuple[Item, ...]
    net_worth_history: dict[dt.date, float]   # date -> household net worth, sorted by date
    income_history: dict[int, float]          # year -> household income
    monthly_expenses: float | None
    assumptions: Assumptions
    as_of: dt.date | None = None    # date of the current snapshot, if the file says
    notes: tuple[str, ...] = ()     # things the user should know about how the file was read

    @property
    def total_assets(self) -> float:
        return sum(i.value for i in self.assets)

    @property
    def total_debts(self) -> float:
        return sum(i.value for i in self.debts)

    @property
    def net_worth(self) -> float:
        return self.total_assets - self.total_debts
