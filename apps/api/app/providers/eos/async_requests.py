"""Helpers for bounded polling of EOS asynchronous request results."""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from ...config import settings
from ...raster.errors import AkashaError

PENDING_STATUSES = {"created", "pending", "processing", "running", "queued"}


def default_poll_interval_seconds() -> float:
    return max(1.0, 60.0 / max(1, settings.eos_rate_limit_per_minute))


def is_pending_status(value: Any) -> bool:
    return str(value or "").strip().lower() in PENDING_STATUSES


def poll_result(
    fetch_result: Callable[[], dict[str, Any]],
    *,
    operation: str,
    timeout_seconds: float | None = None,
    poll_interval_seconds: float | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Fetch an EOS async result until it is no longer pending or the budget expires."""
    deadline = time.monotonic() + max(
        0.0,
        float(settings.eos_timeout_seconds if timeout_seconds is None else timeout_seconds),
    )

    while True:
        response = fetch_result()
        status = response.get("status") or response.get("state")
        if not is_pending_status(status):
            return response

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AkashaError(
                "PROVIDER_REQUEST_PENDING",
                f"EOS provider {operation} is still processing. Retry shortly.",
                503,
                {"provider": "eos"},
            )
        interval = (
            default_poll_interval_seconds()
            if poll_interval_seconds is None
            else max(0.0, poll_interval_seconds)
        )
        sleeper(min(interval, remaining))
