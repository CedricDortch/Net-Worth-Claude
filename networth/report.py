"""The honest written report: verdict, findings, section text, suggestions.

All wording lives here (see .claude/rules/tone.md). Every sentence is built from a number
in the analysis. Criticize the finances, never the person.
"""

from __future__ import annotations

from dataclasses import dataclass

from networth import assumptions as assumptions_mod
from networth.analysis import AnalysisResult
from networth.analysis.score import Component
from networth.constants import HIGH_INTEREST_RATE
from networth.formatting import format_money, format_percent

DISCLAIMER = ("This report gives estimates based on public averages and simple models. "
              "It is not financial, tax, or legal advice.")

TIER_MEANING = {
    "Poor": "Expect denials or very high rates. On-time payments and a secured card are the way out.",
    "Fair": "You'll be approved for some loans, but you'll pay noticeably higher rates.",
    "Good": "You'll be approved for most loans, but not always at the best rates.",
    "Very Good": "Lenders will approve you easily and at good rates.",
    "Exceptional": "You qualify for the best rates lenders offer.",
}


def money(v: float) -> str:
    return format_money(v)


def short(v: float) -> str:
    return format_money(v, compact=True)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Finding:
    severity: str        # "bad" | "warning" | "good"
    section: str         # which report section it belongs to
    text: str


@dataclass(frozen=True)
class Suggestion:
    key: str
    title: str           # what to do
    reason: str          # the number that triggered it
    impact: str          # expected effect, in words
    impact_dollars: float | None
    priority: int        # 1 = protect yourself now, 2 = important, 3 = optimize


@dataclass(frozen=True)
class AssumptionWarning:
    field: str
    message: str


@dataclass(frozen=True)
class Report:
    grade: str
    score: float
    headline: str
    verdict: tuple[str, ...]
    findings: tuple[Finding, ...]
    sections: dict[str, tuple[str, ...]]   # breakdown, projections, age, state, credit, income, assumptions
    suggestions: tuple[Suggestion, ...]
    assumption_warnings: tuple[AssumptionWarning, ...]
    assumption_comparison: str | None      # "In 20 years: X with yours vs. Y with the defaults."
    data_notes: tuple[str, ...]
    disclaimer: str = DISCLAIMER


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

