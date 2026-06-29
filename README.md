# Offline KPI Dashboard

Local FastAPI web app for Excel-based weekly KPI reporting. The uploaded Excel workbook remains the source of truth. Remark edits are written to a copied workbook under `uploads/edited/`, never to the original uploaded file.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8010
```

Open http://127.0.0.1:8010.

If port `8000` gives `[WinError 10013]`, Windows is blocking that socket. Use `8010` as shown above.

## Workbook Safety Rule

The original upload is saved in `uploads/`.

When a remark is edited:

1. The app reads the latest active workbook path from SQLite.
2. It creates an exact file copy in `uploads/edited/`.
3. It opens the copied workbook with OpenPyXL.
4. It writes only the detected Remarks cell, such as `H12`.
5. It saves the copied workbook.
6. It updates SQLite so future edits continue from the latest edited copy.

This preserves KPI values, formulas, formatting, merged cells, colors, and sheet layout in the original workbook.

## Main Code Blocks

### `app/config.py`

`BASE_DIR`, `UPLOAD_DIR`, `EDITED_DIR`, and `DATABASE_PATH` define the local project paths. Keeping these in one file prevents path strings from being scattered across the codebase.

`DEFAULT_CONFIG` stores threshold defaults. These are also written to `config/config.json`, so threshold values are configurable instead of hardcoded inside parser logic.

`ensure_project_dirs()` creates the runtime folders. It is needed because a fresh clone may not have `uploads/`, `uploads/edited/`, or `database/`.

`load_config()` reads `config/config.json`. If the file does not exist, it creates one with defaults first.

### `app/database.py`

`SCHEMA` creates three core tables:

- `reports`: one row per uploaded workbook.
- `kpi_records`: parsed searchable KPI rows.
- `remarks_history`: an audit trail of every remark change.

`get_db()` opens a SQLite connection and commits automatically when the block finishes. This keeps route code shorter and makes database writes consistent.

`init_db()` runs the schema on startup. It is safe to call repeatedly because every table uses `CREATE TABLE IF NOT EXISTS`.

### `app/services/excel_parser.py`

`find_header_row()` scans the first 20 rows of each sheet to locate a row that looks like headers. It searches for common KPI header names such as `KPI`, `Metric`, or `Parameter`.

`first_matching_column()` finds important columns like KPI name, Category, and Remarks. This lets the app handle reports where column positions change.

`value_columns()` treats non-metadata columns as week/value columns. It excludes headers such as KPI, Category, Remarks, Status, and Threshold.

`parse_workbook()` opens the workbook read-only from the app's perspective, extracts KPI data, calculates status, and stores exact cell coordinates such as `B12` and `H12`. Those cell coordinates are what make later remark edits targeted.

### `app/services/excel_writer.py`

`write_remark_to_copy()` is the important safety block. It receives the current active workbook path, copies it into `uploads/edited/`, opens only the copy, updates only the requested Remarks cell, and saves that copy.

The original upload is not opened for writing.

### `app/main.py`

`startup()` creates folders and initializes SQLite when FastAPI starts.

`upload_workbook()` saves the uploaded Excel file, parses it, and stores parsed rows in SQLite. It does not edit the workbook.

`kpi_explorer()` loads searchable/filterable KPI rows for the explorer page.

`kpi_detail()` loads one KPI row, its trend values, and remark history.

`save_remark()` controls the full remark workflow: fetch KPI row, validate that a Remarks cell exists, create edited workbook copy, write the new remark into that copy, store audit history, update visible remark values in SQLite, and mark the edited copy as the report's new active workbook.

## Current Parser Assumptions

The parser is intentionally generic for the first version:

- Header row appears within the first 20 rows.
- KPI column header is similar to `KPI`, `KPI Name`, `Metric`, `Parameter`, or `Name`.
- Remarks column header is similar to `Remark`, `Remarks`, `Comment`, or `Comments`.
- Week/value columns are the remaining non-metadata columns.
- Utilization is detected when KPI name or category contains words like `util`, `usage`, or `capacity`.

If your real Excel template has fixed headers, the parser can be tightened to match it exactly.

## Offline Frontend

The app does not use CDN links. Static files live under `app/static/`.

For this first implementation, the table search/sort and charts are lightweight local JavaScript. If corporate policy allows bundling official Bootstrap/DataTables/Chart.js files, place them in `app/static/vendor/` and the templates can use them without internet access.

