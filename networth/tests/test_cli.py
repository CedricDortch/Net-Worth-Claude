from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from networth import cli
@pytest.fixture(autouse=True)
def in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def answers(*replies: str):
    """A fake `input` that returns the given replies in order and records the questions."""
    it: Iterator[str] = iter(replies)
    asked: list[str] = []

    def ask(question: str) -> str:
        asked.append(question)
        return next(it)

    ask.asked = asked  # type: ignore[attr-defined]
    return ask


def write(path: Path, text: str) -> Path:
    path.write_text(text)
    return path


# --- Security (M1) ----------------------------------------------------------

def test_clean_file_prints_profile_and_report(samples: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([str(samples / "sample_input.csv"), "--no-input"]) == 0
    out = capsys.readouterr().out
    assert "Net worth: $54,800" in out
    assert "Texas (TX)" in out
    assert "NET WORTH REPORT · GRADE" in out
    assert "WHAT TO DO NEXT" in out
    assert "It is not financial, tax, or legal advice.\n\nReport written to " in out


def test_pii_file_exits_2_and_writes_nothing(
    samples: Path, in_tmp: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main([str(samples / "sample_with_pii.txt")]) == 2
    err = capsys.readouterr().err
    assert "SECURITY CHECK FAILED" in err
    assert "run the program again" in err
    for secret in ["123-45-6789", "4421-889-0012", "4111 1111 1111 1111", "Jordan", "ABC-1234"]:
        assert secret not in err
    assert list(in_tmp.iterdir()) == []


def test_unsupported_file_exits_1(in_tmp: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([str(write(in_tmp / "nw.pages", "x"))]) == 1
    assert "not supported" in capsys.readouterr().err


def test_missing_file_exits_1(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["does_not_exist.csv"]) == 1
    assert "not found" in capsys.readouterr().err


# --- Profile fields: CLI > file > prompt ------------------------------------

def test_prompts_for_missing_fields(in_tmp: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(in_tmp / "nw.txt", "ASSETS\nBrokerage 1: $10,000\n")
    ask = answers("27", "762", "Columbus, Ohio")
    assert cli.main([str(path)], ask=ask) == 0
    assert ask.asked == ["Age: ", "Credit score: ", "State: "]
    assert "Age 27 · Ohio (OH) · Credit score 762" in capsys.readouterr().out


def test_reprompts_after_invalid_answer(in_tmp: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(in_tmp / "nw.txt", "State: MI\nCredit Score: 700\nASSETS\nBrokerage 1: $10\n")
    ask = answers("200", "27")
    assert cli.main([str(path)], ask=ask) == 0
    assert "16 to 110" in capsys.readouterr().err


def test_invalid_file_value_is_asked_again(in_tmp: Path) -> None:
    path = write(in_tmp / "nw.txt", "Age: 29\nState: MI\nCredit Score: 900\nASSETS\nBrokerage 1: $10\n")
    ask = answers("750")
    assert cli.main([str(path)], ask=ask) == 0
    assert ask.asked == ["Credit score: "]


def test_cli_flags_override_file(samples: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main([str(samples / "sample_input.csv"), "--age", "27", "--state", "Ohio",
                          "--credit-score", "762", "--no-input"])
    assert code == 0
    assert "Age 27 · Ohio (OH) · Credit score 762" in capsys.readouterr().out


def test_no_input_fails_when_missing(in_tmp: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(in_tmp / "nw.txt", "ASSETS\nBrokerage 1: $10\n")
    assert cli.main([str(path), "--no-input"]) == 1
    assert "Age is missing" in capsys.readouterr().err


def test_couple_prompts_for_partner_2(samples: Path, in_tmp: Path) -> None:
    lines = (samples / "sample_couple.csv").read_text().splitlines()
    kept = [l for l in lines if not l.startswith(("Profile,Age 2", "Profile,Credit Score 2"))]
    path = write(in_tmp / "couple.csv", "\n".join(kept))
    ask = answers("31", "668")
    assert cli.main([str(path)], ask=ask) == 0
    assert ask.asked == ["Partner 2 age: ", "Partner 2 credit score: "]


def test_household_flag_and_two_ages(in_tmp: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(in_tmp / "nw.txt", "State: GA\nASSETS\nHouse 1: $300,000\n")
    code = cli.main([str(path), "--household", "couple", "--age", "34", "31",
                          "--credit-score", "745", "668", "--no-input"])
    assert code == 0
    assert "Partner 2: age 31, credit score 668" in capsys.readouterr().out


# --- Assumptions --------------------------------------------------------------

def test_assumption_flags(samples: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main([str(samples / "sample_input.csv"), "--no-input",
                          "--return", "6", "--contribution", "1500"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Investment Return: 6% (cli)" in out
    assert "Monthly Contribution: $1,500/month (cli)" in out


def test_bad_assumption_exits_1(samples: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([str(samples / "sample_input.csv"), "--no-input", "--return", "40"]) == 1
    assert "out of range" in capsys.readouterr().err


def test_expenses_flag(samples: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([str(samples / "sample_timeseries.csv"), "--age", "27", "--state", "OH",
                          "--credit-score", "762", "--expenses", "2500", "--no-input"]) == 0
    out = capsys.readouterr().out
    assert "Monthly expenses: $2,500" in out
    assert "as of 2025-06-15" in out