def _findings(r: AnalysisResult) -> list[Finding]:
    t, p, a, c, inc = r.totals, r.projections, r.age_rank, r.credit, r.income
    out: list[Finding] = []
    add = lambda sev, sec, text: out.append(Finding(sev, sec, text))  # noqa: E731

    # Debt
    for d in sorted(r.profile.debts, key=lambda d: -(d.interest_rate or 0)):
        if d.interest_rate is not None and d.interest_rate >= HIGH_INTEREST_RATE:
            cost = d.value * d.interest_rate / 100
            add("bad", "breakdown", f"You are paying {format_percent(d.interest_rate)} interest on "
                f"{money(d.value)} of {d.label}. That costs you about {money(cost)} a year for nothing.")
    if t.total_debts == 0:
        add("good", "breakdown", "You have no debt listed, so none of your income goes to interest.")
    elif t.total_debts > t.total_assets:
        add("bad", "breakdown", f"You owe {money(t.total_debts)} but own only {money(t.total_assets)}. "
            f"Your net worth is {money(t.net_worth)}.")

    # Cash
    if t.cash == 0:
        add("bad", "breakdown", "You have no cash listed at all. One car repair, medical bill, or lost "
            "paycheck means selling investments (maybe at a loss) or borrowing.")
    elif t.emergency_fund_months is not None:
        m = t.emergency_fund_months
        if m < 1:
            add("bad", "breakdown", f"You have {m:.1f} months of expenses in cash. One emergency puts you into debt.")
        elif m < 3:
            add("warning", "breakdown", f"You have {m:.1f} months of expenses in cash. Three to six is the "
                "minimum cushion.")
        elif m > 12:
            add("warning", "breakdown", f"You're holding {m:.0f} months of expenses in cash. Past 6-12 months, "
                "that money is losing ground to inflation.")
        else:
            add("good", "breakdown", f"You have {m:.1f} months of expenses in cash, a solid cushion.")

    # Assets
    if t.depreciating_share is not None and t.depreciating_share > 30:
        add("bad", "breakdown", f"Vehicles are {t.depreciating_share:.0f}% of everything you own, and they "
            "lose value every year.")
    employer = sum(i.value for i in r.profile.assets
                   if any(w in i.label.lower() for w in ("company stock", "employer", "rsu", "espp")))
    if t.total_assets and employer / t.total_assets >= 0.10:
        add("warning", "breakdown", f"{employer / t.total_assets:.0%} of your assets is your employer's stock. "
            "If the company struggles, your job and your savings take the hit together.")
    if not any(i.category == "retirement" for i in r.profile.assets):
        add("bad", "breakdown", "You have no retirement accounts listed. Every year without tax-advantaged "
            "saving is compounding you don't get back.")

    # Age rank
    std = a.standard
    if std.percentile >= 90:
        add("good", "age", f"You're in the {std.phrase} for ages {std.bracket.label.lower()}.")
    elif std.percentile >= 50:
        add("good", "age", f"You're ahead of the typical household your age: {std.phrase}, "
            f"{money(-std.gap_to_median)} above the median.")
    elif std.percentile >= 25:
        add("warning", "age", f"You're below the median for your age ({std.phrase}), "
            f"{money(std.gap_to_median)} behind it.")
    else:
        add("bad", "age", f"You're in the {std.phrase} for your age, {money(std.gap_to_median)} behind the median.")

    # Trend
    if p.trend:
        slope = p.trend.slope_per_year
        if slope < 0:
            add("bad", "projections", f"Your net worth has been falling by about {money(-slope)} a year "
                f"over {p.trend.span_years:.1f} years.")
        else:
            bench = next(cp for cp in r.score.components if cp.key == "trend")
            if bench.score is not None and bench.score >= 100:
                add("good", "projections", f"Your net worth grew about {money(slope)} a year over "
                    f"{p.trend.span_years:.1f} years. That's a strong pace.")
            elif bench.score is not None and bench.score < 50:
                add("warning", "projections", f"Your net worth grew only {money(slope)} a year over "
                    f"{p.trend.span_years:.1f} years. That's slow.")
    if p.at(10) < 0:
        add("bad", "projections", f"If nothing changes, you will be {money(-p.at(10))} in the hole in 10 years.")

    # Income
    if inc:
        if inc.spent_the_raise:
            years = ", ".join(str(y) for y in inc.spent_the_raise)
            add("bad", "income", f"Your income went up in {years} but your net worth went down. "
                "You are spending your raises.")
        if inc.average_savings_rate is not None:
            rate = inc.average_savings_rate
            if rate < 0:
                add("bad", "income", f"Your net worth shrinks by about {-rate:.0f}% of your income each year. "
                    "You're spending more than you earn. 15-20% saved is the target.")
            elif rate < 10:
                add("bad" if rate < 5 else "warning", "income",
                    f"You're keeping about {rate:.0f}% of your income. 15-20% is the target.")
            elif rate >= 20:
                add("good", "income", f"You're keeping about {rate:.0f}% of your income, well above the 15% target.")
        if (not inc.spent_the_raise and (inc.income_cagr or 0) >= 5
                and inc.average_savings_rate is not None and 0 <= inc.average_savings_rate < 5):
            add("bad", "income", f"Your income grew {inc.income_cagr:.0f}% a year but your net worth barely "
                "moved. That's lifestyle creep.")

    # Credit
    for i, pc in enumerate(c.people, start=1):
        who = f"Partner {i}'s" if len(c.people) == 2 else "Your"
        if pc.tier.name in ("Very Good", "Exceptional"):
            add("good", "credit", f"{who} credit score of {pc.score} is {pc.tier.name}, "
                f"{pc.vs_state:+d} points vs. the {r.state.name} average.")
        elif pc.tier.name in ("Poor", "Fair"):
            add("bad", "credit", f"{who} credit score of {pc.score} is {pc.tier.name}. "
                "That makes every loan you take more expensive.")

    # Couples
    if r.profile.household_type == "couple":
        if c.gap is not None and c.gap >= 60:
            low = min(range(2), key=lambda k: c.people[k].score)
            add("warning", "credit", f"Partner {low + 1}'s credit score of {c.people[low].score} is "
                f"{c.gap} points below Partner {2 - low}'s and will raise your rate on any joint loan.")
        owner_debts = {o: d for o, (_, d) in t.by_owner.items() if o != "joint"}
        if t.total_debts:
            for owner, debt in owner_debts.items():
                if debt / t.total_debts > 0.75:
                    add("warning", "breakdown", f"Partner {owner[-1]} holds {debt / t.total_debts:.0%} of "
                        "the household's debt.")
    return out


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

