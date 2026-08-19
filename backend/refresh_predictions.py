"""Daily refresh job: score all 18 monitored zones with the trained XGBoost
model (model/gee_pipeline/xgb_model.joblib) and write a static snapshot the
frontend can fetch instantly (app/public/data/xgb_predictions.json).

Why not score live per-request? Two reasons: (1) Earth Engine queries take
1-5s, which would make every page load slow; (2) the model's own inputs
(GRIDMET, MODIS) only update every few days at best, so scoring more often
than daily wouldn't reflect any new information anyway. This should be run
on a daily cron/scheduled task — see README at the bottom of this file.

Feature sourcing (deliberately mixed, for a reason):
  - tmmx/tmmn/vs/rmin/pr for "Today"/+1/+2/+3: Open-Meteo forecast, unit-
    converted to match GRIDMET's training units (Kelvin, m/s, mm, %). GRIDMET
    itself has no future data and its "latest" day is ~3 days stale, so using
    it for "today" would mislabel a 3-day-old snapshot as current.
  - pr_90d (drought signal) for all four days: GRIDMET's actual 90-day
    trailing sum through its latest available date. A 90-day sum barely
    moves day-to-day, so reusing one value across today/+1/+2/+3 is a
    negligible approximation — and this one truly can't come from a
    forecast product.
  - The past-7-day trend sparkline: real GRIDMET history (backward-looking,
    so its few-day lag doesn't create any labeling inconsistency).
  - elevation/slope/aspect/forest_fraction/prior_fire_count: static, from
    the nearest of the 24,383 training grid cells to each zone's anchor point.
"""
import json
import os
import urllib.request

import ee
import joblib
import numpy as np
import pandas as pd

PROJECT_ID = "cosmic-axe-503210-h2"
HERE = os.path.dirname(__file__)
GEE_DIR = os.path.join(HERE, "..", "model", "gee_pipeline")
OUT_PATH = os.path.join(HERE, "..", "app", "public", "data", "xgb_predictions.json")

FEATURES = ["tmmx", "tmmn", "vs", "rmin", "pr", "pr_90d",
            "elevation", "slope", "aspect", "forest_fraction", "prior_fire_count"]

# Same 18 curated regions as app/index.html's ZONES array — kept in sync by hand.
ZONES = [
    {"n": "Klamath", "r": "Siskiyou County", "lat": 41.70, "lng": -123.20},
    {"n": "Modoc Plateau", "r": "Modoc County", "lat": 41.55, "lng": -120.60},
    {"n": "Shasta-Trinity", "r": "Trinity County", "lat": 40.75, "lng": -122.55},
    {"n": "Plumas", "r": "Northern Sierra", "lat": 39.95, "lng": -120.85},
    {"n": "Tahoe Basin", "r": "El Dorado County", "lat": 39.10, "lng": -120.15},
    {"n": "Mendocino", "r": "North Coast Ranges", "lat": 39.45, "lng": -123.05},
    {"n": "Sonoma-Napa Hills", "r": "Bay Area North", "lat": 38.55, "lng": -122.50},
    {"n": "Stanislaus", "r": "Central Sierra", "lat": 38.25, "lng": -120.05},
    {"n": "Yosemite Sierra", "r": "Mariposa County", "lat": 37.85, "lng": -119.60},
    {"n": "Sequoia-Kings", "r": "Southern Sierra", "lat": 36.70, "lng": -118.65},
    {"n": "Kern River Canyon", "r": "Kern County", "lat": 35.60, "lng": -118.45},
    {"n": "Los Padres North", "r": "Monterey County", "lat": 36.15, "lng": -121.45},
    {"n": "Santa Lucia", "r": "San Luis Obispo County", "lat": 35.35, "lng": -120.35},
    {"n": "Ventura Backcountry", "r": "Ventura County", "lat": 34.55, "lng": -119.05},
    {"n": "Angeles", "r": "San Gabriel Mountains", "lat": 34.30, "lng": -118.05},
    {"n": "San Bernardino", "r": "Inland Empire", "lat": 34.20, "lng": -116.90},
    {"n": "San Diego Backcountry", "r": "San Diego County", "lat": 32.95, "lng": -116.60},
    {"n": "Central Valley Edge", "r": "Fresno County", "lat": 36.85, "lng": -119.85},
]

ee.Initialize(project=PROJECT_ID)
model = joblib.load(os.path.join(GEE_DIR, "xgb_model.joblib"))

# --- static per-zone features, from the nearest training grid cell ---
grid = pd.read_csv(os.path.join(GEE_DIR, "grid_cells.csv"))
monthly = pd.read_csv(os.path.join(GEE_DIR, "monthly_features.csv"))
fire_counts = (monthly.groupby(["row", "col"])["burned"].sum()
               .reset_index().rename(columns={"burned": "prior_fire_count"}))
grid = grid.merge(fire_counts, on=["row", "col"], how="left")
grid["prior_fire_count"] = grid["prior_fire_count"].fillna(0)

for z in ZONES:
    d2 = (grid["lat"] - z["lat"]) ** 2 + (grid["lon"] - z["lng"]) ** 2
    nearest = grid.loc[d2.idxmin()]
    z["elevation"] = float(nearest["elevation"])
    z["slope"] = float(nearest["slope"])
    z["aspect"] = float(nearest["aspect"])
    z["forest_fraction"] = float(nearest["forest_fraction"])
    z["prior_fire_count"] = float(nearest["prior_fire_count"])


def predict(feat):
    x = np.array([[feat[f] for f in FEATURES]])
    return float(model.predict_proba(x)[0, 1])


