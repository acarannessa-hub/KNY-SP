"""
google_sheets.py -- secure, server-side access to the PRIVATE Google Sheet
that holds the KNY-SP financial records.

What it does
  * Logs in to Google as a SERVICE ACCOUNT (a robot user). The sheet stays
    private: only people you share it with, plus that robot, can open it.
  * Reads and appends rows using the column layout in sheets_schema.py.
  * Refuses to write if the sheet's header row was changed, so data can never
    silently land in the wrong columns.

Settings (environment variables / .env / Vercel):
    GOOGLE_SERVICE_ACCOUNT_B64   the service account JSON key, base64-encoded
                                 (one line; see the setup guide)
    GOOGLE_SHEET_ID              the long ID in the sheet's web address
                                 (pasting the whole URL also works)

Security notes
  * The key is read from the environment ONLY. Never commit it, never put it
    in a template or JavaScript.
  * Only the "spreadsheets" permission is requested (not Google Drive).
  * Every exception message is safe to show to a user. Technical details go
    to the server log; `error.hint` is for the person running the server and
    never contains key material.
  * Values are written with RAW input, so text such as "=1+1" stays plain
    text and is never executed as a spreadsheet formula, and IDs such as
    "007" keep their leading zeros.
"""

import base64
import json
import logging
import os
import re
import threading

import sheets_schema as schema

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

GENERIC = "The financial records are temporarily unavailable. Please try again."


class SheetsError(Exception):
    """str(error) is safe to show to a user.
    error.hint is an operator-facing explanation (no secrets)."""

    def __init__(self, message=GENERIC, hint=""):
        super().__init__(message)
        self.hint = hint


# --------------------------------------------------
# Settings
# --------------------------------------------------
def _env(name):
    return (os.getenv(name) or "").strip()


def _config_error(hint):
    log.error("Google Sheets configuration problem: %s", hint)
    return SheetsError(GENERIC, hint)


def _describe_bad_b64(encoded):
    """Say WHY a value is not base64, without ever echoing the value itself."""
    problems = []
    if encoded.startswith("{"):
        problems.append("it looks like the raw JSON, not base64")
    if encoded.startswith(("<", "[")) or "<" in encoded or ">" in encoded:
        problems.append("it contains < > (a placeholder was probably left in)")
    if '"' in encoded or "'" in encoded:
        problems.append("it contains quote marks")
    if len(encoded) < 1500:
        problems.append(
            f"it is only {len(encoded)} characters long (a real key is about "
            "3000), so it was probably cut off or is the wrong text"
        )
    elif len(encoded) % 4:
        problems.append("it looks cut off (the length is not a multiple of 4)")
    return (" (" + "; ".join(problems) + ")") if problems else ""


def _load_service_account_info():
    """Read and sanity-check the service account key from the environment."""
    encoded = "".join(_env("GOOGLE_SERVICE_ACCOUNT_B64").split())
    if encoded:
        try:
            text = base64.b64decode(encoded, validate=True).decode("utf-8")
        except ValueError:
            raise _config_error(
                "GOOGLE_SERVICE_ACCOUNT_B64 is not valid base64"
                + _describe_bad_b64(encoded)
                + ". Fix it by running: python add_google_key.py "
                  "\"C:\\path\\to\\your-key.json\""
            )
    else:
        text = _env("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not text:
            raise _config_error(
                "No Google credentials found. Set GOOGLE_SERVICE_ACCOUNT_B64 "
                "(see the setup guide)."
            )

    try:
        info = json.loads(text)
    except ValueError:
        raise _config_error(
            "The service account credentials are not valid JSON (the value "
            "may be cut off or the wrong text). Fix it by running: "
            "python add_google_key.py \"C:\\path\\to\\your-key.json\""
        )

    if not isinstance(info, dict):
        raise _config_error("The service account credentials have the wrong shape.")

    required = ("type", "client_email", "private_key", "token_uri")
    missing = [key for key in required if not info.get(key)]
    if missing or info.get("type") != "service_account":
        raise _config_error(
            "The credentials are not a service account key"
            + (f" (missing: {', '.join(missing)})" if missing else "")
            + ". Download a JSON key for a SERVICE ACCOUNT."
        )
    return info


def service_account_email():
    """The robot's email address (what you share the sheet with). '' if the
    credentials are not set up yet. This is not a secret."""
    try:
        return _load_service_account_info()["client_email"]
    except SheetsError:
        return ""


_ID_IN_URL = re.compile(r"/spreadsheets/d/([A-Za-z0-9_-]+)")


def _sheet_id():
    raw = _env("GOOGLE_SHEET_ID")
    if not raw:
        raise _config_error(
            "GOOGLE_SHEET_ID is not set. Use the long ID from the sheet's "
            "web address (between /d/ and /edit)."
        )
    match = _ID_IN_URL.search(raw)
    sheet_id = match.group(1) if match else raw
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,}", sheet_id):
        raise _config_error(
            "GOOGLE_SHEET_ID does not look like a spreadsheet ID. Use the "
            "long ID between /d/ and /edit in the sheet's web address."
        )
    return sheet_id


