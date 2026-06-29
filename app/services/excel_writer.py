from __future__ import annotations

from datetime import datetime
from pathlib import Path
from shutil import copy2

from openpyxl import load_workbook

from app.config import EDITED_DIR


def edited_copy_path(source_path: Path, report_id: int) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return EDITED_DIR / f"report_{report_id}_{timestamp}_{source_path.name}"


def write_remark_to_copy(
    source_path: Path,
    report_id: int,
    sheet_name: str,
    remarks_cell: str,
    new_remark: str,
) -> Path:
    """Copy the workbook first, then edit only the requested Remarks cell."""
    EDITED_DIR.mkdir(parents=True, exist_ok=True)
    destination = edited_copy_path(source_path, report_id)
    copy2(source_path, destination)

    workbook = load_workbook(destination, data_only=False)
    try:
        sheet = workbook[sheet_name]
        sheet[remarks_cell] = new_remark
        workbook.save(destination)
    finally:
        workbook.close()

    return destination
