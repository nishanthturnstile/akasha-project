"""Provider status routes."""
from __future__ import annotations

from fastapi import APIRouter

from ..config import settings
from .models import ProviderFeature, ProviderStatus

router = APIRouter(prefix="/api/providers", tags=["providers"])

_EOS_FEATURES = [
    "fields",
    "scenes",
    "tiles",
    "analytics",
    "imagery_exports",
    "weather",
    "zoning",
]


def _eos_status_payload() -> ProviderStatus:
    configured = bool(settings.eos_api_key.strip())
    mode = (settings.provider_mode or "disabled").strip().lower()
    enabled = configured and settings.eos_enabled and mode not in {"disabled", "mock"}
    status = "ready" if enabled else "disabled" if configured else "unconfigured"
    return ProviderStatus(
        provider="eos",
        mode=mode,
        configured=configured,
        enabled=enabled,
        status=status,
        features=[
            ProviderFeature(id=feature, available=enabled)
            for feature in _EOS_FEATURES
        ],
        cache_ttl_seconds=settings.eos_cache_ttl_seconds,
        rate_limit_per_minute=settings.eos_rate_limit_per_minute,
    )


@router.get("/eos/status", response_model=ProviderStatus, response_model_by_alias=True)
async def get_eos_status() -> ProviderStatus:
    """Return provider readiness without contacting EOS or exposing secrets."""
    return _eos_status_payload()
