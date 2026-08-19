# Forest Guardian — Map Screen

React + Vite + MapLibre GL. No login, English only, per spec.md.

## Run

```
npm install
npm run dev       # dev server on http://localhost:5173, proxies /api/firms
```

Production:

```
npm run build
npm start         # serves dist/ and proxies /api/firms, on http://localhost:4173
```

Both need `FIRMS_MAP_KEY` set in the `.env` file at the project root (one level up).

## How it works

- **Basemap:** OpenFreeMap "positron" style (free, no API key), tinted slightly warm via CSS filter.
- **Fire risk layer:** a heatmap over a grid of points inside Azerbaijan's actual land boundary
  (`src/data/azerbaijanBoundary.json`, pulled from OSM once — not fetched live). Each grid point's
  risk score comes from `src/lib/fireRiskModel.js`, which runs the trained logistic regression
  (`src/data/fireRiskModel.json`) against that point's live Open-Meteo forecast.
- **Active detections:** live NASA FIRMS VIIRS detections, fetched through the `/api/firms` proxy
  (see below) and rendered as markers with a click popup.
- **The proxy:** `firms-proxy.js` keeps `FIRMS_MAP_KEY` server-side only — the browser never sees it.
  `vite.config.js` wires it in as dev middleware; `server.js` is the same handler as a tiny standalone
  server for production, since a plain static host can't hide the key.

## Known limitations (MVP scope)

- The model is trained on **daily, country-level** fire-vs-no-fire labels (did any VIIRS detection
  happen anywhere in the bbox that day), not per-pixel forest fire labels — see `model/train_model.py`
  for the full method. Spatial variation on the map comes from evaluating that same model against
  each grid point's own forecast weather, not from spatially-resolved training data. Test AUC was 0.68
  on a ~15 month window (479 days, 399 of them fire-days) — a reasonable signal for an MVP, not a
  production-grade risk model.
- `dist/assets/index-*.js` is ~1.2MB (~325KB gzipped), almost entirely MapLibre GL — normal for any
  interactive map library, not something worth trading away for "lightweight" here.
