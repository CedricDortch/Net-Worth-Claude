"""Current snapshot: totals, ratios, mix."""

from __future__ import annotations

from dataclasses import dataclass

from networth.constants import HIGH_INTEREST_RATE
from networth.models import ASSET_CATEGORIES, DEBT_CATEGORIES, NetWorthProfile


@dataclass(frozen=True)
class Totals:
    total_assets: float
    total_debts: float
    net_worth: float
    debt_to_asset: float | None          # debts ÷ assets; None if there are no assets
    liquid_net_worth: float              # cash + investments − credit card debt
    cash: float
    assets_by_category: dict[str, float]
    debts_by_category: dict[str, float]
    asset_mix: dict[str, float]          # % of total assets, by category
    debt_mix: dict[str, float]           # % of total debts, by category
    weighted_debt_rate: float | None     # balance-weighted APR of debts that list a rate
    high_interest_debt: float            # balance at or above HIGH_INTEREST_RATE
    yearly_interest_cost: float          # approximate interest paid per year on debts with a rate
    emergency_fund_months: float | None  # cash ÷ monthly expenses; None if expenses unknown
    depreciating_share: float | None     # vehicles ÷ total assets, %
    by_owner: dict[str, tuple[float, float]]  # owner -> (assets, debts); couples only


def _share(parts: dict[str, float], total: float) -> dict[str, float]:
    return {k: (v / total * 100 if total else 0.0) for k, v in parts.items() if v}


def compute_totals(profile: NetWorthProfile) -> Totals:
    assets = {c: sum(i.value for i in profile.assets if i.category == c) for c in ASSET_CATEGORIES}
    debts = {c: sum(i.value for i in profile.debts if i.category == c) for c in DEBT_CATEGORIES}
    total_assets, total_debts = profile.total_assets, profile.total_debts

    rated = [d for d in profile.debts if d.interest_rate is not None]
    rated_balance = sum(d.value for d in rated)
    weighted_rate = (sum(d.value * d.interest_rate for d in rated) / rated_balance) if rated_balance else None

    by_owner: dict[str, tuple[float, float]] = {}
    if profile.household_type == "couple":
        for owner in ("partner1", "partner2", "joint"):
            by_owner[owner] = (sum(i.value for i in profile.assets if i.owner == owner),
                               sum(i.value for i in profile.debts if i.owner == owner))

    return Totals(
        total_assets=total_assets,
        total_debts=total_debts,
        net_worth=total_assets - total_debts,
        debt_to_asset=(total_debts / total_assets) if total_assets else None,
        liquid_net_worth=assets["cash"] + assets["investments"] - debts["credit_card"],
        cash=assets["cash"],
        assets_by_category={k: v for k, v in assets.items() if v},
        debts_by_category={k: v for k, v in debts.items() if v},
        asset_mix=_share(assets, total_assets),
        debt_mix=_share(debts, total_debts),
        weighted_debt_rate=weighted_rate,
        high_interest_debt=sum(d.value for d in rated if d.interest_rate >= HIGH_INTEREST_RATE),
        yearly_interest_cost=sum(d.value * d.interest_rate / 100 for d in rated),
        emergency_fund_months=(assets["cash"] / profile.monthly_expenses)
        if profile.monthly_expenses else None,
        depreciating_share=(assets["vehicles"] / total_assets * 100) if total_assets else None,
        by_owner=by_owner,
    )
