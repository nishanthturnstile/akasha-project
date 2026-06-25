"""CDSE (Copernicus Data Space Ecosystem) provider adapter — placeholder.

Copernicus Data Space Ecosystem is the ESA platform for Sentinel-1/2/3/5P
and other Copernicus missions.  This adapter is a placeholder stub; all
methods raise ``ProviderActionUnsupported`` until the CDSE ingestion phase
begins.

CDSE is a free, open data service — no commercial preflight is required.
"""

from __future__ import annotations

from ._placeholder import PlaceholderAdapterBase

__all__ = ["CDSEAdapter"]


class CDSEAdapter(PlaceholderAdapterBase):
    """Placeholder adapter for the Copernicus Data Space Ecosystem (CDSE).

    Replace this stub with a concrete implementation that wraps the CDSE
    OData/STAC API (``https://dataspace.copernicus.eu``) when the CDSE
    ingestion phase begins.

    Relevant CDSE capabilities (for future implementation):
    - OData v4 search: ``/odata/v1/Products``
    - STAC API: ``/stac``
    - Free direct HTTP download with OIDC Bearer token
    - No tasking/order API; data is available on-demand
    """

    adapter_name: str = "cdse"
