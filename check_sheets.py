"""
check_sheets.py -- verify the Google Sheets connection.

Never prints your key. Read-only unless you pass a flag.

  python check_sheets.py                 check only (changes nothing)
  python check_sheets.py --setup         ALSO write the header row on EMPTY tabs
  python check_sheets.py --write-test    ALSO add, edit and batch-add hidden test
                                         rows, read them back to prove text and
                                         leading zeros are preserved, then
                                         delete them

Checks:
  1. Credentials in .env are valid (shows the robot email to share the sheet with)
  2. The sheet can be opened
  3. The 4 tabs exist and have the right header row
  4. (--write-test) adding, editing and batch-adding rows works correctly

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
    """
    Exercise every kind of write the app uses, on hidden TEST rows, verify
    what came back, then delete the rows:
      1. add one row            (append_row)
      2. edit it in place       (batch_update)  -> leading zeros survive edits
      3. add two rows at once   (append_rows)
    """
    tab = "membership_fees"
    suffix = uuid.uuid4().hex[:10]
    ids = [f"TEST-{suffix}-{n}" for n in (1, 2, 3)]

    def make(record_id, membership_id, notes):
        row = schema.build_row(
            tab,
            {
                "membership_id": membership_id,   # leading zeros must survive
                "quarter": "q1",
                "payment_date": "2026-01-15",
                "amount": "123.45",
                "payment_method": "Cash",
                "reference_no": "T-" + record_id[-1],
                "notes": notes,                    # must stay text, never a formula
            },
            created_by="check_sheets",
        )
        row["record_id"] = record_id
        row["status"] = "deleted"                  # hidden even if cleanup fails
        return row

    def fetch(record_id):
        found = [r for r in gs.read_rows(tab, include_deleted=True)
                 if r["record_id"] == record_id]
        return found[0] if len(found) == 1 else None

    def wrong(got, expected):
        return [name for name, want in expected.items() if got.get(name) != want]

    ok = True
    try:
        # 1. single add -------------------------------------------------
        gs._append_row(tab, make(ids[0], "007", "=1+1"))
        say(True, "Write test row", f"added {ids[0]} (status=deleted)")
        got = fetch(ids[0])
        problems = ["row missing"] if got is None else wrong(got, {
            "membership_id": "007", "quarter": "Q1", "amount": "123.45",
            "notes": "=1+1", "payment_date": "2026-01-15"})
        if problems:
            say(False, "Read back", "values changed in the sheet: " + ", ".join(problems))
            return False
        say(True, "Read back",
            "'007', '=1+1' and amounts came back exactly as written")

        # 2. edit in place ---------------------------------------------
        gs.update_row(tab, ids[0],
                      {"notes": "=2+2", "amount": "5.00", "payment_method": "GCash"},
                      user_id="check_sheets", allow_deleted=True)
        got = fetch(ids[0])
        problems = ["row missing"] if got is None else wrong(got, {
            "membership_id": "007", "notes": "=2+2", "amount": "5.00",
            "payment_method": "GCash", "created_by": "check_sheets",
            "updated_by": "check_sheets", "record_id": ids[0],
            "import_key": schema.make_import_key(tab, got) if got else ""})
        if problems:
            say(False, "Edit row", "values wrong after editing: " + ", ".join(problems))
            return False
        say(True, "Edit row",
            "edited in place; '007' and '=2+2' still plain text; key recomputed")

        # 3. batch add --------------------------------------------------
        gs._append_rows(tab, [make(ids[1], "008", "batch one"),
                              make(ids[2], "009", "batch two")])
        a, b = fetch(ids[1]), fetch(ids[2])
        if not (a and b and a["membership_id"] == "008" and b["membership_id"] == "009"
                and a["notes"] == "batch one" and b["notes"] == "batch two"):
            say(False, "Batch add", "the two rows did not come back as written")
            return False
        say(True, "Batch add", "two rows saved in one call and read back correctly")

    except gs.SheetsError as error:
        fail("Write test", error)
        ok = False
    finally:
        removed = left = 0
        for record_id in ids:
            try:
                if gs.delete_test_row(tab, record_id):
                    removed += 1
            except gs.SheetsError:
                left += 1
        if left:
            say(False, "Cleanup",
                f"could not remove {left} test row(s) (their ids start with "
                "TEST- and status is 'deleted': hidden and harmless; delete "
                "those rows by hand)")
            ok = False
        else:
            say(True if removed else None, "Cleanup",
                f"{removed} test row(s) removed")
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
