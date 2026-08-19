"""For every forest-masked grid cell (model/gee_pipeline/grid_cells.csv) and
every month in the training window, pull:
  - fire label: any MODIS MCD64A1 burned pixel in that cell that month
  - weather: GRIDMET monthly aggregates (temp, wind, humidity, precip) plus
    a 90-day trailing precipitation sum as a drought signal

Note: monthly, not weekly — MCD64A1 (the burned-area product) is natively
monthly, and at this grid's scale (tens of thousands of cells) a weekly
timestep would multiply the export cost ~4x for temporal resolution finer
than the label itself actually supports.

Output: model/gee_pipeline/monthly_features.csv
"""
import csv
import os

import ee

PROJECT_ID = "cosmic-axe-503210-h2"
HERE = os.path.dirname(__file__)
# MCD64A1 (burned-area) has ~3.5 months of processing latency — the most
# recent available month as of this pipeline run was 2026-05. Trimmed to 22
# months (two fire seasons) to keep the ~24,000-cell export tractable —
# timing tests showed ~12s per 2000-cell chunk, so the full 33-month range
# would have taken 80+ minutes.
MONTHS = [f"{y}-{m:02d}" for y, m in
          [(2024, mm) for mm in range(8, 13)] +
          [(2025, mm) for mm in range(1, 13)] +
          [(2026, mm) for mm in range(1, 6)]]

ee.Initialize(project=PROJECT_ID)

cells = list(csv.DictReader(open(os.path.join(HERE, "grid_cells.csv"))))
print(f"Loaded {len(cells)} forest cells")

CHUNK = 2000


def month_bounds(ym):
    y, m = map(int, ym.split("-"))
    start = f"{y}-{m:02d}-01"
    end = f"{y+1}-01-01" if m == 12 else f"{y}-{m+1:02d}-01"
    return start, end


out_path = os.path.join(HERE, "monthly_features.csv")
fieldnames = ["row", "col", "month", "burned",
              "tmmx", "tmmn", "vs", "rmin", "pr", "pr_90d"]

with open(out_path, "w", newline="") as out_f:
    w = csv.DictWriter(out_f, fieldnames=fieldnames)
    w.writeheader()

    for ym in MONTHS:
        start, end = month_bounds(ym)
        y, m = map(int, ym.split("-"))
        pr90_start = ee.Date(start).advance(-90, "day")

        # MCD64A1: BurnDate band is day-of-year (1-366) the pixel burned that
        # month, 0 = unburned. "burned" here just means >0 in that month's image.
        mcd_month = (
            ee.ImageCollection("MODIS/061/MCD64A1")
            .filterDate(start, end)
            .select("BurnDate")
            .max()
        )
        burned_mask = mcd_month.gt(0).unmask(0).rename("burned")

        gridmet_month = ee.ImageCollection("IDAHO_EPSCOR/GRIDMET").filterDate(start, end)
        weather_month = gridmet_month.select(["tmmx", "tmmn", "vs", "rmin"]).mean()
        pr_month = gridmet_month.select("pr").sum().rename("pr")
        pr_90d = (
            ee.ImageCollection("IDAHO_EPSCOR/GRIDMET")
            .filterDate(pr90_start, end)
            .select("pr")
            .sum()
            .rename("pr_90d")
        )

        combined = burned_mask.addBands(weather_month).addBands(pr_month).addBands(pr_90d)

        n_written_this_month = 0
        for i in range(0, len(cells), CHUNK):
            chunk = cells[i:i + CHUNK]
            feats = [
                ee.Feature(ee.Geometry.Point([float(c["lon"]), float(c["lat"])]),
                           {"row": int(c["row"]), "col": int(c["col"])})
                for c in chunk
            ]
            fc = ee.FeatureCollection(feats)
            sampled = combined.reduceRegions(
                collection=fc, reducer=ee.Reducer.mean(), scale=500
            ).getInfo()

            for feat in sampled["features"]:
                p = feat["properties"]
                w.writerow({
                    "row": p["row"], "col": p["col"], "month": ym,
                    "burned": 1 if (p.get("burned") or 0) > 0.5 else 0,
                    "tmmx": p.get("tmmx"), "tmmn": p.get("tmmn"),
                    "vs": p.get("vs"), "rmin": p.get("rmin"),
                    "pr": p.get("pr"), "pr_90d": p.get("pr_90d"),
                })
                n_written_this_month += 1
        out_f.flush()
        print(f"{ym}: wrote {n_written_this_month} cell-month rows", flush=True)

print(f"Done. Wrote to {out_path}")
