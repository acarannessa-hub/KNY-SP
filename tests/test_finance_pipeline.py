"""
Unit tests for the financial data pipeline (no database, no Google).

Run from the project folder:
    python -m unittest discover -s tests -v
"""

import io
import os
import sys
import unittest
from datetime import date, datetime
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sheets_schema  # noqa: E402
from services.finance import LEDGERS, cleaning, ingestion, sheets_mirror  # noqa: E402

TODAY = date(2026, 11, 24)


def clean(ledger, raw, **kwargs):
    kwargs.setdefault("today", TODAY)
    return cleaning.clean_record(ledger, raw, **kwargs)


class LedgerLayoutTests(unittest.TestCase):
    def test_fields_match_google_sheet_layout(self):
        for key, ledger in LEDGERS.items():
            self.assertEqual(ledger.field_names, sheets_schema.TABS[key]["fields"], key)
            self.assertEqual(ledger.date_field, sheets_schema.TABS[key]["date_field"], key)


class AmountTests(unittest.TestCase):
    def test_accepts_common_spellings(self):
        for text in ("1500", "1,500.00", "₱1,500", "PHP 1500.5", " 1500.50 ", 1500, 1500.5):
            self.assertIn(cleaning.parse_amount(text), (Decimal("1500.00"), Decimal("1500.50")), text)

    def test_rejects_invalid(self):
        for value in ("", None, "abc", "0", "-5", "10.005", "NaN", "Infinity", "99999999999", True):
            with self.assertRaises(cleaning.FieldError, msg=repr(value)):
                cleaning.parse_amount(value)

    def test_keeps_two_decimals(self):
        self.assertEqual(str(cleaning.parse_amount("7")), "7.00")


class DateTests(unittest.TestCase):
    def test_accepts_formats(self):
        expected = date(2026, 3, 15)
        for value in ("2026-03-15", "2026/03/15", "03/15/2026", "3/15/2026",
                      "March 15, 2026", "Mar 15 2026", "15 March 2026",
                      "2026-03-15 00:00:00", datetime(2026, 3, 15, 8, 0), expected):
            self.assertEqual(cleaning.parse_date(value, TODAY), expected, value)

    def test_rejects_future_ancient_and_garbage(self):
        for value in ("2026-11-25", "1999-12-31", "15/03/2026", "soon", ""):
            with self.assertRaises(cleaning.FieldError, msg=value):
                cleaning.parse_date(value, TODAY)


class RecordTests(unittest.TestCase):
    def test_fundraising_clean_record(self):
        cleaned, errors = clean("fundraising", {
            "fundraising_date": "11/02/2026",
            "amount": "2,500",
            "payment_method": "  g-cash ",
            "reference_no": "  REF   001 ",
            "notes": "  Bake sale\r\n  ",
        })
        self.assertEqual(errors, [])
        self.assertEqual(cleaned, {
            "fundraising_date": date(2026, 11, 2),
            "amount": Decimal("2500.00"),
            "payment_method": "GCash",
            "reference_no": "REF 001",
            "notes": "Bake sale",
        })

    def test_blank_optional_fields_become_none(self):
        cleaned, errors = clean("fundraising", {"fundraising_date": "2026-01-05", "amount": "10"})
        self.assertEqual(errors, [])
        self.assertIsNone(cleaned["payment_method"])
        self.assertIsNone(cleaned["notes"])

    def test_collects_every_error(self):
        _, errors = clean("sponsorships", {"sponsorship_date": "", "amount": "-1", "sponsor_name": " "})
        self.assertEqual(len(errors), 3)
        self.assertIn("Date is required.", errors)
        self.assertIn("Amount must be greater than zero.", errors)
        self.assertIn("Sponsor name is required.", errors)

    def test_length_limit(self):
        _, errors = clean("fundraising", {
            "fundraising_date": "2026-01-05", "amount": "1", "payment_method": "x" * 51,
        })
        self.assertEqual(errors, ["Payment method must be at most 50 characters."])

    def test_expense_category_reuses_existing_spelling(self):
        known = {"food & drinks": "Food & Drinks"}
        cleaned, errors = clean("expenses", {
            "expense_date": "2026-02-01", "amount": "300", "category": "  FOOD &  drinks ",
        }, known_categories=known)
        self.assertEqual(errors, [])
        self.assertEqual(cleaned["category"], "Food & Drinks")

    def test_expense_category_title_cased_when_new(self):
        cleaned, _ = clean("expenses", {"expense_date": "2026-02-01", "amount": "1", "category": "transportation"})
        self.assertEqual(cleaned["category"], "Transportation")


