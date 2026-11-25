"""
Definitions of the four financial ledgers.

The field order matches sheets_schema.TABS (the Google Sheet layout) and the
columns in models.py. Nothing here imports Flask or the database, so the
cleaning code and its tests can use it on their own.

Field kinds
    date            transaction date (required)
    amount          money, > 0, at most 2 decimals
    text            single-line text (whitespace collapsed)
    longtext        multi-line text (notes, descriptions)
    member          a membership ID that must exist in `members`
    quarter         Q1-Q4
    payment_method  free text, common spellings unified (GCash, Cash, ...)
    category        expense category, matched to existing spellings
    income_type     Donation / Registration Fee / Sponsorship / Event Proceeds ...
    sponsor_type    Individual / Business / Organization
    year            dues year (defaults to the payment date's year)

Privacy: `payer` (fundraising), `sponsor_name`, reference numbers and notes
are private; services/finance/public_dataset.py never publishes them.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    kind: str
    required: bool = False
    max_length: int | None = None


@dataclass(frozen=True)
class Ledger:
    key: str
    label: str            # page / report title, e.g. "Membership Fees"
    noun: str             # one record, e.g. "membership fee record"
    kind: str             # "income" or "expense"
    date_field: str
    fields: tuple

    @property
    def field_names(self):
        return [field.name for field in self.fields]

    @property
    def required_fields(self):
        return [field.name for field in self.fields if field.required]

    def field(self, name):
        for field in self.fields:
            if field.name == name:
                return field
        raise KeyError(name)


_PAYMENT_METHOD = Field("payment_method", "Payment method", "payment_method", max_length=50)
_REFERENCE_NO = Field("reference_no", "Reference number", "text", max_length=100)
_NOTES = Field("notes", "Notes", "longtext", max_length=2000)
_AMOUNT = Field("amount", "Amount", "amount", required=True)
_ACTIVITY = Field("activity", "Activity", "text", max_length=255)


LEDGERS = {
    "fundraising": Ledger(
        key="fundraising",
        label="Fundraising",
        noun="fundraising record",
        kind="income",
        date_field="fundraising_date",
        fields=(
            Field("fundraising_date", "Date", "date", required=True),
            _ACTIVITY,
            Field("income_type", "Income type", "income_type", max_length=50),
            _AMOUNT,
            _PAYMENT_METHOD,
            _REFERENCE_NO,
            Field("payer", "Account no. / name", "text", max_length=255),
            _NOTES,
        ),
    ),
    "sponsorships": Ledger(
        key="sponsorships",
        label="Sponsorships",
        noun="sponsorship record",
        kind="income",
        date_field="sponsorship_date",
        fields=(
            Field("sponsorship_date", "Date", "date", required=True),
            Field("sponsor_name", "Sponsor name", "text", required=True, max_length=150),
            Field("sponsor_type", "Sponsor type", "sponsor_type", max_length=50),
            _ACTIVITY,
            _AMOUNT,
            _PAYMENT_METHOD,
            _REFERENCE_NO,
            _NOTES,
        ),
    ),
    "membership_fees": Ledger(
        key="membership_fees",
        label="Membership Fees",
        noun="membership fee record",
        kind="income",
        date_field="payment_date",
        fields=(
            Field("membership_id", "Membership ID", "member", required=True, max_length=64),
            Field("year", "Dues year", "year"),
            Field("quarter", "Quarter", "quarter", required=True),
            Field("payment_date", "Payment date", "date", required=True),
            _AMOUNT,
            _PAYMENT_METHOD,
            _REFERENCE_NO,
            _NOTES,
        ),
    ),
    "expenses": Ledger(
        key="expenses",
        label="Expenses",
        noun="expense record",
        kind="expense",
        date_field="expense_date",
        fields=(
            Field("expense_date", "Date", "date", required=True),
            _ACTIVITY,
            Field("category", "Category", "category", required=True, max_length=100),
            Field("description", "Description", "longtext", max_length=2000),
            _AMOUNT,
            _PAYMENT_METHOD,
            _REFERENCE_NO,
            _NOTES,
        ),
    ),
}
