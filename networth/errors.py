"""Custom exceptions. Library modules raise these; only networth.py catches them."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from networth.security import Finding


class NetWorthError(Exception):
    """Base class for expected errors. `exit_code` is what the CLI exits with."""

    exit_code = 1


class UnsupportedFileError(NetWorthError):
    """The input file type is not supported."""


class UnreadableFileError(NetWorthError):
    """The file exists but cannot be read (corrupted, locked, empty, scanned)."""


class InvalidInputError(NetWorthError):
    """A value in the input is missing or outside its valid range."""


class InvalidAssumptionError(NetWorthError):
    """A growth assumption is out of range or not a number."""


class ReferenceDataError(NetWorthError):
    """A data/*.json benchmark file is missing or damaged."""


class PersonalInformationError(NetWorthError):
    """The input contains personal information. Carries masked findings only."""

    exit_code = 2

    def __init__(self, findings: Sequence[Finding]) -> None:
        self.findings = tuple(findings)
        # Never put the values themselves in the message.
        super().__init__(f"{len(self.findings)} possible personal information item(s) found")
