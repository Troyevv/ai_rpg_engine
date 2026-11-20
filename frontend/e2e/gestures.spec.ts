import {
  test,
  expect,
  type Page,
  type APIRequestContext,
} from '@playwright/test';
import { contact, swipe } from './touch';
import { nav } from './navigation';

async function narrative(
  page: Page,
  request: APIRequestContext,
  fixture = 'phone-seed'
) {
  const selection = await (await request.post('/test/' + fixture)).json();
  await page.addInitScript(
    (s) => localStorage.setItem('selection', JSON.stringify(s)),
    selection
  );
  await page.goto('/');
  await expect(page.locator('.composer')).toBeVisible();
  return selection;
}
test.beforeEach(({}, info) =>
  test.skip(info.project.name !== 'mobile', 'Touch input in mobile Chromium')
);
test('drag the real drawer, cancel, navigate and retain Narrative draft without mutations', async ({
  page,
  request,
}) => {
  await narrative(page, request);
  const writes: string[] = [];
  page.on('request', (req) => {
    if (
      req.url().includes('/api/') &&
      req.method() !== 'GET' &&
      new URL(req.url()).pathname !== '/api/markdown'
    )
      writes.push(req.url());
  });
  const input = page.getByLabel('Своё действие или реплика');
  await input.fill('Черновик на месте.');
  await input.blur();
  const trigger = page.getByRole('button', { name: 'Меню игры', exact: true });
  const menu = page.locator('.mobile-game-menu');
  await swipe(page, trigger, -85, 1, { cancel: true });
  await expect(menu).toHaveCount(0);
  await swipe(page, trigger, -120, 2);
  await expect(menu).toBeVisible();
  await swipe(page, menu.locator('.mobile-menu-brand'), 115, 2);
  await expect(menu).toHaveCount(0);
  await nav(page, 'Мир');
  const crumb = page.locator('.inspector-breadcrumb');
  await swipe(page, crumb, -80, 3);
  await expect(page.locator('.inspector-workspace')).toHaveAttribute(
    'aria-label',
    'Сцена'
  );
  await swipe(page, crumb, 82, 1);
  await expect(page.locator('.inspector-workspace')).toHaveAttribute(
    'aria-label',
    'Мир'
  );
  await page.goBack();
  await expect(input).toHaveValue('Черновик на месте.');
  expect(writes).toEqual([]);
});
test('calendar swipes change one visible period and leave the save untouched on wide touch screens', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 940, height: 510 });
  const s = await narrative(page, request);
  await nav(page, 'Календарь');
  const period = page.locator('.calendar-period h3');
  const initial = await period.innerText();
  const before = await (await request.get('/api/saves/' + s.save)).json();
  await swipe(page, period, -110, 3);
  await expect(period).not.toHaveText(initial);
  const next = await period.innerText();
  await swipe(page, period, 90, 1, { cancel: true });
  await expect(period).toHaveText(next);
  await swipe(page, period, 90, 2);
  await expect(period).toHaveText(initial);
  const after = await (await request.get('/api/saves/' + s.save)).json();
  expect(after.revision).toBe(before.revision);
  expect(after.state.world_clock).toEqual(before.state.world_clock);
});
test('library row actions, deliberate refresh and live control preferences', async ({
  page,
  request,
}) => {
  await narrative(page, request);
  await page.locator('.breadcrumb').click();
  const library = page.locator('.library-dialog'),
    card = library.locator('.world-card-wrap').first();
  await swipe(page, card, -88, 1);
  const actions = page.getByRole('group', { name: 'Действия строки' });
  await expect(actions).toBeVisible();
  await expect(actions.getByRole('button', { name: /Удалить/ })).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(1);
  await page.goBack();
  await expect(actions).toHaveCount(0);
  await expect(library).toBeVisible();
  await swipe(page, card, 0, 0, { hold: 650 });
  await expect(actions).toBeVisible();
  await actions.getByLabel('Свернуть действия').click();
  const response = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname === '/api/worlds' &&
      r.request().method() === 'GET'
  );
  await swipe(page, library.locator('.gesture-refresh'), 0, 95);
  await response;
  await library.locator('.dialog-close').click();
  await nav(page, 'Настройки');
  const settings = page.locator('.gesture-settings');
  await settings.locator(':scope > summary').click();
  await settings.getByLabel('Подсказки по управлению').uncheck();
  await settings.getByLabel('Управление жестами').uncheck();
  await settings.getByText('Управление и жесты', { exact: true }).click();
  await expect(
    settings.getByRole('button', { name: 'Повторить обучение' })
  ).toBeVisible();
  await page.reload();
  await page.locator('.breadcrumb').click();
  await swipe(page, card, -100, 0);
  await expect(actions).toHaveCount(0);
  await expect(page.locator('.gesture-tip')).toHaveCount(0);
  await library.locator('.dialog-close').click();
  await nav(page, 'Настройки');
  await settings.locator(':scope > summary').click();
  await expect(settings.getByLabel('Управление жестами')).not.toBeChecked();
  await settings
    .getByRole('button', { name: 'Сбросить настройки управления' })
    .click();
  await expect(settings.getByLabel('Управление жестами')).toBeChecked();
  await settings.getByText('Управление и жесты', { exact: true }).click();
  await settings.getByRole('button', { name: 'Повторить обучение' }).click();
  expect(
    await page.evaluate(() =>
      JSON.parse(localStorage.getItem('interface.gesture-learning.v1')!)
    )
  ).toEqual([]);
});
test('phone members, thread, list and contact return one level; second finger cancels navigation', async ({
  page,
  request,
}) => {
  await narrative(page, request, 'group152-seed');
  await swipe(page, page.getByRole('button', { name: /^Телефон/ }), 0, -90);
  const phone = page.locator('.phone-screen'),
    header = phone.locator('.phone-heading');
  await phone.getByRole('button', { name: 'Переписки', exact: true }).click();
  await phone.locator('.phone-thread').first().click();
  await phone.getByLabel('Управление участниками').click();
  await swipe(page, header, 100, 0);
  await expect(phone.locator('.phone-messages')).toBeVisible();
  await swipe(page, header, 100, 0);
  await expect(phone.locator('.phone-conversations')).toBeVisible();
  const tabs = phone.locator('.phone-bottom'),
    r = (await tabs.boundingBox())!;
  const c = await page.context().newCDPSession(page);
  const p = { x: r.x + r.width / 2, y: r.y + r.height / 2, id: 1 };
  await contact(c, 'touchStart', p);
  await contact(c, 'touchStart', p, { x: p.x + 40, y: p.y, id: 2 });
  await contact(c, 'touchEnd');
  await c.detach();
  await expect(
    phone.getByRole('button', { name: 'Переписки', exact: true })
  ).toHaveAttribute('aria-pressed', 'true');
  await swipe(page, tabs, -100, 0);
  await expect(
    phone.getByRole('button', { name: 'Контакты', exact: true })
  ).toHaveAttribute('aria-pressed', 'true');
  await phone.locator('.phone-contact-name').first().click();
  await swipe(page, header, 104, 0);
  await expect(phone.locator('.phone-directory')).toBeVisible();
  await swipe(page, header, 104, 0);
  await expect(page.locator('.phone-device')).not.toHaveClass(/is-open/);
});

