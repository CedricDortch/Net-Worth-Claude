# Security and Personal Information (PII)

This rule always applies. Security failures are the worst possible bug in this project.

## Order of operations

- The PII scan in `security.py` runs on the raw text/tables **before** extraction into `NetWorthProfile` and before any analysis.
- If anything is found:
  1. Raise `PersonalInformationError` (custom exception, carries a list of findings).
  2. The CLI prints each finding: type + location (line or cell) + **masked** value (e.g. `***-**-1234`, `****8890`).
  3. Tell the user to remove the information, use generic labels like "Bank Account 1" or "Car 1", and run again.
  4. Exit with code **2**. Do not write `index.html` or any other file.

Expected output:

```text
SECURITY CHECK FAILED — personal information detected.

  [Line 4]  Possible account number: ****8890
  [Line 9]  Possible street address: "*** Main St"
  [Cell B7] Possible license plate: "***-1234"

Remove this information, use generic labels like "Bank Account 1" or "Car 1",
and run the program again.
```

## Allowed

Age · state · credit score · dollar amounts (`$`, commas, decimals) · years (e.g. `2024`) · interest rates / percentages · generic labels ("Bank Account 1", "Car 2", "Credit Card 1") · "Partner 1", "Partner 2", "Joint".

## Blocked (one detector function each)

| Type | Detection |
|---|---|
| Social Security number | `###-##-####`, `### ## ####`, or 9 digits next to "SSN"/"social" |
| Bank account number | 8–17 digit runs not formatted as money; "acct", "account #", "acct no" followed by digits |
| Routing number | 9 digits passing the ABA checksum, or next to "routing" |
| Card number | 13–19 digits (optional spaces/dashes) passing Luhn |
| Street address | Number + street word (St, Street, Ave, Rd, Blvd, Ln, Dr, Ct, Way, Apt, Suite); "PO Box" |
| ZIP code | 5-digit or ZIP+4 next to a state or address |
| Phone number | `(###) ###-####`, `###-###-####`, `+1 …` |
| Email | Standard email pattern |
| License plate | Plate-like string next to "plate", "tag", "license" |
| VIN | 17 chars, no I/O/Q |
| Date of birth | Full date next to "DOB", "birth", "born" |
| Name | Text after "Name:", "Account holder:", "Owner:" unless it is Partner 1 / Partner 2 / Joint |
| Driver's license / passport | Number next to "license #", "DL", "passport" |

## False-positive guards

- Money-formatted numbers (`$30,000`, `30,000.00`) are never account numbers.
- 4-digit numbers 1900–2100 in a history/income section are years.
- Credit score (300–850) and age fields are allowed.
- Every detector needs tests for both catching real PII and ignoring safe values.

## Never

- Never write raw input to disk, logs, or the HTML report. The report contains only labels and computed numbers.
- Never print an unmasked PII value, including in exception messages, tracebacks, or debug logging.
- Never add network calls. Chart.js loaded by the browser is the only external resource.
- Never weaken a detector to make a test pass; fix the false-positive guard instead.
- Never copy a user's real data file or its numbers (or their age, state, credit score, or city) into `samples/`, `networth/tests/`, rules, or docs. Build fake data with the same layout instead. Real files and generated reports stay out of the repo (see `.gitignore`).
