"""
services.finance -- the KNYC financial data pipeline.

    ingestion.py     read uploaded CSV / Excel (.xlsx) files into raw rows
    cleaning.py      normalize and validate one record (pure Python, no DB)
    records.py       save / update / delete / bulk-import through the database
    sheets_mirror.py copy each ledger to the dedicated Google Sheet

Routes in app.py should call records.py and never touch the models for
financial writes directly, so every entry path (form, CSV, Excel) passes
through the same cleaning and duplicate checks.
"""

from .ledgers import LEDGERS, Ledger, Field  # noqa: F401
