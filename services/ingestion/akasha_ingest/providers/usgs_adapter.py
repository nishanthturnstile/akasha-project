"""USGS EarthExplorer provider adapter — placeholder.

USGS EarthExplorer provides access to Landsat, ASTER, MODIS, and other
satellite collections via the Machine-to-Machine (M2M) API.  This adapter
is a placeholder stub; all methods raise ``ProviderActionUnsupported`` until
the USGS ingestion phase begins.

USGS data is free and publicly available — no commercial preflight required.
"""

from __future__ import annotations

from ._placeholder import PlaceholderAdapterBase

__all__ = ["USGSAdapter"]


class USGSAdapter(PlaceholderAdapterBase):
    """Placeholder adapter for USGS EarthExplorer (M2M API).

    Replace this stub with a concrete implementation wrapping the USGS M2M
    API (``https://m2m.cr.usgs.gov/api/api/json/stable``) when the USGS
    ingestion phase begins.

    Relevant USGS M2M capabilities (for future implementation):
    - Login/token: ``/login`` (username + password or application token)
    - Dataset search: ``/dataset-search``, ``/scene-search``
    - Download options: ``/download-options``
    - Download request/retrieve: ``/download-request``, ``/download-retrieve``
    - No tasking/order API for most collections; bulk download via staging queue
    """

    adapter_name: str = "usgs"
