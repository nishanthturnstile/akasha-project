"""Generic commercial vendor provider adapter — placeholder (commercial).

This adapter is a placeholder stub for any commercial satellite data vendor
that does not have a dedicated first-class adapter (e.g., Maxar, Airbus
Defence & Space, BlackSky, Satellogic, etc.).  It enforces fail-closed
commercial preflight semantics; no paid order or tasking call can be made
until the commercial state is approved and an operator passes
``allow_paid_order=True`` with a documented readiness record.

All commercial vendor data access requires a paid contract (SEC-007).
"""

from __future__ import annotations

from ._placeholder import CommercialPlaceholderAdapterBase

__all__ = ["VendorAdapter"]


class VendorAdapter(CommercialPlaceholderAdapterBase):
    """Placeholder adapter for a generic commercial satellite data vendor.

    Replace this stub with a concrete implementation (or subclass with a
    specific vendor name) when a commercial vendor ingestion phase begins.

    This class intentionally provides no vendor-specific logic.  When
    implementing a specific vendor, subclass ``VendorAdapter`` and override
    ``adapter_name`` plus the required protocol methods.

    Commercial guard (SEC-007):
    - ``order()`` always raises ``CommercialPreflightFailed`` unless
      ``commercial_state`` is not blocked AND ``allow_paid_order=True`` AND
      a ``commercial_readiness_record_id`` is provided.
    - Default placeholder state is ``commercial_blocked``; no production
      use until the commercial readiness phase is completed.
    """

    adapter_name: str = "vendor"
