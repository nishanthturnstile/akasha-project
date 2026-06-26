"""ASF (Alaska Satellite Facility) DAAC provider adapter — placeholder.

ASF provides access to Sentinel-1 SAR, ALOS PALSAR, ERS, JERS, and other
SAR collections via the ASF SearchAPI (formerly Vertex).  This adapter is a
placeholder stub; all methods raise ``ProviderActionUnsupported`` until the
ASF ingestion phase begins.

ASF data is free and publicly available — no commercial preflight required.
"""

from __future__ import annotations

from ._placeholder import PlaceholderAdapterBase

__all__ = ["ASFAdapter"]


class ASFAdapter(PlaceholderAdapterBase):
    """Placeholder adapter for the Alaska Satellite Facility (ASF) DAAC.

    Replace this stub with a concrete implementation wrapping the ASF Search
    API (``https://api.daac.asf.alaska.edu``) when the ASF ingestion phase
    begins.

    Relevant ASF capabilities (for future implementation):
    - Granule/product search: ``/services/search/param`` (GeoJSON, CSV, JSONLITE)
    - Health endpoint: ``/health``
    - Baseline search (InSAR pairs): ``/baseline``
    - Download via HTTPS with Earthdata Login (EDL) credentials
    - No commercial tasking; Sentinel-1 and ALOS data are free on demand
    """

    adapter_name: str = "asf"
