from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR, UPLOAD_DIR, ensure_project_dirs
from app.database import get_db, init_db
from app.services.dashboard_service import dashboard_summary, distribution, top_risks, weekly_status_trend
from app.services.excel_parser import parse_workbook
from app.services.excel_writer import write_remark_to_copy
from app.services.report_repository import create_report, update_report_active_path


app = FastAPI(title="Offline KPI Dashboard")
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")


@app.on_event("startup")
def startup() -> None:
    ensure_project_dirs()
    init_db()


def redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def clean_text_filter(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def clean_int_filter(value: str | int | None, field_name: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name} filter.") from exc


def safe_excel_name(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".xlsx", ".xlsm"}:
        raise HTTPException(status_code=400, detail="Only .xlsx and .xlsm files are supported.")
    stem = Path(filename).stem.replace(" ", "_")
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}_{stem}{suffix}"


def safe_upload_file(path_text: str | None) -> Path | None:
    """Return a path only when it is inside this project's uploads folder."""
    if not path_text:
        return None
    path = Path(path_text).resolve()
    upload_root = UPLOAD_DIR.resolve()
    if path == upload_root or upload_root not in path.parents:
        return None
    return path


def delete_file_if_safe(path_text: str | None) -> None:
    path = safe_upload_file(path_text)
    if path and path.exists() and path.is_file():
        path.unlink()


def collect_report_file_paths(db, report_id: int | None = None) -> set[str]:
    report_query = "SELECT stored_path, active_path FROM reports"
    history_query = "SELECT DISTINCT workbook_path FROM remarks_history"
    params: tuple[object, ...] = ()
    if report_id is not None:
        report_query += " WHERE id = ?"
        history_query += " WHERE report_id = ?"
        params = (report_id,)

    reports = db.execute(report_query, params).fetchall()
    edited_paths = db.execute(history_query, params).fetchall()
    file_paths: set[str] = set()
    for report in reports:
        file_paths.add(str(report["stored_path"]))
        file_paths.add(str(report["active_path"]))
    file_paths.update(str(row["workbook_path"]) for row in edited_paths)
    return file_paths


def delete_report_rows(db, report_id: int | None = None) -> set[str]:
    file_paths = collect_report_file_paths(db, report_id)
    if report_id is None:
        db.execute("DELETE FROM reports")
    else:
        db.execute("DELETE FROM reports WHERE id = ?", (report_id,))
    return file_paths


def delete_paths_after_commit(file_paths: set[str]) -> None:
    for file_path in file_paths:
        delete_file_if_safe(file_path)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    with get_db() as db:
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "summary": dashboard_summary(db),
                "status_distribution": distribution(db, "status"),
                "category_distribution": distribution(db, "category"),
                "metric_distribution": distribution(db, "metric_type"),
                "weekly_status": weekly_status_trend(db),
                "top_risks": top_risks(db),
            },
        )


@app.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request) -> HTMLResponse:
    with get_db() as db:
        reports = db.execute("SELECT id, original_filename, uploaded_at, total_rows FROM reports ORDER BY uploaded_at DESC").fetchall()
    return templates.TemplateResponse("upload.html", {"request": request, "reports": reports})


@app.post("/upload")
def upload_workbook(file: UploadFile = File(...), clear_existing: str | None = Form(None)) -> RedirectResponse:
    if clear_existing:
        with get_db() as db:
            old_paths = delete_report_rows(db)
        delete_paths_after_commit(old_paths)

    stored_name = safe_excel_name(file.filename or "workbook.xlsx")
    stored_path = UPLOAD_DIR / stored_name

    with stored_path.open("wb") as output:
        shutil.copyfileobj(file.file, output)

    records = parse_workbook(stored_path)
    with get_db() as db:
        create_report(db, file.filename or stored_name, stored_path, records)

    return redirect("/reports")


