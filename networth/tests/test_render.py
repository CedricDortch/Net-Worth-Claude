from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import pytest

from networth import analysis
from networth import extractor
from networth import cli
from networth import render
from networth import report
from conftest import make_profile
from networth.models import Assumptions, Item, Person
from networth.parsers import parse_file

D = dt.date
ALWAYS = ["chart-projection", "chart-age-ladder", "chart-age-medians", "chart-state"]


def html_for(profile, ref) -> str:
    r = analysis.analyze(profile, ref)
    return render.render_html(r, report.build_report(r), generated=D(2026, 10, 18))


def chart_data(html: str) -> dict:
    blob = re.search(r'<script type="application/json" id="report-data">(.*?)</script>', html, re.S).group(1)
    return json.loads(blob)["charts"]


@pytest.fixture
def full(ref) -> str:
    return html_for(make_profile(
        [Item("Bank Account 1", 30_000, "cash"), Item("401k 1", 45_000, "retirement"), Item("Car 1", 2_000, "vehicles")],
        [Item("Credit Card 1", 4_200, "credit_card", 24.9)],
        expenses=3_200, income={2024: 60_000, 2025: 65_000},
        history={D(2023, 12, 31): 40_000, D(2024, 12, 31): 55_000, D(2025, 12, 31): 72_800},
    ), ref)


def test_page_structure(full: str) -> None:
    assert full.startswith("<!doctype html>")
    for cid in ALWAYS + ["chart-categories", "chart-history", "chart-income"]:
        assert f'id="{cid}"' in full
    for heading in report.SECTION_TITLES.values():
        assert heading.replace("'", "&#39;") in full
    assert "What to do next" in full and "Final summary" in full and "Data sources" in full
    assert full.count(report.DISCLAIMER) >= 2   # header and footer


def test_only_external_resource_is_pinned_chart_js(full: str) -> None:
    srcs = re.findall(r'<script[^>]*src="([^"]+)"', full)
    assert srcs == [render.CHART_JS_URL]
    assert "@4.4.1" in render.CHART_JS_URL
    assert not re.search(r'<link[^>]+href="https?://', full)
    assert "fetch(" not in full and "XMLHttpRequest" not in full


def test_chart_data_is_embedded_and_complete(full: str) -> None:
    data = chart_data(full)
    assert data["categories"]["labels"] == ["Cash", "Retirement", "Vehicles", "Credit cards"]
    assert data["categories"]["asset_pcts"][0] == "39%"
    assert len(data["projection"]["expected"]) == 21
    assert data["projection"]["default"] is None
    assert any(b["you"] for b in data["age_ladder"]["bars"])
    assert data["income"]["labels"] == ["2024", "2025"]


def test_every_chart_has_a_table(full: str) -> None:
    for title in ["every item", "net worth history", "projection by year", "all percentiles",
                  "medians and means by age", "state comparison", "income and savings rate"]:
        assert f"Show table: {title}" in full


def test_missing_data_hides_charts_with_a_reason(ref) -> None:
    html = html_for(make_profile([Item("Brokerage 1", 10_000, "investments")]), ref)
    assert 'id="chart-history"' not in html and 'id="chart-income"' not in html
    assert "Add at least two dated net worth values" in html
    assert 'id="chart-owners"' not in html
    for cid in ALWAYS:
        assert f'id="{cid}"' in html


def test_income_without_matching_history_explains(ref) -> None:
    html = html_for(make_profile(income={2025: 60_000}), ref)
    assert 'id="chart-income"' not in html
    assert "Add income history (year and amount) next to your net worth history" in html


def test_couple_gets_ownership_chart_and_both_scores(ref) -> None:
    html = html_for(make_profile(
        [Item("House 1", 300_000, "real_estate"), Item("401k 1", 60_000, "retirement", owner="partner1")],
        [Item("Mortgage 1", 250_000, "mortgage", 6.0)], ages=(34, 31), scores=(745, 668), state="GA"), ref)
    assert 'id="chart-owners"' in html
    assert "Partner 1: 745" in html and "Partner 2: 668" in html
    assert chart_data(html)["owners"]["labels"] == ["Partner 1", "Partner 2", "Joint"]


def test_changed_assumptions_add_default_line(ref) -> None:
    a = Assumptions(investment_return=9, source={"investment_return": "cli"})
    html = html_for(make_profile(assumptions=a), ref)
    assert chart_data(html)["projection"]["default"] is not None
    assert "Orange line: the same forecast at default assumptions." in html


def test_labels_are_escaped(ref) -> None:
    evil = '</script><img src=x onerror=alert(1)>'
    html = html_for(make_profile([Item(evil, 1_000, "other")]), ref)
    assert evil not in html
    assert "&lt;/script&gt;" in html                     # escaped in the HTML table
    assert chart_data(html) is not None                   # JSON blob still parses
    blob = re.search(r'id="report-data">(.*?)</script>', html, re.S).group(1)
    assert "</" not in blob and "<img" not in blob


@pytest.mark.parametrize(("score", "shift"), [(320, "0%"), (700, "-50%"), (845, "-100%")])
def test_credit_labels_stay_inside(ref, score: int, shift: str) -> None:
    html = html_for(make_profile(scores=(score,)), ref)
    assert f"transform: translateX({shift}); top: -30px\">You: {score}" in html


def test_raw_file_text_never_reaches_the_page(samples: Path, ref) -> None:
    # sample_timeseries has a free-text note ("Market dip") that is not a label or number.
    ex = extractor.extract(parse_file(samples / "sample_timeseries.csv"))
    profile = extractor.build_profile(ex, household_type="single", people=[Person(27, 762)], state="OH",
                                      monthly_expenses=None, assumptions=Assumptions(source={}))
    r = analysis.analyze(profile, ref)
    html = render.render_html(r, report.build_report(r))
    assert "Market dip" not in html
    assert "Savings Account" in html  # labels are fine


# --- CLI ----------------------------------------------------------------------

def test_cli_writes_index_html(samples: Path, tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli.main([str(samples / "sample_input.csv"), "--no-input"]) == 0
    assert (tmp_path / "index.html").exists()
    assert f"Report written to {tmp_path.resolve() / 'index.html'}" in capsys.readouterr().out


def test_cli_out_path(samples: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "reports" / "mine.html"
    assert cli.main([str(samples / "sample_couple.csv"), "--no-input", "--out", str(out)]) == 0
    assert out.exists() and not (tmp_path / "index.html").exists()
    assert 'id="chart-owners"' in out.read_text()
