"""Provider adapter registry for the Akasha ingestion scheduler.

Implements TASK-008 from
docs/impl-plan/architecture-satellite-ingestion-scheduler-1.md.

Single entry point: ``get_provider_adapter(provider)`` returns an instantiated
``ProviderAdapter`` for the named provider, or raises ``UnknownProviderError``
for any unrecognised provider key (fail-closed contract).

Design notes
------------
- All imports are **lazy** (deferred to inside the function call); importing
  this module never triggers heavy deps or provider-specific code.
- The Bhoonidhi adapter is imported lazily.  If ``bhoonidhi_adapter.py`` does
  not yet exist (the module is owned by a separate todo), the registry raises
  ``UnknownProviderError("bhoonidhi")`` rather than a bare ``ImportError``,
  preserving the consistent fail-closed contract.
- Unknown provider keys always raise ``UnknownProviderError``.  There is no
  silent fallback or None return.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from .base import ProviderAdapter, ProviderError

if TYPE_CHECKING:
    pass  # keep this section for future type-only imports

__all__ = [
    "UnknownProviderError",
    "get_provider_adapter",
]

# ---------------------------------------------------------------------------
# Registry exception
# ---------------------------------------------------------------------------


class UnknownProviderError(ProviderError):
    """Raised when no adapter is registered for the requested provider key.

    This is a fail-closed exception: callers must not proceed with ingestion
    if the provider is not recognised.  Add the provider to the registry
    (or register a placeholder adapter) before scheduling ingestion jobs.

    Example::

        raise UnknownProviderError("sentinel-2")
        # → ProviderError: Unknown provider 'sentinel-2'. ...
    """

    def __init__(self, provider: str) -> None:
        super().__init__(
            f"Unknown provider '{provider}'. "
            "No adapter is registered for this provider key. "
            "Add the provider to the registry in "
            "'akasha_ingest.providers.registry' or register a placeholder "
            "adapter before scheduling ingestion jobs."
        )
        self.provider = provider


# ---------------------------------------------------------------------------
# Known provider map: provider_key → (relative_module, class_name)
# ---------------------------------------------------------------------------

# Bhoonidhi is intentionally absent here; it is handled with a separate lazy
# import below so that missing bhoonidhi_adapter.py raises UnknownProviderError
# rather than an ImportError.
_PROVIDER_MAP: dict[str, tuple[str, str]] = {
    "cdse": (".cdse_adapter", "CDSEAdapter"),
    "usgs": (".usgs_adapter", "USGSAdapter"),
    "earthdata": (".earthdata_adapter", "EarthdataAdapter"),
    "asf": (".asf_adapter", "ASFAdapter"),
    "planet": (".planet_adapter", "PlanetAdapter"),
    "jaxa": (".jaxa_adapter", "JAXAAdapter"),
    "vendor": (".vendor_adapter", "VendorAdapter"),
    "usda": (".usda_adapter", "USDAAdapter"),
}


# ---------------------------------------------------------------------------
# Registry API
# ---------------------------------------------------------------------------


def get_provider_adapter(provider: str) -> ProviderAdapter:
    """Return an instantiated adapter for *provider*.

    Parameters
    ----------
    provider:
        Provider key string as used in ``SourceStateRow.provider`` and the
        source-state registry (e.g. ``"bhoonidhi"``, ``"cdse"``, ``"planet"``).

    Returns
    -------
    ProviderAdapter:
        A concrete (or placeholder) adapter implementing the provider contract.
        Placeholder adapters raise ``ProviderActionUnsupported`` on every call
        until a real implementation is in place.

    Raises
    ------
    UnknownProviderError:
        If *provider* is not registered.  The caller must not proceed with
        ingestion for an unrecognised provider.
    """
    # Bhoonidhi is owned by a separate todo (TASK-009).  Import lazily so that
    # this registry works even before bhoonidhi_adapter.py is created.
    if provider == "bhoonidhi":
        try:
            mod = importlib.import_module(
                ".bhoonidhi_adapter", package=__package__
            )
            cls = mod.BhoonidhiAdapter  # type: ignore[attr-defined]
            return cls()  # type: ignore[return-value]
        except (ImportError, AttributeError):
            raise UnknownProviderError(provider) from None

    if provider not in _PROVIDER_MAP:
        raise UnknownProviderError(provider)

    relative_module, class_name = _PROVIDER_MAP[provider]
    mod = importlib.import_module(relative_module, package=__package__)
    # class_name is a dynamic string from _PROVIDER_MAP; getattr is necessary here.
    cls = getattr(mod, class_name)  # noqa: B009
    return cls()  # type: ignore[return-value]
