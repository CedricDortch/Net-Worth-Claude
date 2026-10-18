# Error Handling

- Define custom exceptions in one place (`errors.py`): `PersonalInformationError`, `UnsupportedFileError`, `UnreadableFileError`, `InvalidInputError`, `InvalidAssumptionError`.
- Library modules raise; only `networth/cli.py` catches, prints a plain-English message, and exits.
- Messages tell the user **what went wrong and how to fix it**. No raw tracebacks for expected errors.
- Never include unmasked input values in error messages (see `security-pii.md`).

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Bad input (file type, unreadable file, invalid value, invalid assumption) |
| 2 | Personal information detected |

## Situations

| Situation | Behavior |
|---|---|
| Personal information found | `PersonalInformationError`, masked findings, ask user to remove and retry, exit 2, no files written |
| Unsupported file type | List supported types, exit 1 |
| File unreadable / corrupted / password-protected | Clear message, exit 1 |
| Scanned PDF with no text | Ask for a text-based file (no OCR in v1), exit 1 |
| Missing age / state / credit score | Prompt in the terminal |
| Couple missing one partner's age or credit score | Prompt for the missing value |
| Invalid value (credit score 900, age −3, unknown state) | Explain the valid range and prompt again |
| `Owner` not Partner 1 / Partner 2 / Joint | Explain allowed values (security check runs first, so real names are already caught) |
| Growth assumption out of range or not a number | Show the allowed range, exit 1 |
| No assets and no debts found | Explain the expected format, point to `samples/` |
| Only one year of history | Skip trend projection, use income-based fallback, say so in the report |

Interactive prompts must be skippable in tests: accept a `prompt_fn` parameter (default `input`) or a `--no-input` flag that turns missing fields into an `InvalidInputError`.
