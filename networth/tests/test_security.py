from __future__ import annotations

import pytest

from networth import security
from conftest import table_doc, text_doc
from networth.errors import PersonalInformationError


def kinds(*lines: str) -> list[str]:
    return [f.kind for f in security.scan(text_doc(*lines))]


# --- Catches real PII -------------------------------------------------------

@pytest.mark.parametrize(("line", "kind"), [
    ("SSN: 123-45-6789", "Social Security number"),
    ("ssn 123456789", "Social Security number"),
    ("Social Security Number: 123 45 6789", "Social Security number"),
    ("My number is 123-45-6789", "Social Security number"),
    ("Checking account # 4421-889-0012: $30,000", "account number"),
    ("Acct no. 99887766", "account number"),
    ("Account ending in 1234", "account number"),
    ("Account Number: xxxx5678", "account number"),
    ("Savings 12345678901: $5,000", "account number"),
    ("Routing number 021000021", "routing number"),
    ("ABA: 011000015", "routing number"),
    ("Bank 021000021", "routing number"),  # bare 9 digits passing the ABA checksum
    ("Visa 4111 1111 1111 1111", "credit/debit card number"),
    ("Card 5500-0000-0000-0004", "credit/debit card number"),
    ("Amex 378282246310005", "credit/debit card number"),
    ("742 Evergreen Terrace", "street address"),
    ("Home at 123 Main St: $250,000", "street address"),
    ("1600 Pennsylvania Avenue", "street address"),
    ("PO Box 1234", "street address"),
    ("Apt 4B", "street address"),
    ("Suite 210", "street address"),
    ("Austin, TX 78701", "ZIP code"),
    ("Texas 75001", "ZIP code"),
    ("Zip: 30301", "ZIP code"),
    ("90210-1234", "ZIP code"),
    ("Phone: (555) 867-5309", "phone number"),
    ("Call 555-867-5309", "phone number"),
    ("+1 555.867.5309", "phone number"),
    ("Email: jordan@example.com", "email address"),
    ("Car 1 plate ABC-1234", "license plate"),
    ("License plate: 7XYZ123", "license plate"),
    ("VIN 1HGCM82633A004352", "VIN"),
    ("DOB: 04/12/1991", "date of birth"),
    ("Date of birth: March 3, 1990", "date of birth"),
    ("Born 1990-03-03", "date of birth"),
    ("Driver's license: D1234567", "driver's license / passport number"),
    ("Passport # 123456789", "driver's license / passport number"),
    ("Name: Jordan Example", "name"),
    ("Account holder: Sam", "name"),
    ("Owner: Jordan", "name"),
])
def test_detects(line: str, kind: str) -> None:
    assert kind in kinds(line)


def test_ssn_not_also_reported_as_account() -> None:
    assert kinds("SSN: 123-45-6789") == ["Social Security number"]


# --- Ignores safe values ----------------------------------------------------

@pytest.mark.parametrize("line", [
    "Bank Account 1: $30,000",
    "Bank Account 12: $3,000",
    "Car 1 is worth $2000",
    "Car 1: $2,000",
    "401k 1: $45,000",
    "Student Loan 1: $18,000 (5.5%)",
    "Credit Card 1: $4,200 (24.9%)",
    "Mortgage 1: $285,000 at 6.1%",
    "House 1: $340,000",
    "Age: 29",
    "State: Texas",
    "State: TX",
    "Credit Score: 712",
    "2024: $42,000",
    "2021-2025",
    "Net worth: $12,000,000",
    "Net worth: $1,234,567.89",
    "Net worth: 12,345,678",
    "Owner: Partner 1",
    "Owner: Joint",
    "Household Type: Couple",
    "Monthly Expenses: $3,200",
    "Statement date 2025-01-31",
    "Car 2 is on its way out",
    "License plate number unknown",
    "Born in 1990",
])
def test_ignores_safe_values(line: str) -> None:
    assert kinds(line) == []


def test_plain_number_in_text_is_flagged_but_money_column_is_not() -> None:
    assert kinds("Bank Account 1 12000000") == ["account number"]
    doc = table_doc(["Section", "Label", "Value"], ["Asset", "Bank Account 1", "12000000"])
    assert security.scan(doc) == []


def test_long_number_in_money_column_still_flagged() -> None:
    doc = table_doc(["Section", "Label", "Value"], ["Asset", "Account", "44218890012"])
    assert [f.kind for f in security.scan(doc)] == ["account number"]


# --- Tables -----------------------------------------------------------------

def test_table_findings_point_to_the_cell() -> None:
    doc = table_doc(
        ["Section", "Label", "Value"],
        ["Profile", "Age", "29"],
        ["Profile", "Name", "Jordan Example"],
    )
    (finding,) = security.scan(doc)
    assert finding.kind == "name"
    assert finding.location == "Cell C3"


def test_owner_column_must_not_contain_names() -> None:
    header = ["Section", "Label", "Value", "Owner"]
    ok = table_doc(header, ["Asset", "Car 1", "2000", "Partner 2"], ["Asset", "Car 2", "900", "Joint"])
    assert security.scan(ok) == []
    bad = table_doc(header, ["Asset", "Car 1", "2000", "Jordan"])
    assert [(f.kind, f.location) for f in security.scan(bad)] == [("name", "Cell D2")]


def test_header_row_is_not_a_name() -> None:
    assert security.scan(table_doc(["Name", "Value"], ["Car 1", "2000"])) == []


# --- Masking ----------------------------------------------------------------

@pytest.mark.parametrize(("line", "secret"), [
    ("SSN: 123-45-6789", "123-45-6789"),
    ("Checking account # 4421-889-0012", "4421-889-0012"),
    ("Visa 4111 1111 1111 1111", "4111 1111 1111 1111"),
    ("Email: jordan@example.com", "jordan@example.com"),
    ("Name: Jordan Example", "Jordan"),
    ("Account ending in 1234", "1234"),
    ("Car 1 plate ABC-1234", "ABC-1234"),
])
def test_message_never_contains_full_value(line: str, secret: str) -> None:
    findings = security.scan(text_doc(line))
    assert findings
    assert secret not in security.format_findings(findings)


def test_mask_formats() -> None:
    assert security.mask_digits("123-45-6789") == "***-**-6789"
    assert security.mask_digits("1234") == "****"
    assert security.mask_email("jordan@example.com") == "j***@***.com"
    assert security.mask_address("123 Main St") == "*** Main St"
    assert security.mask_name("Jordan Example") == "J*** E***"


# --- Checksums --------------------------------------------------------------

def test_luhn() -> None:
    assert security.luhn_valid("4111111111111111")
    assert not security.luhn_valid("4111111111111112")


def test_aba() -> None:
    assert security.aba_valid("021000021")
    assert not security.aba_valid("123456789")
    assert not security.aba_valid("000000000")


# --- check() ----------------------------------------------------------------

def test_check_raises_with_findings() -> None:
    with pytest.raises(PersonalInformationError) as exc:
        security.check(text_doc("Bank Account 1: $30,000", "SSN: 123-45-6789"))
    assert len(exc.value.findings) == 1
    assert "123-45-6789" not in str(exc.value)


def test_check_passes_clean_document() -> None:
    security.check(text_doc("Age: 29", "Bank Account 1: $30,000"))


def test_duplicate_findings_are_merged() -> None:
    findings = security.scan(text_doc("SSN: 123-45-6789", "SSN: 123-45-6789"))
    assert [f.location for f in findings] == ["Line 1", "Line 2"]
