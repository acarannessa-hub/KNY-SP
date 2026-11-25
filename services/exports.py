"""Export Management: what can be exported, and turning it into CSV / Excel / PDF.

    DATASETS                     every exportable dataset and who may get it
    build(key, start, end)       -> list[Section] (plain Python values)
    render(sections, fmt, meta)  -> (bytes, mimetype, extension)

Nothing here touches Flask requests or permissions; app.py decides who may
download what, and logs every export.

Privacy
- Datasets marked `personal` contain names, emails, payers or reference
  numbers (Data Privacy Act). Non-admins must request them and wait for an
  admin's approval; files carry a confidentiality notice.
- The "summary" dataset only has monthly totals, so any logged-in user may
  download it straight away.

Security
- Text that a spreadsheet would treat as a formula (= + - @ ...) is prefixed
  with an apostrophe in CSV and Excel files (CSV / formula injection).
"""

import csv
import io
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from models import db, Member, Due, Profile
from services.finance import LEDGERS
from services.finance import records as finance_records
from services.notifications.mailer import ORG_NAME

FORMATS = OrderedDict([("xlsx", "Excel (.xlsx)"), ("csv", "CSV"), ("pdf", "PDF")])


@dataclass(frozen=True)
class Dataset:
    key: str
    label: str
    description: str
    personal: bool          # contains personal data -> approval needed for non-admins
    admin_only: bool = False
    uses_dates: bool = True


DATASETS = OrderedDict((d.key, d) for d in [
    Dataset("all", "All financial records",
            "Fundraising, sponsorships, membership fees and expenses, one section each, with totals.", True),
    Dataset("fundraising", "Fundraising", "Every fundraising record with activity, income type and payer.", True),
    Dataset("sponsorships", "Sponsorships", "Every sponsorship with sponsor, type and activity.", True),
    Dataset("membership_fees", "Membership fees", "Every fee payment with the member's name.", True),
    Dataset("expenses", "Expenses", "Every expense with activity, category and description.", True),
    Dataset("dues", "Dues status", "What each member owed and paid per quarter.", True),
    Dataset("summary", "Monthly summary",
            "Income and expenses per month, totals only. Safe to share.", False),
    Dataset("members", "Member directory", "Members with organization role, email and login role.",
            True, admin_only=True, uses_dates=False),
])


def datasets_for(role):
    return [d for d in DATASETS.values() if role == "admin" or not d.admin_only]


def needs_approval(dataset_key, role):
    return role != "admin" and DATASETS[dataset_key].personal


@dataclass
class Section:
    title: str
    headers: list
    rows: list = field(default_factory=list)
    money: set = field(default_factory=set)      # column indexes holding amounts
    total: bool = True                           # add a total row for money columns
    kind: str = ""                               # income / expense / ""


def _period_label(start, end):
    return f"{start.isoformat() if start else 'Beginning'} to {end.isoformat() if end else 'Present'}"


# --------------------------------------------------
# Building the data
# --------------------------------------------------
def _ledger_section(key, start, end):
    ledger = LEDGERS[key]
    model = finance_records.MODELS[key]
    date_col = getattr(model, ledger.date_field)
    query = model.query
    if start:
        query = query.filter(date_col >= start)
    if end:
        query = query.filter(date_col <= end)
    records = query.order_by(date_col, model.id).all()

    headers = []
    money = set()
    for f in ledger.fields:
        if f.kind == "amount":
            money.add(len(headers))
        headers.append(f.label)
        if f.kind == "member":
            headers.append("Member name")
    section = Section(ledger.label, headers, money=money, kind=ledger.kind)
    for record in records:
        values = finance_records._values(key, record)
        row = []
        for f in ledger.fields:
            value = values.get(f.name)
            row.append(value if value is not None else "")
            if f.kind == "member":
                member = getattr(record, "member", None)
                row.append(member.full_name if member else "")
        section.rows.append(row)
    return section


