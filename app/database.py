from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.config import DATABASE_PATH, ensure_project_dirs


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_filename TEXT NOT NULL,
    stored_filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    active_path TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    total_rows INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS kpi_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL,
    sheet_name TEXT NOT NULL,
    row_number INTEGER NOT NULL,
    kpi_name TEXT NOT NULL,
    category TEXT,
    week_label TEXT NOT NULL,
    value_text TEXT,
    value_number REAL,
    value_cell TEXT NOT NULL,
    remarks_cell TEXT,
    current_remark TEXT,
    threshold REAL,
    status TEXT NOT NULL,
    metric_type TEXT NOT NULL,
    FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_kpi_report ON kpi_records(report_id);
CREATE INDEX IF NOT EXISTS idx_kpi_name ON kpi_records(kpi_name);
CREATE INDEX IF NOT EXISTS idx_kpi_status ON kpi_records(status);
CREATE INDEX IF NOT EXISTS idx_kpi_week ON kpi_records(week_label);

CREATE TABLE IF NOT EXISTS remarks_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL,
    kpi_record_id INTEGER NOT NULL,
    workbook_path TEXT NOT NULL,
    sheet_name TEXT NOT NULL,
    remarks_cell TEXT NOT NULL,
    old_remark TEXT,
    new_remark TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE,
    FOREIGN KEY(kpi_record_id) REFERENCES kpi_records(id) ON DELETE CASCADE
);
"""


def dict_factory(cursor: sqlite3.Cursor, row: tuple[object, ...]) -> dict[str, object]:
    return {column[0]: row[index] for index, column in enumerate(cursor.description)}


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    ensure_project_dirs()
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = dict_factory
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db() -> None:
    with get_db() as db:
        db.executescript(SCHEMA)


def path_for_db(path: Path) -> str:
    return str(path.resolve())