test('a held portrait, two-finger zoom, pan and double tap stay within the viewer', async ({
  page,
  request,
}) => {
  await narrative(page, request, 'appearance-seed');
  await nav(page, 'Персонажи');
  const portrait = page
    .locator('.character-profile .portrait-control button.character-avatar')
    .first();
  await portrait.click();
  const pane = page.getByLabel('Оригинал портрета', { exact: true }),
    zoom = page.getByLabel('Масштаб просмотра', { exact: true });
  const rect = (await pane.boundingBox())!,
    x = rect.x + rect.width * 0.5,
    y = rect.y + rect.height * 0.5;
  const c = await page.context().newCDPSession(page);
  const pair = (d: number) => [
    { x: x - d, y, id: 1 },
    { x: x + d, y, id: 2 },
  ];
  await contact(c, 'touchStart', ...pair(24));
  for (const d of [30, 40, 54]) await contact(c, 'touchMove', ...pair(d));
  await contact(c, 'touchEnd');
  await expect
    .poll(async () => Number(await zoom.inputValue()))
    .toBeGreaterThan(2);
  const start = await pane.evaluate((el) => el.scrollTop);
  await swipe(page, pane, 0, -72);
  await expect
    .poll(() => pane.evaluate((el) => el.scrollTop))
    .toBeGreaterThan(start);
  await page.getByRole('button', { name: 'Сбросить масштаб' }).click();
  await page.touchscreen.tap(x, y);
  await page.touchscreen.tap(x, y);
  await expect
    .poll(async () => Number(await zoom.inputValue()))
    .toBeGreaterThan(1);
  await expect(page.locator('.portrait-dialog')).toBeVisible();
  await contact(c, 'touchStart', ...pair(20));
  await contact(c, 'touchCancel');
  await c.detach();
  await page.goBack();
  await expect(pane).toHaveCount(0);
  await expect(page.locator('.inspector-workspace')).toHaveAttribute(
    'aria-label',
    'Персонажи'
  );
});

