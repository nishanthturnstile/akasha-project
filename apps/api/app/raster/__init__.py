"""Akasha BFF raster/index package (Slice 2 — Phase 2 raster de-risk).

Responsibility split (architecture-tech-stack.md / data-ingestion rules):
  * TiTiler serves RGB display tiles only.
  * The BFF computes cloud/SCL-masked, offset-corrected index statistics here
    using rasterio (reading BOTH the analytic COG window and the SCL COG window
    for the request polygon).

Design rules for this package:
  * `statistics_core` is PURE numpy (no I/O) so the index math is unit-testable
    without any COG/MinIO access.
  * `raster_reader`, `geo_validate` lazily import rasterio/shapely/pyproj so that
    importing the FastAPI app (the live Emergent preview) never requires heavy
    geospatial wheels to be installed.
"""