@app.get("/kpis", response_class=HTMLResponse)
def kpi_explorer(
    request: Request,
    report_id: str | None = None,
    status: str | None = None,
    category: str | None = None,
    week: str | None = None,
) -> HTMLResponse:
    report_filter = clean_int_filter(report_id, "report")
    status_filter = clean_text_filter(status)
    category_filter = clean_text_filter(category)
    week_filter = clean_text_filter(week)

    query = """
        WITH enriched AS (
            SELECT
                k.*,
                r.original_filename,
                LAG(k.value_number) OVER (
                    PARTITION BY k.report_id, k.kpi_name, COALESCE(k.category, '')
                    ORDER BY k.id
                ) AS previous_value
            FROM kpi_records k
            JOIN reports r ON r.id = k.report_id
        )
        SELECT *,
               CASE
                   WHEN value_number IS NOT NULL AND previous_value IS NOT NULL
                   THEN value_number - previous_value
               END AS value_delta
        FROM enriched
        WHERE (? IS NULL OR report_id = ?)
          AND (? IS NULL OR status = ?)
          AND (? IS NULL OR COALESCE(category, '') = ?)
          AND (? IS NULL OR week_label = ?)
        ORDER BY id DESC
        LIMIT 3000
    """
    with get_db() as db:
        records = db.execute(
            query,
            (report_filter, report_filter, status_filter, status_filter, category_filter, category_filter, week_filter, week_filter),
        ).fetchall()
        reports = db.execute("SELECT id, original_filename FROM reports ORDER BY uploaded_at DESC").fetchall()
        categories = db.execute(
            """
            SELECT DISTINCT category
            FROM kpi_records
            WHERE category IS NOT NULL
              AND TRIM(category) <> ''
              AND (? IS NULL OR report_id = ?)
            ORDER BY category
            """,
            (report_filter, report_filter),
        ).fetchall()
        weeks = db.execute(
            """
            SELECT DISTINCT week_label
            FROM kpi_records
            WHERE (? IS NULL OR report_id = ?)
            ORDER BY week_label DESC
            """,
            (report_filter, report_filter),
        ).fetchall()
        return templates.TemplateResponse(
            "kpi_explorer.html",
            {
                "request": request,
                "records": records,
                "reports": reports,
                "categories": categories,
                "weeks": weeks,
                "filters": {"report_id": report_filter, "status": status_filter, "category": category_filter, "week": week_filter},
            },
        )


@app.get("/kpis/{record_id}", response_class=HTMLResponse)
def kpi_detail(request: Request, record_id: int) -> HTMLResponse:
    with get_db() as db:
        record = db.execute(
            """
            SELECT k.*, r.original_filename, r.active_path
            FROM kpi_records k
            JOIN reports r ON r.id = k.report_id
            WHERE k.id = ?
            """,
            (record_id,),
        ).fetchone()
        if not record:
            raise HTTPException(status_code=404, detail="KPI record not found")

        history = db.execute(
            """
            SELECT id, week_label, value_number, value_text, threshold, status
            FROM kpi_records
            WHERE report_id = ?
              AND kpi_name = ?
              AND COALESCE(category, '') = COALESCE(?, '')
            ORDER BY id
            """,
            (record["report_id"], record["kpi_name"], record["category"]),
        ).fetchall()
        previous_value: float | None = None
        selected_delta: float | None = None
        selected_previous: float | None = None
        for item in history:
            item["value_delta"] = None
            if item["value_number"] is not None and previous_value is not None:
                item["value_delta"] = float(item["value_number"]) - previous_value
            if item["id"] == record_id:
                selected_delta = item["value_delta"]
                selected_previous = previous_value
            if item["value_number"] is not None:
                previous_value = float(item["value_number"])

        remarks = db.execute(
            """
            SELECT old_remark, new_remark, changed_at, workbook_path
            FROM remarks_history
            WHERE report_id = ? AND kpi_record_id = ?
            ORDER BY changed_at DESC
            """,
            (record["report_id"], record_id),
        ).fetchall()

    return templates.TemplateResponse(
        "kpi_detail.html",
        {
            "request": request,
            "record": record,
            "history": history,
            "remarks": remarks,
            "selected_delta": selected_delta,
            "selected_previous": selected_previous,
        },
    )


