import { expect, test } from '@playwright/test';
import { readdirSync, readFileSync } from 'node:fs';

test('previous mode preference opens the Narrative shell on first load and reload', async ({page}) => {
  await page.goto('/offline.html');
  await page.evaluate(() => {
    localStorage.setItem('game-mode', 'tabletop');
    localStorage.setItem('tabletop-game', 'old-campaign');
  });
  await page.goto('/');
  for (let visit = 0; visit < 2; visit++) {
    if (visit) await page.reload();
    await expect(page.locator('.narrative-shell')).toBeVisible();
    await expect(page.getByRole('button', {name:'Твои истории', exact:false})).toBeVisible();
    await expect(page.getByRole('button', {name:/Tabletop|Настольная RPG/, includeHidden:true})).toHaveCount(0);
  }
});

test('production JS and CSS exclude retired client and API', () => {
  const assets = new URL('../dist/assets/', import.meta.url);
  const bundles = readdirSync(assets).filter(name => /\.(js|css)$/.test(name));
  expect(bundles.length).toBeGreaterThan(0);
  for (const name of bundles) {
    expect(readFileSync(new URL(name, assets), 'utf8'), name)
      .not.toMatch(/\/api\/tabletop|\.tt-shell\b|Настольная RPG|d20-fantasy-v2/i);
  }
});
