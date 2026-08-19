// Shared FIRMS proxy handler: keeps FIRMS_MAP_KEY server-side only. Used both
// as Vite dev-server middleware and by the small production server (server.js) —
// the frontend never sees the key, it just calls same-origin /api/firms.
const BBOX = '-124.48,32.53,-114.13,42.01';

export function createFirmsHandler(mapKey) {
  return async function firmsHandler(req, res) {
    if (!mapKey) {
      res.statusCode = 500;
      res.end('FIRMS_MAP_KEY is not configured on the server');
      return;
    }
    const url = `https://firms.modaps.eosdis.nasa.gov/api/area/csv/${mapKey}/VIIRS_SNPP_NRT/${BBOX}/1`;
    try {
      const upstream = await fetch(url);
      const text = await upstream.text();
      res.statusCode = upstream.status;
      res.setHeader('Content-Type', 'text/csv');
      res.setHeader('Cache-Control', 'public, max-age=900');
      res.end(text);
    } catch (err) {
      console.error('FIRMS proxy error:', err.message);
      res.statusCode = 502;
      res.end(`FIRMS upstream request failed: ${err.message}`);
    }
  };
}
