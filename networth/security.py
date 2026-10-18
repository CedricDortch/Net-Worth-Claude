"""Personal information (PII) scan. Runs on raw parser output before anything else.

How it works:
- The document is turned into segments: one per text line, and one per table row
  (cells joined with " | ", each cell remembering its location and column header).
- Detectors run in priority order. Each match claims its span of text so a later,
  looser detector can't report the same characters again (e.g. an SSN is not also
  reported as an account number).
- "Safe" patterns (money, dates, year ranges, percentages) claim their spans
  without reporting, so the catch-all digit-run detector never sees them.

Findings only ever carry masked values.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

from networth.constants import STATES
from networth.errors import PersonalInformationError
from networth.parsers.document import ParsedDocument, Table

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    kind: str      # human label, e.g. "account number"
    location: str  # e.g. "Line 4", "Cell B7"
    masked: str    # never the full value


@dataclass(frozen=True)
class _Span:
    start: int
    end: int
    location: str
    header: str | None = None  # lower-cased column header for table cells


@dataclass(frozen=True)
class Segment:
    text: str
    spans: tuple[_Span, ...]

    def span_at(self, pos: int) -> _Span:
        for span in self.spans:
            if span.start <= pos < span.end:
                return span
        return self.spans[-1] if pos >= self.spans[-1].start else self.spans[0]


@dataclass(frozen=True)
class _Match:
    start: int
    end: int
    value: str      # the sensitive part
    value_pos: int  # where `value` starts, for the location


@dataclass(frozen=True)
class _Detector:
    kind: str
    find: Callable[[Segment], Iterable[_Match]]
    masker: Callable[[str], str]
    report: bool = True


# ---------------------------------------------------------------------------
# Masking
# ---------------------------------------------------------------------------


def _visible(n: int) -> int:
    """How many trailing characters may stay visible. Short values are hidden fully."""
    return 4 if n >= 9 else 2 if n >= 5 else 0


def mask_digits(value: str) -> str:
    """Hide all digits except the last few; keep separators. 123-45-6789 -> ***-**-6789."""
    total = sum(c.isdigit() for c in value)
    keep = _visible(total)
    seen = 0
    out = []
    for c in value:
        if c.isdigit():
            seen += 1
            out.append(c if seen > total - keep else "*")
        else:
            out.append(c)
    return "".join(out).strip()


def mask_alnum(value: str) -> str:
    """Hide letters and digits except the last few. ABC-1234 -> ***-*234."""
    total = sum(c.isalnum() for c in value)
    keep = _visible(total)
    seen = 0
    out = []
    for c in value:
        if c.isalnum():
            seen += 1
            out.append(c if seen > total - keep else "*")
        else:
            out.append(c)
    return "".join(out).strip()


def mask_all(value: str) -> str:
    return re.sub(r"[A-Za-z0-9]", "*", value).strip()


def mask_address(value: str) -> str:
    """Hide house/unit numbers, keep the street words: 123 Main St -> *** Main St."""
    return re.sub(r"\d", "*", value).strip()


def mask_email(value: str) -> str:
    local, _, domain = value.partition("@")
    tld = domain.rsplit(".", 1)[-1] if "." in domain else ""
    return f"{local[:1]}***@***.{tld}"


def mask_name(value: str) -> str:
    return " ".join(f"{w[:1]}***" for w in value.split())


# ---------------------------------------------------------------------------
# Detector helpers
# ---------------------------------------------------------------------------

_SEP = r"[\s:#|=\-]*"  # between a keyword and its value ("Acct #: ", "Name | ")
_NUM_LABEL = r"(?:\s*(?:no\.?|num(?:ber)?\.?|#))?"


def _regex(pattern: str, flags: int = re.IGNORECASE, group: int = 1,
           accept: Callable[[str, Segment, re.Match[str]], bool] | None = None,
           ) -> Callable[[Segment], Iterator[_Match]]:
    """Detector from a regex. `group` is the sensitive part (0 = whole match)."""
    compiled = re.compile(pattern, flags)

    def find(seg: Segment) -> Iterator[_Match]:
        for m in compiled.finditer(seg.text):
            value = m.group(group)
            if value is None or (accept and not accept(value, seg, m)):
                continue
            yield _Match(m.start(), m.end(), value, m.start(group))

    return find


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def luhn_valid(number: str) -> bool:
    """Credit card checksum."""
    digits = [int(d) for d in _digits(number)]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return bool(digits) and total % 10 == 0


def aba_valid(number: str) -> bool:
    """US bank routing number checksum: 3*(d1+d4+d7) + 7*(d2+d5+d8) + (d3+d6+d9) ≡ 0 mod 10."""
    d = [int(c) for c in _digits(number)]
    if len(d) != 9 or not any(d):
        return False
    return (3 * (d[0] + d[3] + d[6]) + 7 * (d[1] + d[4] + d[7]) + (d[2] + d[5] + d[8])) % 10 == 0


_MONEY_HEADERS = {
    "value", "amount", "balance", "worth", "net worth", "networth",
    "income", "interestrate", "interest rate", "rate", "total",
}
_PLAIN_NUMBER = re.compile(r"^\$?\d+(?:\.\d+)?$")


def _is_money_cell(seg: Segment, m: re.Match[str]) -> bool:
    """A bare number that is the whole content of a Value/Amount/... column cell."""
    span = seg.span_at(m.start())
    if span.header not in _MONEY_HEADERS:
        return False
    return bool(_PLAIN_NUMBER.match(seg.text[span.start:span.end].strip()))


def _bare_run_ok(min_digits: int, max_digits: int) -> Callable[[str, Segment, re.Match[str]], bool]:
    """Accept a bare digit run unless it's a plain money cell of ≤ 9 digits."""
    def accept(value: str, seg: Segment, m: re.Match[str]) -> bool:
        n = len(_digits(value))
        if not min_digits <= n <= max_digits:
            return False
        return not (n <= 9 and _is_money_cell(seg, m))
    return accept


