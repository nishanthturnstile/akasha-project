"""Provider adapter sub-package for the Akasha ingestion scheduler.

Implements Phase 2 of docs/impl-plan/architecture-satellite-ingestion-scheduler-1.md.

Structure
---------
- base.py          — typed request/result objects and ProviderAdapter Protocol (TASK-007)
- registry.py      — get_provider_adapter() factory (TASK-008)
- bhoonidhi_adapter.py  — ISRO/Bhoonidhi thin wrapper (TASK-009)
- <future>_adapter.py   — placeholders for CDSE/USGS/Earthdata/ASF/Planet/JAXA/Vendor (TASK-010)
"""
