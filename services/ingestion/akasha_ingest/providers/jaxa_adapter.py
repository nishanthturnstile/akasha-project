"""JAXA G-Portal provider adapter — placeholder.

JAXA G-Portal provides access to GCOM-C (SGLI), GCOM-W (AMSR2), ALOS-2
(PALSAR-2), and other JAXA Earth observation missions.  This adapter is a
placeholder stub that enforces fail-closed commercial preflight semantics for
any paid tasking paths (e.g., ALOS-2 scene tasking/ordering), while free
archive data paths (GCOM-C/W) use the open-data base.

Most JAXA G-Portal archive data is free; ALOS-2 tasking is commercial.
This placeholder uses ``CommercialPlaceholderAdapterBase`` as the safer
default to prevent accidental commercial order calls.
"""

from __future__ import annotations

from ._placeholder import CommercialPlaceholderAdapterBase

__all__ = ["JAXAAdapter"]


class JAXAAdapter(CommercialPlaceholderAdapterBase):
    """Placeholder adapter for JAXA G-Portal.

    Replace this stub with a concrete implementation wrapping the JAXA
    G-Portal API (``https://gportal.jaxa.jp``) when the JAXA ingestion phase
    begins.  A separate free-data subclass may be warranted for GCOM-C/W
    paths that do not require commercial preflight.

    Relevant JAXA G-Portal capabilities (for future implementation):
    - Dataset/file search via G-Portal Web API (OpenSearch / WMTS)
    - Bulk download with FTP or HTTPS credentials
    - ALOS-2 scene tasking API (commercial; requires contract)
    - GCOM-C (SGLI L1B/L2) and GCOM-W (AMSR2) free archive access

    Commercial guard (SEC-007):
    - ``order()`` always raises ``CommercialPreflightFailed`` unless
      ``commercial_state`` is not blocked AND ``allow_paid_order=True`` AND
      a ``commercial_readiness_record_id`` is provided.
    - Default placeholder state is ``commercial_blocked`` to prevent
      accidental ALOS-2 tasking charges.
    """

    adapter_name: str = "jaxa"
