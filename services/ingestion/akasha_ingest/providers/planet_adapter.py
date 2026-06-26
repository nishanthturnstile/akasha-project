"""Planet Labs provider adapter — placeholder (commercial).

Planet Labs provides access to PlanetScope, SkySat, and RapidEye imagery
via the Planet Orders API.  This adapter is a placeholder stub that enforces
fail-closed commercial preflight semantics; no paid order or tasking call can
be made until the commercial state is approved and an operator sets
``allow_paid_order=True`` with a documented readiness record.

All data access via Planet requires a paid subscription (SEC-007).
"""

from __future__ import annotations

from ._placeholder import CommercialPlaceholderAdapterBase

__all__ = ["PlanetAdapter"]


class PlanetAdapter(CommercialPlaceholderAdapterBase):
    """Placeholder adapter for Planet Labs (commercial imagery provider).

    Replace this stub with a concrete implementation wrapping the Planet
    Orders v2 API (``https://api.planet.com/compute/ops/orders/v2``) and
    Data API (``https://api.planet.com/data/v1``) when the Planet
    ingestion phase begins.

    Relevant Planet capabilities (for future implementation):
    - Scene search: ``/data/v1/quick-search`` (item type + date/cloud/AOI filters)
    - Asset activation: ``/data/v1/item-types/{}/items/{}/assets``
    - Orders v2 workflow: create order → poll → download archive bundle
    - All endpoints require X-Api-Key header (paid API key)

    Commercial guard (SEC-007):
    - ``order()`` always raises ``CommercialPreflightFailed`` unless
      ``commercial_state`` is not blocked AND ``allow_paid_order=True`` AND
      a ``commercial_readiness_record_id`` is provided.
    - Default placeholder state is ``commercial_blocked``; no production
      use until the commercial readiness phase is completed.
    """

    adapter_name: str = "planet"
