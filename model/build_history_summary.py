"""Summarize recent real FIRMS detections into named fire "events" for the
Canopy map screen's history section — spatial clustering of real points,
not fabricated incidents. Output: app/public/data/fire_history.json
"""
import csv
import json
import os
from collections import defaultdict
from datetime import date, timedelta

HERE = os.path.dirname(__file__)

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


def nearest_zone(lat, lon):
    return min(ZONES, key=lambda z: (z["lat"] - lat) ** 2 + (z["lng"] - lon) ** 2)


rows = list(csv.DictReader(open(os.path.join(HERE, "historical_fires_raw.csv"))))
max_date = max(date.fromisoformat(r["acq_date"]) for r in rows)
window_start = max_date - timedelta(days=21)
recent = [r for r in rows if date.fromisoformat(r["acq_date"]) >= window_start]

CELL = 0.7  # degrees, spatial cluster size — coarse enough to merge one fire's spread

clusters = defaultdict(list)
for r in recent:
    lat, lon = float(r["lat"]), float(r["lon"])
    key = (round(lat / CELL), round(lon / CELL))
    clusters[key].append(r)

events = []
for key, pts in clusters.items():
    lat = sum(float(p["lat"]) for p in pts) / len(pts)
    lon = sum(float(p["lon"]) for p in pts) / len(pts)
    dates = sorted(date.fromisoformat(p["acq_date"]) for p in pts)
    total_frp = sum(float(p["frp"]) for p in pts)
    zone = nearest_zone(lat, lon)
    events.append({
        "n": zone["n"],
        "r": zone["r"],
        "lat": round(lat, 3),
        "lng": round(lon, 3),
        "firstDate": dates[0].isoformat(),
        "lastDate": dates[-1].isoformat(),
        "detections": len(pts),
        "totalFrp": round(total_frp, 1),
        "active": (max_date - dates[-1]).days <= 1,
    })

events.sort(key=lambda e: -e["totalFrp"])
seen_zones = set()
top = []
for e in events:
    if e["n"] in seen_zones:
        continue
    seen_zones.add(e["n"])
    top.append(e)
    if len(top) == 6:
        break

out_path = os.path.join(HERE, "..", "app", "public", "data", "fire_history.json")
with open(out_path, "w") as f:
    json.dump({"asOf": max_date.isoformat(), "events": top}, f, indent=2)
print(f"Wrote {len(top)} events (from {len(events)} clusters) to {out_path}")
for e in top:
    print(f"  {e['n']} ({e['r']}): {e['detections']} detections, {e['totalFrp']} MW total, "
          f"{e['firstDate']}..{e['lastDate']}, active={e['active']}")
