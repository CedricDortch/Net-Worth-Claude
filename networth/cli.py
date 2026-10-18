"""Net Worth Analyzer CLI.

Read the file, run the personal information check, build the profile (asking
for anything missing), analyze it, print the honest report, and write index.html.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TypeVar

from networth import analysis
from networth import assumptions
from networth import extractor
from networth import render
from networth import report
from networth import security
from networth.errors import InvalidInputError, NetWorthError, PersonalInformationError
from networth.formatting import format_money, format_percent
from networth.models import NetWorthProfile, Person
from networth.normalize import (
    validate_age, validate_credit_score, validate_expenses, validate_household, validate_state,
)
from networth.constants import STATES
from networth.parsers import parse_file

T = TypeVar("T")
AskFn = Callable[[str], str]
MAX_TRIES = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m networth",
        description="Analyze an anonymized net worth document and write an honest report.",
    )
    parser.add_argument("file", type=Path, help="net worth document (.pdf .docx .xlsx .xls .csv .txt .md .json)")

    profile = parser.add_argument_group("profile (overrides the file; asked for if missing)")
    profile.add_argument("--household", metavar="TYPE", help="single or couple")
    profile.add_argument("--age", nargs="+", metavar="AGE", help="age (couples: two ages)")
    profile.add_argument("--credit-score", nargs="+", metavar="SCORE", help="FICO score (couples: two scores)")
    profile.add_argument("--state", help="state name or 2-letter code, e.g. Ohio or OH")
    profile.add_argument("--expenses", metavar="DOLLARS", help="monthly expenses")
    profile.add_argument("--no-input", action="store_true", help="never prompt; fail if something is missing")

    growth = parser.add_argument_group("growth assumptions (override the file and defaults)")
    for spec in assumptions.SPECS:
        growth.add_argument(spec.flag, dest=spec.field, metavar="N",
                            help=f"{spec.label.lower()} ({spec.describe_range()})")

    output = parser.add_argument_group("output")
    output.add_argument("--out", type=Path, default=Path("index.html"), metavar="PATH",
                        help="where to write the HTML report (default: index.html)")
    output.add_argument("--open", action="store_true", help="open the report in your browser when done")
    return parser


# ---------------------------------------------------------------------------
# Profile fields: CLI > file > prompt
# ---------------------------------------------------------------------------

def _ask_until_valid(question: str, validate: Callable[[str], T], ask: AskFn) -> T:
    for _ in range(MAX_TRIES):
        try:
            return validate(ask(question))
        except InvalidInputError as exc:
            print(f"  {exc}", file=sys.stderr)
    raise InvalidInputError(f"No valid answer after {MAX_TRIES} tries.")


def _resolve(name: str, flag: str, cli: str | None, from_file: str | None,
             validate: Callable[[str], T], ask: AskFn | None) -> T:
    raw = cli if cli is not None else from_file
    if raw is not None and str(raw).strip():
        try:
            return validate(raw)
        except InvalidInputError as exc:
            if ask is None:
                raise
            print(f"  {exc}", file=sys.stderr)
    elif ask is None:
        raise InvalidInputError(f"{name} is missing. Add it to the file or pass {flag}.")
    return _ask_until_valid(f"{name}: ", validate, ask)


def _nth(values: list[str] | None, i: int) -> str | None:
    return values[i] if values and len(values) > i else None


def resolve_profile(args: argparse.Namespace, ex: extractor.Extracted, ask: AskFn | None) -> NetWorthProfile:
    household = validate_household(args.household or ex.household_type or "single")
    count = 2 if household == "couple" else 1

    people = []
    for i in range(count):
        who = f"Partner {i + 1} " if count == 2 else ""
        age = _resolve(f"{who}age".capitalize(), "--age", _nth(args.age, i), ex.ages.get(i + 1),
                       lambda v, w=who: validate_age(v, f"{w}age".capitalize()), ask)
        score = _resolve(f"{who}credit score".capitalize(), "--credit-score", _nth(args.credit_score, i),
                         ex.credit_scores.get(i + 1),
                         lambda v, w=who: validate_credit_score(v, f"{w}credit score".capitalize()), ask)
        people.append(Person(age=age, credit_score=score))

    state = _resolve("State", "--state", args.state, ex.state, validate_state, ask)
    expenses = validate_expenses(args.expenses) if args.expenses is not None else ex.monthly_expenses

    cli_assumptions = {spec.field: getattr(args, spec.field) for spec in assumptions.SPECS}
    growth = assumptions.resolve(ex.assumptions, cli_assumptions)

    return extractor.build_profile(
        ex, household_type=household, people=people, state=state,
        monthly_expenses=expenses, assumptions=growth,
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def describe_profile(profile: NetWorthProfile, filename: str) -> str:
    as_of = f" (as of {profile.as_of.isoformat()})" if profile.as_of else ""
    out = [f"Read {filename}{as_of}", ""]

    if profile.household_type == "couple":
        who = " · ".join(f"Partner {i}: age {p.age}, credit score {p.credit_score}"
                         for i, p in enumerate(profile.people, start=1))
        out.append(f"Household: Couple · {who} · {STATES[profile.state]} ({profile.state})")
    else:
        p = profile.people[0]
        out.append(f"Household: Single · Age {p.age} · {STATES[profile.state]} ({profile.state}) "
                   f"· Credit score {p.credit_score}")

    width = max([len(i.label) for i in (*profile.assets, *profile.debts)] + [10])
    couple = profile.household_type == "couple"

    def item_line(i) -> str:
        rate = f"  {format_percent(i.interest_rate)}" if i.interest_rate is not None else ""
        owner = f"  [{i.owner.replace('partner', 'Partner ').title()}]" if couple else ""
        return f"  {i.label.ljust(width)}  {i.category.ljust(12)} {format_money(i.value):>12}{rate}{owner}"

    out += ["", f"Assets: {format_money(profile.total_assets)}"]
    out += [item_line(i) for i in profile.assets] or ["  none listed"]
    out += ["", f"Debts: {format_money(profile.total_debts)}"]
    out += [item_line(i) for i in profile.debts] or ["  none listed"]
    out += ["", f"Net worth: {format_money(profile.net_worth)}"]

    h = profile.net_worth_history
    if h:
        first, last = next(iter(h)), next(reversed(h))
        out.append(f"Net worth history: {len(h)} points, {first.isoformat()} to {last.isoformat()} "
                   f"({format_money(h[first])} -> {format_money(h[last])})")
    else:
        out.append("Net worth history: none")
    inc = profile.income_history
    out.append(f"Income history: {len(inc)} years, {min(inc)}-{max(inc)}" if inc else "Income history: none")
    out.append("Monthly expenses: " + (format_money(profile.monthly_expenses)
                                       if profile.monthly_expenses is not None else "not given"))

    return "\n".join(out)


def run(args: argparse.Namespace, ask: AskFn | None) -> None:
    doc = parse_file(args.file)
    security.check(doc)
    ex = extractor.extract(doc)
    profile = resolve_profile(args, ex, ask)
    print(describe_profile(profile, args.file.name))
    print()
    result = analysis.analyze(profile)
    rep = report.build_report(result)
    print(report.render_text(rep))

    out = render.write_report(result, rep, args.out).resolve()
    print(f"\nReport written to {out}")
    if args.open:
        import webbrowser
        webbrowser.open(out.as_uri())


def main(argv: Sequence[str] | None = None, ask: AskFn | None = input) -> int:
    args = build_parser().parse_args(argv)
    if args.no_input or (ask is input and not sys.stdin.isatty()):
        ask = None
    try:
        run(args, ask)
    except PersonalInformationError as exc:
        print(security.format_findings(exc.findings), file=sys.stderr)
        return exc.exit_code
    except NetWorthError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return exc.exit_code
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