def _dues_section(start, end):
    query = Due.query
    if start:
        query = query.filter(Due.year >= start.year)
    if end:
        query = query.filter(Due.year <= end.year)
    names = {m.membership_id: m.full_name for m in Member.query}
    section = Section("Dues status", ["Year", "Quarter", "Membership ID", "Member", "Amount due",
                                      "Amount paid", "Balance", "Status"], money={4, 5, 6})
    for due in query.order_by(Due.year, Due.quarter, Due.membership_id):
        section.rows.append([due.year, due.quarter, due.membership_id, names.get(due.membership_id, ""),
                             due.amount_due, due.amount_paid, due.balance, due.status.capitalize()])
    return section


def _summary_section(start, end):
    months = OrderedDict()
    columns = ["fundraising", "sponsorships", "membership_fees", "expenses"]
    for key in columns:
        ledger_section = _ledger_section(key, start, end)
        date_index = 0
        amount_index = min(ledger_section.money)
        for row in ledger_section.rows:
            month = row[date_index].strftime("%Y-%m") if hasattr(row[date_index], "strftime") else str(row[date_index])[:7]
            months.setdefault(month, {k: Decimal("0") for k in columns})
            months[month][key] += Decimal(row[amount_index] or 0)
    section = Section("Monthly summary", ["Month", "Fundraising", "Sponsorships", "Membership fees",
                                          "Total income", "Expenses", "Net"], money={1, 2, 3, 4, 5, 6})
    for month in sorted(months):
        m = months[month]
        income = m["fundraising"] + m["sponsorships"] + m["membership_fees"]
        section.rows.append([month, m["fundraising"], m["sponsorships"], m["membership_fees"],
                             income, m["expenses"], income - m["expenses"]])
    return section


def _members_section():
    section = Section("Member directory", ["Membership ID", "Last name", "First name", "Middle name",
                                           "Organization role", "Email", "Login role", "Status"], total=False)
    for member in Member.query.order_by(Member.last_name, Member.first_name):
        account = next((a for a in member.users or [] if a.status == "active"), None)
        section.rows.append([member.membership_id, member.last_name, member.first_name,
                             member.middle_name or "", member.org_role, member.notify_email or "",
                             account.role.capitalize() if account else "", member.status.capitalize()])
    return section


def build(dataset_key, start=None, end=None):
    if dataset_key not in DATASETS:
        raise ValueError("Unknown dataset.")
    if not DATASETS[dataset_key].uses_dates:
        start = end = None
    if dataset_key == "all":
        return [_ledger_section(k, start, end) for k in ("fundraising", "sponsorships", "membership_fees", "expenses")]
    if dataset_key in LEDGERS:
        return [_ledger_section(dataset_key, start, end)]
    if dataset_key == "dues":
        return [_dues_section(start, end)]
    if dataset_key == "summary":
        return [_summary_section(start, end)]
    return [_members_section()]


def totals(section):
    sums = {}
    for index in section.money:
        sums[index] = sum((Decimal(row[index] or 0) for row in section.rows), Decimal("0"))
    return sums


def overview(sections):
    """Totals across ledger sections, for the summary sheet / PDF ending."""
    income = sum((totals(s).get(min(s.money), Decimal("0")) for s in sections if s.kind == "income"), Decimal("0"))
    expense = sum((totals(s).get(min(s.money), Decimal("0")) for s in sections if s.kind == "expense"), Decimal("0"))
    return income, expense


# --------------------------------------------------
# Rendering
# --------------------------------------------------
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def safe_text(value):
    """Stop spreadsheets from running text as a formula."""
    if isinstance(value, str) and value.startswith(_FORMULA_START):
        return "'" + value
    return value


def _cell_text(value):
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


@dataclass
class Meta:
    dataset: Dataset
    start: object
    end: object
    generated_by: str
    generated_at: str

    @property
    def period(self):
        return _period_label(self.start, self.end) if self.dataset.uses_dates else "Current"

    @property
    def notice(self):
        if self.dataset.personal:
            return ("CONFIDENTIAL: contains personal data. Use only for organization business, "
                    "do not share publicly, and delete when no longer needed (Data Privacy Act of 2012).")
        return "Totals only; contains no personal data."


def filename(meta, ext):
    period = ""
    if meta.dataset.uses_dates and (meta.start or meta.end):
        period = f"_{meta.start.isoformat() if meta.start else 'start'}_to_{meta.end.isoformat() if meta.end else 'present'}"
    return f"knyc_{meta.dataset.key}{period}_{meta.generated_at[:10]}.{ext}"


