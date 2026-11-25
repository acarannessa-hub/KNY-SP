"""
Tests for the treasurer-spreadsheet preprocessing (no database, no Google).

The CSV snippets copy the COLUMN LAYOUT and the kinds of messy values found
in KNYC's real sheets (P-prefixed amounts, N/A, two-digit years, "Deffered",
names with line breaks), but every name, number and reference is made up.

Run from the project folder:
    python -m unittest discover -s tests -v
"""

import os
import sys
import unittest
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.finance import cleaning, ingestion, membership_import, public_dataset  # noqa: E402

TODAY = date(2026, 11, 25)

EXPENSES_CSV = (
    "Expense_ID,Date,Activity,Category,Short_Description,Amount,Payment_Method,"
    "Reference_Number / Sales Invoice No. \n"
    ",8/31/2025,Sample Anniversary ,Fees,Transaction fee ,18.00,GCASH,CA Withdrawal\n"
    ',10/25/2025,Sample Forum,Venue,Event Place Fee,"P 3,000.00",CASH,N/A\n'
    ',12/27/2025,Sample Assembly,Food,Food Expense,"9,678 .00",CASH,N/A\n'
    ",,,,,,,\n"
    ",08/23/26,Sample Anniversary,Transportation,Fare,₱180.00,MARIBANK,BC0000000001\n"
    ',,Sample Outreach,Food,Snacks,"1,869.00",CASH,\n'
).encode("utf-8")

FUNDRAISING_CSV = (
    "Fundraising_ID,Date,Activity,Income_Type,Amount,Payment_Method,Reference_Number,ACCOUNT NO./ NAME,,,\n"
    ",04/14/2026,Sample Drive,Donations,200.00,GCASH,7000000000001,Juan Example,,,\n"
    ",05/12/2026,Sample Seminar,Registration Fees,20.00,MAYA,N/A,Maria Sample,,,\n"
    ",05/12/2026,Sample Seminar,Registration Fees,20.00,MAYA,N/A,Pedro Sample,,,\n"
).encode("utf-8")

SPONSORSHIPS_CSV = (
    "Sponsorship_ID,Date,Sponsor,Sponsor_Type,Amount,Payment_Method,Reference_Number,Purpose\n"
    ',10/25/2025,Sample Travel Co.,Business," 1, 000.00",CASH,N/A,Sample Forum\n'
).encode("utf-8")


class TreasurerLedgerTests(unittest.TestCase):
    def rows(self, ledger, data):
        return ingestion.read_rows(ledger, f"{ledger}.csv", data)

    def test_expense_columns_and_values(self):
        rows = self.rows("expenses", EXPENSES_CSV)
        self.assertEqual(len(rows), 5)                     # blank separator row ignored
        number, raw = rows[0]
        self.assertEqual(number, 2)
        self.assertEqual(raw["activity"], "Sample Anniversary ")
        self.assertEqual(raw["description"], "Transaction fee ")
        self.assertEqual(raw["reference_no"], "CA Withdrawal")

        cleaned = [cleaning.clean_record("expenses", r, today=TODAY) for _, r in rows]
        (first, e1), (venue, e2), (food, e3), (fare, e4), (_, e5) = cleaned
        self.assertEqual((e1, e2, e3, e4), ([], [], [], []))
        self.assertEqual(first["activity"], "Sample Anniversary")
        self.assertEqual(first["payment_method"], "GCash")
        self.assertEqual(venue["amount"], Decimal("3000.00"))
        self.assertIsNone(venue["reference_no"])           # "N/A" -> empty
        self.assertEqual(food["amount"], Decimal("9678.00"))
        self.assertEqual(fare["expense_date"], date(2026, 8, 23))
        self.assertEqual(fare["payment_method"], "MariBank")
        self.assertEqual(e5, ["Date is required."])        # blank date -> review

    def test_fundraising_payer_kept_private(self):
        rows = self.rows("fundraising", FUNDRAISING_CSV)
        values = [cleaning.clean_record("fundraising", r, today=TODAY)[0] for _, r in rows]
        self.assertEqual(values[0]["income_type"], "Donation")
        self.assertEqual(values[1]["income_type"], "Registration Fee")
        self.assertEqual(values[0]["payer"], "Juan Example")
        # Same date/amount/no reference but different payers: not duplicates.
        self.assertNotEqual(cleaning.fingerprint("fundraising", values[1]),
                            cleaning.fingerprint("fundraising", values[2]))
        table = public_dataset.build_table({"fundraising": values})
        flat = " ".join(str(c) for row in table for c in row)
        self.assertNotIn("Example", flat)
        self.assertNotIn("7000000000001", flat)
        self.assertIn("Registration Fee", flat)
        self.assertIn("Sample Seminar", flat)              # activity is public

    def test_sponsorship_columns(self):
        (_, raw), = self.rows("sponsorships", SPONSORSHIPS_CSV)
        cleaned, errors = cleaning.clean_record("sponsorships", raw, today=TODAY)
        self.assertEqual(errors, [])
        self.assertEqual(cleaned["sponsor_name"], "Sample Travel Co.")
        self.assertEqual(cleaned["sponsor_type"], "Business")
        self.assertEqual(cleaned["activity"], "Sample Forum")
        self.assertEqual(cleaned["amount"], Decimal("1000.00"))
        row = public_dataset.build_table({"sponsorships": [cleaned]})[1]
        self.assertEqual(row[6], "Sponsorship (Business)")
        self.assertNotIn("Sample Travel Co.", row)