# --------------------------------------------------
# Error translation
# --------------------------------------------------
def _status_of(exc):
    return getattr(getattr(exc, "response", None), "status_code", None)


def _translate(exc):
    """Turn any Google/network exception into a safe SheetsError."""
    if isinstance(exc, SheetsError):
        return exc

    name = type(exc).__name__
    status = _status_of(exc)
    message = GENERIC

    if name == "SpreadsheetNotFound" or status == 404:
        hint = ("Spreadsheet not found. Check GOOGLE_SHEET_ID (the long ID in "
                "the sheet's web address).")
    elif status == 403:
        hint = ("Permission denied. Share the sheet with the service "
                "account's email as Editor, and make sure the Google Sheets "
                "API is enabled in your Google Cloud project.")
    elif status == 429:
        message = ("Too many requests to the records sheet. "
                   "Please wait a minute and try again.")
        hint = "Google Sheets rate limit reached."
    elif status is not None and status >= 500:
        hint = "Google had a temporary problem. Try again shortly."
    elif status == 400:
        hint = "Google rejected the request (HTTP 400)."
    elif name == "RefreshError":
        hint = ("Google rejected the service account key (the key may have "
                "been deleted or disabled, or this computer's date/time is "
                "wrong).")
    elif name == "TransportError" or isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        hint = "Could not reach Google (network problem)."
    else:
        hint = f"Unexpected {name} while talking to Google Sheets."

    log.error("Google Sheets call failed: %s (HTTP %s): %s | %s",
              name, status, hint, str(exc)[:300])
    return SheetsError(message, hint)


def _call(fn):
    try:
        return fn()
    except SheetsError:
        raise
    except Exception as exc:  # noqa: BLE001 - everything is translated
        raise _translate(exc) from exc


# --------------------------------------------------
# Connection (cached for the life of the process)
# --------------------------------------------------
_lock = threading.Lock()
_spreadsheet = None


def _open_spreadsheet():
    try:
        import gspread
    except ModuleNotFoundError:
        raise _config_error(
            "The 'gspread' package is not installed. "
            "Run: pip install -r requirements.txt"
        )
    info = _load_service_account_info()
    sheet_id = _sheet_id()

    def connect():
        client = gspread.service_account_from_dict(info, scopes=SCOPES)
        return client.open_by_key(sheet_id)

    return _call(connect)


def get_spreadsheet():
    global _spreadsheet
    with _lock:
        if _spreadsheet is None:
            _spreadsheet = _open_spreadsheet()
        return _spreadsheet


def use_spreadsheet(spreadsheet):
    """Inject a spreadsheet object (used by tests)."""
    global _spreadsheet
    with _lock:
        _spreadsheet = spreadsheet


def reset():
    use_spreadsheet(None)


# --------------------------------------------------
# Tabs and headers
# --------------------------------------------------
def _require_tab(tab):
    if tab not in schema.TABS:
        raise ValueError(f"Unknown financial tab: {tab!r}")


def _worksheet(tab):
    _require_tab(tab)
    spreadsheet = get_spreadsheet()
    try:
        return spreadsheet.worksheet(tab)
    except Exception as exc:  # noqa: BLE001
        if type(exc).__name__ == "WorksheetNotFound":
            raise _config_error(
                f"The tab '{tab}' is missing in the Google Sheet. "
                "Create a tab with exactly that name."
            ) from exc
        raise _translate(exc) from exc


def _clean(row):
    return [str(cell).strip() for cell in row]


