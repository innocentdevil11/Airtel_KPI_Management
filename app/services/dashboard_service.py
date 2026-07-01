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
        SELECT COALESCE(NULLIF(TRIM({field}), ''), 'Uncategorized') AS label, COUNT(*) AS total
        FROM kpi_records
        GROUP BY COALESCE(NULLIF(TRIM({field}), ''), 'Uncategorized')
        ORDER BY total DESC
        LIMIT 12
        """
    ).fetchall()


def weekly_status_trend(db: Connection) -> list[dict[str, object]]:
    return db.execute(
        """
        SELECT
            week_label AS label,
            SUM(CASE WHEN status = 'Critical' THEN 1 ELSE 0 END) AS critical,
            SUM(CASE WHEN status = 'Warning' THEN 1 ELSE 0 END) AS warning,
            SUM(CASE WHEN status = 'Healthy' THEN 1 ELSE 0 END) AS healthy,
            SUM(CASE WHEN status = 'Pending' THEN 1 ELSE 0 END) AS pending
        FROM kpi_records
        GROUP BY week_label
        ORDER BY week_label
        LIMIT 24
        """
    ).fetchall()


def top_risks(db: Connection) -> list[dict[str, object]]:
    return db.execute(
        """
        SELECT
            k.kpi_name,
            COALESCE(k.category, '') AS category,
            k.week_label,
            k.value_number,
            k.threshold,
            k.status,
            k.metric_type,
            r.original_filename,
            CASE
                WHEN k.value_number IS NULL THEN NULL
                WHEN k.metric_type = 'utilization' THEN k.value_number - k.threshold
                ELSE k.threshold - k.value_number
            END AS threshold_gap
        FROM kpi_records k
        JOIN reports r ON r.id = k.report_id
        WHERE k.status IN ('Critical', 'Warning')
        ORDER BY
            CASE k.status WHEN 'Critical' THEN 1 WHEN 'Warning' THEN 2 ELSE 3 END,
            ABS(COALESCE(threshold_gap, 0)) DESC,
            k.id DESC
        LIMIT 10
        """
    ).fetchall()
