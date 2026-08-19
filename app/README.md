# Forest Guardian — Canopy Map Screen

A single static page (`index.html`) implementing the approved "Canopy" design from
Claude Design (project: Portugal Risk Map Screen), wired to real data. No React —
the design is self-contained HTML/CSS/JS (Leaflet for the map, D3/topojson + Three.js
for the hero globe, all loaded from CDN via native `<script type="importmap">`).
`three` is also an npm dependency purely so Vite's dev resolver can serve it locally.

## Run

```
npm install
npm run dev       # dev server on http://localhost:5183ish, proxies /api/firms
```

Production:

```
npm run build
npm start         # serves dist/ and proxies /api/firms, on http://localhost:4173
```

Both need `FIRMS_MAP_KEY` set in the `.env` file at the project root (one level up).

## What's real vs. what's decorative

- **Risk zones** (organic shapes per named California region): real. `loadZoneWeather()`
  fetches each region's own past/forecast daily weather from Open-Meteo and runs it
  through the trained model (`public/data/fire_risk_model.json`, same logistic
  regression from `model/train_model.py`) client-side.
- **Fires burning now**: real. `loadFires()` reads live NASA FIRMS detections through
  the `/api/firms` proxy (which keeps `FIRMS_MAP_KEY` server-side), clusters nearby
  points into readable events, and fetches real wind direction for each.
- **Fire history section**: real. Precomputed by `model/build_history_summary.py`
  from the historical FIRMS archive into `public/data/fire_history.json` — spatial
  clusters of actual detections, not fabricated incident records. No hectares/
  containment status are shown because point detections alone don't give you that;
  the labels say "detections" and "active/no longer detected" instead.
  Regenerate it with: `python3 ../model/build_history_summary.py`
- **The 18 named regions** (Klamath, Shasta-Trinity, etc.) are a curated, fixed list
  of anchor points/names — not fetched from anywhere. Their *risk scores* are real;
  the *set of regions monitored* is a fixed editorial choice, same as the original
  design.
- **The 3D hero globe** (Three.js): decorative only. It's a generic spinning-earth
  visual, not tied to real fire data — left as designed.

## The proxy

`firms-proxy.js` keeps `FIRMS_MAP_KEY` server-side only — the browser never sees it.
`vite.config.js` wires it in as dev middleware; `server.js` is the same handler as a
tiny standalone server for production, since a plain static host can't hide the key.

## Known limitations (MVP scope)

- The model is trained on **spatially-binned, ~15 month** FIRMS + Open-Meteo data
  (grid cell × day → was a fire detected there, given that cell's own weather that
  day) — see `model/build_spatial_training_data.py` and `model/train_model.py`.
  Test AUC 0.66. This is a real, modest signal appropriate for an MVP, not a
  production-grade fire danger index — the earlier whole-region-daily-aggregate
  approach was tried first and discarded because it gave almost no negative
  examples to learn from (California has *some* detection almost every day).
- Confidence percentages for VIIRS detections are a rough mapping from FIRMS'
  categorical `l`/`n`/`h` confidence codes (35/70/92%), not a true probability.
