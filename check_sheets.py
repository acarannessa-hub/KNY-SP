"""
check_sheets.py -- verify the Google Sheets connection.

Never prints your key. Read-only unless you pass a flag.

  python check_sheets.py                 check only (changes nothing)
  python check_sheets.py --setup         ALSO write the header row on EMPTY tabs
  python check_sheets.py --write-test    ALSO add one hidden test row, read it
                                         back to prove text/leading zeros are
                                         preserved, then delete it

Checks:
  1. Credentials in .env are valid (shows the robot email to share the sheet with)
  2. The sheet can be opened
  3. The 4 tabs exist and have the right header row
  4. (--write-test) writing and reading back works correctly

Settings come from .env:
  GOOGLE_SERVICE_ACCOUNT_B64, GOOGLE_SHEET_ID
"""

import argparse
import sys
import uuid

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import google_sheets as gs
import sheets_schema as schema


def say(ok, label, detail=""):
    mark = {True: "PASS", False: "FAIL", None: "SKIP"}[ok]
    print(f"[{mark}] {label}" + (f" -- {detail}" if detail else ""))


def fail(label, error):
    say(False, label, str(error))
    if getattr(error, "hint", ""):
        print(f"       Fix: {error.hint}")


def check_credentials():
    try:
        info = gs._load_service_account_info()
    except gs.SheetsError as error:
        fail("Credentials", error)
        return False
    say(True, "Credentials", "service account key is readable")
    print(f"       Share your Google Sheet (as Editor) with: {info['client_email']}")
    return True


def check_connection():
    try:
        spreadsheet = gs.get_spreadsheet()
    except gs.SheetsError as error:
        fail("Open spreadsheet", error)
        return None
    say(True, "Open spreadsheet", f"'{spreadsheet.title}'")
    return spreadsheet


def check_tabs(setup):
    all_ok = True
    for tab in schema.TABS:
        try:
            status = gs.header_status(tab)
            if status == "empty" and setup:
                gs.ensure_headers(tab)
                say(True, f"Tab '{tab}'", "was empty -> header row created")
                continue
        except gs.SheetsError as error:
            fail(f"Tab '{tab}'", error)
            all_ok = False
            continue

        if status == "ok":
            say(True, f"Tab '{tab}'", "headers are correct")
        elif status == "empty":
            say(False, f"Tab '{tab}'",
                "tab is empty -> run: python check_sheets.py --setup")
            all_ok = False
        else:
            say(False, f"Tab '{tab}'",
                "has other content / different headers (use an empty tab)")
            all_ok = False
    return all_ok


def write_test():
    """Append one hidden row, read it back, verify, delete it."""
    tab = "membership_fees"
    test_id = "TEST-" + uuid.uuid4().hex[:12]
    row = schema.build_row(
        tab,
        {
            "membership_id": "007",          # leading zeros must survive
            "quarter": "q1",
            "payment_date": "2026-01-15",
            "amount": "123.45",
            "payment_method": "Cash",
            "reference_no": "T-1",
            "notes": "=1+1",                  # must stay text, never a formula
        },
        created_by="check_sheets",
    )
    row["record_id"] = test_id
    row["status"] = "deleted"                 # hidden even if cleanup fails

    ok = True
    try:
        gs._append_row(tab, row)
        say(True, "Write test row", f"added {test_id} (status=deleted)")

        found = [r for r in gs.read_rows(tab, include_deleted=True)
                 if r["record_id"] == test_id]
        if len(found) != 1:
            say(False, "Read back", f"expected 1 row, found {len(found)}")
            ok = False
        else:
            got = found[0]
            problems = [name for name, want in (
                ("membership_id", "007"), ("quarter", "Q1"),
                ("amount", "123.45"), ("notes", "=1+1"),
                ("payment_date", "2026-01-15"),
            ) if got.get(name) != want]
            if problems:
                say(False, "Read back",
                    "values changed in the sheet: " + ", ".join(problems))
                ok = False
            else:
                say(True, "Read back",
                    "'007', '=1+1' and amounts came back exactly as written")
    except gs.SheetsError as error:
        fail("Write test", error)
        ok = False
    finally:
        try:
            removed = gs.delete_test_row(tab, test_id)
            say(True if removed else None, "Cleanup",
                "test row removed" if removed else "no test row to remove")
        except gs.SheetsError as error:
            say(False, "Cleanup",
                f"could not remove {test_id}; it is hidden (status=deleted) "
                "and harmless, delete that row by hand")
            ok = False
    return ok


def main():
    parser = argparse.ArgumentParser(description="Check Google Sheets setup.")
    parser.add_argument("--setup", action="store_true",
                        help="write the header row on empty tabs")
    parser.add_argument("--write-test", action="store_true",
                        help="add, read back and delete one hidden test row")
    args = parser.parse_args()

    print("KNY-SP Google Sheets check\n" + "=" * 27)

    if not check_credentials():
        sys.exit(1)

    if check_connection() is None:
        sys.exit(1)

    tabs_ok = check_tabs(args.setup)
    results = [tabs_ok]

    if args.write_test:
        if tabs_ok:
            results.append(write_test())
        else:
            say(None, "Write test", "skipped until all tabs pass")
            results.append(False)

    print("\n" + ("ALL CHECKS PASSED." if all(results)
                  else "SOME CHECKS FAILED - fix the FAIL lines above, then "
                       "run again."))
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
