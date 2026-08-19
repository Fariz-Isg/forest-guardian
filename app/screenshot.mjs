import { chromium } from 'playwright';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const logs = [];
page.on('console', (msg) => logs.push(`[console.${msg.type()}] ${msg.text()}`));
page.on('pageerror', (err) => logs.push(`[pageerror] ${err.message}`));
page.on('requestfailed', (req) => logs.push(`[requestfailed] ${req.url()} ${req.failure()?.errorText}`));
page.on('response', (res) => { if (!res.ok()) logs.push(`[http ${res.status()}] ${res.url()}`); });

await page.goto(process.argv[3] || 'http://localhost:5183/', { waitUntil: 'networkidle' });
await page.waitForTimeout(10000);
await page.screenshot({ path: process.argv[2] || '/tmp/fg-screenshot.png' });

console.log('--- console/page logs ---');
console.log(logs.join('\n') || '(none)');

await browser.close();