_DRAG_TEXT = {
    "age_percentile": "low net worth for your age",
    "trend": "slow net worth growth",
    "debt": "your debt load",
    "emergency_fund": "your emergency fund",
    "credit": "your credit score",
    "state_adjusted": "low net worth for your age, even at local prices",
}


def _biggest_drag(components: tuple[Component, ...]) -> Component | None:
    lost = [(c.weight * (100 - c.score) / 100, c) for c in components if c.score is not None]
    worst = max(lost, key=lambda x: x[0], default=None)
    return worst[1] if worst and worst[0] >= 3 else None


def _verdict(r: AnalysisResult, findings: list[Finding]) -> tuple[str, list[str]]:
    sc, std, p = r.score, r.age_rank.standard, r.projections
    nw = money(r.totals.net_worth)
    grade = sc.grade

    if grade == "A":
        headline = (f"Your finances are strong. You're in the {std.phrase} for your age with {nw}. "
                    "Keep doing exactly what you're doing.")
    elif grade == "B":
        headline = (f"You're well ahead of most people your age ({std.phrase}). "
                    "One or two fixes would put you in the top tier.")
    elif grade == "C":
        if std.percentile >= 60:
            headline = f"You're ahead of most people your age ({std.phrase}), but your score is held back."
        elif std.percentile >= 40:
            headline = f"You're average for your age ({std.phrase}). Average is not a plan."
        else:
            headline = f"You're behind most people your age ({std.phrase})."
    else:
        # D and F: say where they actually stand; a low grade can come from debt or no cash
        # even when net worth is fine for their age.
        standing = f"You're in the {std.phrase} for your age"
        if std.percentile < 50:
            standing += f", {money(std.gap_to_median)} behind the median"
        if p.trend and p.trend.slope_per_year < 0:
            standing += ", and your net worth is shrinking"
        elif r.totals.total_debts > r.totals.total_assets:
            standing += ", and you owe more than you own"
        if grade == "D":
            opener = "You are behind." if std.percentile < 50 else "Your finances have serious weak spots."
            headline = f"{opener} {standing}."
        else:
            trend = ""
            if p.trend and p.trend.slope_per_year < 0:
                trend = f" and has been falling about {money(-p.trend.slope_per_year)} a year"
            headline = f"Your finances are in serious trouble. Your net worth is {nw}{trend}."
            if std.percentile >= 50:
                headline += f" {standing}, but the rest of the picture is bad."
            elif std.percentile >= 25:
                headline += f" {standing}."
            if p.at(10) < 0:
                headline += f" If nothing changes, you will be {money(-p.at(10))} in the hole in 10 years."

    verdict = [f"Score: {sc.score:.0f}/100, grade {grade}."]
    next_floor = {"B": 90, "C": 80, "D": 65, "F": 50}.get(grade)
    if next_floor and next_floor - sc.score <= 5:
        next_grade = {90: "an A", 80: "a B", 65: "a C", 50: "a D"}[next_floor]
        verdict.append(f"You're {next_floor - sc.score:.1f} points from {next_grade}.")
    drag = _biggest_drag(sc.components)
    if drag:
        verdict.append(f"The biggest thing holding you back is {_DRAG_TEXT[drag.key]} "
                       f"({drag.score:.0f}/100 on that part of the score: {drag.detail}).")
    problems = [f.text for f in findings if f.severity == "bad"][:3]
    strengths = [f.text for f in findings if f.severity == "good"][:3]
    if problems:
        verdict.append("Problems: " + " ".join(problems))
    if strengths:
        verdict.append("What's working: " + " ".join(strengths))
    if sc.missing:
        verdict.append(f"Not scored (no data): {', '.join(sc.missing)}. Their weight went to the other parts.")
    return headline, verdict


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def _breakdown(r: AnalysisResult) -> list[str]:
    t = r.totals
    out = [f"You own {money(t.total_assets)} and owe {money(t.total_debts)}, "
           f"for a net worth of {money(t.net_worth)}."]
    if t.asset_mix:
        top = max(t.asset_mix, key=t.asset_mix.get)
        out.append(f"{t.asset_mix[top]:.0f}% of your assets are in {top.replace('_', ' ')}.")
    if t.weighted_debt_rate is not None:
        out.append(f"Your debts average {format_percent(round(t.weighted_debt_rate, 1))} interest, "
                   f"about {money(t.yearly_interest_cost)} a year.")
    if t.debt_to_asset is not None and t.total_debts:
        out.append(f"Your debts equal {t.debt_to_asset:.0%} of your assets.")
    return out


