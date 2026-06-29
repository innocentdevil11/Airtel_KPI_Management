from __future__ import annotations

from sqlite3 import Connection


def dashboard_summary(db: Connection) -> dict[str, int]:
    row = db.execute(
        """
        SELECT
            COUNT(*) AS total_kpis,
            SUM(CASE WHEN metric_type = 'utilization' THEN 1 ELSE 0 END) AS total_utilizations,
            SUM(CASE WHEN status = 'Critical' THEN 1 ELSE 0 END) AS critical_kpis,
            SUM(CASE WHEN status = 'Warning' THEN 1 ELSE 0 END) AS warning_kpis,
            SUM(CASE WHEN status = 'Healthy' THEN 1 ELSE 0 END) AS healthy_kpis,
            SUM(CASE WHEN current_remark IS NULL OR TRIM(current_remark) = '' THEN 1 ELSE 0 END) AS pending_remarks
        FROM kpi_records
        """
    ).fetchone()
    reports = db.execute("SELECT COUNT(*) AS total_reports FROM reports").fetchone()
    return {
        "total_kpis": int(row["total_kpis"] or 0),
        "total_utilizations": int(row["total_utilizations"] or 0),
        "critical_kpis": int(row["critical_kpis"] or 0),
        "warning_kpis": int(row["warning_kpis"] or 0),
        "healthy_kpis": int(row["healthy_kpis"] or 0),
        "pending_remarks": int(row["pending_remarks"] or 0),
        "total_reports": int(reports["total_reports"] or 0),
    }


def distribution(db: Connection, field: str) -> list[dict[str, object]]:
    if field not in {"status", "category", "metric_type"}:
        raise ValueError("Unsupported distribution field")
    return db.execute(
        f"""
        SELECT COALESCE({field}, 'Uncategorized') AS label, COUNT(*) AS total
        FROM kpi_records
        GROUP BY COALESCE({field}, 'Uncategorized')
        ORDER BY total DESC
        """
    ).fetchall()