FEES_HEADER = ("Membership_ID,Last_Name,First_Name,Middle_Name,Year,Date,Mem_Type,Com_or_Pos,"
               "Amount,Payment_Method,Reference_Number,Status,Balance\n")


def fee_rows(body, header=FEES_HEADER):
    return ingestion.read_table("Membership_Fees_Q3.csv", (header + body).encode("utf-8"))


class MembershipSheetTests(unittest.TestCase):
    INDEX = membership_import.MemberIndex([
        ("KNYC-001", "Ana Marie", "Reyes", "SANTOS", "active"),
        ("KNYC-002", "Ben", None, "Cruz", "active"),
        ("KNYC-003", "Carla Jean", "Lopez", "Dela Paz", "inactive"),
    ])

    def analyze(self, body, overrides=None, header=FEES_HEADER):
        headers, rows = fee_rows(body, header)
        return membership_import.analyze(headers, rows, "Q3", self.INDEX, TODAY, overrides)

    def test_quarter_from_filename(self):
        self.assertEqual(membership_import.quarter_from_filename("KNYC - Membership_Fees_Q2.csv"), "Q2")
        self.assertEqual(membership_import.quarter_from_filename("fees_q4.xlsx"), "Q4")
        self.assertIsNone(membership_import.quarter_from_filename("fees.csv"))

    def test_paid_row_matches_member_despite_messy_name(self):
        (item,) = self.analyze(',"SANTOS\n","Ana Marie R. ",Reyes,2026,09/10/26,Member,Official Member,90.00,GCASH,7000000000009,PAID,0.00\n')
        self.assertEqual(item.membership_id, "KNYC-001")
        self.assertEqual(item.status, "paid")
        self.assertEqual(item.amount_paid, Decimal("90.00"))
        self.assertEqual(item.payment["payment_date"], date(2026, 9, 10))
        self.assertEqual(item.review, [])

    def test_close_spelling_is_matched_and_noted(self):
        (item,) = self.analyze(",Dela Paz,Carla Jhean,Lopez,2025,08/20/25,Member,Official Member,90.00,CASH,N/A,PAID,0.00\n")
        self.assertEqual(item.membership_id, "KNYC-003")
        self.assertTrue(any("matched to member" in note for note in item.notes))

    def test_partial_payment(self):
        (item,) = self.analyze(",Cruz,Ben,N/A,2026,09/10/26,Executive,Chairperson,50.00,GCASH,7000000000010,PAID,40.00\n")
        self.assertEqual((item.status, item.amount_paid, item.balance, item.amount_due),
                         ("partial", Decimal("50.00"), Decimal("40.00"), Decimal("90.00")))
        self.assertIsNotNone(item.payment)

    def test_deferred_and_unpaid_create_no_payment(self):
        items = self.analyze(
            ",Cruz,Ben,,2026,,Member,Official Member,90.00,,,Deffered,90.00\n"
            ",SANTOS,Ana Marie,Reyes,2026,,Member,Official Member,,,,UNPAID,90.00\n"
        )
        self.assertEqual([i.status for i in items], ["deferred", "unpaid"])
        self.assertTrue(all(i.payment is None and i.balance == Decimal("90.00") for i in items))
        self.assertTrue(all(i.review == [] for i in items))

    def test_unknown_date_needs_review_then_override(self):
        body = ",Cruz,Ben,,2025,12/2025,Member,Official Member,90.00,CASH,N/A,PAID,0.00\n"
        (item,) = self.analyze(body)
        self.assertEqual([k for k, _ in item.review], ["date"])
        (fixed,) = self.analyze(body, overrides={2: {"date": "2025-12-27"}})
        self.assertEqual(fixed.review, [])
        self.assertEqual(fixed.payment["payment_date"], date(2025, 12, 27))

    def test_unpaid_with_payment_evidence_is_a_conflict(self):
        body = ",Cruz,Ben,,2026,11/04/26,Executive,Secretary,90.00,,7000000000011,UNPAID,0.00\n"
        (item,) = self.analyze(body)
        self.assertEqual([k for k, _ in item.review], ["conflict"])
        (fixed,) = self.analyze(body, overrides={2: {"treat_as_paid": True}})
        self.assertEqual((fixed.review, fixed.status), ([], "paid"))

    def test_unknown_member_review_and_create(self):
        body = ",Newperson,Dana,Ortiz,2026,,Member,Official Member,90.00,,,UNPAID,90.00\n"
        (item,) = self.analyze(body)
        self.assertEqual([k for k, _ in item.review], ["member"])
        (created,) = self.analyze(body, overrides={2: {"create_member": True}})
        self.assertEqual(created.review, [])
        self.assertEqual(created.new_member["last_name"], "Newperson")
        self.assertEqual(created.new_member["status"], "active")

    def test_paid_without_amount_needs_amount(self):
        (item,) = self.analyze(",Cruz,Ben,,2025,1/17/2025,Head,Committee,,GCASH,7000000000012,PAID,0.00\n")
        self.assertIn("amount", [k for k, _ in item.review])

    def test_blank_date_header_column_is_found(self):
        header = FEES_HEADER.replace("Year,Date,", "Year,,")
        (item,) = self.analyze(",Cruz,Ben,,2025,12/07/25,Member,Official Member,90.00,GCASH,7000000000013,PAID,0.00\n",
                               header=header)
        self.assertEqual(item.payment["payment_date"], date(2025, 12, 7))

    def test_bad_status_is_an_error(self):
        (item,) = self.analyze(",Cruz,Ben,,2025,,Member,Official Member,90.00,,,MAYBE,0.00\n")
        self.assertIn("Status", item.error)