@app.post("/kpis/{record_id}/remarks")
def save_remark(record_id: int, new_remark: str = Form(...)) -> RedirectResponse:
    with get_db() as db:
        record = db.execute(
            """
            SELECT k.*, r.active_path
            FROM kpi_records k
            JOIN reports r ON r.id = k.report_id
            WHERE k.id = ?
            """,
            (record_id,),
        ).fetchone()
        if not record:
            raise HTTPException(status_code=404, detail="KPI record not found")
        if not record["remarks_cell"]:
            raise HTTPException(status_code=400, detail="No Remarks column was detected for this KPI row.")

        edited_path = write_remark_to_copy(
            Path(str(record["active_path"])),
            int(record["report_id"]),
            str(record["sheet_name"]),
            str(record["remarks_cell"]),
            new_remark,
        )

        db.execute(
            """
            INSERT INTO remarks_history (
                report_id, kpi_record_id, workbook_path, sheet_name, remarks_cell,
                old_remark, new_remark, changed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["report_id"],
                record_id,
                str(edited_path.resolve()),
                record["sheet_name"],
                record["remarks_cell"],
                record["current_remark"],
                new_remark,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        db.execute(
            """
            UPDATE kpi_records
            SET current_remark = ?
            WHERE report_id = ? AND sheet_name = ? AND row_number = ? AND remarks_cell = ?
            """,
            (new_remark, record["report_id"], record["sheet_name"], record["row_number"], record["remarks_cell"]),
        )
        update_report_active_path(db, int(record["report_id"]), edited_path)

    return redirect(f"/kpis/{record_id}")


@app.get("/reports", response_class=HTMLResponse)
def reports(request: Request) -> HTMLResponse:
    with get_db() as db:
        rows = db.execute(
            """
            SELECT r.*,
                   SUM(CASE WHEN k.status = 'Critical' THEN 1 ELSE 0 END) AS critical_count,
                   SUM(CASE WHEN k.current_remark IS NULL OR TRIM(k.current_remark) = '' THEN 1 ELSE 0 END) AS pending_remarks
            FROM reports r
            LEFT JOIN kpi_records k ON k.report_id = r.id
            GROUP BY r.id
            ORDER BY r.uploaded_at DESC
            """
        ).fetchall()
    return templates.TemplateResponse("reports.html", {"request": request, "reports": rows})


@app.get("/reports/{report_id}/download")
def download_report(report_id: int) -> FileResponse:
    with get_db() as db:
        report = db.execute(
            "SELECT original_filename, active_path FROM reports WHERE id = ?",
            (report_id,),
        ).fetchone()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    path = safe_upload_file(str(report["active_path"]))
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Workbook file not found")

    return FileResponse(
        path=path,
        filename=str(report["original_filename"]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.post("/reports/{report_id}/delete")
def delete_report(report_id: int) -> RedirectResponse:
    with get_db() as db:
        report = db.execute("SELECT id FROM reports WHERE id = ?", (report_id,)).fetchone()
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        file_paths = delete_report_rows(db, report_id)

    delete_paths_after_commit(file_paths)
    return redirect("/reports")


@app.post("/reports/delete-all")
def delete_all_reports() -> RedirectResponse:
    with get_db() as db:
        file_paths = delete_report_rows(db)
    delete_paths_after_commit(file_paths)
    return redirect("/upload")


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = "", status: str | None = None) -> HTMLResponse:
    status_filter = clean_text_filter(status)
    terms = [term for term in q.strip().split() if term]
    params: list[object] = []
    where_parts: list[str] = []

    if status_filter:
        where_parts.append("k.status = ?")
        params.append(status_filter)

    for term in terms:
        pattern = f"%{term}%"
        where_parts.append(
            """
            (
                k.kpi_name LIKE ?
                OR COALESCE(k.category, '') LIKE ?
                OR COALESCE(k.current_remark, '') LIKE ?
                OR k.week_label LIKE ?
                OR k.status LIKE ?
                OR r.original_filename LIKE ?
            )
            """
        )
        params.extend([pattern, pattern, pattern, pattern, pattern, pattern])

    where_sql = "WHERE " + " AND ".join(where_parts) if where_parts else ""
    with get_db() as db:
        rows = db.execute(
            f"""
            SELECT k.*, r.original_filename,
                   CASE k.status
                       WHEN 'Critical' THEN 1
                       WHEN 'Warning' THEN 2
                       WHEN 'Pending' THEN 3
                       ELSE 4
                   END AS status_rank
            FROM kpi_records k
            JOIN reports r ON r.id = k.report_id
            {where_sql}
            ORDER BY status_rank, k.id DESC
            LIMIT 700
            """,
            tuple(params),
        ).fetchall()
    return templates.TemplateResponse("search.html", {"request": request, "q": q, "status": status_filter, "records": rows})


@app.get("/compare", response_class=HTMLResponse)
def compare(request: Request, left: int | None = None, right: int | None = None) -> HTMLResponse:
    comparisons = []
    with get_db() as db:
        reports = db.execute("SELECT id, original_filename FROM reports ORDER BY uploaded_at DESC").fetchall()
        if left and right:
            comparisons = db.execute(
                """
                SELECT
                    l.kpi_name,
                    COALESCE(l.category, '') AS category,
                    l.week_label,
                    l.value_number AS left_value,
                    rr.value_number AS right_value,
                    (rr.value_number - l.value_number) AS difference,
                    l.threshold AS left_threshold,
                    rr.threshold AS right_threshold,
                    l.status AS left_status,
                    rr.status AS right_status,
                    l.current_remark AS left_remark,
                    rr.current_remark AS right_remark
                FROM kpi_records l
                JOIN kpi_records rr
                  ON rr.kpi_name = l.kpi_name
                 AND rr.week_label = l.week_label
                 AND COALESCE(rr.category, '') = COALESCE(l.category, '')
                WHERE l.report_id = ? AND rr.report_id = ?
                ORDER BY ABS(COALESCE(rr.value_number, 0) - COALESCE(l.value_number, 0)) DESC
                LIMIT 1000
                """,
                (left, right),
            ).fetchall()

    return templates.TemplateResponse(
        "compare.html",
        {"request": request, "reports": reports, "comparisons": comparisons, "left": left, "right": right},
    )


@app.get("/analysis", response_class=HTMLResponse)
def kpi_analysis(request: Request, key: str | None = None) -> HTMLResponse:
    selected_report_id: int | None = None
    selected_category = ""
    selected_kpi = ""
    if key:
        parts = key.split("||", 2)
        if len(parts) == 3:
            selected_report_id = clean_int_filter(parts[0], "report")
            selected_category = parts[1]
            selected_kpi = parts[2]

    with get_db() as db:
        options = db.execute(
            """
            SELECT DISTINCT
                k.report_id,
                r.original_filename,
                k.kpi_name,
                COALESCE(k.category, '') AS category
            FROM kpi_records k
            JOIN reports r ON r.id = k.report_id
            ORDER BY r.uploaded_at DESC, k.kpi_name
            """
        ).fetchall()

        if not selected_report_id and options:
            first = options[0]
            selected_report_id = int(first["report_id"])
            selected_category = str(first["category"] or "")
            selected_kpi = str(first["kpi_name"])

        rows: list[dict[str, object]] = []
        selected_option = None
        if selected_report_id and selected_kpi:
            selected_option = {
                "report_id": selected_report_id,
                "category": selected_category,
                "kpi_name": selected_kpi,
            }
            rows = db.execute(
                """
                SELECT
                    id,
                    week_label,
                    value_number,
                    value_text,
                    threshold,
                    status,
                    metric_type,
                    current_remark
                FROM kpi_records
                WHERE report_id = ?
                  AND kpi_name = ?
                  AND COALESCE(category, '') = ?
                ORDER BY id
                """,
                (selected_report_id, selected_kpi, selected_category),
            ).fetchall()

    previous_value: float | None = None
    numeric_values: list[float] = []
    remarks_count = 0
    critical_count = 0
    warning_count = 0
    for row in rows:
        row["value_delta"] = None
        row["value_delta_pct"] = None
        if row["current_remark"] and str(row["current_remark"]).strip():
            remarks_count += 1
        if row["status"] == "Critical":
            critical_count += 1
        if row["status"] == "Warning":
            warning_count += 1
        if row["value_number"] is not None:
            current = float(row["value_number"])
            numeric_values.append(current)
            if previous_value is not None:
                row["value_delta"] = current - previous_value
                if previous_value != 0:
                    row["value_delta_pct"] = ((current - previous_value) / abs(previous_value)) * 100
            previous_value = current

    first_value = numeric_values[0] if numeric_values else None
    latest_value = numeric_values[-1] if numeric_values else None
    total_change = latest_value - first_value if first_value is not None and latest_value is not None else None
    total_change_pct = ((total_change / abs(first_value)) * 100) if total_change is not None and first_value not in (None, 0) else None
    average_value = (sum(numeric_values) / len(numeric_values)) if numeric_values else None
    is_subscriber_metric = "subscriber" in selected_kpi.lower() or "subs" in selected_kpi.lower()

    if not rows:
        narrative = "Select a KPI to see week-wise movement, remarks, and threshold context."
    elif total_change is None:
        narrative = "This KPI has no numeric values yet, so movement analysis is limited to remarks and status history."
    else:
        direction = "increased" if total_change > 0 else "decreased" if total_change < 0 else "remained flat"
        unit_label = "subscribers" if is_subscriber_metric else "points"
        narrative = (
            f"Across {len(rows)} week entries, {selected_kpi} {direction} by {abs(total_change):.2f} {unit_label}. "
            f"The average value is {average_value:.2f}. There are {critical_count} critical and {warning_count} warning observations. "
            f"Remarks are available on {remarks_count} week entries."
        )

    return templates.TemplateResponse(
        "analysis.html",
        {
            "request": request,
            "options": options,
            "selected_option": selected_option,
            "selected_key": key,
            "rows": rows,
            "narrative": narrative,
            "first_value": first_value,
            "latest_value": latest_value,
            "total_change": total_change,
            "total_change_pct": total_change_pct,
            "average_value": average_value,
            "remarks_count": remarks_count,
            "critical_count": critical_count,
            "warning_count": warning_count,
            "is_subscriber_metric": is_subscriber_metric,
        },
    )
