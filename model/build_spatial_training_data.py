"""Build a spatio-temporal training set: for each (grid cell, day), was any fire
detected in that cell that day, and what was that cell's own weather that day.

This replaces the earlier whole-state daily aggregate (which was nearly always
"yes, a fire happened somewhere in California" and gave the model almost no
negative examples to learn from). Binning by cell gives real spatial contrast:
most cell-days have no fire, and the ones that do correlate with that cell's
local weather, not the state's.
"""
import csv
import json
import os
import urllib.request
from datetime import date

HERE = os.path.dirname(__file__)
BBOX = dict(west=-124.48, south=32.53, east=-114.13, north=42.01)
COLS, ROWS = 12, 12
START_DATE = date(2025, 4, 28)
END_DATE = date(2026, 8, 18)

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

print(f"Land cells: {len(cells)} / {ROWS * COLS} raw grid cells")


def cell_index(lat, lon):
    r = int((lat - BBOX["south"]) / (BBOX["north"] - BBOX["south"]) * ROWS)
    c = int((lon - BBOX["west"]) / (BBOX["east"] - BBOX["west"]) * COLS)
    return r, c


# Bin raw historical detections into (row, col, date) -> hit
fire_cells = set()
with open(os.path.join(HERE, "historical_fires_raw.csv")) as f:
    for row in csv.DictReader(f):
        r, c = cell_index(float(row["lat"]), float(row["lon"]))
        fire_cells.add((r, c, row["acq_date"]))

print(f"Distinct (cell, date) fire hits: {len(fire_cells)}")

# Fetch historical weather for every land cell in one multi-location request.
lats = ",".join(str(c["lat"]) for c in cells)
lons = ",".join(str(c["lon"]) for c in cells)
url = (
    "https://archive-api.open-meteo.com/v1/archive?"
    f"latitude={lats}&longitude={lons}"
    f"&start_date={START_DATE.isoformat()}&end_date={END_DATE.isoformat()}"
    "&daily=temperature_2m_max,temperature_2m_min,windspeed_10m_max,"
    "precipitation_sum,relative_humidity_2m_mean"
    "&timezone=UTC"
)
print("Fetching historical weather for all land cells (one request)...")
with urllib.request.urlopen(url, timeout=120) as resp:
    weather_by_cell = json.loads(resp.read().decode("utf-8"))

if isinstance(weather_by_cell, dict):
    weather_by_cell = [weather_by_cell]
print(f"Got weather for {len(weather_by_cell)} cells")

out_path = os.path.join(HERE, "spatial_training_data.csv")
n_rows = 0
n_positive = 0
with open(out_path, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "row", "col", "lat", "lon", "date", "fire_detected",
        "temp_max", "temp_min", "wind_max", "precip_sum", "humidity_mean",
    ])
    for cell, weather in zip(cells, weather_by_cell):
        daily = weather["daily"]
        has_humidity = "relative_humidity_2m_mean" in daily and any(
            v is not None for v in daily["relative_humidity_2m_mean"]
        )
        for i, d in enumerate(daily["time"]):
            label = 1 if (cell["row"], cell["col"], d) in fire_cells else 0
            humidity = (
                daily["relative_humidity_2m_mean"][i]
                if has_humidity and daily["relative_humidity_2m_mean"][i] is not None
                else 45.0
            )
            w.writerow([
                cell["row"], cell["col"], cell["lat"], cell["lon"], d, label,
                daily["temperature_2m_max"][i], daily["temperature_2m_min"][i],
                daily["windspeed_10m_max"][i], daily["precipitation_sum"][i], humidity,
            ])
            n_rows += 1
            n_positive += label

print(f"Wrote {n_rows} cell-day rows ({n_positive} positive, {n_positive/n_rows:.1%}) to {out_path}")
