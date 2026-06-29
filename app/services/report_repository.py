from __future__ import annotations

from datetime import datetime
from pathlib import Path
from sqlite3 import Connection

from app.database import path_for_db
from app.services.excel_parser import ParsedKpiRecord


def create_report(db: Connection, original_filename: str, stored_path: Path, records: list[ParsedKpiRecord]) -> int:
    cursor = db.execute(
        """
        INSERT INTO reports (original_filename, stored_filename, stored_path, active_path, uploaded_at, total_rows)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            original_filename,
            stored_path.name,
            path_for_db(stored_path),
            path_for_db(stored_path),
            datetime.now().isoformat(timespec="seconds"),
            len(records),
        ),
    )
    report_id = int(cursor.lastrowid)
    insert_records(db, report_id, records)
    return report_id


def insert_records(db: Connection, report_id: int, records: list[ParsedKpiRecord]) -> None:
    db.executemany(
        """
        INSERT INTO kpi_records (
            report_id, sheet_name, row_number, kpi_name, category, week_label,
            value_text, value_number, value_cell, remarks_cell, current_remark,
            threshold, status, metric_type
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                report_id,
                record.sheet_name,
                record.row_number,
                record.kpi_name,
                record.category,
                record.week_label,
                record.value_text,
                record.value_number,
                record.value_cell,
                record.remarks_cell,
                record.current_remark,
                record.threshold,
                record.status,
                record.metric_type,
            )
            for record in records
        ],
    )


def update_report_active_path(db: Connection, report_id: int, active_path: Path) -> None:
    db.execute("UPDATE reports SET active_path = ? WHERE id = ?", (path_for_db(active_path), report_id))
