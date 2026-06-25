"""NASA Earthdata (CMR) provider adapter — placeholder.

NASA Earthdata / Common Metadata Repository (CMR) provides access to MODIS,
VIIRS, SRTM, and hundreds of other NASA Earth science collections.  This
adapter is a placeholder stub; all methods raise ``ProviderActionUnsupported``
until the Earthdata ingestion phase begins.

Earthdata data is free and publicly available — no commercial preflight required.
"""

from __future__ import annotations

from ._placeholder import PlaceholderAdapterBase

__all__ = ["EarthdataAdapter"]


class EarthdataAdapter(PlaceholderAdapterBase):
    """Placeholder adapter for NASA Earthdata / CMR.

    Replace this stub with a concrete implementation wrapping the CMR Search
    API (``https://cmr.earthdata.nasa.gov/search``) when the Earthdata
    ingestion phase begins.

    Relevant Earthdata/CMR capabilities (for future implementation):
    - Granule search: ``/granules`` (STAC/UMMC/JSON formats)
    - Collection search: ``/collections``
    - Download via HTTPS with Earthdata Login (EDL) OAuth2 Bearer token
    - S3 direct access for DAAC data in us-west-2 (requester pays)
    - No commercial tasking; data is free on demand
    """

    adapter_name: str = "earthdata"