test('a single anchored tip respects dismissal, input, restart and disabled hints', async ({
  page,
}) => {
  await page.goto('/');
  const tip = page.locator('.gesture-tip');
  await expect(tip).toBeVisible();
  await expect(tip).toHaveCount(1);
  await tip.getByLabel('Закрыть подсказку').click();
  const ids = await page.evaluate(() =>
    JSON.parse(localStorage.getItem('interface.gesture-learning.v1')!)
  );
  expect(ids.length).toBe(1);
  await page.reload();
  await nav(page, 'Настройки');
  const prefs = page.locator('.gesture-settings');
  await prefs.locator(':scope>summary').click();
  await prefs.getByLabel('Подсказки по управлению').uncheck();
  await expect(tip).toHaveCount(0);
  await prefs.getByText('Управление и жесты', { exact: true }).click();
  await prefs.getByRole('button', { name: 'Повторить обучение' }).click();
  await prefs.getByLabel('Подсказки по управлению').check();
  await page.getByLabel('API-ключ DeepSeek', { exact: true }).focus();
  await page.waitForTimeout(2100);
  await expect(tip).toHaveCount(0);
  await page.goBack();
  await expect(page.locator('.settings-dialog')).toHaveCount(0);
  await expect(tip).toHaveCount(1, { timeout: 12000 });
});