def _projection_text(r: AnalysisResult) -> list[str]:
    p, a = r.projections, r.profile.assumptions
    ages = lambda y: " and ".join(str(x) for x in p.ages_at[y])  # noqa: E731
    out = [f"At your current pace you'd have about {short(p.at(10))} at age {ages(10)} "
           f"({short(p.at(10, real=True))} in today's dollars) and {short(p.at(20))} at age {ages(20)} "
           f"({short(p.at(20, real=True))} in today's dollars)."]
    out.append(f"Range in 20 years: {short(p.at(20, 'conservative'))} if returns run "
               f"{format_percent(a.investment_return - a.scenario_spread)} and you save 25% less, up to "
               f"{short(p.at(20, 'optimistic'))} at {format_percent(a.investment_return + a.scenario_spread)} "
               "and 25% more.")
    if p.contribution_source == "history" and p.trend and p.market_growth_per_year is not None:
        out.append(
            f"How this is estimated: your net worth grew {money(p.trend.slope_per_year)} a year. At a "
            f"{format_percent(a.investment_return)} return, only about {money(p.market_growth_per_year)} of "
            f"that is market growth, which leaves {money(p.annual_contribution)} a year "
            f"({money(p.annual_contribution / 12)}/month) of implied savings.")
        if p.trend.span_years < 3 or (p.trend.cagr or 0) > 30:
            out.append(
                f"Be careful with this: {p.trend.span_years:.1f} years is a short track record. If markets "
                f"returned more than {format_percent(a.investment_return)} during that time, your real savings "
                "are lower and these projections are too optimistic. Rerun with --contribution set to what "
                "you actually save each month.")
        if p.trend.cagr is not None and p.trend.cagr > 30:
            out.append(f"Your past growth rate ({p.trend.cagr:.0f}% a year) is not used for the forecast. "
                       "Fast growth from a small starting point doesn't keep compounding.")
    elif p.contribution_source == "assumption":
        out.append(f"This uses your contribution of {money(p.annual_contribution / 12)}/month.")
    out.extend(p.notes)
    return out


def _age_text(r: AnalysisResult) -> list[str]:
    a = r.age_rank
    std = a.standard
    who = "" if r.profile.household_type == "single" else f" (using the older partner's age, {a.reference_age})"
    out = [f"With {money(std.net_worth)} you're in the {std.phrase} of households aged "
           f"{std.bracket.label.lower()}{who}. Their median is {money(std.bracket.median)}."]
    if a.fine:
        out.append(f"Against households aged {a.fine.bracket.label.lower()} only, you're in the "
                   f"{a.fine.phrase}. That group is small ({a.fine.bracket.sample_households} households in the "
                   "survey), so treat it as a rough guide.")
    if std.next_tier:
        nt = std.next_tier
        out.append(f"To reach the top {100 - nt.percentile}% for your age you need {money(nt.value)}, "
                   f"{money(nt.gap)} more.")
    out.append(f"Source: Federal Reserve Survey of Consumer Finances 2025 ({a.dollars}).")
    return out