def header_status(tab):
    """'ok', 'empty' (nothing in the tab at all) or 'mismatch'."""
    worksheet = _worksheet(tab)
    expected = schema.headers(tab)
    first = _clean(_call(lambda: worksheet.row_values(1)))

    # Extra columns to the RIGHT of ours are tolerated.
    if first[:len(expected)] == expected:
        return "ok"
    if any(first):
        return "mismatch"

    values = _call(lambda: worksheet.get_all_values())
    has_data = any(any(str(c).strip() for c in row) for row in values)
    return "mismatch" if has_data else "empty"


def _col_letter(number):
    letters = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def ensure_headers(tab):
    """
    Create the header row on an EMPTY tab (and tidy its formatting).
    Returns 'ok' (already fine) or 'created'. Never overwrites anything:
    a tab with other content raises an error instead.
    """
    status = header_status(tab)
    if status == "ok":
        return "ok"
    if status == "mismatch":
        raise _config_error(
            f"Tab '{tab}' already has content that does not start with the "
            f"expected header row: {', '.join(schema.headers(tab))}. "
            "Use an empty tab."
        )

    worksheet = _worksheet(tab)
    headers = schema.headers(tab)
    _call(lambda: worksheet.append_row(headers, value_input_option="RAW"))

    # Cosmetic + protective formatting; failure here is not fatal.
    last = _col_letter(len(headers))
    try:
        worksheet.format(f"A:{last}", {"numberFormat": {"type": "TEXT"}})
        worksheet.format(f"A1:{last}1", {"textFormat": {"bold": True}})
        worksheet.freeze(rows=1)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not format tab %s: %s", tab, str(exc)[:200])
    return "created"


def _checked_worksheet(tab):
    """A worksheet whose header row is verified (cheap, 1 API call)."""
    worksheet = _worksheet(tab)
    expected = schema.headers(tab)
    first = _clean(_call(lambda: worksheet.row_values(1)))
    if first[:len(expected)] != expected:
        raise _config_error(
            f"Tab '{tab}' is missing its header row or the headers were "
            "changed. Run: python check_sheets.py --setup"
        )
    return worksheet


# --------------------------------------------------
# Reading
# --------------------------------------------------
def read_rows(tab, include_deleted=False, with_row_numbers=False):
    """
    All rows of a tab as a list of dicts (every value is a string, exactly
    as shown in the sheet). Rows marked status='deleted' are skipped unless
    include_deleted=True. Blank lines are skipped. With with_row_numbers=True
    each dict also has "_row": the row number as shown in the sheet.
    """
    worksheet = _worksheet(tab)
    expected = schema.headers(tab)
    values = _call(lambda: worksheet.get_all_values())

    if not values or _clean(values[0])[:len(expected)] != expected:
        raise _config_error(
            f"Tab '{tab}' is missing its header row or the headers were "
            "changed. Run: python check_sheets.py --setup"
        )

    rows = []
    for number, raw in enumerate(values[1:], start=2):
        if not any(str(cell).strip() for cell in raw):
            continue
        padded = [str(cell) for cell in raw] + [""] * (len(expected) - len(raw))
        record = dict(zip(expected, padded[:len(expected)]))
        if not include_deleted and schema.is_deleted(record):
            continue
        if with_row_numbers:
            record["_row"] = number
        rows.append(record)
    return rows


# --------------------------------------------------
# Writing
# --------------------------------------------------
def _append_row(tab, row):
    worksheet = _checked_worksheet(tab)
    values = [row.get(header, "") for header in schema.headers(tab)]
    _call(lambda: worksheet.append_row(
        values,
        value_input_option="RAW",        # text stays text; "=1+1" is not run
        insert_data_option="INSERT_ROWS",
        table_range="A1",
    ))


def append_record(tab, record, user_id=""):
    """
    Add ONE new record to a tab and return the complete row that was saved.
    `record` holds the tab's own fields (see sheets_schema.TABS). The caller
    must validate first; this fills in record_id, import_key, status and
    the audit columns. It never overwrites an existing row.
    """
    _require_tab(tab)
    row = schema.build_row(tab, record, created_by=user_id)
    _append_row(tab, row)
    return row


MAX_BATCH_ROWS = 500   # one atomic API call: all rows are saved or none are


