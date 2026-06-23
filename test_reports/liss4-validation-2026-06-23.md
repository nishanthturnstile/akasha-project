# LISS-4 staging product validation — 2026-06-23

## Context

- Source ID: `resourcesat-2a-liss4-mx70-l2`
- Bhoonidhi collection: `ResourceSat-2A_LISS4-MX70_L2`
- Staging VM: `akasha-staging`
- Egress IP: `20.219.3.35`
- Product ZIP inspected: `/srv/akasha/data/raw/bhoonidhi/resourcesat-2a-liss4-mx70-l2/RAF06MAY2026048841009900063SSANSTUC00GTDD.zip`
- ZIP size: `650898903` bytes

## Product structure

ZIP contents include:

- `BAND2.tif`
- `BAND3.tif`
- `BAND4.tif`
- `BAND_META.txt`
- `RAF06MAY2026048841009900063SSANSTUC00GTDD.meta`

`BAND5.tif` is absent, as expected for LISS-4 MX70 L2.

## Metadata excerpts

From `BAND_META.txt` / product `.meta`:

- `NoOfBands= 3`
- `BandNumbers= 234`
- `BytesPerPixel= 2`
- `BitsPerPixel= 10`
- `InputResolutionAlong=   5.80`
- `InputResolutionAcross=   5.80`
- `OutputResolutionAlong=   5.00`
- `OutputResolutionAcross=   5.00`
- `NoPixels= 17761`
- `MapProjection= UTM`
- `Datum= WGS84`

## Raster metadata

All three analytic bands open successfully through GDAL/rasterio using `/vsizip/` paths:

| Band | Exists | CRS | Dtype | Size | Count | Nodata | Resolution | Raster scale/offset tags |
|---|---:|---|---|---|---:|---|---|---|
| BAND2 | yes | EPSG:32643 | uint16 | 17761x16588 | 1 | None | 5.0 x 5.0 m | scales=(1.0,), offsets=(0.0,) |
| BAND3 | yes | EPSG:32643 | uint16 | 17761x16588 | 1 | None | 5.0 x 5.0 m | scales=(1.0,), offsets=(0.0,) |
| BAND4 | yes | EPSG:32643 | uint16 | 17761x16588 | 1 | None | 5.0 x 5.0 m | scales=(1.0,), offsets=(0.0,) |
| BAND5 | no | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

## Scale/offset decision

No product metadata indicating a different reflectance correction was found in this inspection. The raster tags report raw storage scale/offset as `1.0/0.0`, so Akasha should continue applying the ResourceSat BOA source-profile correction `corrected = dn * 0.0001 + 0.0` unless a future NRSC metadata sample provides an explicit different reflectance multiplier/offset.

No code change is required for TASK-022 based on this product inspection.