def _state_text(r: AnalysisResult) -> list[str]:
    s = r.state
    direction = "below" if s.rpp < 100 else "above"
    out = [f"{s.name}'s median household net worth is {money(s.state_median)}; you have "
           f"{s.vs_state_median:.2f}x that."]
    if s.in_state:
        out.append(f"Among all {s.name} households you're in the {s.in_state.phrase}. That includes every age, "
                   "so it's not a fair comparison for younger households.")
    out.append(f"Prices in {s.name} are {abs(100 - s.rpp):.1f}% {direction} the national average, so your "
               f"net worth buys what {money(s.adjusted_net_worth)} would nationally. Adjusted that way, you're in "
               f"the {s.adjusted_age_rank.standard.phrase} for your age.")
    if s.income_vs_state is not None:
        out.append(f"Your latest income ({money(s.latest_income)}) is {s.income_vs_state:.2f}x {s.name}'s "
                   f"median household income ({money(s.median_household_income)}).")
    out.extend(n for n in s.notes if "all ages" not in n)
    return out


def _credit_text(r: AnalysisResult) -> list[str]:
    c, s = r.credit, r.state
    out = []
    for i, pc in enumerate(c.people, start=1):
        who = f"Partner {i}'s score" if len(c.people) == 2 else "Your score"
        line = (f"{who} of {pc.score} is {pc.tier.name}: {pc.vs_state:+d} points vs. the {s.name} average "
                f"({c.state_average}) and {pc.vs_national:+d} vs. the national average ({c.national_average}). "
                f"{TIER_MEANING[pc.tier.name]}")
        if pc.next_tier:
            line += f" {pc.points_to_next_tier} points from {pc.next_tier.name}."
        out.append(line)
    if c.gap is not None:
        out.append(f"Lenders often use the lower score ({c.scoring_score}) on joint loans, so that's the one scored.")
    out.append(f"Averages: Experian, September {c.year}.")
    return out


def _income_text(r: AnalysisResult) -> list[str]:
    inc = r.income
    if inc is None:
        return ["No income history was given, so your savings rate can't be measured. Add an Income section "
                "(year and amount) to see how much of what you earn you keep."]
    out = []
    if inc.income_cagr is not None:
        out.append(f"Your income grew {inc.income_cagr:.1f}% a year from {inc.years[0]} to {inc.years[-1]}.")
    if inc.average_savings_rate is not None and inc.average_savings_rate < 0:
        out.append(f"On average your net worth fell by {-inc.average_savings_rate:.0f}% of your income each year.")
    elif inc.average_savings_rate is not None:
        out.append(f"On average you kept {inc.average_savings_rate:.0f}% of your income as new net worth.")
    else:
        out.append("Net worth history doesn't line up with the income years, so the savings rate can't be measured.")
    return out


def _assumption_text(r: AnalysisResult) -> list[str]:
    a = r.profile.assumptions
    out = []
    for spec in assumptions_mod.SPECS:
        value = getattr(a, spec.field)
        shown = ("from your history" if value is None else
                 money(value) + "/month" if spec.unit == "$" else format_percent(value))
        out.append(f"{spec.label}: {shown} ({a.source.get(spec.field, 'default')})")
    return out


# ---------------------------------------------------------------------------
# Assumption honesty check
# ---------------------------------------------------------------------------

def _assumption_comparison(r: AnalysisResult) -> str | None:
    p = r.projections
    if p.default_expected is None:
        return None
    return (f"In 20 years: {short(p.at(20))} with your assumptions vs. {short(p.default_expected.at(20))} "
            "with the defaults.")


