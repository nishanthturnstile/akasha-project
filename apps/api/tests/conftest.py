from __future__ import annotations

import pytest
from app.config import settings


def pytest_configure(config: pytest.Config) -> None:
    """Silence a verified false-positive Pydantic/FastAPI warning during tests.

    FastAPI (>=0.139) builds a per-field ``TypeAdapter(Annotated[type, FieldInfo])``
    for request-body models, and Pydantic (>=2.13) then emits
    ``UnsupportedFieldAttributeWarning`` for every ``alias_generator``-derived
    alias even though ``populate_by_name`` + ``alias_generator`` work correctly.
    The runtime filter lives in ``app.api_models``; pytest manages its own
    warning filters, so it is repeated here for clean test output.
    """

    config.addinivalue_line(
        "filterwarnings",
        "ignore::pydantic.warnings.UnsupportedFieldAttributeWarning",
    )


@pytest.fixture(autouse=True)
def _allow_local_disabled_auth(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "disabled")
    monkeypatch.setattr(settings, "auth_allow_disabled", True)
    monkeypatch.setattr(settings, "app_env", "test")
    for key in (
        "AKASHA_DEPLOYMENT",
        "COOLIFY_URL",
        "COOLIFY_FQDN",
        "COOLIFY_RESOURCE_UUID",
        "COOLIFY_CONTAINER_NAME",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def _reset_index_rate_limit_buckets():
    """Isolate the process-global index-statistics rate limiter between tests.

    ``_RATE_BUCKETS`` in ``product_router`` is a module-level dict keyed by
    client id and is time-windowed (60s). The full suite runs in a few seconds,
    so without this reset every index-statistics POST across every test file
    accumulates into the same bucket and later tests can spuriously receive
    ``429`` instead of their expected status.
    """

    from app.routers import product_router

    product_router._RATE_BUCKETS.clear()
    yield
    product_router._RATE_BUCKETS.clear()
