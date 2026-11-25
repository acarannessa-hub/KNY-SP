# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Three audiences, all confirmed by the owner:

- **Officers running the portal** (admins, the treasurer, encoders). They record and correct financial records, import the treasurer's spreadsheets, manage the member roster and portal accounts, schedule meetings and events, send dues reminders and warnings, and approve data exports. They work in short sessions between organization activities, often from the same few laptops and phones.
- **Members of the organization** (youth members of Kaya Natin! Youth – Candelaria). They mostly experience the product through email: meeting and event reminders, dues reminders, notices, account invitations and password resets. Some hold portal logins with the viewer or encoder role.
- **The public and community** (residents, sponsors, partners). They visit the public site to learn about the organization and to see how its money is raised and spent.

The site is a real organization website for day-to-day use, not an academic exercise.

## Product Purpose

The website for Kaya Natin! Youth – Candelaria, a youth organization in Candelaria. It has two halves:

- A **public site** that introduces the organization (introduction, history, mission and vision, eight thematic advocacies, roster, events, contact) and publishes its finances openly.
- A **private officers' portal** for financial management, user management (members, accounts, notifications) and export management.

Success means officers can keep the books and the roster accurate without spreadsheets drifting out of sync, members are reliably told about dues, meetings and events, and anyone in the community can see where the organization's money comes from and goes.

## Positioning

Financial transparency is the point, not a feature. The database is the official record; every add, edit, delete, import and export is written to an append-only audit trail that cannot be edited, and deleted records can be restored. Public figures are published from a privacy-safe dataset that never exposes names, payers, reference numbers or notes. A generic club website or a shared spreadsheet cannot truthfully claim that combination of openness and accountability.

## Operating Context

- Hosted free: Flask on Vercel (serverless), Supabase PostgreSQL and Supabase Auth, Google Sheets as a one-way copy of the ledgers, Looker Studio for the public analytics report (planned), Gmail (organization account) for all email.
- The treasurer keeps spreadsheets per quarter (fundraising, sponsorships, membership fees, expenses); the portal imports them through a preview-then-confirm step that flags problems row by row.
- Daily scheduled jobs keep the free database awake and send automatic meeting/event reminders (3 days and 1 day before, around 8:00 AM Philippine time).
- Money is Philippine pesos (₱); times are Philippine time (Asia/Manila).

## Capabilities and Constraints

- **Financial management:** four ledgers (fundraising, sponsorships, membership fees, expenses) plus quarterly dues status; add/edit/delete with validation and duplicate checks; CSV/Excel import; database-versus-Google-Sheet sync check; audit log with restore.
- **User management:** member roster with notification emails; portal accounts with roles admin, encoder and viewer; email invitations and self-service password reset by one-time link; safeguards against removing the last admin.
- **Notifications:** meetings and events with automatic reminders, dues reminders per quarter, warnings, and a full email history.
- **Export management:** Excel, CSV and PDF; the monthly summary (no personal data) downloads at once; anything with personal data needs an admin's password or an approved, expiring request.
- **Removed:** attendance tracking was deliberately removed; do not reintroduce it without a new decision.
- **Cost:** everything must stay on free tiers. Flag anything that would cost money (Gmail allows about 500 emails a day).
- **Open:** the public Looker Studio report is not yet connected; the "expected dues per member per quarter" amount is undecided.

## Brand Commitments

- Name: **Kaya Natin! Youth – Candelaria** (short form "Kaya Natin! Youth", portal abbreviation "KNY"). Keep the exclamation mark.
- Content language: English.

## Evidence on Hand

- Real financial data: the treasurer's spreadsheets (kept outside the repository; they contain personal data and must never be committed).
- Public-site text is **not yet written**: home, introduction, nature, history, mission, vision, the eight advocacies and their focus areas are placeholders. The organization will supply real text and photos later. Never invent mission statements, advocacy titles, history, testimonials, member names or statistics to fill them.

## Product Principles

1. **Transparent by default, private by design.** Publish totals openly; keep personal data (names, payers, reference numbers, emails) behind roles, approvals and the audit trail.
2. **The record is the truth.** One official database; copies (Google Sheet, exports, public report) are derived from it and say so.
3. **Every change is accountable.** Who did what, when, and what it looked like before must always be answerable.
4. **Officers are volunteers.** Workflows must be forgiving: previews before saving, plain-language errors, undo where possible, nothing that requires technical knowledge.
5. **Free to run.** No feature may depend on a paid service.

## Accessibility & Inclusion

Must comply with the Data Privacy Act of 2012 (Philippines) for personal data in exports and email. No specific accessibility standard has been set beyond readable, mobile-friendly pages; officers and members use phones as well as laptops.