# --- GRIDMET: past 8 days (for the trend sparkline) + 90-day trailing precip ---
points_geom = ee.Geometry.MultiPoint([[z["lng"], z["lat"]] for z in ZONES])
latest = ee.Date(ee.ImageCollection("IDAHO_EPSCOR/GRIDMET")
                  .sort("system:time_start", False).first().get("system:time_start"))

past = (ee.ImageCollection("IDAHO_EPSCOR/GRIDMET")
        .filterDate(latest.advance(-7, "day"), latest.advance(1, "day"))
        .select(["tmmx", "tmmn", "vs", "rmin", "pr"]))
past_rows = past.getRegion(points_geom, scale=4000).getInfo()
past_header = past_rows[0]
i_lon, i_lat, i_time = past_header.index("longitude"), past_header.index("latitude"), past_header.index("time")

past_by_zone = {i: [] for i in range(len(ZONES))}


def nearest_zone_index(lon, lat):
    best_i, best_d = 0, float("inf")
    for i, z in enumerate(ZONES):
        d = (z["lng"] - lon) ** 2 + (z["lat"] - lat) ** 2
        if d < best_d:
            best_d, best_i = d, i
    return best_i


for row in past_rows[1:]:
    rec = dict(zip(past_header, row))
    if rec.get("tmmx") is None:
        continue
    zi = nearest_zone_index(rec["longitude"], rec["latitude"])
    past_by_zone[zi].append(rec)

pr90_start = latest.advance(-90, "day")
pr90_img = (ee.ImageCollection("IDAHO_EPSCOR/GRIDMET")
            .filterDate(pr90_start, latest.advance(1, "day"))
            .select("pr").sum().rename("pr_90d"))
pr90_fc = ee.FeatureCollection([
    ee.Feature(ee.Geometry.Point([z["lng"], z["lat"]]), {"i": i}) for i, z in enumerate(ZONES)
])
pr90_result = pr90_img.reduceRegions(collection=pr90_fc, reducer=ee.Reducer.mean(), scale=4000).getInfo()
pr90_by_zone = {f["properties"]["i"]: f["properties"].get("pr_90d", 0) for f in pr90_result["features"]}

print(f"GRIDMET latest date used: {latest.format('YYYY-MM-dd').getInfo()}")

# --- Open-Meteo forecast: today + 3 days ahead, all zones in one request ---
lats = ",".join(str(z["lat"]) for z in ZONES)
lngs = ",".join(str(z["lng"]) for z in ZONES)
url = (
    f"https://api.open-meteo.com/v1/forecast?latitude={lats}&longitude={lngs}"
    "&daily=temperature_2m_max,temperature_2m_min,windspeed_10m_max,"
    "precipitation_sum,relative_humidity_2m_min"
    "&forecast_days=4&timezone=UTC&wind_speed_unit=ms"
)
with urllib.request.urlopen(url, timeout=30) as resp:
    forecast_data = json.loads(resp.read().decode("utf-8"))
forecast_list = forecast_data if isinstance(forecast_data, list) else [forecast_data]

results = {}
for i, z in enumerate(ZONES):
    pr90 = pr90_by_zone.get(i, 0) or 0

    # Past-7-days trend (GRIDMET actuals; last entry ~= GRIDMET's "today")
    week = []
    for rec in sorted(past_by_zone[i], key=lambda r: r["time"])[-7:]:
        feat = {
            "tmmx": rec["tmmx"], "tmmn": rec["tmmn"], "vs": rec["vs"], "rmin": rec["rmin"],
            "pr": rec["pr"], "pr_90d": pr90,
            "elevation": z["elevation"], "slope": z["slope"], "aspect": z["aspect"],
            "forest_fraction": z["forest_fraction"], "prior_fire_count": z["prior_fire_count"],
        }
        week.append(round(predict(feat) * 100))
    while len(week) < 7:
        week.insert(0, week[0] if week else 0)

    # Today + 3 days ahead (Open-Meteo forecast, unit-matched to GRIDMET)
    daily = forecast_list[i]["daily"]
    f_scores = []
    for d in range(4):
        feat = {
            "tmmx": daily["temperature_2m_max"][d] + 273.15,
            "tmmn": daily["temperature_2m_min"][d] + 273.15,
            "vs": daily["windspeed_10m_max"][d],
            "rmin": daily["relative_humidity_2m_min"][d],
            "pr": daily["precipitation_sum"][d],
            "pr_90d": pr90,
            "elevation": z["elevation"], "slope": z["slope"], "aspect": z["aspect"],
            "forest_fraction": z["forest_fraction"], "prior_fire_count": z["prior_fire_count"],
        }
        f_scores.append(round(predict(feat) * 100))

    trend = f_scores[0] - week[-1]
    results[z["n"]] = {
        "r": z["r"], "lat": z["lat"], "lng": z["lng"],
        "v": f_scores[0], "f": f_scores, "week": week,
        "t": ("+" if trend >= 0 else "") + str(trend),
    }
    print(f"  {z['n']}: today={f_scores[0]} forecast={f_scores} week={week}")

with open(OUT_PATH, "w") as f:
    json.dump({
        "generated_at": latest.format("YYYY-MM-dd").getInfo(),
        "model": "xgboost_v2_forest_grid",
        "zones": results,
    }, f, indent=2)
print(f"Wrote {OUT_PATH}")

# --- To schedule this daily (Linux cron example) ---
# crontab -e, then add:
#   0 7 * * * cd "/path/to/VISTAR MVP" && python3 backend/refresh_predictions.py >> /var/log/forest-guardian-refresh.log 2>&1
