from __future__ import annotations

from typing import Any


def detect_metric_type(kpi_name: str, category: str | None) -> str:
    text = f"{kpi_name} {category or ''}".lower()
    if "util" in text or "usage" in text or "capacity" in text:
        return "utilization"
    return "kpi"


def threshold_for(kpi_name: str, metric_type: str, config: dict[str, Any]) -> float:
    special = config.get("special_kpi_thresholds", {})
    if kpi_name in special:
        return float(special[kpi_name])
    if metric_type == "utilization":
        return float(config["general_utilization_threshold"])
    return float(config["general_kpi_threshold"])


def status_for(value: float | None, threshold: float, metric_type: str) -> str:
    if value is None:
        return "Pending"

    if metric_type == "utilization":
        if value >= threshold:
            return "Critical"
        if value >= threshold - 5:
            return "Warning"
        return "Healthy"

    if value < threshold:
        return "Critical"
    if value < threshold + 1:
        return "Warning"
    return "Healthy"
