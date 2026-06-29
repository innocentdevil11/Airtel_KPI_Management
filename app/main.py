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
from app.services.dashboard_service import dashboard_summary, distribution
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
            },
        )


@app.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("upload.html", {"request": request})


@app.post("/upload")
def upload_workbook(file: UploadFile = File(...)) -> RedirectResponse:
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
    report_id: int | None = None,
    status: str | None = None,
    category: str | None = None,
    week: str | None = None,
) -> HTMLResponse:
    query = """
        SELECT k.*, r.original_filename
        FROM kpi_records k
        JOIN reports r ON r.id = k.report_id
        WHERE (? IS NULL OR k.report_id = ?)
          AND (? IS NULL OR k.status = ?)
          AND (? IS NULL OR COALESCE(k.category, '') = ?)
          AND (? IS NULL OR k.week_label = ?)
        ORDER BY k.id DESC
        LIMIT 3000
    """
    with get_db() as db:
        records = db.execute(query, (report_id, report_id, status, status, category, category, week, week)).fetchall()
        reports = db.execute("SELECT id, original_filename FROM reports ORDER BY uploaded_at DESC").fetchall()
        categories = db.execute("SELECT DISTINCT category FROM kpi_records WHERE category IS NOT NULL ORDER BY category").fetchall()
        weeks = db.execute("SELECT DISTINCT week_label FROM kpi_records ORDER BY week_label DESC").fetchall()
        return templates.TemplateResponse(
            "kpi_explorer.html",
            {
                "request": request,
                "records": records,
                "reports": reports,
                "categories": categories,
                "weeks": weeks,
                "filters": {"report_id": report_id, "status": status, "category": category, "week": week},
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
            SELECT week_label, value_number, value_text, status
            FROM kpi_records
            WHERE report_id = ? AND kpi_name = ?
            ORDER BY id
            """,
            (record["report_id"], record["kpi_name"]),
        ).fetchall()
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
        {"request": request, "record": record, "history": history, "remarks": remarks},
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
        report = db.execute(
            "SELECT stored_path, active_path FROM reports WHERE id = ?",
            (report_id,),
        ).fetchone()
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")

        edited_paths = db.execute(
            "SELECT DISTINCT workbook_path FROM remarks_history WHERE report_id = ?",
            (report_id,),
        ).fetchall()
        file_paths = {str(report["stored_path"]), str(report["active_path"])}
        file_paths.update(str(row["workbook_path"]) for row in edited_paths)

        db.execute("DELETE FROM reports WHERE id = ?", (report_id,))

    for file_path in file_paths:
        delete_file_if_safe(file_path)

    return redirect("/reports")


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = "") -> HTMLResponse:
    pattern = f"%{q.strip()}%"
    rows = []
    if q.strip():
        with get_db() as db:
            rows = db.execute(
                """
                SELECT k.*, r.original_filename
                FROM kpi_records k
                JOIN reports r ON r.id = k.report_id
                WHERE k.kpi_name LIKE ?
                   OR COALESCE(k.category, '') LIKE ?
                   OR COALESCE(k.current_remark, '') LIKE ?
                   OR k.week_label LIKE ?
                   OR r.original_filename LIKE ?
                ORDER BY k.id DESC
                LIMIT 500
                """,
                (pattern, pattern, pattern, pattern, pattern),
            ).fetchall()
    return templates.TemplateResponse("search.html", {"request": request, "q": q, "records": rows})


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
