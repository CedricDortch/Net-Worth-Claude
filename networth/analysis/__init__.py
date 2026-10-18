"""Analysis: pure functions from a NetWorthProfile (+ reference data) to results. No I/O."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from networth import reference_data
from networth.analysis.credit import CreditResult, assess_credit
from networth.analysis.income import IncomeAnalysis, analyze_income
from networth.analysis.percentile import PercentileResult, rank_by_age
from networth.analysis.projections import Projections, project
from networth.analysis.score import HealthScore, health_score
from networth.analysis.state_compare import StateComparison, compare_state
from networth.analysis.totals import Totals, compute_totals
from networth.models import NetWorthProfile


@dataclass(frozen=True)
class AnalysisResult:
    profile: NetWorthProfile
    totals: Totals
    projections: Projections
    age_rank: PercentileResult
    state: StateComparison
    credit: CreditResult
    income: IncomeAnalysis | None
    score: HealthScore
    ref: reference_data.ReferenceData   # the benchmarks used, for charts and citations


def analyze(profile: NetWorthProfile, ref: reference_data.ReferenceData | None = None,
            today: dt.date | None = None) -> AnalysisResult:
    ref = ref or reference_data.load()
    totals = compute_totals(profile)
    projections = project(profile, today)
    age_rank = rank_by_age(profile, ref.age)
    state = compare_state(profile, ref)
    credit = assess_credit(profile, ref.credit)
    return AnalysisResult(
        profile=profile, totals=totals, projections=projections, age_rank=age_rank, state=state,
        credit=credit, income=analyze_income(profile),
        score=health_score(totals, projections.trend, age_rank, state, credit),
        ref=ref,
    )
