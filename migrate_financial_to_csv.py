"""
One-time migration: MySQL (RDS) financial tables -> sheet-ready CSV files.

SAFE BY DESIGN
  * Only runs SELECT statements. It never writes to the database.
  * Does NOT import app.py (which would run create_all() and the old
    schema migrations against your live database).
  * Never prints the DATABASE_URL.
  * Refuses to overwrite earlier output unless you pass --force.

OUTPUT (in --out-dir, default ./migration_output)
  fundraising.csv, sponsorships.csv, membership_fees.csv, expenses.csv
  migration_report.txt   <- row counts, totals, duplicates, data problems

USAGE (from the project folder, with your venv active)
  python migrate_financial_to_csv.py
  python migrate_financial_to_csv.py --out-dir my_output --force

DATABASE_URL is read from the environment or from a .env file in the
current folder (the same one your app already uses).
"""

import argparse
import csv
import os
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

import sheets_schema as schema

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv is optional here
    pass


def fetch_rows(connection, tab):
    """SELECT every row of one financial table (names come from our own
    constants, never from user input)."""
    spec = schema.TABS[tab]
    columns = ["id"] + spec["fields"] + ["created_at"]
    query = text(
        f"SELECT {', '.join(columns)} FROM {spec['db_table']} "
        f"ORDER BY {spec['date_field']}, id"
    )
    return [dict(row._mapping) for row in connection.execute(query)]


def build_output_row(tab, db_row):
    """Convert one DB row into one sheet row (a dict keyed by header)."""
    spec = schema.TABS[tab]
    out = {"record_id": schema.new_record_id()}

    for field in spec["fields"]:
        value = db_row.get(field)
        if field == "amount":
            out[field] = schema.normalize_amount(value)
        elif field.endswith("_date"):
            out[field] = schema.normalize_date(value)
        elif field == "quarter":
            out[field] = "" if value is None else str(value).strip().upper()
        else:
            out[field] = "" if value is None else str(value).strip()

    created = schema.format_timestamp(db_row.get("created_at"))
    out["import_key"] = schema.make_import_key(tab, out)
    out["status"] = "active"
    out["created_at"] = created
    out["created_by"] = "legacy-migration"
    out["updated_at"] = created
    out["updated_by"] = "legacy-migration"
    out["legacy_id"] = db_row["id"]
    return out


def find_problems(tab, out_row):
    """Return a list of human-readable problems for one output row.
    Rows are still written; problems are only reported."""
    spec = schema.TABS[tab]
    problems = []
    if not out_row[spec["date_field"]]:
        problems.append(f"missing or invalid {spec['date_field']}")
    if not out_row["amount"]:
        problems.append("missing or invalid amount")
    elif Decimal(out_row["amount"]) <= 0:
        problems.append("amount is zero or negative")
    if tab == "membership_fees":
        if not out_row["membership_id"]:
            problems.append("missing membership_id")
        if out_row["quarter"] not in {"Q1", "Q2", "Q3", "Q4"}:
            problems.append("invalid quarter")
    if tab == "sponsorships" and not out_row["sponsor_name"]:
        problems.append("missing sponsor_name")
    if tab == "expenses" and not out_row["category"]:
        problems.append("missing category")
    return problems


def write_csv(path, tab, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=schema.headers(tab))
        writer.writeheader()
        writer.writerows(rows)


def total_from_csv(path):
    """Re-read the file we just wrote and sum its amounts. This verifies
    the CSV itself, not just our in-memory data."""
    total = Decimal("0")
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                total += Decimal(row["amount"])
            except InvalidOperation:
                pass
    return total


def source_total(db_rows):
    total = Decimal("0")
    for row in db_rows:
        try:
            total += Decimal(str(row["amount"]))
        except (InvalidOperation, TypeError):
            pass
    return total.quantize(Decimal("0.01"))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--out-dir", default="migration_output")
    parser.add_argument("--force", action="store_true",
                        help="overwrite existing output files")
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        sys.exit("DATABASE_URL is not set (checked environment and .env).")

    os.makedirs(args.out_dir, exist_ok=True)
    targets = [os.path.join(args.out_dir, f"{t}.csv") for t in schema.TABS]
    targets.append(os.path.join(args.out_dir, "migration_report.txt"))
    existing = [p for p in targets if os.path.exists(p)]
    if existing and not args.force:
        sys.exit(
            "Output already exists (re-running would create NEW record IDs "
            "and cause a second, different export):\n  "
            + "\n  ".join(existing)
            + "\nUse --force only if you really want to regenerate."
        )

    engine = create_engine(database_url)
    report = ["KNY-SP financial migration report", "=" * 40, ""]
    all_ok = True

    try:
        with engine.connect() as connection:
            for tab in schema.TABS:
                db_rows = fetch_rows(connection, tab)
                out_rows = [build_output_row(tab, r) for r in db_rows]
                path = os.path.join(args.out_dir, f"{tab}.csv")
                write_csv(path, tab, out_rows)

                src_total = source_total(db_rows)
                csv_total = total_from_csv(path)
                counts_match = len(db_rows) == len(out_rows)
                totals_match = src_total == csv_total.quantize(Decimal("0.01"))
                all_ok = all_ok and counts_match and totals_match

                report.append(f"[{tab}]")
                report.append(f"  rows in database : {len(db_rows)}")
                report.append(f"  rows in CSV      : {len(out_rows)}  "
                              f"{'OK' if counts_match else 'MISMATCH'}")
                report.append(f"  total (database) : {src_total:,.2f}")
                report.append(f"  total (CSV)      : {csv_total:,.2f}  "
                              f"{'OK' if totals_match else 'MISMATCH'}")

                # Rows with data problems (still written, just flagged)
                flagged = []
                for row in out_rows:
                    problems = find_problems(tab, row)
                    if problems:
                        flagged.append(
                            f"    legacy id {row['legacy_id']}: "
                            + "; ".join(problems)
                        )
                if flagged:
                    report.append(f"  rows needing review: {len(flagged)}")
                    report.extend(flagged)

                # Rows that would count as duplicates of each other
                groups = defaultdict(list)
                for row in out_rows:
                    groups[row["import_key"]].append(row["legacy_id"])
                dupes = [ids for ids in groups.values() if len(ids) > 1]
                if dupes:
                    report.append(
                        f"  possible duplicate groups: {len(dupes)} "
                        "(all rows were kept)"
                    )
                    for ids in dupes:
                        report.append(
                            "    legacy ids: " + ", ".join(map(str, ids))
                        )
                report.append("")
    except SQLAlchemyError as error:
        # Show the driver's message only, never the connection URL.
        detail = getattr(error, "orig", error)
        sys.exit(f"Database error: {detail}")

    report.append("RESULT: " + (
        "all row counts and totals match." if all_ok
        else "MISMATCH FOUND - do not use these files; send me this report."
    ))
    report_text = "\n".join(report)
    with open(os.path.join(args.out_dir, "migration_report.txt"),
              "w", encoding="utf-8") as handle:
        handle.write(report_text + "\n")
    print(report_text)


if __name__ == "__main__":
    main()
