import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import { contours } from 'd3-contour';
import 'maplibre-gl/dist/maplibre-gl.css';
import { fetchGridWeather, fetchActiveFireDetections, BBOX, GRID_COLS, GRID_ROWS, LAND_CELLS } from '../lib/api';
import { predictRisk } from '../lib/fireRiskModel';
import californiaBoundary from '../data/californiaBoundary.json';
import './FireRiskMap.css';

const CENTER = [(BBOX.west + BBOX.east) / 2, (BBOX.south + BBOX.north) / 2];

// Only zones with real risk are drawn at all — nothing below this is shown.
const THRESHOLDS = [
  { value: 0.5, color: '#f0a34a', label: 'Elevated (50–65%)' },
  { value: 0.65, color: '#e8622c', label: 'High (65–80%)' },
  { value: 0.8, color: '#a8481f', label: 'Extreme (80%+)' },
];

function gridToLngLat([x, y]) {
  return [
    BBOX.west + (x / (GRID_COLS - 1)) * (BBOX.east - BBOX.west),
    BBOX.south + (y / (GRID_ROWS - 1)) * (BBOX.north - BBOX.south),
  ];
}

// Shoelace formula, in grid-index space (units of one grid cell).
function ringArea(ring) {
  let sum = 0;
  for (let i = 0; i < ring.length - 1; i++) {
    const [x1, y1] = ring[i];
    const [x2, y2] = ring[i + 1];
    sum += x1 * y2 - x2 * y1;
  }
  return Math.abs(sum) / 2;
}

// On a coarse grid, marching squares occasionally emits degenerate sliver
// rings (near-zero area, sometimes self-intersecting) — drop them rather
// than let them render as stray lines/holes.
const MIN_RING_AREA = 0.5;

function remapRings(geometry) {
  return geometry
    .map((polygon) => polygon.filter((ring) => ringArea(ring) >= MIN_RING_AREA))
    .filter((polygon) => polygon.length > 0)
    .map((polygon) => polygon.map((ring) => ring.map(gridToLngLat)));
}

function riskGridToZones(values) {
  const gen = contours().size([GRID_COLS, GRID_ROWS]).thresholds(THRESHOLDS.map((t) => t.value));
  const bands = gen(values);
  return {
    type: 'FeatureCollection',
    features: bands.map((band, i) => ({
      type: 'Feature',
      properties: { threshold: THRESHOLDS[i].value, color: THRESHOLDS[i].color },
      geometry: { type: 'MultiPolygon', coordinates: remapRings(band.coordinates) },
    })),
  };
}

function detectionsToGeoJSON(detections) {
  return {
    type: 'FeatureCollection',
    features: detections.map((d) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [d.lon, d.lat] },
      properties: { frp: d.frp, date: d.date, time: d.time, confidence: d.confidence },
    })),
  };
}