class MembershipFeeTests(unittest.TestCase):
    MEMBERS = {"knyc-001": ("KNYC-001", "active"), "knyc-002": ("KNYC-002", "inactive")}

    def fee(self, **overrides):
        raw = {"membership_id": "knyc-001", "quarter": "q2", "payment_date": "2026-04-03", "amount": "50"}
        raw.update(overrides)
        return raw

    def test_matches_member_ignoring_case_and_normalizes_quarter(self):
        cleaned, errors = clean("membership_fees", self.fee(), members=self.MEMBERS)
        self.assertEqual(errors, [])
        self.assertEqual(cleaned["membership_id"], "KNYC-001")
        self.assertEqual(cleaned["quarter"], "Q2")

    def test_quarter_number_only(self):
        cleaned, errors = clean("membership_fees", self.fee(quarter="4"), members=self.MEMBERS)
        self.assertEqual((errors, cleaned["quarter"]), ([], "Q4"))

    def test_unknown_member_and_bad_quarter(self):
        _, errors = clean("membership_fees", self.fee(membership_id="X9", quarter="Q5"), members=self.MEMBERS)
        self.assertEqual(len(errors), 2)

    def test_inactive_member_only_rejected_when_required(self):
        raw = self.fee(membership_id="KNYC-002")
        _, errors = clean("membership_fees", raw, members=self.MEMBERS)
        self.assertEqual(len(errors), 1)
        _, errors = clean("membership_fees", raw, members=self.MEMBERS, require_active_member=False)
        self.assertEqual(errors, [])


class FingerprintTests(unittest.TestCase):
    def test_same_payment_written_differently_is_duplicate(self):
        a, _ = clean("fundraising", {"fundraising_date": "2026-03-01", "amount": "1500", "reference_no": "abc-1"})
        b, _ = clean("fundraising", {"fundraising_date": "03/01/2026", "amount": "1,500.00",
                                     "reference_no": "ABC-1", "notes": "different note"})
        self.assertEqual(cleaning.fingerprint("fundraising", a), cleaning.fingerprint("fundraising", b))

    def test_cash_entries_with_different_notes_are_distinct(self):
        a, _ = clean("fundraising", {"fundraising_date": "2026-03-01", "amount": "100", "notes": "Booth A"})
        b, _ = clean("fundraising", {"fundraising_date": "2026-03-01", "amount": "100", "notes": "Booth B"})
        self.assertNotEqual(cleaning.fingerprint("fundraising", a), cleaning.fingerprint("fundraising", b))


class IngestionTests(unittest.TestCase):
    def test_csv_with_messy_headers_and_blank_rows(self):
        data = (
            "﻿ Fundraising Date ,AMOUNT,payment-method,Extra Column\n"
            "2026-03-01,100,Cash,ignored\n"
            ",,,\n"
            "2026-03-02,200,,\n"
        ).encode("utf-8")
        rows = ingestion.read_rows("fundraising", "march.csv", data)
        self.assertEqual([number for number, _ in rows], [2, 4])
        self.assertEqual(rows[0][1], {"fundraising_date": "2026-03-01", "amount": "100", "payment_method": "Cash"})

    def test_missing_required_column(self):
        with self.assertRaises(ingestion.IngestionError) as ctx:
            ingestion.read_rows("sponsorships", "s.csv", b"Sponsorship_Date,Amount\n2026-01-01,5\n")
        self.assertIn("Sponsor_Name", str(ctx.exception))

    def test_rejects_unsupported_and_empty_files(self):
        for name, data in (("a.xls", b"x"), ("a.txt", b"x"), ("a.csv", b""), ("a.csv", b"Fundraising_Date,Amount\n")):
            with self.assertRaises(ingestion.IngestionError, msg=name):
                ingestion.read_rows("fundraising", name, data)

    def test_non_utf8_csv(self):
        with self.assertRaises(ingestion.IngestionError):
            ingestion.read_rows("fundraising", "a.csv", "Fundraising_Date,Amount\n2026-01-01,₱5\n".encode("utf-16"))

    def test_xlsx(self):
        from openpyxl import Workbook
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Membership_ID", "Quarter", "Payment_Date", "Amount"])
        sheet.append([1001, "Q1", datetime(2026, 1, 15), 50.0])
        buffer = io.BytesIO()
        workbook.save(buffer)

        rows = ingestion.read_rows("membership_fees", "fees.xlsx", buffer.getvalue())
        self.assertEqual(len(rows), 1)
        cleaned, errors = clean(
            "membership_fees", rows[0][1], members={"1001": ("1001", "active")}
        )
        self.assertEqual(errors, [])
        self.assertEqual(cleaned["membership_id"], "1001")
        self.assertEqual(cleaned["payment_date"], date(2026, 1, 15))
        self.assertEqual(cleaned["amount"], Decimal("50.00"))

    def test_corrupt_xlsx(self):
        with self.assertRaises(ingestion.IngestionError):
            ingestion.read_rows("fundraising", "bad.xlsx", b"not a zip file")