test('original tab and input own taps, selection, diagonals, orientation cancellation and native scrolling', async ({
  page,
  request,
}) => {
  await narrative(page, request);
  await nav(page, 'Персонажи');
  const tabs = page.locator('.dossier-tabs'),
    first = tabs.getByRole('tab').first();
  await first.scrollIntoViewIfNeeded();
  await swipe(page, first, -5, 0);
  await expect(first).toHaveAttribute('aria-selected', 'true');
  await swipe(page, tabs, -80, 85);
  await expect(first).toHaveAttribute('aria-selected', 'true');
  const c = await page.context().newCDPSession(page),
    r = (await tabs.boundingBox())!;
  await contact(c, 'touchStart', { x: r.x + 120, y: r.y + 15 });
  await contact(c, 'touchMove', { x: r.x + 90, y: r.y + 16 });
  await page.setViewportSize({ width: 780, height: 400 });
  await contact(c, 'touchEnd');
  await c.detach();
  await expect(first).toHaveAttribute('aria-selected', 'true');
  const text = page.locator('.dossier-name h2');
  await text.evaluate((el) => {
    const range = document.createRange();
    range.selectNodeContents(el);
    window.getSelection()!.addRange(range);
  });
  await expect
    .poll(() => page.evaluate(() => window.getSelection()?.toString()))
    .not.toBe('');
  await page.evaluate(() => window.getSelection()?.removeAllRanges());
  await page.setViewportSize({ width: 390, height: 780 });
  await swipe(page, first, -65, 0, { from: 0.9 });
  await expect(tabs.getByRole('tab').nth(1)).toHaveAttribute(
    'aria-selected',
    'true'
  );
  await page.goBack();
  const draft = page.getByLabel('Своё действие или реплика');
  await draft.fill('Собственный ввод');
  await swipe(page, draft, -80, 2);
  await expect(draft).toHaveValue('Собственный ввод');
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('pulling a world row refreshes once; swiping it never executes its delete action', async ({
  page,
  request,
}) => {
  await narrative(page, request);
  await page.locator('.breadcrumb').click();
  const card = page.locator('.world-card-wrap').first();
  await expect(card).toBeVisible();
  const reads: string[] = [],
    deletes: string[] = [];
  page.on('request', (r) => {
    if (new URL(r.url()).pathname === '/api/worlds') reads.push(r.method());
    if (r.method() === 'DELETE') deletes.push(r.url());
  });
  await swipe(page, card, 0, 85);
  await expect.poll(() => reads.length).toBe(1);
  await swipe(page, card, -95, 2);
  await expect(
    page.getByRole('group', { name: 'Действия строки' })
  ).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(1);
  expect(deletes).toEqual([]);
});

test('long workshop records can be dragged, cancelled and reordered without saving the world', async ({
  page,
  request,
}) => {
  const { readFileSync } = await import('node:fs');
  const { workshopNav, authorView } = await import('./workshop-navigation');
  const state = JSON.parse(
    readFileSync(
      new URL(
        '../../tests/fixtures/initial_world/workshop188.json',
        import.meta.url
      ),
      'utf8'
    )
  );
  const goals = state.world.characters.ilya.goals;
  goals.push({
    ...goals[0],
    id: 'qa_drag_goal',
    text: 'Вторая цель для проверки',
  });
  const w = await (
    await request.post('/api/workspaces', {
      data: { name: 'Жесты в мастерской' },
    })
  ).json();
  const path = '/api/workspaces/' + w.id + '/draft';
  expect(
    (
      await request.post(path + '/import', {
        data: { revision: 0, format: 'json', text: JSON.stringify(state) },
      })
    ).ok()
  ).toBeTruthy();
  await page.addInitScript(
    (id) => localStorage.setItem('draftWorkspace', id),
    w.id
  );
  await page.goto('/');
  await nav(page, 'Создать');
  await authorView(page);
  await workshopNav(page, 'Персонажи');
  await page
    .getByRole('button', { name: 'Досье Илья Соколов', exact: true })
    .click();
  const dossier = page.locator('.ww-dossier-dialog');
  await dossier.getByRole('tab', { name: 'Цели', exact: true }).click();
  await dossier
    .locator('.draft-field')
    .filter({ hasText: 'Вторая цель для проверки' })
    .getByRole('button', { name: /Изменить/ })
    .click();
  const editor = page.locator('.ww-field-dialog'),
    rows = editor
      .locator('.ww-structured-row')
      .filter({ has: page.locator(':scope > .gesture-sort-grip') });
  const grip = rows.first().locator(':scope > .gesture-sort-grip');
  await editor.locator('.dialog-title').tap();
  await swipe(page, grip, 0, 80, { cancel: true });
  await expect(
    editor.locator('[data-insert-before],[data-insert-after]')
  ).toHaveCount(0);
  await grip.scrollIntoViewIfNeeded();
  const c = await page.context().newCDPSession(page);
  try {
    const b = (await grip.boundingBox())!,
      x = b.x + b.width / 2,
      y = b.y + b.height / 2;
    const edge = await grip.evaluate((el) => {
      for (let p = el.parentElement; p; p = p.parentElement)
        if (
          p.scrollHeight > p.clientHeight &&
          /auto|scroll/.test(getComputedStyle(p).overflowY)
        )
          return Math.min(innerHeight, p.getBoundingClientRect().bottom) - 8;
      return innerHeight - 8;
    });
    await contact(c, 'touchStart', { x, y });
    for (let i = 1; i <= 8; i++)
      await contact(c, 'touchMove', { x, y: y + ((edge - y) * i) / 8 });
    await expect(editor.locator('[data-insert-after]').first()).toBeVisible({
      timeout: 9000,
    });
    await contact(c, 'touchEnd');
  } finally {
    await c.detach();
  }
  await expect(rows.first().locator('input').first()).toHaveValue(
    'qa_drag_goal'
  );
  await rows.first().getByRole('button', { name: 'Ниже', exact: true }).click();
  await expect(rows.first().locator('input').first()).toHaveValue(goals[0].id);
  const persisted = await (await request.get(path + '?author=true')).json();
  expect(persisted.state.world.characters.ilya.goals).toEqual(goals);
});
