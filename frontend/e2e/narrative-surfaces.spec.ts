import { test, expect, type Page, type Locator, type APIRequestContext } from '@playwright/test';
import { inspectorSections } from '../src/lib/inspector';
import { nav } from './navigation';

async function pressAt(page: Page, target: Locator, touch: boolean) {
  const r = (await target.boundingBox())!;
  const x = r.x + r.width / 2,
    y = r.y + r.height / 2;
  if (touch) await page.touchscreen.tap(x, y);
  else await page.mouse.click(x, y);
}

async function outsideGesture(page: Page, menu: Locator, target: Locator, touch: boolean) {
  await target.evaluate((el) => {
    el.setAttribute('data-input-events', '');
    for (const type of ['pointerdown', 'touchstart', 'pointerup', 'touchend', 'click']) {
      el.addEventListener(type, () =>
        el.setAttribute('data-input-events', el.getAttribute('data-input-events') + ' ' + type),
      );
    }
  });
  await pressAt(page, menu, touch);
  await expect(menu).toHaveAttribute('aria-expanded', 'true');
  await pressAt(page, target, touch);
  await expect(menu).toHaveAttribute('aria-expanded', 'false');
  await expect(target).toHaveAttribute('data-input-events', '');
  await pressAt(page, target, touch);
  await expect(target).toHaveAttribute(
    'data-input-events',
    touch ? /pointerdown.*touchstart.*click/ : /pointerdown.*pointerup.*click/,
  );
}

async function openNarrative(page: Page, request: APIRequestContext, mobile: boolean, worldName?: string) {
  let seed = await (await request.post('/test/phone-seed?incoming=false')).json();
  if (worldName) {
    const source = await (await request.get('/api/worlds/' + seed.world)).json();
    const created = await request.post('/api/worlds', {
      data: { name: worldName, markdown: source.source_md },
    });
    expect(created.ok(), await created.text()).toBe(true);
    const world = (await created.json()).id;
    const save = await request.post('/api/worlds/' + world + '/saves', { data: { name: 'Границы панели' } });
    expect(save.ok(), await save.text()).toBe(true);
    seed = { world, save: (await save.json()).id };
  }
  const theme = mobile ? 'parchment' : 'graphite';
  expect(
    (await request.put('/api/worlds/' + seed.world + '/presentation', { data: { theme_id: theme } })).ok(),
  ).toBe(true);
  await page.addInitScript((s) => localStorage.setItem('selection', JSON.stringify(s)), seed);
  await page.goto('/');
}

test('outside input dismisses the actor list without activating the underlying button', async ({
  page,
  request,
}, info) => {
  await openNarrative(page, request, info.project.name === 'mobile');
  const management = page.locator('.current-game-entry button');
  await outsideGesture(
    page,
    page.locator('button[aria-label="Управляемый персонаж"]'),
    management,
    info.project.name === 'mobile',
  );
  await expect(
    page.getByRole('dialog').getByRole('heading', { name: 'Управление игрой', exact: true }),
  ).toBeVisible();
});

test('outside input dismisses the inspector character list before changing character', async ({
  page,
  request,
}, info) => {
  await openNarrative(page, request, info.project.name === 'mobile');
  await nav(page, 'Персонажи');
  const toolbar = page.locator('.inspector-character-toolbar');
  await outsideGesture(
    page,
    toolbar.locator('button[role=combobox]'),
    toolbar.locator('button').first(),
    info.project.name === 'mobile',
  );
});

async function checkPanel(header: Locator, safeTop: number) {
  await expect(header).toBeVisible();
  const covered = await header.evaluate((el, safeTop) => {
    const panel = el.getBoundingClientRect();
    const buttons = [...el.querySelectorAll<HTMLElement>('button, .inspector-breadcrumb strong')].filter(
      (b) => b.offsetWidth > 0,
    );
    return buttons
      .filter((b) => {
        const r = b.getBoundingClientRect();
        const x = (r.left + r.right) / 2;
        return (
          r.bottom > panel.bottom + 1 ||
          r.top < Math.max(panel.top, safeTop) - 1 ||
          r.right > innerWidth + 1 ||
          r.left < -1 ||
          !b.contains(document.elementFromPoint(x, r.bottom - 2)) ||
          !b.contains(document.elementFromPoint(x, r.top + 2))
        );
      })
      .map((b) => b.getAttribute('aria-label') || b.innerText);
  }, safeTop);
  expect(covered, 'Every header control must remain visible and receive input over its full height').toEqual(
    [],
  );
}

test('Narrative panels keep the active toolbar above their own scrolling content', async ({
  page,
  request,
}, info) => {
  const mobile = info.project.name === 'mobile';
  const safeTop = mobile ? 24 : 0;
  if (mobile) {
    await page.setViewportSize({ width: 320, height: 740 });
    const cdp = await page.context().newCDPSession(page);
    await cdp.send('Emulation.setSafeAreaInsetsOverride', { insets: { top: safeTop, left: 8, right: 8 } });
  }
  const title = 'Архив островных экспедиций и прибрежных обсерваторий '.repeat(2).trim();
  await openNarrative(page, request, mobile, title);
  await expect(page.locator('.topbar .breadcrumb')).toHaveAttribute('title', title);
  await checkPanel(page.locator('.topbar'), safeTop);
  for (const section of ['Календарь', 'Родословная']) {
    await nav(page, section);
    await expect(page.getByRole('dialog')).toHaveCount(0);
    const content = page.locator('.save-workspace');
    await expect(content).toHaveAccessibleName(section);
    await expect(content).toBeVisible();
    await checkPanel(page.locator('.topbar'), safeTop);
    const header = (await page.locator('.topbar').boundingBox())!;
    expect((await content.boundingBox())!.y).toBeGreaterThanOrEqual(header.y + header.height - 1);
    const scroll = await content.evaluate((el) => {
      const distance = Math.min(80, el.scrollHeight - el.clientHeight);
      el.scrollTop = distance;
      return { distance, top: el.scrollTop, page: window.scrollY };
    });
    expect(scroll.top).toBe(scroll.distance);
    expect(scroll.page).toBe(0);
    await checkPanel(page.locator('.topbar'), safeTop);
  }
  for (const { id } of inspectorSections) {
    await nav(page, id);
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page.locator('.inspector-breadcrumb strong')).toHaveText(id);
    await checkPanel(page.locator('.inspector-topbar'), safeTop);
  }
});
