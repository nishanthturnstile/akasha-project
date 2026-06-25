"""USDA provider adapter — placeholder.

USDA provides NAIP (National Agriculture Imagery Program) aerial imagery
for the continental United States.  This adapter is a placeholder stub; all
methods raise ``ProviderActionUnsupported`` until the USDA ingestion phase
begins.

NAIP data is free and publicly available (cloud-hosted COG on Planetary
Computer / AWS) — no commercial preflight required.  Note that NAIP is
US-only and therefore permanently out-of-AOI for all India deployments;
sources using this adapter must be marked ``aoi_scope=reference_only``
(see SRC-006 in source_registry.py).
"""

from __future__ import annotations

from ._placeholder import PlaceholderAdapterBase

__all__ = ["USDAAdapter"]


class USDAAdapter(PlaceholderAdapterBase):
    """Placeholder adapter for USDA NAIP (cloud COG / Planetary Computer).

    Replace this stub with a concrete implementation when USDA ingestion is
    required.  NAIP COGs are accessible without authentication via the
    Microsoft Planetary Computer STAC API
    (``https://planetarycomputer.microsoft.com/api/stac/v1/collections/naip``)
    or directly from AWS Open Data.

    NAIP is out-of-AOI for all India deployments; this adapter should only
    ever be invoked in reference/testing contexts.
    """

    adapter_name: str = "usda"