export default function FireRiskMap() {
  const mapContainer = useRef(null);
  const mapRef = useRef(null);
  const [status, setStatus] = useState('Loading live conditions…');
  const [detectionCount, setDetectionCount] = useState(null);
  const [updatedAt, setUpdatedAt] = useState(null);

  useEffect(() => {
    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: 'https://tiles.openfreemap.org/styles/positron',
      center: CENTER,
      zoom: 5.4,
      attributionControl: { compact: true },
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');

    map.on('load', async () => {
      map.addSource('ca-boundary', { type: 'geojson', data: californiaBoundary });
      map.addLayer({
        id: 'ca-boundary-line',
        type: 'line',
        source: 'ca-boundary',
        paint: { 'line-color': '#a8481f', 'line-width': 1.5, 'line-opacity': 0.35 },
      });

      map.addSource('fire-risk-zones', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      map.addLayer({
        id: 'fire-risk-fill',
        type: 'fill',
        source: 'fire-risk-zones',
        paint: {
          'fill-color': ['get', 'color'],
          'fill-opacity': 0.55,
        },
      });
      map.addLayer({
        id: 'fire-risk-outline',
        type: 'line',
        source: 'fire-risk-zones',
        paint: { 'line-color': ['get', 'color'], 'line-width': 1, 'line-opacity': 0.8 },
      });

      map.addSource('fire-detections', { type: 'geojson', data: detectionsToGeoJSON([]) });
      map.addLayer({
        id: 'fire-detections-glow',
        type: 'circle',
        source: 'fire-detections',
        paint: {
          'circle-radius': 9,
          'circle-color': '#e8622c',
          'circle-opacity': 0.25,
          'circle-blur': 0.8,
        },
      });
      map.addLayer({
        id: 'fire-detections-point',
        type: 'circle',
        source: 'fire-detections',
        paint: {
          'circle-radius': 4,
          'circle-color': '#a8481f',
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 1.5,
        },
      });

      map.on('click', 'fire-detections-point', (e) => {
        const p = e.features[0].properties;
        new maplibregl.Popup({ closeButton: false })
          .setLngLat(e.lngLat)
          .setHTML(
            `<div class="fg-popup"><strong>Active detection</strong><br/>${p.date} ${p.time} UTC<br/>FRP ${Number(p.frp).toFixed(1)} MW · confidence ${p.confidence}</div>`
          )
          .addTo(map);
      });
      map.on('mouseenter', 'fire-detections-point', () => (map.getCanvas().style.cursor = 'pointer'));
      map.on('mouseleave', 'fire-detections-point', () => (map.getCanvas().style.cursor = ''));

      async function refresh() {
        try {
          const [gridWeather, detections] = await Promise.all([
            fetchGridWeather(),
            fetchActiveFireDetections().catch(() => []),
          ]);
          const riskByCell = new Map(gridWeather.map((g) => [`${g.row},${g.col}`, predictRisk(g.weather)]));
          const values = new Float64Array(GRID_COLS * GRID_ROWS);
          for (const { row, col } of LAND_CELLS) {
            values[row * GRID_COLS + col] = riskByCell.get(`${row},${col}`) ?? 0;
          }
          map.getSource('fire-risk-zones').setData(riskGridToZones(values));
          map.getSource('fire-detections').setData(detectionsToGeoJSON(detections));
          setDetectionCount(detections.length);
          setUpdatedAt(new Date());
          setStatus('ok');
        } catch (err) {
          setStatus(`error: ${err.message}`);
        }
      }

      refresh();
      const interval = setInterval(refresh, 15 * 60 * 1000);
      map._fgInterval = interval;
    });

    return () => {
      clearInterval(map._fgInterval);
      map.remove();
    };
  }, []);

  return (
    <div className="fg-map-wrap">
      <div ref={mapContainer} className="fg-map" />
      <Legend />
      <StatusBar status={status} detectionCount={detectionCount} updatedAt={updatedAt} />
    </div>
  );
}

function Legend() {
  return (
    <div className="fg-card fg-legend">
      <div className="fg-legend-title">Predicted fire risk (50%+ only)</div>
      <div className="fg-legend-row">
        {THRESHOLDS.map((t) => (
          <div key={t.label} className="fg-legend-item">
            <span className="fg-swatch" style={{ background: t.color }} />
            {t.label}
          </div>
        ))}
      </div>
      <div className="fg-legend-divider" />
      <div className="fg-legend-item">
        <span className="fg-swatch fg-swatch--dot" />
        Active satellite detection
      </div>
    </div>
  );
}

function StatusBar({ status, detectionCount, updatedAt }) {
  return (
    <div className="fg-card fg-status">
      {status === 'ok' ? (
        <>
          <strong>{detectionCount}</strong> active detections in view
          {updatedAt && <span className="fg-status-time"> · updated {updatedAt.toLocaleTimeString()}</span>}
        </>
      ) : status.startsWith('error') ? (
        <span className="fg-status-error">Live data unavailable — {status.replace('error: ', '')}</span>
      ) : (
        status
      )}
    </div>
  );
}
