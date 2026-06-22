# Module 07 — Weather

Guide page: <https://eos.com/user-guide/crop-monitoring/weather/>

## Purpose
Historical and forecast weather analytics for a field. Reachable from the Weather
analytics tab (right sidebar) or via **Forecast** from Monitoring when "Weather
today" data isn't enough or cross-period comparison is needed.

## Sub-features

### 7.1 Historical Weather
- Archived **temperature** and **precipitation** data.
- Set the **vegetation period**: choose a season (data available from **2008**) and
  its start/end dates via calendar.
- A **Growth Stages** curve is overlaid on all graphs by default; disabled
  automatically if no stages fall in the range, and can be toggled off manually.
- **Compare with 5-year average** toggle adds a 5-year-average curve.

### 7.2 Accumulated & Daily Precipitation graphs
- When 5-year average is enabled, the graphs show the current period vs. the last
  5 years.
- Two graphs: **Accumulated Precipitation** and **Daily Precipitation**.

### 7.3 Daily Temperatures
- Graph of daily **min °C** and **max °C**; adds **5-year-average** min/max when that
  option is on.

### 7.4 Sum of Active Temperatures
- Dropdown with three thresholds: **0 °C (1–5 °C)**, **5 °C (6–10 °C)**, **10 °C
  (11 °C+)**. Selecting a band shows the summed active temperatures for that band.
  (Growing-degree-style accumulation.)

### 7.5 Weather Forecast
- **14-day** forecast including wind speed, humidity, cloud coverage, and expected
  precipitation.

### 7.6 Recommended time for field activities
- On the forecast page: recommended hourly windows for activities like **soil
  tillage** and **spraying**.
- Computed from: air temperature, air humidity, wind speed, rainfall forecast,
  rainfall totals for the last **24/48/72 h**, soil moisture, soil temperature.
- Each hour gets a colored marker: **Green = optimal**, **Orange = acceptable**,
  **Red = not recommended**.

## Notes for replica
- Two data regimes: historical archive (from 2008) and 14-day forecast.
- Reusable curve/legend components shared with Monitoring charts (temperature,
  moisture). The activity-recommendation engine is a rules layer over forecast +
  soil data producing a per-hour traffic-light score.
- 5-year-average overlay is a recurring pattern (precip + temperature).
