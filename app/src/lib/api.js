import californiaBoundary from '../data/californiaBoundary.json';

export const BBOX = { west: -124.48, south: 32.53, east: -114.13, north: 42.01 };

// Raster resolution for the risk field. Marching-squares isobands interpolate
// between cells, so this doesn't need to be huge to look smooth.
export const GRID_COLS = 22;
export const GRID_ROWS = 22;

const DAILY_FIELDS =
  'temperature_2m_max,temperature_2m_min,windspeed_10m_max,precipitation_sum,relative_humidity_2m_mean';

// Ray-casting point-in-polygon, extended to a MultiPolygon (mainland + islands).
function pointInRing(lon, lat, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    const intersects = yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi;
    if (intersects) inside = !inside;
  }
  return inside;
}

function pointInCalifornia(lon, lat) {
  return californiaBoundary.geometry.coordinates.some(([outer]) => pointInRing(lon, lat, outer));
}

// Sample points align with integer (col, row) grid indices — this is the
// coordinate convention d3-contour expects, so contour polygons can be
// mapped back to lon/lat with the same formula (see FireRiskMap.jsx).
function cellCenter(bbox, cols, rows, row, col) {
  const lat = bbox.south + (row / (rows - 1)) * (bbox.north - bbox.south);
  const lon = bbox.west + (col / (cols - 1)) * (bbox.east - bbox.west);
  return { lat: Number(lat.toFixed(4)), lon: Number(lon.toFixed(4)) };
}

// Only land cells get fetched/scored; everything else stays 0 so isobands
// naturally stop at the coastline/border instead of covering the ocean.
export const LAND_CELLS = (() => {
  const cells = [];
  for (let row = 0; row < GRID_ROWS; row++) {
    for (let col = 0; col < GRID_COLS; col++) {
      const { lat, lon } = cellCenter(BBOX, GRID_COLS, GRID_ROWS, row, col);
      if (pointInCalifornia(lon, lat)) cells.push({ row, col, lat, lon });
    }
  }
  return cells;
})();

export async function fetchGridWeather(cells = LAND_CELLS) {
  const lats = cells.map((p) => p.lat).join(',');
  const lons = cells.map((p) => p.lon).join(',');
  const url =
    `https://api.open-meteo.com/v1/forecast?latitude=${lats}&longitude=${lons}` +
    `&daily=${DAILY_FIELDS}&forecast_days=1&timezone=UTC`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Open-Meteo request failed: ${res.status}`);
  const data = await res.json();
  const list = Array.isArray(data) ? data : [data];
  return list.map((entry, i) => ({
    row: cells[i].row,
    col: cells[i].col,
    lat: cells[i].lat,
    lon: cells[i].lon,
    weather: {
      temp_max: entry.daily.temperature_2m_max[0],
      temp_min: entry.daily.temperature_2m_min[0],
      wind_max: entry.daily.windspeed_10m_max[0],
      precip_sum: entry.daily.precipitation_sum[0],
      humidity_mean: entry.daily.relative_humidity_2m_mean?.[0] ?? 45,
    },
  }));
}

export async function fetchActiveFireDetections() {
  const res = await fetch('/api/firms');
  if (!res.ok) throw new Error(`FIRMS proxy request failed: ${res.status}`);
  const text = await res.text();
  const lines = text.trim().split('\n');
  if (lines.length < 2) return [];
  const header = lines[0].split(',');
  const idxLat = header.indexOf('latitude');
  const idxLon = header.indexOf('longitude');
  const idxFrp = header.indexOf('frp');
  const idxDate = header.indexOf('acq_date');
  const idxTime = header.indexOf('acq_time');
  const idxConf = header.indexOf('confidence');
  return lines.slice(1).map((line) => {
    const parts = line.split(',');
    return {
      lat: Number(parts[idxLat]),
      lon: Number(parts[idxLon]),
      frp: Number(parts[idxFrp]),
      date: parts[idxDate],
      time: parts[idxTime],
      confidence: parts[idxConf],
    };
  });
}
