"""Build the forest-masked 3km grid over California and export a cell
inventory (row, col, lat, lon, forest_fraction, elevation, slope, aspect,
worldcover_class) as a first Earth Engine batch export — this proves the
export/download mechanics before we layer in 104 weeks of weather/fire/
vegetation bands on top of it.

Forest-only per the product brief: cells are kept only where ESA WorldCover
"Tree cover" (class 10) covers at least FOREST_THRESHOLD of the cell area.
"""
import ee

PROJECT_ID = "cosmic-axe-503210-h2"
BBOX = dict(west=-124.48, south=32.53, east=-114.13, north=42.01)
GRID_M = 3000  # 3km cells
FOREST_THRESHOLD = 0.3  # keep a cell if >=30% of it is tree cover

ee.Initialize(project=PROJECT_ID)

ca_geom = ee.Geometry.Rectangle([BBOX["west"], BBOX["south"], BBOX["east"], BBOX["north"]])

# Build a 3km-spaced point grid in a metric CRS (EPSG:3310, CA Albers) so
# "3km" is actually 3km, not a lon/lat degree approximation.
proj = ee.Projection("EPSG:3310")
region_3310 = ca_geom.transform(proj, 1)
bounds = region_3310.bounds(1, proj).coordinates().get(0)
bounds = ee.List(bounds)


def make_grid():
    xs = ee.List(bounds).map(lambda p: ee.List(p).get(0))
    ys = ee.List(bounds).map(lambda p: ee.List(p).get(1))
    minx, maxx = ee.List(xs).reduce(ee.Reducer.min()), ee.List(xs).reduce(ee.Reducer.max())
    miny, maxy = ee.List(ys).reduce(ee.Reducer.min()), ee.List(ys).reduce(ee.Reducer.max())
    return minx, maxx, miny, maxy


minx, maxx, miny, maxy = make_grid()
minx, maxx, miny, maxy = minx.getInfo(), maxx.getInfo(), miny.getInfo(), maxy.getInfo()
n_cols = int((maxx - minx) // GRID_M) + 1
n_rows = int((maxy - miny) // GRID_M) + 1
print(f"Grid extent (EPSG:3310 meters): x[{minx:.0f},{maxx:.0f}] y[{miny:.0f},{maxy:.0f}]")
print(f"Raw grid: {n_cols} cols x {n_rows} rows = {n_cols*n_rows} cells (before forest mask)")

# Points at cell centers, in projected meters, then reprojected to lon/lat for
# the FeatureCollection (Earth Engine geometries are always stored as WGS84).
points = []
for r in range(n_rows):
    for c in range(n_cols):
        x = minx + (c + 0.5) * GRID_M
        y = miny + (r + 0.5) * GRID_M
        points.append((r, c, x, y))
print(f"Built {len(points)} candidate cell centers")

# Earth Engine has practical limits on client-constructed FeatureCollections
# built this way; batch in chunks for the reduceRegions forest-fraction pass.
worldcover = ee.ImageCollection("ESA/WorldCover/v200").first()
tree_mask = worldcover.select("Map").eq(10).rename("forest")
srtm = ee.Image("USGS/SRTMGL1_003")
terrain = ee.Terrain.products(srtm).select(["elevation", "slope", "aspect"])

CHUNK = 2000
kept_cells = []
for i in range(0, len(points), CHUNK):
    chunk = points[i:i + CHUNK]
    point_feats = []
    square_feats = []
    for (r, c, x, y) in chunk:
        pt = ee.Geometry.Point([x, y], proj)
        point_feats.append(ee.Feature(pt.transform("EPSG:4326", 1), {"row": r, "col": c}))
        # Square footprint of the actual 3km cell, for a true area-fraction
        # of forest cover — a bare point only samples the single pixel under it.
        square = ee.Geometry.Rectangle(
            [x - GRID_M / 2, y - GRID_M / 2, x + GRID_M / 2, y + GRID_M / 2], proj, False
        )
        square_feats.append(ee.Feature(square.transform("EPSG:4326", 1), {"row": r, "col": c}))

    forest_by_cell = tree_mask.reduceRegions(
        collection=ee.FeatureCollection(square_feats),
        reducer=ee.Reducer.mean().setOutputs(["forest"]), scale=30
    ).getInfo()
    terrain_by_cell = terrain.reduceRegions(
        collection=ee.FeatureCollection(point_feats), reducer=ee.Reducer.first(), scale=30
    ).getInfo()

    terrain_lookup = {(f["properties"]["row"], f["properties"]["col"]): f
                       for f in terrain_by_cell["features"]}

    for feat in forest_by_cell["features"]:
        p = feat["properties"]
        key = (p["row"], p["col"])
        if p.get("forest") is not None and p["forest"] >= FOREST_THRESHOLD:
            t_feat = terrain_lookup.get(key)
            if t_feat is None:
                continue
            t = t_feat["properties"]
            lon, lat = t_feat["geometry"]["coordinates"]  # already WGS84, no extra EE call needed
            r, c = key
            kept_cells.append({
                "row": r, "col": c,
                "lon": round(lon, 5), "lat": round(lat, 5),
                "forest_fraction": round(p["forest"], 3),
                "elevation": t.get("elevation"),
                "slope": t.get("slope"),
                "aspect": t.get("aspect"),
            })
    print(f"  chunk {i}-{i+len(chunk)}: {len(kept_cells)} forest cells kept so far", flush=True)

print(f"Final forest-masked grid: {len(kept_cells)} cells (of {len(points)} candidates, "
      f"{len(kept_cells)/len(points):.1%})")

import csv
import os
out_path = os.path.join(os.path.dirname(__file__), "grid_cells.csv")
with open(out_path, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["row", "col", "lon", "lat", "forest_fraction", "elevation", "slope", "aspect"])
    w.writeheader()
    w.writerows(kept_cells)
print(f"Wrote {out_path}")