def _min_digits(n: int) -> Callable[[str, Segment, re.Match[str]], bool]:
    return lambda value, seg, m: len(_digits(value)) >= n


def _has_digit(value: str, seg: Segment, m: re.Match[str]) -> bool:
    return any(c.isdigit() for c in value)


def _letter_and_digit(value: str, seg: Segment, m: re.Match[str]) -> bool:
    return any(c.isdigit() for c in value) and any(c.isalpha() for c in value)


# Words that look like names after "Name:"/"Owner:" but aren't.
_NOT_NAMES = {
    "joint", "single", "couple", "self", "me", "us", "none", "n/a", "na", "unknown",
    "household", "both", "partner", "value", "label", "amount", "balance", "category",
    "section", "owner", "type", "item", "description", "interestrate", "interest rate",
}
_NAME_HEADERS = {"name", "owner", "account holder", "holder", "full name"}


def _is_name(value: str, seg: Segment, m: re.Match[str]) -> bool:
    return value.strip().lower() not in _NOT_NAMES


def _find_header_names(seg: Segment) -> Iterator[_Match]:
    """Cells under a Name/Owner column must be Partner 1 / Partner 2 / Joint, not names."""
    for span in seg.spans:
        if span.header not in _NAME_HEADERS:
            continue
        cell = seg.text[span.start:span.end].strip()
        if re.fullmatch(r"[A-Za-z][A-Za-z.' -]{1,60}", cell) and cell.lower() not in _NOT_NAMES:
            start = seg.text.index(cell, span.start)
            yield _Match(start, start + len(cell), cell, start)


_STATE_ABBR = "|".join(STATES)
_STATE_NAMES = "|".join(re.escape(n) for n in STATES.values())
_STREET_SUFFIX = (
    r"(?i:st|street|ave|avenue|rd|road|blvd|boulevard|ln|lane|dr|drive|ct|court|way|"
    r"pl|place|ter|terrace|pkwy|parkway|hwy|highway|cir|circle|trl|trail)"
)
_MONTH_DATE = r"[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4}"
_NUM_DATE = r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}-\d{2}-\d{2}"
_NOT_IN_NUMBER_BEFORE = r"(?<![\w$.,])"
_NOT_IN_NUMBER_AFTER = r"(?![\d,%]|\.\d)"

