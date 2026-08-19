"""Build a historical training dataset for the Forest Guardian fire-risk model.

Combines:
  - NASA FIRMS historical fire detections (VIIRS_SNPP_SP science-quality archive,
    plus the VIIRS_SNPP_NRT tail for the most recent ~4 months) for the Azerbaijan bbox.
  - Open-Meteo historical daily weather for the bbox center point.

Output: model/training_data.csv, one row per day:
  date, fire_detected, fire_count, max_frp, temp_max, temp_min, wind_max, precip_sum, humidity_mean
"""
import csv
import os
import time
import urllib.request
from datetime import date, timedelta

BBOX = "-124.48,32.53,-114.13,42.01"
CENTER_LAT, CENTER_LON = 37.27, -119.30

MAP_KEY = None
for line in open(os.path.join(os.path.dirname(__file__), "..", ".env")):
    if line.startswith("FIRMS_MAP_KEY="):
        MAP_KEY = line.strip().split("=", 1)[1]
if not MAP_KEY:
    raise SystemExit("FIRMS_MAP_KEY not found in .env")

SP_END = date(2026, 4, 27)     # last day covered by VIIRS_SNPP_SP archive
SP_START = SP_END - timedelta(days=365)
NRT_START = date(2026, 4, 28)  # VIIRS_SNPP_NRT coverage starts here
NRT_END = date(2026, 8, 18)    # yesterday relative to "today" 2026-08-19


def fetch_chunk(source, end_date, day_range):
    url = (
        f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{source}/"
        f"{BBOX}/{day_range}/{end_date.isoformat()}"
    )
    with urllib.request.urlopen(url, timeout=30) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    lines = text.strip().splitlines()
    if len(lines) < 2:
        return []
    header = lines[0].split(",")
    idx_date = header.index("acq_date")
    idx_frp = header.index("frp")
    idx_lat = header.index("latitude")
    idx_lon = header.index("longitude")
    rows = []
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) <= max(idx_date, idx_frp, idx_lat, idx_lon):
            continue
        rows.append((
            parts[idx_date],
            float(parts[idx_lat]),
            float(parts[idx_lon]),
            float(parts[idx_frp]) if parts[idx_frp] else 0.0,
        ))
    return rows


def fetch_range(source, start, end, day_range=10):
    """Step backward from `end` to `start` in day_range-sized chunks."""
    all_rows = []
    cursor = end
    while cursor >= start:
        rows = fetch_chunk(source, cursor, day_range)
        all_rows.extend(rows)
        print(f"  {source} chunk ending {cursor}: {len(rows)} detections")
        cursor -= timedelta(days=day_range)
        time.sleep(0.3)
    return all_rows


print("Fetching FIRMS SP archive (historical)...")
sp_rows = fetch_range("VIIRS_SNPP_SP", SP_START, SP_END, day_range=5)
print("Fetching FIRMS NRT tail (recent)...")
nrt_rows = fetch_range("VIIRS_SNPP_NRT", NRT_START, NRT_END, day_range=5)

fire_rows = sp_rows + nrt_rows

raw_path = os.path.join(os.path.dirname(__file__), "historical_fires_raw.csv")
with open(raw_path, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["acq_date", "lat", "lon", "frp"])
    w.writerows([(d, lat, lon, frp) for d, lat, lon, frp in fire_rows])
print(f"Wrote {len(fire_rows)} raw detections to {raw_path}")

daily_fire = {}
for acq_date, lat, lon, frp in fire_rows:
    d = daily_fire.setdefault(acq_date, {"count": 0, "max_frp": 0.0})
    d["count"] += 1
    d["max_frp"] = max(d["max_frp"], frp)

print(f"Total fire detections: {len(fire_rows)} across {len(daily_fire)} distinct days")

print("Fetching Open-Meteo historical daily weather...")
weather_url = (
    "https://archive-api.open-meteo.com/v1/archive?"
    f"latitude={CENTER_LAT}&longitude={CENTER_LON}"
    f"&start_date={SP_START.isoformat()}&end_date={NRT_END.isoformat()}"
    "&daily=temperature_2m_max,temperature_2m_min,windspeed_10m_max,"
    "precipitation_sum,relative_humidity_2m_mean"
    "&timezone=UTC"
)
import json

with urllib.request.urlopen(weather_url, timeout=60) as resp:
    weather = json.loads(resp.read().decode("utf-8"))

if "daily" not in weather:
    raise SystemExit(f"Open-Meteo error: {weather}")

daily = weather["daily"]
has_humidity = "relative_humidity_2m_mean" in daily and any(
    v is not None for v in daily["relative_humidity_2m_mean"]
)
if not has_humidity:
    print("  NOTE: relative_humidity_2m_mean unavailable from archive API; will impute via a fixed fallback.")

out_path = os.path.join(os.path.dirname(__file__), "training_data.csv")
with open(out_path, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "date", "fire_detected", "fire_count", "max_frp",
        "temp_max", "temp_min", "wind_max", "precip_sum", "humidity_mean",
    ])
    n = len(daily["time"])
    for i in range(n):
        d = daily["time"][i]
        fd = daily_fire.get(d, {"count": 0, "max_frp": 0.0})
        humidity = (
            daily["relative_humidity_2m_mean"][i]
            if has_humidity and daily["relative_humidity_2m_mean"][i] is not None
            else 55.0
        )
        w.writerow([
            d,
            1 if fd["count"] > 0 else 0,
            fd["count"],
            round(fd["max_frp"], 2),
            daily["temperature_2m_max"][i],
            daily["temperature_2m_min"][i],
            daily["windspeed_10m_max"][i],
            daily["precipitation_sum"][i],
            humidity,
        ])

print(f"Wrote {n} days of training data to {out_path}")