def render(sections, fmt, meta):
    if fmt == "csv":
        return _csv(sections), "text/csv; charset=utf-8", "csv"
    if fmt == "xlsx":
        return _xlsx(sections, meta), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"
    if fmt == "pdf":
        return _pdf(sections, meta), "application/pdf", "pdf"
    raise ValueError("Unknown format.")


def _csv(sections):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    if len(sections) == 1:
        s = sections[0]
        writer.writerow(s.headers)
        for row in s.rows:
            writer.writerow([safe_text(_cell_text(v)) for v in row])
    else:
        # One table: a "Ledger" column plus the union of every section's columns.
        columns = []
        for s in sections:
            for h in s.headers:
                if h not in columns:
                    columns.append(h)
        writer.writerow(["Ledger"] + columns)
        for s in sections:
            for row in s.rows:
                cells = dict(zip(s.headers, row))
                writer.writerow([s.title] + [safe_text(_cell_text(cells.get(h, ""))) for h in columns])
    return ("﻿" + output.getvalue()).encode("utf-8")


def _xlsx(sections, meta):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    about = wb.active
    about.title = "About"
    header_fill = PatternFill("solid", fgColor="5D4B9A")
    total_fill = PatternFill("solid", fgColor="E9E3F5")
    lines = [
        (ORG_NAME, Font(bold=True, size=14)),
        (meta.dataset.label, Font(bold=True, size=12, color="5D4B9A")),
        (f"Period: {meta.period}", None),
        (f"Generated: {meta.generated_at} by {meta.generated_by}", None),
        (meta.notice, Font(bold=True, color="9B2F3C" if meta.dataset.personal else "315C37")),
    ]
    for i, (text, font) in enumerate(lines, start=1):
        cell = about.cell(row=i, column=1, value=text)
        if font:
            cell.font = font
    row_n = len(lines) + 2
    about.cell(row=row_n, column=1, value="Sheet").font = Font(bold=True)
    about.cell(row=row_n, column=2, value="Records").font = Font(bold=True)
    for s in sections:
        row_n += 1
        about.cell(row=row_n, column=1, value=s.title)
        about.cell(row=row_n, column=2, value=len(s.rows))
    if any(s.kind for s in sections) and len(sections) > 1:
        income, expense = overview(sections)
        for label, value in (("Total income", income), ("Total expenses", expense), ("Net", income - expense)):
            row_n += 1
            about.cell(row=row_n, column=1, value=label).font = Font(bold=True)
            c = about.cell(row=row_n, column=2, value=float(value))
            c.number_format = "#,##0.00"
    about.column_dimensions["A"].width = 60
    about.column_dimensions["B"].width = 16

    for s in sections:
        ws = wb.create_sheet(title=s.title[:31])
        ws.append(s.headers)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = header_fill
            cell.alignment = Alignment(vertical="center")
        for row in s.rows:
            out = []
            for i, v in enumerate(row):
                if i in s.money:
                    out.append(float(v or 0))
                elif isinstance(v, (date, int)) and not isinstance(v, bool):
                    out.append(v)
                else:
                    out.append(safe_text(_cell_text(v)))
            ws.append(out)
        if s.total and s.money and s.rows:
            sums = totals(s)
            total_row = ["Total" if i == 0 else (float(sums[i]) if i in sums else "") for i in range(len(s.headers))]
            ws.append(total_row)
            for cell in ws[ws.max_row]:
                cell.font = Font(bold=True)
                cell.fill = total_fill
        for col_index in range(1, len(s.headers) + 1):
            letter = get_column_letter(col_index)
            if col_index - 1 in s.money:
                for cell in ws[letter][1:]:
                    cell.number_format = "#,##0.00"
            elif s.rows and isinstance(s.rows[0][col_index - 1], date):
                for cell in ws[letter][1:]:
                    cell.number_format = "yyyy-mm-dd"
            longest = max([len(str(s.headers[col_index - 1]))] +
                          [len(_cell_text(r[col_index - 1])) for r in s.rows[:500]])
            ws.column_dimensions[letter].width = min(max(10, longest + 2), 60)
        ws.freeze_panes = "A2"
        if s.rows:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(s.headers))}{len(s.rows) + 1}"

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _pdf(sections, meta):
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    page = landscape(A4)
    doc = SimpleDocTemplate(buffer, pagesize=page, leftMargin=0.4 * inch, rightMargin=0.4 * inch,
                            topMargin=0.45 * inch, bottomMargin=0.55 * inch,
                            title=f"{ORG_NAME} - {meta.dataset.label}", author=ORG_NAME)
    styles = getSampleStyleSheet()
    purple = colors.HexColor("#5d4b9a")
    h_org = ParagraphStyle("org", parent=styles["Heading2"], textColor=purple, spaceAfter=2)
    h_title = ParagraphStyle("title", parent=styles["Title"], alignment=0, fontSize=18, spaceAfter=4)
    small = ParagraphStyle("small", parent=styles["BodyText"], fontSize=8, leading=10)
    cell = ParagraphStyle("cell", parent=styles["BodyText"], fontSize=7, leading=8.5)
    notice_style = ParagraphStyle("notice", parent=small,
                                  textColor=colors.HexColor("#9b2f3c" if meta.dataset.personal else "#315c37"))

    story = [
        Paragraph(escape(ORG_NAME), h_org),
        Paragraph(escape(meta.dataset.label), h_title),
        Paragraph(f"Period: {escape(meta.period)} &nbsp;&nbsp; Generated: {escape(meta.generated_at)} "
                  f"by {escape(meta.generated_by)}", small),
        Paragraph(escape(meta.notice), notice_style),
        Spacer(1, 10),
    ]
    usable = page[0] - doc.leftMargin - doc.rightMargin
    for s in sections:
        story.append(Paragraph(f"{escape(s.title)} ({len(s.rows)} record{'s' if len(s.rows) != 1 else ''})",
                               styles["Heading3"]))
        data = [[Paragraph(f"<b>{escape(h)}</b>", ParagraphStyle('hd', parent=cell, textColor=colors.white))
                 for h in s.headers]]
        if not s.rows:
            data.append([Paragraph("No records for this period.", cell)] + [""] * (len(s.headers) - 1))
        for row in s.rows:
            data.append([
                f"{Decimal(v or 0):,.2f}" if i in s.money else Paragraph(escape(_cell_text(v)), cell)
                for i, v in enumerate(row)
            ])
        has_total = s.total and s.money and s.rows
        if has_total:
            sums = totals(s)
            data.append(["Total" if i == 0 else (f"{sums[i]:,.2f}" if i in sums else "")
                         for i in range(len(s.headers))])
        # money/date columns narrow, text columns share the rest
        weights = [0.9 if i in s.money else (1.0 if "date" in h.lower() or h in ("Year", "Quarter") else 1.6)
                   for i, h in enumerate(s.headers)]
        widths = [usable * w / sum(weights) for w in weights]
        table = Table(data, repeatRows=1, colWidths=widths)
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), purple),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d9d6e3")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 1), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        for i in s.money:
            style.append(("ALIGN", (i, 1), (i, -1), "RIGHT"))
            style.append(("RIGHTPADDING", (i, 0), (i, -1), 8))
        if len(data) > 2:
            style.append(("ROWBACKGROUNDS", (0, 1), (-1, -2 if has_total else -1),
                          [colors.white, colors.HexColor("#f6f4fa")]))
        if has_total:
            style += [("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e9e3f5")),
                      ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")]
        table.setStyle(TableStyle(style))
        story += [table, Spacer(1, 12)]

    if len(sections) > 1 and any(s.kind for s in sections):
        income, expense = overview(sections)
        story.append(Paragraph(f"Total income: {income:,.2f} &nbsp;&nbsp; Total expenses: {expense:,.2f} "
                               f"&nbsp;&nbsp; <b>Net: {income - expense:,.2f}</b>", styles["Heading3"]))

    footer_text = f"{ORG_NAME} · {meta.dataset.label} · {meta.period}"

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawString(document.leftMargin, 0.3 * inch, footer_text[:150])
        canvas.drawRightString(page[0] - document.rightMargin, 0.3 * inch, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