class SyncCompareTests(unittest.TestCase):
    def test_detects_missing_extra_edited_and_hand_typed_rows(self):
        from services.finance import sheets_mirror
        rec1, _ = cleaning.clean_record("fundraising", {"fundraising_date": "2026-03-01", "amount": "100"}, today=TODAY)
        rec2, _ = cleaning.clean_record("fundraising", {"fundraising_date": "2026-03-02", "amount": "200"}, today=TODAY)
        rec3, _ = cleaning.clean_record("fundraising", {"fundraising_date": "2026-03-03", "amount": "300"}, today=TODAY)
        db = {str(i): cleaning.fingerprint("fundraising", r) for i, r in ((1, rec1), (2, rec2), (3, rec3))}

        def sheet_row(record_id, record, amount_text=None):
            row = {"record_id": str(record_id), "fundraising_date": record["fundraising_date"].isoformat(),
                   "amount": amount_text or f"{record['amount']:,}"}
            return row

        in_sync = [sheet_row(1, rec1), sheet_row(2, rec2), sheet_row(3, rec3)]
        self.assertTrue(sheets_mirror.compare("fundraising", db, in_sync)["ok"])

        drifted = [
            sheet_row(1, rec1),
            sheet_row(2, rec2, amount_text="250"),           # amount typed over in the sheet
            sheet_row(9, rec3),                               # id not in the database
            {"record_id": "", "fundraising_date": "2026-03-04", "amount": "5"},  # typed by hand
        ]                                                     # record 3 missing
        result = sheets_mirror.compare("fundraising", db, drifted)
        self.assertFalse(result["ok"])
        self.assertEqual(result["missing"], ["3"])
        self.assertEqual(result["extra"], ["9"])
        self.assertEqual(result["changed"], ["2"])
        self.assertEqual(result["unlabeled"], 1)


class DuesSummaryTests(unittest.TestCase):
    def test_totals_per_period_without_names(self):
        dues = [
            {"year": 2026, "quarter": "Q3", "amount_due": Decimal("90"), "amount_paid": Decimal("90"),
             "balance": Decimal("0"), "status": "paid", "membership_id": "KNYC-001"},
            {"year": 2026, "quarter": "Q3", "amount_due": Decimal("90"), "amount_paid": Decimal("50"),
             "balance": Decimal("40"), "status": "partial", "membership_id": "KNYC-002"},
            {"year": 2026, "quarter": "Q3", "amount_due": Decimal("90"), "amount_paid": Decimal("0"),
             "balance": Decimal("90"), "status": "deferred", "membership_id": "KNYC-003"},
        ]
        header, row = public_dataset.build_dues_summary(dues)
        self.assertEqual(header, public_dataset.DUES_SUMMARY_HEADERS)
        self.assertEqual(row, ["2026-Q3", 2026, "Q3", 3, 1, 1, 1, 270.0, 140.0, 130.0, 0.5185])
        self.assertNotIn("KNYC-001", [str(c) for c in row])


if __name__ == "__main__":
    unittest.main()
