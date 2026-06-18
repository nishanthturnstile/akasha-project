# Module 17 — Access Through API

Guide page: <https://eos.com/user-guide/crop-monitoring/access-through-api/>

## Purpose
Programmatic access to the platform's data/capabilities via an API, for users who
want to integrate EOSDA data into their own systems.

## Sub-features

### 17.1 Current API capabilities
- **Extended satellite sources:** Sentinel-2, Sentinel-1, Landsat 8/7/5/4, MODIS,
  NAIP, CBERS-4. (Broader than the in-app Monitoring sources.)
- **Extended vegetation indices:** NDVI, EVI, GNDVI, CVI, NDRE, MSAVI, ReCI, NDSI,
  NDWI, SAVI, ARVI, GCI, SIPI, NBR, MSI, ISTACK, FIDET, CCCI.
- **Weather data archive** going back **20 years**.

### 17.2 Get access
- **My Account** (side menu) → **API** icon → **Get started** → register on the
  **developer portal** to obtain an **API key**. Links to EOSDA API documentation.

## Cross-references
- Wider satellite/index coverage than the UI hints at the underlying data platform
  capabilities that could back several modules (imagery sources in module 06, weather
  archive in module 07).

## Notes for replica
- For a replica, this is a developer-portal + API-key issuance surface plus the public
  API itself. Scope for a first build: API key management UI (generate/revoke keys —
  Akasha already has API keys in `account.py`), and documented endpoints mirroring
  imagery, index, and weather queries.
- The extended satellite/index list is aspirational vs. the in-app UI; treat as a
  longer-term capability catalog rather than launch scope.
