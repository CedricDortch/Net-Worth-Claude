"""Credit score tier and comparison with national and state averages."""

from __future__ import annotations

from dataclasses import dataclass

from networth.models import NetWorthProfile
from networth.reference_data import CreditData, CreditTier


@dataclass(frozen=True)
class PersonCredit:
    score: int
    tier: CreditTier
    next_tier: CreditTier | None
    points_to_next_tier: int | None
    vs_national: int          # score − national average
    vs_state: int             # score − state average


@dataclass(frozen=True)
class CreditResult:
    people: tuple[PersonCredit, ...]
    national_average: int
    state_average: int
    year: int
    scoring_score: int        # the score used in the health score (lower one for couples)
    gap: int | None           # couples: difference between the two scores


def assess_credit(profile: NetWorthProfile, credit: CreditData) -> CreditResult:
    national, state = credit.national_average, credit.state_average(profile.state)
    people = []
    for p in profile.people:
        tier = credit.tier_for(p.credit_score)
        higher = [t for t in credit.tiers if t.min > tier.max]
        nxt = higher[0] if higher else None
        people.append(PersonCredit(
            score=p.credit_score, tier=tier, next_tier=nxt,
            points_to_next_tier=(nxt.min - p.credit_score) if nxt else None,
            vs_national=p.credit_score - national, vs_state=p.credit_score - state,
        ))
    scores = [p.credit_score for p in profile.people]
    return CreditResult(
        people=tuple(people), national_average=national, state_average=state, year=credit.latest_year,
        scoring_score=min(scores), gap=(max(scores) - min(scores)) if len(scores) == 2 else None,
    )