def append_records(tab, records, user_id=""):
    """
    Add several NEW records in ONE call (all saved, or none). Returns the
    complete rows that were saved. The caller validates and removes
    duplicates first. At most MAX_BATCH_ROWS rows.
    """
    _require_tab(tab)
    if not records:
        return []
    if len(records) > MAX_BATCH_ROWS:
        raise ValueError(f"At most {MAX_BATCH_ROWS} rows per batch.")

    rows = [schema.build_row(tab, r, created_by=user_id) for r in records]
    _append_rows(tab, rows)
    return rows


def _append_rows(tab, rows):
    """Write complete, already-built rows in ONE call."""
    headers = schema.headers(tab)
    values = [[row.get(h, "") for h in headers] for row in rows]
    worksheet = _checked_worksheet(tab)
    _call(lambda: worksheet.append_rows(
        values,
        value_input_option="RAW",
        insert_data_option="INSERT_ROWS",
        table_range="A1",
    ))


def _find_row_index(worksheet, record_id):
    """Sheet row number (1-based) holding this record_id, or None."""
    wanted = str(record_id).strip().lower()
    ids = _call(lambda: worksheet.col_values(1))
    matches = [
        number for number, value in enumerate(ids, start=1)
        if number > 1 and str(value).strip().lower() == wanted
    ]
    if not matches:
        return None
    if len(matches) > 1:
        raise _config_error(
            f"record_id {record_id} appears {len(matches)} times in the "
            "sheet. Each record_id must be unique; delete the copy."
        )
    return matches[0]


def _modify_row(tab, record_id, mutate, allow_deleted=False):
    """
    Load the row with this record_id, let `mutate(row_dict)` change it, and
    write that ONE row back (RAW). Returns the new row dict, or None if the
    record does not exist (or is already deleted).
    """
    worksheet = _checked_worksheet(tab)
    index = _find_row_index(worksheet, record_id)
    if index is None:
        return None

    headers = schema.headers(tab)
    current = _call(lambda: worksheet.row_values(index))
    padded = [str(c) for c in current] + [""] * (len(headers) - len(current))
    row = dict(zip(headers, padded[:len(headers)]))

    # Guard: the sheet may have been edited between our two reads.
    if row["record_id"].strip().lower() != str(record_id).strip().lower():
        raise SheetsError(
            "The record changed while you were working. Please reload the "
            "page and try again.",
            "Row moved between reading the id column and the row.",
        )
    if schema.is_deleted(row) and not allow_deleted:
        return None

    mutate(row)

    values = [row.get(h, "") for h in headers]
    last = _col_letter(len(headers))
    _call(lambda: worksheet.batch_update(
        [{"range": f"A{index}:{last}{index}", "values": [values]}],
        value_input_option="RAW",
    ))
    return row


def update_row(tab, record_id, changes, user_id="", allow_deleted=False):
    """
    Change fields of ONE existing record (found by record_id). `changes`
    holds tab fields only; record_id and the created_* columns can never be
    changed here. Recomputes import_key and stamps updated_at/updated_by.
    Returns the updated row dict, or None if the record was not found.
    """
    _require_tab(tab)
    unknown = set(changes) - set(schema.TABS[tab]["fields"])
    if unknown:
        raise ValueError(f"Unknown field(s): {', '.join(sorted(unknown))}")
    normalized = schema.normalize_fields(tab, changes)

    def mutate(row):
        row.update(normalized)
        row["import_key"] = schema.make_import_key(tab, row)
        row["updated_at"] = schema.utc_now_text()
        row["updated_by"] = str(user_id or "")

    return _modify_row(tab, record_id, mutate, allow_deleted=allow_deleted)


def mark_deleted(tab, record_id, user_id=""):
    """Soft-delete: set status='deleted' (the row stays in the sheet as an
    audit trail). Returns the row, or None if not found."""
    _require_tab(tab)

    def mutate(row):
        row["status"] = "deleted"
        row["updated_at"] = schema.utc_now_text()
        row["updated_by"] = str(user_id or "")

    return _modify_row(tab, record_id, mutate)


def delete_test_row(tab, record_id):
    """Remove a row created by check_sheets.py. Only ids starting with
    'TEST-' are accepted, so this can never delete real records."""
    if not str(record_id).startswith("TEST-"):
        raise ValueError("delete_test_row only removes TEST- rows")
    worksheet = _worksheet(tab)
    ids = _call(lambda: worksheet.col_values(1))
    for index in range(len(ids), 0, -1):          # bottom-up
        if str(ids[index - 1]).strip() == record_id:
            _call(lambda i=index: worksheet.delete_rows(i))
            return True
    return False