def _assumption_warnings(r: AnalysisResult) -> list[AssumptionWarning]:
    a, p = r.profile.assumptions, r.projections
    out: list[AssumptionWarning] = []

    def warn(field: str, message: str) -> None:
        out.append(AssumptionWarning(field, message))

    if a.source.get("investment_return") != "default" and a.investment_return > 10:
        warn("investment_return", f"You assumed {format_percent(a.investment_return)} a year. The long-run "
             "stock market average is closer to 7-10%.")
    if a.monthly_contribution is not None and p.trend is not None and p.default_expected:
        # default_expected learned its contribution from history, so it's the historical savings.
        historical = p.default_expected.annual_contribution
        if historical > 0 and a.monthly_contribution * 12 > 2 * historical:
            warn("monthly_contribution", f"You assumed you'll save {money(a.monthly_contribution)} a month. "
                 f"Your history shows about {money(historical / 12)}.")
    if a.source.get("inflation") != "default" and a.inflation < 1:
        warn("inflation", f"{format_percent(a.inflation)} inflation is not realistic. "
             "Your future dollars will buy less.")
    if a.source.get("home_appreciation") != "default" and a.home_appreciation > 6:
        warn("home_appreciation", f"You assumed homes gain {format_percent(a.home_appreciation)} a year. "
             "Long-run home prices rise about 3-5% a year.")
    if a.source.get("vehicle_depreciation") != "default" and a.vehicle_depreciation < 5:
        warn("vehicle_depreciation", f"You assumed cars lose only {format_percent(a.vehicle_depreciation)} a "
             "year. Most lose 15-20% a year.")
    return out


# ---------------------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------------------

def _future_value(monthly: float, annual_return: float, years: int) -> float:
    r = (1 + annual_return / 100) ** (1 / 12) - 1
    n = years * 12
    return monthly * n if r == 0 else monthly * ((1 + r) ** n - 1) / r


