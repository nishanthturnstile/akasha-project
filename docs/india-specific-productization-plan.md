---
title: India-Specific Productization Plan
status: draft
last_updated: 2026-06-04
---

# India-Specific Productization Plan

This plan defines India-specific product direction after EOS-like parity. It is decision-support only: Akasha risk outputs, vegetation indices, weather context, and scout records are not crop disease diagnosis, treatment advice, insurance determination, or government certification.

## Crop seasons

- **Kharif:** monsoon-dependent sowing and harvest windows, rainfall anomaly context, waterlogging and delayed monsoon risk.
- **Rabi:** winter sowing windows, irrigation dependence, cold-wave and fog context.
- **Zaid:** short summer crop windows, heat stress and irrigation scheduling context.

State, district, and crop-specific calendars should be configurable data, not hard-coded product assumptions.

## Indian crop catalog

Initial catalog candidates include paddy/rice, wheat, maize, millets, cotton, sugarcane, pulses, oilseeds, horticulture crops, and plantation crops. Variety names and regional calendars should remain metadata so local partners can validate them.

## Weather and warnings

IMD forecasts and warnings are the preferred native path for heavy rainfall, heatwave, cold-wave, cyclone, thunderstorm, monsoon onset/withdrawal, rainfall anomaly, drought, and waterlogging context. Weather providers must stay behind the BFF/provider adapter boundary.

## Smallholder workflows

Akasha should support many small plots, mobile-first field workflows, low-bandwidth views, offline capture for boundaries/scout notes/photos, and aggregation by village, panchayat, block, or district where appropriate.

## Regional languages

English is the baseline. Hindi and launch-state languages should be prioritized for farmer-facing summaries. Advisory templates require local review; technical labels should be translated when they affect farmer action.

## Advisory delivery path

Potential delivery surfaces:
- In-app advisory cards.
- WhatsApp/SMS summaries for low-bandwidth users.
- Human-reviewed crop-stage, weather-warning, irrigation-reminder, and scouting follow-up messages.

High-impact advisories should require partner or agronomist review before delivery.

## Government and insurance workflows

Potential workflows include PMFBY-style crop-loss support, administrative aggregation, survey/khata identifiers where lawful, and evidence packs with imagery date, source, cloud/valid-pixel metrics, weather context, and scout records.

Satellite indices alone must never be presented as definitive crop-loss assessment or official determination.

## Data and provider strategy

Native sources should prioritize Sentinel-2, Sentinel-1, Landsat, public DEM/soil/weather datasets, and IMD warnings. ISRO/Bhoonidhi and paid high-resolution imagery should be optional adapters only after access, licensing, and cost are confirmed.

## Safety and limitations

- NDVI and related indices are indicators, not crop-health diagnosis.
- Disease and pest diagnosis requires validated crop/pathogen models and field observations.
- Risk levels must expose inputs, model version, confidence/unknown state, and limitations.
- Cloud cover, stale imagery, missing weather, and local validation gaps must be visible.
- Insurance/government outputs are evidence support, not official decisions.
