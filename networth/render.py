"""Write index.html from an AnalysisResult + Report. The only module that writes the report file.

The page is one static file: all data is embedded as a JSON blob, the only external
resource is Chart.js from a pinned CDN URL, and every chart has a table twin so the
page still works (and prints) without JavaScript or a network connection.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from networth import assumptions as assumptions_mod
from networth.analysis import AnalysisResult
from networth.constants import STATES
from networth.formatting import format_money, format_percent
from networth.report import SECTION_TITLES, Report

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
CHART_JS_URL = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"

CATEGORY_LABELS = {
    "cash": "Cash", "investments": "Investments", "retirement": "Retirement", "real_estate": "Real estate",
    "vehicles": "Vehicles", "other": "Other", "mortgage": "Mortgage", "auto": "Auto loans",
    "student": "Student loans", "credit_card": "Credit cards", "personal": "Personal loans",
}
# Fixed category -> categorical slot, so a category keeps its color in every report.
ASSET_SLOTS = {"cash": 1, "investments": 2, "retirement": 3, "real_estate": 4, "vehicles": 5, "other": 6}
STATUS_LABEL = {"bad": "Problem", "warning": "Warning", "good": "Good"}


def _year_fraction(d: dt.date) -> float:
    return round(d.year + (d.timetuple().tm_yday - 1) / 365.25, 4)


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _table(headers: list[str], rows: list[list[str]]) -> dict[str, Any]:
    return {"headers": headers, "rows": rows}


def _score_status(score: float | None) -> tuple[str, str]:
    if score is None:
        return "none", "No data"
    if score >= 70:
        return "good", "Strong"
    if score >= 40:
        return "warning", "Needs work"
    return "critical", "Weak"


# ---------------------------------------------------------------------------
# View model
# ---------------------------------------------------------------------------

def build_view(r: AnalysisResult, rep: Report, generated: dt.date) -> dict[str, Any]:
    t, p, a, s, c, prof = r.totals, r.projections, r.age_rank, r.state, r.credit, r.profile
    charts: dict[str, Any] = {}
    tables: dict[str, dict[str, Any]] = {}
    hidden: dict[str, str] = {}

    # --- Assets and debts by category
    if t.assets_by_category or t.debts_by_category:
        cats = [k for k in (*ASSET_SLOTS, "mortgage", "auto", "student", "credit_card", "personal")
                if k in t.assets_by_category or k in t.debts_by_category]
        if t.debts_by_category.get("other") and "other" not in cats:
            cats.append("other")
        charts["categories"] = {
            "labels": [CATEGORY_LABELS[k] for k in cats],
            "assets": [t.assets_by_category.get(k, 0) if k in ASSET_SLOTS else 0 for k in cats],
            "debts": [t.debts_by_category.get(k, 0) for k in cats],
            "asset_pcts": [f"{t.asset_mix[k]:.0f}%" if k in t.asset_mix else "" for k in cats],
            "has_debts": bool(t.debts_by_category),
        }
        tables["categories"] = _table(
            ["Item", "Category", "Type", "Value"],
            [[i.label, CATEGORY_LABELS[i.category], "Asset", format_money(i.value)] for i in prof.assets]
            + [[d.label, CATEGORY_LABELS[d.category],
                "Debt" + (f" ({format_percent(d.interest_rate)})" if d.interest_rate is not None else ""),
                format_money(d.value)] for d in prof.debts])

    # --- Asset mix: shown as share labels on the category bars, plus a table
    if t.asset_mix:
        tables["mix"] = _table(["Category", "Value", "Share of assets"],
                               [[CATEGORY_LABELS[k], format_money(t.assets_by_category[k]), f"{v:.1f}%"]
                                for k, v in sorted(t.asset_mix.items(), key=lambda kv: ASSET_SLOTS[kv[0]])])

    # --- History
    hist = prof.net_worth_history
    if len(hist) >= 2:
        charts["history"] = [{"x": _year_fraction(d), "date": d.isoformat(), "y": v} for d, v in hist.items()]
        tables["history"] = _table(["Date", "Net worth"], [[d.isoformat(), format_money(v)] for d, v in hist.items()])
    else:
        hidden["history"] = "Add at least two dated net worth values to see your history."

    # --- Projections
    x0 = _year_fraction(p.start_date)
    years = list(range(len(p.scenarios["expected"].nominal)))
    charts["projection"] = {
        "x": [round(x0 + y, 4) for y in years],
        "start_year": p.start_date.year,
        "expected": list(p.scenarios["expected"].nominal),
        "conservative": list(p.scenarios["conservative"].nominal),
        "optimistic": list(p.scenarios["optimistic"].nominal),
        "default": list(p.default_expected.nominal) if p.default_expected else None,
        "history": charts.get("history", []),
        "ages": {str(y): list(v) for y, v in p.ages_at.items()},
    }
    milestones = []
    for y in (5, 10, 15, 20):
        milestones.append({
            "years": y, "ages": " & ".join(str(x) for x in p.ages_at[y]),
            "year": p.start_date.year + y,
            "expected": format_money(p.at(y), compact=True),
            "real": format_money(p.at(y, real=True), compact=True),
            "low": format_money(p.at(y, "conservative"), compact=True),
            "high": format_money(p.at(y, "optimistic"), compact=True),
        })
    tables["projection"] = _table(
        ["Year", "Age", "Conservative", "Expected", "Optimistic", "Expected (today's $)"]
        + (["Default assumptions"] if p.default_expected else []),
        [[str(p.start_date.year + y), " & ".join(str(x) for x in p.ages_at[y]),
          format_money(p.at(y, "conservative")), format_money(p.at(y)), format_money(p.at(y, "optimistic")),
          format_money(p.at(y, real=True))]
         + ([format_money(p.default_expected.at(y))] if p.default_expected else [])
         for y in years])

    # --- Age: percentile ladder for the user's bracket
    std = a.standard
    pct = std.bracket.percentiles
    shown = [x for x in (10, 25, 50, 75, 90) if x in pct]
    above = [x for x in (95, 99) if x in pct and pct[x] > std.net_worth]
    if std.net_worth > pct.get(90, float("inf")) and above:
        shown.append(above[0])
    ladder = [{"label": f"{_ordinal(x)} percentile", "value": pct[x], "you": False} for x in shown]
    ladder.append({"label": "You", "value": std.net_worth, "you": True})
    ladder.sort(key=lambda d: d["value"])
    charts["age_ladder"] = {"bars": ladder, "bracket": std.bracket.label}
    tables["age_ladder"] = _table(["Percentile", f"Net worth, ages {std.bracket.label.lower()}"],
                                  [[_ordinal(k), format_money(v)] for k, v in sorted(pct.items())]
                                  + [["You", format_money(std.net_worth)]])

    # --- Age: medians by bracket
    ref = r.ref
    short_label = {"under_35": "<35", "75_plus": "75+"}
    medians = [{"label": b.label, "short": short_label.get(b.key, b.label), "value": b.median,
                "you": b.key == std.bracket.key} for b in ref.age.brackets]
    charts["age_medians"] = {"bars": medians, "you": std.net_worth}
    tables["age_medians"] = _table(["Age of household head", "Median net worth", "Mean net worth"],
                                   [[b.label, format_money(b.median), format_money(b.mean)] for b in ref.age.brackets])

    # --- State
    state_bars = [
        {"label": "You", "value": s.net_worth, "you": True},
        {"label": f"{s.name} median", "value": s.state_median, "you": False},
        {"label": "U.S. median", "value": s.national_median, "you": False},
        {"label": "You, at national prices", "value": s.adjusted_net_worth, "you": True},
    ]
    tables["state"] = _table(["", "Net worth"], [[b["label"], format_money(b["value"])] for b in state_bars])
    state_bars[-1]["lines"] = ["You, at", "national prices"]  # two-line axis label so it fits on phones
    charts["state"] = {"bars": state_bars}

    # --- Income
    inc = r.income
    if inc and inc.net_worth_change:
        yrs = sorted(inc.net_worth_change)
        charts["income"] = {"labels": [str(y) for y in yrs], "income": [inc.income[y] for y in yrs],
                            "change": [inc.net_worth_change[y] for y in yrs]}
        tables["income"] = _table(["Year", "Income", "Change in net worth", "Savings rate"],
                                  [[str(y), format_money(inc.income[y]), format_money(inc.net_worth_change[y]),
                                    f"{inc.savings_rate[y]:.0f}%" if y in inc.savings_rate else "n/a"] for y in yrs])
    else:
        hidden["income"] = ("Add income history (year and amount) next to your net worth history to see your "
                            "savings rate.")

    # --- Couples: ownership
    if prof.household_type == "couple":
        owners = ["partner1", "partner2", "joint"]
        names = {"partner1": "Partner 1", "partner2": "Partner 2", "joint": "Joint"}
        charts["owners"] = {"labels": [names[o] for o in owners],
                            "assets": [t.by_owner[o][0] for o in owners],
                            "debts": [t.by_owner[o][1] for o in owners]}
        tables["owners"] = _table(["Owner", "Assets", "Debts"],
                                  [[names[o], format_money(t.by_owner[o][0]), format_money(t.by_owner[o][1])]
                                   for o in owners])

    # --- Credit meter (HTML)
    span = 850 - 300
    pos = lambda score: round((score - 300) / span * 100, 2)  # noqa: E731
    # Keep labels inside the card: anchor left near the start, right near the end.
    shift = lambda p_: "0%" if p_ < 15 else "-100%" if p_ > 85 else "-50%"  # noqa: E731
    credit_view = {
        "tiers": [{"name": tier.name, "width": round((tier.max - tier.min + 1) / span * 100, 2),
                   "step": i + 1, "range": f"{tier.min}-{tier.max}"}
                  for i, tier in enumerate(ref.credit.tiers)],
        "people": [{"label": (f"Partner {i}" if len(c.people) == 2 else "You"), "score": pc.score,
                    "pos": pos(pc.score), "shift": shift(pos(pc.score)), "tier": pc.tier.name}
                   for i, pc in enumerate(c.people, start=1)],
        "marks": [{"label": f"{s.name} avg {c.state_average}", "pos": pos(c.state_average),
                   "shift": shift(pos(c.state_average))},
                  {"label": f"U.S. avg {c.national_average}", "pos": pos(c.national_average),
                   "shift": shift(pos(c.national_average))}],
    }

    # --- Score rows (HTML)
    score_rows = []
    for comp in r.score.components:
        status, word = _score_status(comp.score)
        score_rows.append({"label": comp.label, "score": comp.score, "weight": comp.weight,
                           "base_weight": comp.base_weight, "detail": comp.detail,
                           "status": status, "word": word})

    # --- Tiles
    cred = c.people[0] if len(c.people) == 1 else min(c.people, key=lambda x: x.score)
    tiles = [
        {"label": "Grade", "value": rep.grade, "sub": f"{rep.score:.0f} out of 100"},
        {"label": f"Rank, ages {std.bracket.label.lower()}", "value": std.phrase.capitalize(),
         "sub": f"{_ordinal(round(std.percentile))} percentile"},
        {"label": "Credit" if len(c.people) == 1 else "Lower credit score", "value": str(cred.score),
         "sub": cred.tier.name},
        {"label": "Debt to assets", "value": f"{t.debt_to_asset:.0%}" if t.debt_to_asset is not None else "n/a",
         "sub": "no debt" if not t.total_debts else format_money(t.total_debts) + " owed"},
    ]

    a_ = prof.assumptions
    assumption_rows = []
    for spec in assumptions_mod.SPECS:
        value = getattr(a_, spec.field)
        shown = ("from your history" if value is None else
                 format_money(value) + "/month" if spec.unit == "$" else format_percent(value))
        assumption_rows.append({"label": spec.label, "value": shown, "source": a_.source.get(spec.field, "default")})

    findings_by_section: dict[str, list[dict[str, str]]] = {}
    for f in rep.findings:
        findings_by_section.setdefault(f.section, []).append(
            {"severity": f.severity, "label": STATUS_LABEL[f.severity], "text": f.text})

    return {
        "generated": generated.isoformat(),
        "as_of": p.start_date.isoformat(),
        "household": ("Couple" if prof.household_type == "couple" else "Single"),
        "ages": " & ".join(str(x.age) for x in prof.people),
        "state_name": STATES[prof.state],
        "net_worth": format_money(t.net_worth),
        "assets": format_money(t.total_assets),
        "debts": format_money(t.total_debts),
        "tiles": tiles,
        "report": rep,
        "titles": SECTION_TITLES,
        "findings": findings_by_section,
        "milestones": milestones,
        "assumption_rows": assumption_rows,
        "credit": credit_view,
        "score_rows": score_rows,
        "missing": r.score.missing,
        "tables": tables,
        "hidden": hidden,
        "has": {k: k in charts for k in ("categories", "history", "income", "owners")}
               | {"default": p.default_expected is not None},
        "income_given": r.income is not None,
        "category_height": 80 + 44 * len(charts.get("categories", {}).get("labels", [])),
        "sources": [src.citation() for src in ref.sources],
        "chart_js_url": CHART_JS_URL,
        "chart_json": _safe_json({"charts": charts}),
    }


def _safe_json(data: Any) -> str:
    """JSON that can't break out of a <script> element."""
    return (json.dumps(data, separators=(",", ":"))
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_html(r: AnalysisResult, rep: Report, generated: dt.date | None = None) -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape(["html", "j2"]),
                      trim_blocks=True, lstrip_blocks=True)
    return env.get_template("index.html.j2").render(**build_view(r, rep, generated or dt.date.today()))


def write_report(r: AnalysisResult, rep: Report, out: Path, generated: dt.date | None = None) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(r, rep, generated), encoding="utf-8")
    return out
