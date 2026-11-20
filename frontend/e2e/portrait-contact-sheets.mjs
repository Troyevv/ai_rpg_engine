// Run from a checkout with the normal backend and frontend dependencies installed.
// PYTHON=.venv/bin/python node frontend/e2e/portrait-contact-sheets.mjs --out /tmp/portrait-review
import { execFileSync } from 'node:child_process';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { chromium } from 'playwright';
import { build, preview } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

const frontend = fileURLToPath(new URL('../', import.meta.url));
const repo = path.dirname(path.resolve(frontend));
const { values } = parseArgs({ options: {
  out: { type: 'string' }, groups: { type: 'string' }, cases: { type: 'string' },
  // Only substitutes the v4 art function in the temporary review bundle.
  'illustration-renderer': { type: 'string' },
  'full-size': { type: 'boolean', default: false },
}});
if (!values.out) throw new Error('Provide an output directory with --out');
const groups = values.cases
  ? JSON.parse(await readFile(values.cases, 'utf8'))
  : JSON.parse(execFileSync(process.env.PYTHON || 'python', ['-m', 'devtools.issue269.visual_cases'], {
      cwd: repo, encoding: 'utf8', maxBuffer: 4 * 1024 * 1024,
    }));
const selected = values.groups ? values.groups.split(',') : Object.keys(groups);
for (const group of selected) {
  if (!/^[a-z][a-z0-9_-]*$/.test(group) || !Array.isArray(groups[group]) || !groups[group].length) {
    throw new Error(`Missing review cases for ${group}`);
  }
}
const destination = path.resolve(values.out);
await mkdir(destination, { recursive: true });
const temp = await mkdtemp(path.join(tmpdir(), 'portrait-contact-sheets-'));
let server, browser;
try {
  const renderer = values['illustration-renderer'];
  const reviewRenderer = renderer && {
    name: 'local-illustration-review',
    enforce: 'pre',
    resolveId(source, importer) {
      if (importer === path.join(frontend, 'src/workshop/proceduralPortrait.ts') &&
          source === './illustratedPortrait') return path.resolve(renderer);
    },
  };
  await build({
    root: frontend, configFile: false, logLevel: 'warn', define: { 'process.env.NODE_ENV': JSON.stringify('production') },
    plugins: [reviewRenderer, react(), tailwindcss()], resolve: { alias: { '@': path.join(frontend, 'src') } },
    build: { outDir: temp, emptyOutDir: true, lib: {
      entry: fileURLToPath(new URL('./portrait-review.mount.tsx', import.meta.url)),
      formats: ['es'], fileName: () => 'review.js', cssFileName: 'review',
    }},
  });
  await writeFile(path.join(temp, 'index.html'), `<!doctype html><html lang="ru">
    <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="./review.css"><title>Проверка портретов</title>
    <main class="world-workshop" id="review"></main><script type="module">
    import {render} from './review.js'; window.renderPortraitCases = render;
    </script></html>`);
  server = await preview({
    root: frontend, configFile: false, build: { outDir: temp }, preview: { host: '127.0.0.1', port: 0 },
  });
  const port = server.httpServer.address().port;
  browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH || undefined });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1 });
  page.on('pageerror', error => console.error(error.message));
  for (const group of selected) {
    for (const style of ['anime', 'semi_realistic']) {
      await page.goto(`http://127.0.0.1:${port}/`);
      await page.waitForFunction(() => typeof window.renderPortraitCases === 'function');
      await page.evaluate(([rows, style, full]) => window.renderPortraitCases(rows, style, full),
                          [groups[group], style, values['full-size']]);
      const file = `${group}-${style}.jpg`;
      await page.locator('#review').screenshot({ path: path.join(destination, file), quality: 90 });
      console.log(`${file} — ${groups[group].length}`);
    }
  }
  await writeFile(path.join(destination, 'cases.json'),
                  JSON.stringify(Object.fromEntries(selected.map(key => [key, groups[key]])), null, 2));
} finally {
  try { await browser?.close(); }
  finally {
    if (server) await new Promise(resolve => server.httpServer.close(resolve));
    await rm(temp, { recursive: true, force: true });
  }
}