class SheetRowTests(unittest.TestCase):
    def test_row_layout(self):
        values, _ = clean("membership_fees", {
            "membership_id": "KNYC-001", "quarter": "Q1", "payment_date": "2026-01-15",
            "amount": "50", "notes": "=HYPERLINK(\"x\")",
        }, members={"knyc-001": ("KNYC-001", "active")})
        row = sheets_mirror.row_values(
            "membership_fees", 7, values,
            created_at=datetime(2026, 1, 15, 9, 30),
            extras={"member_name": "Juan Dela Cruz", "org_role": "Member"},
        )
        headers = sheets_mirror.sheet_headers("membership_fees")
        record = dict(zip(headers, row))
        self.assertEqual(len(row), len(headers))
        self.assertEqual(headers[:len(sheets_schema.headers("membership_fees"))],
                         sheets_schema.headers("membership_fees"))
        self.assertEqual(record["record_id"], "7")
        self.assertEqual(record["amount"], 50.0)              # a number, so SUM() works
        self.assertEqual(record["payment_date"], "2026-01-15")
        self.assertEqual(record["notes"], "=HYPERLINK(\"x\")")  # written RAW, stays text
        self.assertEqual(record["status"], "active")
        self.assertEqual(record["created_at"], "2026-01-15 09:30:00")
        self.assertEqual(record["member_name"], "Juan Dela Cruz")
        self.assertEqual(record["import_key"], cleaning.fingerprint("membership_fees", values))


class PublicDatasetTests(unittest.TestCase):
    PRIVATE_VALUES = ("KNYC-001", "REF-9", "secret note", "Juan", "GCash", "Acme Corp", "lunch for Juan")

    def test_combined_table_is_public_safe_and_sorted(self):
        from services.finance import public_dataset
        fee, _ = clean("membership_fees", {
            "membership_id": "KNYC-001", "quarter": "Q1", "payment_date": "2026-02-10",
            "amount": "50", "payment_method": "gcash", "reference_no": "REF-9", "notes": "secret note",
        }, members={"knyc-001": ("KNYC-001", "active")})
        sponsor, _ = clean("sponsorships", {"sponsorship_date": "2026-01-05", "sponsor_name": "Acme Corp", "amount": "5000"})
        expense, _ = clean("expenses", {"expense_date": "2026-03-31", "category": "Food",
                                        "description": "lunch for Juan", "amount": "300.50"})
        table = public_dataset.build_table({
            "membership_fees": [fee], "sponsorships": [sponsor], "expenses": [expense], "fundraising": [],
        })

        self.assertEqual(table[0], public_dataset.PUBLIC_HEADERS)
        self.assertEqual([row[0] for row in table[1:]], ["2026-01-05", "2026-02-10", "2026-03-31"])
        self.assertEqual(table[1], ["2026-01-05", 2026, "2026-Q1", "2026-01", "Income",
                                    "Sponsorships", "Sponsorships", 5000.0, 5000.0])
        self.assertEqual(table[3][4:], ["Expense", "Expenses", "Food", 300.5, -300.5])
        flat = " ".join(str(cell) for row in table for cell in row)
        for private in self.PRIVATE_VALUES:
            self.assertNotIn(private, flat)

    def test_quarter_boundaries(self):
        from services.finance import public_dataset
        for day, quarter in ((date(2026, 3, 31), "2026-Q1"), (date(2026, 4, 1), "2026-Q2"),
                             (date(2026, 12, 31), "2026-Q4")):
            row = public_dataset.transaction_row("fundraising", {"fundraising_date": day, "amount": Decimal("1")})
            self.assertEqual(row[2], quarter)


if __name__ == "__main__":
    unittest.main()
