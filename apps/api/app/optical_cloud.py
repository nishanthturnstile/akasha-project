"""Shared per-user optical cloud-threshold helpers."""

from __future__ import annotations

from typing import Any

DEFAULT_OPTICAL_CLOUD_THRESHOLD_PERCENT = 20
MAX_OPTICAL_CLOUD_THRESHOLD_PERCENT = 70
_USER_THRESHOLD_OVERRIDES: dict[str, int] = {}


def optical_cloud_threshold(user: Any | None = None) -> int:
    """Return a bounded user threshold, falling back for old sessions/contracts."""
    user_id = str(getattr(user, "id", ""))
    if user_id in _USER_THRESHOLD_OVERRIDES:
        return _USER_THRESHOLD_OVERRIDES[user_id]
    value = getattr(user, "optical_cloud_threshold_percent", None)
    try:
        value = int(value)
    except (TypeError, ValueError):
        return DEFAULT_OPTICAL_CLOUD_THRESHOLD_PERCENT
    return max(0, min(MAX_OPTICAL_CLOUD_THRESHOLD_PERCENT, value))


def set_optical_cloud_threshold(user_id: Any, value: Any) -> int:
    threshold = threshold_from_mapping(value)
    _USER_THRESHOLD_OVERRIDES[str(user_id)] = threshold
    return threshold


def threshold_from_mapping(value: Any) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return DEFAULT_OPTICAL_CLOUD_THRESHOLD_PERCENT
    return max(0, min(MAX_OPTICAL_CLOUD_THRESHOLD_PERCENT, value))


def normalize_field_date(
    item: dict[str, Any],
    *,
    fallback: dict[str, Any] | None = None,
    threshold_percent: int = DEFAULT_OPTICAL_CLOUD_THRESHOLD_PERCENT,
) -> dict[str, Any]:
    """Normalize current and legacy ingestion field-date contracts."""
    fallback = fallback or {}
    status = item.get("availabilityStatus") or item.get("status")
    available = item.get("available")
    if available is None:
        available = item.get("selectable")
    if available is None and status is not None:
        available = str(status).upper() in {"AVAILABLE", "SELECTABLE", "USABLE"}
    available = bool(available)
    status = str(status or ("AVAILABLE" if available else "UNAVAILABLE")).upper()
    cloud = item.get("cloudMaskedPercent")
    if cloud is None:
        cloud = item.get("cloudPercentage")
    shadow = item.get("shadowPercent")
    if shadow is None:
        shadow = item.get("shadowPercentage")
    obscured = item.get("obscuredPercent")
    if obscured is None:
        obscured = item.get("obscuredPercentage")
    reason = item.get("unavailableReason")
    if reason is None:
        reason = item.get("reason")
    tile_available = item.get("tileAvailable")
    if tile_available is None:
        tile_available = fallback.get("tileAvailable")
    applied_threshold = item.get("appliedCloudThresholdPercent")
    if applied_threshold is None:
        applied_threshold = threshold_percent
    result = {
        "available": available,
        "selectable": available,
        "availabilityStatus": status,
        "tileAvailable": bool(tile_available) if tile_available is not None else available,
        "appliedCloudThresholdPercent": threshold_from_mapping(applied_threshold),
        "cloudMaskedPercent": cloud,
        "shadowPercent": shadow,
        "obscuredPercent": obscured,
        "unavailableReason": reason if not available else None,
    }
    if item.get("selectedSceneDate") is not None:
        result["selectedSceneDate"] = item["selectedSceneDate"]
    if item.get("usablePixelPercentage") is not None:
        result["usablePixelPercent"] = item["usablePixelPercentage"]
    if item.get("fieldCoveragePercentage") is not None:
        result["coveragePercent"] = item["fieldCoveragePercentage"]
    if item.get("validPixelCount") is not None:
        result["validPixelCount"] = item["validPixelCount"]
    return result


def apply_optical_threshold_to_dates(
    dates: list[dict[str, Any]], threshold_percent: int
) -> list[dict[str, Any]]:
    """Annotate catalog dates without conflating tile availability and selection."""
    threshold = threshold_from_mapping(threshold_percent)
    copied: list[dict[str, Any]] = []
    for entry in dates:
        item = dict(entry)
        item["appliedCloudThresholdPercent"] = threshold
        tile_available = bool(item.get("tileAvailable", True))
        cloud = item.get("cloudMaskedPercent")
        if cloud is None:
            cloud = item.get("cloudPercentage")
        selectable = tile_available
        if cloud is not None:
            try:
                selectable = selectable and float(cloud) <= threshold
            except (TypeError, ValueError):
                pass
        item["tileAvailable"] = tile_available
        item["selectable"] = selectable
        item["availabilityStatus"] = (
            "AVAILABLE" if selectable else ("QUALITY_LIMITED" if tile_available else "UNAVAILABLE")
        )
        if not selectable and not item.get("unavailableReason") and cloud is not None:
            item["unavailableReason"] = (
                f"Cloud-masked percentage exceeds the {threshold}% optical threshold."
            )
        copied.append(item)
    newest = max(
        (str(item.get("acquisitionDate")) for item in copied if item.get("selectable")),
        default=None,
    )
    for item in copied:
        item["isLatestUsable"] = bool(newest and item.get("acquisitionDate") == newest)
    return copied
