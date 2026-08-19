// Minimal production server: serves the built static site (dist/) and proxies
// /api/firms so FIRMS_MAP_KEY never reaches the browser. Run `npm run build`
// first, then `node server.js`.
import { config } from 'dotenv';
import http from 'node:http';
import { createReadStream, existsSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createFirmsHandler } from './firms-proxy.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
config({ path: path.join(__dirname, '..', '.env') });
const distDir = path.join(__dirname, 'dist');
const port = process.env.PORT || 4173;
const firmsHandler = createFirmsHandler(process.env.FIRMS_MAP_KEY);

const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.json': 'application/json' };

const server = http.createServer((req, res) => {
  if (req.url.startsWith('/api/firms')) {
    firmsHandler(req, res);
    return;
  }
  let filePath = path.join(distDir, req.url === '/' ? 'index.html' : req.url);
  if (!existsSync(filePath) || statSync(filePath).isDirectory()) {
    filePath = path.join(distDir, 'index.html');
  }
  const ext = path.extname(filePath);
  res.setHeader('Content-Type', MIME[ext] || 'application/octet-stream');
  createReadStream(filePath).pipe(res);
});

server.listen(port, () => {
  console.log(`Forest Guardian serving on http://localhost:${port}`);
});
