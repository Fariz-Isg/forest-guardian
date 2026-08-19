"""Pull monthly Sentinel-2 (NDVI, NDMI) and Sentinel-1 (VV, VH backscatter)
composites for every land grid cell over the training window, via Earth
Engine. Vegetation state changes slowly, so monthly composites are both
sufficient signal and far more robust to cloud gaps than daily/biweekly
would be.

Uses ImageCollection.getRegion() for cheap per-point time-series sampling —
NOT a full-area median mosaic, which times out: that forces Earth Engine to
composite the entire California bbox at native resolution before sampling.
getRegion samples each matching scene directly at our 66 points server-side,
so the per-call cost only scales with (images x points), not bbox area.

Output: model/sentinel_features.csv, columns: row, col, month, ndvi, ndmi, vv, vh
"""
import csv
import json
import os
import statistics

import ee

PROJECT_ID = "cosmic-axe-503210-h2"
HERE = os.path.dirname(__file__)
BBOX = dict(west=-124.48, south=32.53, east=-114.13, north=42.01)
COLS, ROWS = 12, 12
MONTHS = [f"{y}-{m:02d}" for y, m in
          [(2025, mm) for mm in range(4, 13)] + [(2026, mm) for mm in range(1, 9)]]

ee.Initialize(project=PROJECT_ID)

with open(os.path.join(HERE, "californiaBoundary.json")) as f:
    boundary = json.load(f)
POLYGONS = boundary["geometry"]["coordinates"]


def point_in_ring(lon, lat, ring):
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def in_california(lon, lat):
    return any(point_in_ring(lon, lat, poly[0]) for poly in POLYGONS)


cells = []
for r in range(ROWS):
    for c in range(COLS):
        lat = BBOX["south"] + (r + 0.5) / ROWS * (BBOX["north"] - BBOX["south"])
        lon = BBOX["west"] + (c + 0.5) / COLS * (BBOX["east"] - BBOX["west"])
        if in_california(lon, lat):
            cells.append({"row": r, "col": c, "lat": round(lat, 4), "lon": round(lon, 4)})

print(f"Land cells: {len(cells)}", flush=True)

points_geom = ee.Geometry.MultiPoint([[c["lon"], c["lat"]] for c in cells])
# Match getRegion's sampled coordinates back to our cells by nearest point
# (pixel-center snapping means exact float equality isn't reliable).
def nearest_cell(lon, lat):
    return min(cells, key=lambda c: (c["lon"] - lon) ** 2 + (c["lat"] - lat) ** 2)


def month_bounds(ym):
    y, m = map(int, ym.split("-"))
    start = f"{y}-{m:02d}-01"
    end = f"{y+1}-01-01" if m == 12 else f"{y}-{m+1:02d}-01"
    return start, end


results = {}  # (row, col, month) -> dict of lists, medianed at the end

for ym in MONTHS:
    start, end = month_bounds(ym)
    print(f"Processing {ym}...", flush=True)

    s2 = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterDate(start, end)
        .filterBounds(points_geom)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40))
        .select(["B8", "B4", "B11"])
    )
    s2_rows = s2.getRegion(points_geom, scale=30).getInfo()
    s2_header = s2_rows[0]
    i_lon, i_lat = s2_header.index("longitude"), s2_header.index("latitude")
    i_b8, i_b4, i_b11 = s2_header.index("B8"), s2_header.index("B4"), s2_header.index("B11")
    for row in s2_rows[1:]:
        if row[i_b8] is None or row[i_b4] is None or row[i_b11] is None:
            continue
        cell = nearest_cell(row[i_lon], row[i_lat])
        b8, b4, b11 = row[i_b8], row[i_b4], row[i_b11]
        ndvi = (b8 - b4) / (b8 + b4) if (b8 + b4) else None
        ndmi = (b8 - b11) / (b8 + b11) if (b8 + b11) else None
        key = (cell["row"], cell["col"], ym)
        results.setdefault(key, {}).setdefault("ndvi", []).append(ndvi)
        results.setdefault(key, {}).setdefault("ndmi", []).append(ndmi)

    s1 = (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterDate(start, end)
        .filterBounds(points_geom)
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .select(["VV", "VH"])
    )
    s1_rows = s1.getRegion(points_geom, scale=30).getInfo()
    s1_header = s1_rows[0]
    j_lon, j_lat = s1_header.index("longitude"), s1_header.index("latitude")
    j_vv, j_vh = s1_header.index("VV"), s1_header.index("VH")
    for row in s1_rows[1:]:
        if row[j_vv] is None or row[j_vh] is None:
            continue
        cell = nearest_cell(row[j_lon], row[j_lat])
        key = (cell["row"], cell["col"], ym)
        results.setdefault(key, {}).setdefault("vv", []).append(row[j_vv])
        results.setdefault(key, {}).setdefault("vh", []).append(row[j_vh])

    print(f"  {ym}: {len(s2_rows)-1} S2 samples, {len(s1_rows)-1} S1 samples", flush=True)

out_path = os.path.join(HERE, "sentinel_features.csv")
n_rows = 0
n_complete = 0
with open(out_path, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["row", "col", "month", "ndvi", "ndmi", "vv", "vh"])
    for (row, col, ym), vals in sorted(results.items()):
        med = {k: (statistics.median(v) if v else None) for k, v in vals.items()}
        w.writerow([row, col, ym, med.get("ndvi"), med.get("ndmi"), med.get("vv"), med.get("vh")])
        n_rows += 1
        if all(med.get(k) is not None for k in ("ndvi", "ndmi", "vv", "vh")):
            n_complete += 1

print(f"Wrote {n_rows} (cell, month) rows to {out_path} ({n_complete} complete)", flush=True)
