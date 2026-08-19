"""Sanity-check Google Earth Engine access and pull a real Sentinel-2 scene
over one of Forest Guardian's monitored regions (Sequoia-Kings, Southern Sierra
— one of the areas the fire-history summary flagged as still active).

Prerequisites (one-time, interactive — this script can't do it for you):
    python3 -c "import ee; ee.Authenticate()"
This opens a browser login and caches credentials locally, after which
ee.Initialize() below will work non-interactively from then on.

Run:
    python3 model/earth_engine_test.py
"""
import datetime

import ee

PROJECT_ID = "cosmic-axe-503210-h2"

ee.Initialize(project=PROJECT_ID)
print(f"Earth Engine initialized OK for project '{PROJECT_ID}'.")

# Sequoia-Kings (Southern Sierra), one of ZONES in the Canopy map screen —
# ~0.3 deg buffer around the anchor point used there.
CENTER_LAT, CENTER_LON = 36.70, -118.65
BUFFER_DEG = 0.3
aoi = ee.Geometry.Rectangle([
    CENTER_LON - BUFFER_DEG, CENTER_LAT - BUFFER_DEG,
    CENTER_LON + BUFFER_DEG, CENTER_LAT + BUFFER_DEG,
])

end = datetime.date.today()
start = end - datetime.timedelta(days=30)

collection = (
    ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
    .filterBounds(aoi)
    .filterDate(start.isoformat(), end.isoformat())
    .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
)

count = collection.size().getInfo()
print(f"Sentinel-2 scenes over Sequoia-Kings, last 30 days, <20% cloud: {count}")

if count == 0:
    print("No scenes matched — try widening the date range or cloud threshold.")
else:
    image = collection.sort("CLOUDY_PIXEL_PERCENTAGE").first()
    info = image.getInfo()
    props = info["properties"]
    print(f"Least-cloudy scene: {props.get('PRODUCT_ID', '(no id)')}")
    print(f"  Date: {datetime.datetime.utcfromtimestamp(props['system:time_start']/1000)}")
    print(f"  Cloud cover: {props.get('CLOUDY_PIXEL_PERCENTAGE')}%")
    print(f"  Bands: {[b['id'] for b in info['bands']]}")

    # NDVI (vegetation health/dryness proxy) as a quick derived-product check,
    # since that's the kind of signal that would feed into a fire-risk model.
    ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")
    mean_ndvi = ndvi.reduceRegion(
        reducer=ee.Reducer.mean(), geometry=aoi, scale=100, maxPixels=1e9
    ).getInfo()
    print(f"  Mean NDVI over AOI: {mean_ndvi.get('NDVI')}")

    thumb_url = image.select(["B4", "B3", "B2"]).getThumbURL({
        "region": aoi, "dimensions": 512, "min": 0, "max": 3000,
    })
    print(f"  True-color preview: {thumb_url}")