# Priority order matters: specific, keyword-anchored detectors first.
_DETECTORS: tuple[_Detector, ...] = (
    _Detector("email address", _regex(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", group=0), mask_email),
    _Detector("Social Security number", _regex(
        r"\b(?:ssn|social\s+security)" + _NUM_LABEL + _SEP + r"(\d{3}[- ]?\d{2}[- ]?\d{4})\b"), mask_digits),
    _Detector("Social Security number", _regex(r"\b(\d{3}-\d{2}-\d{4}|\d{3} \d{2} \d{4})\b"), mask_digits),
    _Detector("date of birth", _regex(
        r"\b(?:dob|d\.o\.b\.?|date\s+of\s+birth|birth\s*date|birthday|born(?:\s+on)?)" + _SEP
        + rf"({_NUM_DATE}|{_MONTH_DATE})"), mask_all),
    _Detector("routing number", _regex(
        r"\b(?:routing|aba|rtn)(?:\s*transit)?" + _NUM_LABEL + _SEP + r"(\d{9})\b"), mask_digits),
    _Detector("account number", _regex(
        r"\b(?:acct|account|a/c)\b\.?" + _NUM_LABEL
        + r"(?:\s*(?:ending(?:\s+in)?|ends\s+in))?" + _SEP
        + r"((?:[x*•]+[- ]?)?\d{2,}(?:[ -]\d{2,})*)",
        accept=_min_digits(4)), mask_digits),
    _Detector("credit/debit card number", _regex(
        _NOT_IN_NUMBER_BEFORE + r"(\d(?:[ -]?\d){12,18})" + _NOT_IN_NUMBER_AFTER,
        accept=lambda v, s, m: luhn_valid(v)), mask_digits),
    _Detector("phone number", _regex(
        r"(?<![\d$])((?:\+?1[\s.-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.-])\d{3}[\s.-]\d{4})(?!\d)"), mask_digits),
    _Detector("ZIP code", _regex(r"\b(\d{5}-\d{4})\b"), mask_digits),
    _Detector("ZIP code", _regex(r"\b(?:zip|postal)(?:\s*code)?" + _SEP + r"(\d{5}(?:-\d{4})?)\b"), mask_digits),
    _Detector("ZIP code", _regex(
        rf"\b(?:{_STATE_ABBR}|(?i:{_STATE_NAMES}))\s*,?\s+(\d{{5}}(?:-\d{{4}})?)\b", flags=0), mask_digits),
    _Detector("street address", _regex(r"\b(p\.?\s?o\.?\s*box\s*#?\s*\d+)"), mask_address),
    _Detector("street address", _regex(
        r"\b(\d{1,6}\s+(?:[A-Z0-9][A-Za-z0-9.'-]*\s+){1,4}" + _STREET_SUFFIX + r")\b\.?", flags=0), mask_address),
    _Detector("street address", _regex(
        r"\b((?:apt|apartment|suite|ste)\.?\s*#?\s*[A-Z0-9-]+)\b", accept=_has_digit), mask_address),
    _Detector("VIN", _regex(r"\b([A-HJ-NPR-Z0-9]{17})\b", accept=_letter_and_digit), mask_alnum),
    _Detector("license plate", _regex(
        r"\b(?:license\s+plate|plate|tag)" + _NUM_LABEL + _SEP + r"([A-Z0-9]{1,8}(?:[- ][A-Z0-9]{1,4})?)\b",
        accept=lambda v, s, m: len(re.sub(r"\W", "", v)) >= 2 and _has_digit(v, s, m)), mask_alnum),
    _Detector("driver's license / passport number", _regex(
        r"\b(?:driver'?s?\s+licen[cs]e|licen[cs]e|dl|passport)" + _NUM_LABEL + _SEP + r"([A-Z0-9][A-Z0-9-]{4,})\b",
        accept=_has_digit), mask_alnum),
    _Detector("name", _regex(
        r"\b(?:full\s+name|first\s+name|last\s+name|name|account\s+holder|holder|owner|prepared\s+for|"
        r"client|customer|borrower|beneficiary|spouse)\s*[:|]\s*([A-Za-z][A-Za-z.' -]{0,60}?)\s*(?=$|\|)",
        accept=_is_name), mask_name),
    _Detector("name", _find_header_names, mask_name),
    # --- Safe patterns: claim the text, report nothing. ---
    _Detector("money", _regex(r"\$\s?\d[\d,]*(?:\.\d+)?|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b", group=0), str, report=False),
    _Detector("percent", _regex(r"\d+(?:\.\d+)?\s?%", group=0), str, report=False),
    _Detector("year range", _regex(r"\b(?:19|20)\d{2}\s*[-–]\s*(?:19|20)\d{2}\b", group=0), str, report=False),
    _Detector("date", _regex(rf"\b(?:{_NUM_DATE})\b", group=0), str, report=False),
    _Detector("decimal", _regex(r"\b\d+\.\d+\b", group=0), str, report=False),
    # --- Catch-alls for unlabeled numbers. ---
    _Detector("routing number", _regex(
        _NOT_IN_NUMBER_BEFORE + r"(\d{9})" + _NOT_IN_NUMBER_AFTER,
        accept=lambda v, s, m: aba_valid(v) and not _is_money_cell(s, m)), mask_digits),
    _Detector("account number", _regex(
        _NOT_IN_NUMBER_BEFORE + r"(\d(?:[ -]?\d){7,16})" + _NOT_IN_NUMBER_AFTER,
        accept=_bare_run_ok(8, 17)), mask_digits),
)


# ---------------------------------------------------------------------------
# Segments
# ---------------------------------------------------------------------------

_HEADER_WORDS = {"section", "label", "value", "category", "owner", "item", "amount",
                 "balance", "interestrate", "interest rate", "description", "name"}


def _table_segments(table: Table) -> Iterator[Segment]:
    headers: tuple[str, ...] = ()
    first = next((i for i, r in enumerate(table.rows) if any(c.strip() for c in r)), None)
    if first is not None:
        lowered = tuple(c.strip().lower() for c in table.rows[first])
        if any(c in _HEADER_WORDS for c in lowered):
            headers = lowered

    for r, row in enumerate(table.rows):
        parts: list[str] = []
        spans: list[_Span] = []
        pos = 0
        for c, cell in enumerate(row):
            if not cell.strip():
                continue
            if parts:
                parts.append(" | ")
                pos += 3
            header = headers[c] if c < len(headers) and r != first else None
            spans.append(_Span(pos, pos + len(cell), table.cell_location(r, c), header))
            parts.append(cell)
            pos += len(cell)
        if spans:
            yield Segment("".join(parts), tuple(spans))


def segments(doc: ParsedDocument) -> Iterator[Segment]:
    for line in doc.lines:
        if line.text.strip():
            yield Segment(line.text, (_Span(0, len(line.text), line.location),))
    for table in doc.tables:
        yield from _table_segments(table)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_segment(seg: Segment) -> list[Finding]:
    claimed: list[tuple[int, int]] = []
    findings: list[Finding] = []
    for det in _DETECTORS:
        for m in det.find(seg):
            if any(m.start < end and start < m.end for start, end in claimed):
                continue
            claimed.append((m.start, m.end))
            if det.report:
                findings.append(Finding(det.kind, seg.span_at(m.value_pos).location, det.masker(m.value)))
    return findings


def scan(doc: ParsedDocument) -> list[Finding]:
    """All PII findings in document order, de-duplicated."""
    seen: set[tuple[str, str, str]] = set()
    results: list[Finding] = []
    for seg in segments(doc):
        for f in scan_segment(seg):
            key = (f.kind, f.location, f.masked)
            if key not in seen:
                seen.add(key)
                results.append(f)
    return results


def check(doc: ParsedDocument) -> None:
    """Raise PersonalInformationError if the document contains any PII."""
    findings = scan(doc)
    if findings:
        raise PersonalInformationError(findings)


_HINTS: dict[str, str] = {
    "account number": "If a long number is a dollar amount, write it with $ or commas (e.g. $12,000,000). "
                      "Otherwise replace account numbers with labels like 'Bank Account 1'.",
    "routing number": "Remove routing numbers. Use labels like 'Bank Account 1'.",
    "credit/debit card number": "Remove card numbers. Use labels like 'Credit Card 1'.",
    "street address": "Remove addresses. For a home use a label like 'House 1'.",
    "ZIP code": "Remove ZIP codes. Only the state is needed.",
    "license plate": "Remove plate numbers. Use labels like 'Car 1'.",
    "VIN": "Remove VINs. Use labels like 'Car 1'.",
    "name": "Remove names. For couples use 'Partner 1', 'Partner 2', or 'Joint'.",
    "date of birth": "Remove your date of birth. Only your age is needed.",
}


def format_findings(findings: Iterable[Finding]) -> str:
    """The message shown when the security check fails."""
    findings = list(findings)
    width = max(len(f.location) for f in findings) + 2
    lines = ["SECURITY CHECK FAILED — personal information detected.", ""]
    lines += [f"  {('[' + f.location + ']').ljust(width)}  Possible {f.kind}: {f.masked}" for f in findings]
    hints = list(dict.fromkeys(_HINTS[f.kind] for f in findings if f.kind in _HINTS))
    if hints:
        lines += ["", "Tips:"] + [f"  - {h}" for h in hints]
    lines += [
        "",
        'Remove this information, use generic labels like "Bank Account 1" or "Car 1",',
        "and run the program again.",
    ]
    return "\n".join(lines)