def _suggestions(r: AnalysisResult) -> list[Suggestion]:
    t, p, inc, c, prof = r.totals, r.projections, r.income, r.credit, r.profile
    ret = prof.assumptions.investment_return
    out: list[Suggestion] = []

    high = [d for d in prof.debts if d.interest_rate is not None and d.interest_rate >= HIGH_INTEREST_RATE]
    if high:
        cost = sum(d.value * d.interest_rate / 100 for d in high)
        worst = max(high, key=lambda d: d.interest_rate)
        out.append(Suggestion(
            "high_interest", "Pay off high-interest debt with the avalanche method (highest rate first).",
            f"{money(sum(d.value for d in high))} is at {format_percent(HIGH_INTEREST_RATE)}+ interest; "
            f"{worst.label} is at {format_percent(worst.interest_rate)}.",
            f"Saves about {money(cost)} a year in interest.", cost, 1))

    months = t.emergency_fund_months
    if t.cash == 0 or (months is not None and months < 3):
        if prof.monthly_expenses:
            target = 3 * prof.monthly_expenses
            gap = max(0.0, target - t.cash)
            reason = f"You have {money(t.cash)} in cash, {months or 0:.1f} months of expenses."
            impact = f"Set aside {money(gap)} more to reach 3 months ({money(target)}), then aim for 6."
        else:
            reason = "You have no cash listed." if t.cash == 0 else f"You have {money(t.cash)} in cash."
            impact = ("Aim for 3-6 months of expenses. Add your monthly expenses with --expenses to get an "
                      "exact target.")
        out.append(Suggestion(
            "emergency_fund", "Build a 3-6 month emergency fund in a high-yield savings account before "
            "investing more.", reason, impact, None, 1))

    if not any(i.category == "retirement" for i in prof.assets):
        fv = _future_value(300, ret, 20)
        out.append(Suggestion(
            "retirement", "Open a 401(k) (take any employer match first) or an IRA.",
            "You have no retirement accounts listed.",
            f"$300/month at {format_percent(ret)} grows to about {short(fv)} in 20 years.", fv, 2))

    low_credit = any(pc.score < 670 for pc in c.people)
    if low_credit:
        low_i = min(range(len(c.people)), key=lambda k: c.people[k].score)
        whose = f"Partner {low_i + 1}'s" if len(c.people) == 2 else "your"
        joint = " Do it before applying for any joint loan." if len(c.people) == 2 else ""
        out.append(Suggestion(
            "credit", f"Raise {whose} credit score: pay every bill on time, keep card balances under 30% of the "
            f"limit (under 10% is better), keep old cards open, and check reports for errors.{joint}",
            f"A score of {c.people[low_i].score} is below Good (670).",
            "Better rates on every future loan and lower insurance costs in many states.", None, 2))

    if t.depreciating_share is not None and t.depreciating_share > 30:
        out.append(Suggestion(
            "vehicles", "Stop buying depreciating assets. Keep your current car longer instead of upgrading.",
            f"Vehicles are {t.depreciating_share:.0f}% of your assets.",
            f"A car loses roughly {format_percent(prof.assumptions.vehicle_depreciation)} of its value a year.",
            None, 2))

    if p.trend and p.trend.slope_per_year < 0:
        out.append(Suggestion(
            "negative_trend", "Track every dollar for 30 days, then cut your 3 largest non-essential costs.",
            f"Your net worth is falling about {money(-p.trend.slope_per_year)} a year.",
            f"Stopping the decline alone keeps {money(-p.trend.slope_per_year * 10)} over 10 years.",
            -p.trend.slope_per_year * 10, 1))

    if inc and inc.average_savings_rate is not None and inc.average_savings_rate < 10:
        latest = inc.income[max(inc.income)]
        extra = (15 - inc.average_savings_rate) / 100 * latest
        fv = _future_value(extra / 12, ret, 20)
        out.append(Suggestion(
            "savings_rate", "Automate your savings: move money to savings or investments on payday, "
            "targeting 15-20% of income.",
            f"You keep about {inc.average_savings_rate:.0f}% of your income." if inc.average_savings_rate >= 0
            else f"Your net worth falls by about {-inc.average_savings_rate:.0f}% of your income each year.",
            f"Getting to 15% means about {money(extra)} more a year, roughly {short(fv)} after 20 years.", fv, 2))

    if inc and (inc.spent_the_raise or ((inc.income_cagr or 0) >= 5 and (inc.average_savings_rate or 0) < 5)):
        out.append(Suggestion(
            "lifestyle_creep", "Save at least half of every raise before you get used to spending it.",
            "Your income rose but your net worth didn't keep up.", "Raises turn into wealth instead of habits.",
            None, 2))

    if months is not None and months > 12 and prof.monthly_expenses:
        extra = t.cash - 6 * prof.monthly_expenses
        gain = extra * (ret - prof.assumptions.cash_rate) / 100
        out.append(Suggestion(
            "idle_cash", "Invest the cash beyond a 6-month emergency fund.",
            f"You hold {months:.0f} months of expenses in cash.",
            f"About {money(gain)} more a year at a {format_percent(ret)} return instead of "
            f"{format_percent(prof.assumptions.cash_rate)}.", gain, 3))

    if r.state.adjusted_age_rank.standard.percentile < 50:
        out.append(Suggestion(
            "income_growth", "Focus on growing your income: new skills, certifications, or a job change.",
            f"Even adjusted for {r.state.name} prices you're in the "
            f"{r.state.adjusted_age_rank.standard.phrase} for your age.",
            "Income is the biggest lever on savings; cutting costs only goes so far.", None, 2))

    employer = sum(i.value for i in prof.assets
                   if any(w in i.label.lower() for w in ("company stock", "employer", "rsu", "espp")))
    if t.total_assets and employer / t.total_assets >= 0.10:
        out.append(Suggestion(
            "employer_stock", "Sell down employer stock to under 10% of your assets and diversify.",
            f"{employer / t.total_assets:.0%} of your assets is your employer's stock.",
            "Your job and your savings stop depending on the same company.", None, 2))

    if prof.household_type == "couple":
        if c.gap is not None and c.gap >= 60 and not low_credit:
            out.append(Suggestion(
                "couple_credit", "Improve the lower credit score before applying for any joint loan.",
                f"Your scores are {c.gap} points apart; lenders often use the lower one ({c.scoring_score}).",
                "A lower rate on a mortgage or car loan.", None, 2))
        for owner, (_, debt) in t.by_owner.items():
            if owner != "joint" and t.total_debts and debt / t.total_debts > 0.75:
                out.append(Suggestion(
                    "couple_debt", f"Make a joint payoff plan for Partner {owner[-1]}'s highest-rate debt.",
                    f"Partner {owner[-1]} holds {debt / t.total_debts:.0%} of the household's debt.",
                    "Debt paid off faster as a team.", None, 2))

    strong = r.score.grade in ("A", "B") or (r.age_rank.standard.percentile >= 75 and not high)
    if strong:
        out.append(Suggestion(
            "optimize", "Optimize: max out tax-advantaged accounts (401(k), HSA, Roth IRA) before taxable "
            "investing, and keep your investments diversified.",
            f"You're in the {r.age_rank.standard.phrase} for your age with no high-interest debt."
            if not high else f"Grade {r.score.grade}.",
            "Lower taxes now and in retirement compound on top of your returns.", None, 3))

    if p.contribution_source == "history" and p.trend and (p.trend.span_years < 3 or (p.trend.cagr or 0) > 30):
        out.append(Suggestion(
            "real_savings", "Find out what you actually save each month and rerun with --contribution.",
            f"Your projections assume {money(p.annual_contribution / 12)}/month, estimated from "
            f"{p.trend.span_years:.1f} years of history.",
            "A forecast built on your real savings instead of an estimate.", None, 3))

    return sorted(out, key=lambda s: (s.priority, -(s.impact_dollars or 0)))[:7]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_report(r: AnalysisResult) -> Report:
    findings = _findings(r)
    order = {"bad": 0, "warning": 1, "good": 2}
    findings.sort(key=lambda f: order[f.severity])
    headline, verdict = _verdict(r, findings)
    return Report(
        grade=r.score.grade,
        score=r.score.score,
        headline=headline,
        verdict=tuple(verdict),
        findings=tuple(findings),
        sections={
            "breakdown": tuple(_breakdown(r)),
            "projections": tuple(_projection_text(r)),
            "age": tuple(_age_text(r)),
            "state": tuple(_state_text(r)),
            "credit": tuple(_credit_text(r)),
            "income": tuple(_income_text(r)),
            "assumptions": tuple(_assumption_text(r)),
        },
        suggestions=tuple(_suggestions(r)),
        assumption_warnings=tuple(_assumption_warnings(r)),
        assumption_comparison=_assumption_comparison(r),
        data_notes=r.profile.notes,
    )


SECTION_TITLES = {
    "breakdown": "What you own and owe",
    "projections": "Where you're headed",
    "age": "You vs. people your age",
    "state": "You vs. your state",
    "credit": "Credit score",
    "income": "Income and savings",
    "assumptions": "Assumptions used",
}
_MARK = {"bad": "[!!]", "warning": "[! ]", "good": "[ok]"}


def render_text(rep: Report) -> str:
    """The report for the terminal."""
    line = "=" * 64
    out = [line, f"NET WORTH REPORT · GRADE {rep.grade} · {rep.score:.0f}/100", line, "", rep.headline, ""]
    out += rep.verdict
    out += ["", "FINDINGS"] + [f"  {_MARK[f.severity]} {f.text}" for f in rep.findings]
    for key, title in SECTION_TITLES.items():
        out += ["", title.upper()] + [f"  {s}" for s in rep.sections[key]]
    if rep.assumption_warnings or rep.assumption_comparison:
        out += ["", "ASSUMPTION CHECK"] + [f"  [! ] {w.message}" for w in rep.assumption_warnings]
        if rep.assumption_comparison:
            out.append(f"  {rep.assumption_comparison}")
    out += ["", "WHAT TO DO NEXT"]
    for i, s in enumerate(rep.suggestions, start=1):
        out += [f"  {i}. {s.title}", f"     Why: {s.reason}", f"     Impact: {s.impact}"]
    if rep.data_notes:
        out += ["", "ABOUT YOUR FILE"] + [f"  - {n}" for n in rep.data_notes]
    out += ["", rep.disclaimer]
    return "\n".join(out)
