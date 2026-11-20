import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { nav } from './navigation';
import { authorView, workshopNav } from './workshop-navigation';
import { chooseOption } from './choice-navigation';

test('illustrated studio and selective local style conversion', async ({ page, request }, info) => {
  test.setTimeout(150000);
  const mobile = info.project.name === 'mobile';
  await page.setViewportSize({ width: mobile ? 360 : 1280, height: mobile ? 720 : 850 });
  const state = JSON.parse(
    readFileSync(
      new URL('../../tests/fixtures/initial_world/runtime_presentation.json', import.meta.url),
      'utf8',
    ),
  );
  state.creation_settings = { portrait_style: 'anime' };
  const base = state.characters[0],
    original = state.world.characters[base.id];
  for (let i = 0; i < 72; i++) {
    const card = state.characters[i] || {
      ...structuredClone(base),
      id: 'cast_' + i,
      name: 'Житель ' + i,
    };
    state.characters[i] = card;
    state.world.characters[card.id] = {
      ...(state.world.characters[card.id] || original),
      id: card.id,
      developmental_stage: 'adult',
    };
    card.portrait_traits = { form: 'human', clothing: 'blazer', hair: 'wolf' };
  }
  const w = await (
    await request.post('/api/workspaces', { data: { name: 'Альбом иллюстраций' } })
  ).json();
  const url = '/api/workspaces/' + w.id + '/draft';
  const imported = await request.post(url + '/import', {
    data: { revision: 0, format: 'json', text: JSON.stringify(state) },
  });
  expect(imported.ok(), await imported.text()).toBeTruthy();
  await page.addInitScript((id) => localStorage.setItem('draftWorkspace', id), w.id);
  await page.goto('/');
  await nav(page, 'Создать');
  await authorView(page);
  await workshopNav(page, 'Персонажи');
  const button = (name: string) => page.getByRole('button', { name, exact: true });
  const stored = async () =>
    await (await request.get(url + '/characters/' + base.id + '/portraits?author=true')).json();
  const before = (await stored()).descriptor;
  const card = button('Досье ' + base.name);
  await card.screenshot({ path: info.outputPath('card.jpg'), scale: 'css' });
  await card.click();
  const open = async () => {
    await button('Редактировать портрет').click();
    await button('Настроить иллюстрацию').click();
  };
  let dispatches = 0;
  page.on('request', (r) => {
    if (/portrait-proposals.*\/generate$/.test(r.url())) dispatches++;
  });
  await open();
  await button('Полуреалистичное аниме').click();
  await button('Одежда').click();
  await page.getByRole('searchbox', { name: 'Поиск вариантов' }).fill('Техноплащ');
  await button('Техноплащ').click();
  await button('Цвета').click();
  await button('Отделка').click();
  await button('Графит').click();
  if (mobile) {
    await page.screenshot({ path: info.outputPath('studio-360.jpg'), scale: 'css' });
    await page.setViewportSize({ width: 393, height: 500 });
    await chooseOption(page.getByRole('combobox', { name: 'Раздел настройки' }), 'clothes');
    await expect(button('Техноплащ')).toHaveCount(0);
    await page.getByRole('searchbox', { name: 'Поиск вариантов' }).fill('Техноплащ');
    await expect(button('Техноплащ')).toHaveAttribute('aria-pressed', 'true');
  }
  const save = button('Сохранить иллюстрацию'),
    bounds = await save.boundingBox();
  expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(page.viewportSize()!.height);
  expect(
    await page.locator('.studio-open').evaluate((e) => e.scrollWidth <= e.clientWidth + 1),
  ).toBeTruthy();
  await page.screenshot({ path: info.outputPath('studio.jpg'), scale: 'css' });
  await page.route(
    '**/portraits/procedural',
    (r) => r.fulfill({ status: 409, json: { detail: 'Конфликт ревизии' } }),
    { times: 1 },
  );
  await save.click();
  await expect(page.getByRole('alert')).toContainText('Конфликт');
  await button('Сбросить несохранённые изменения').click();
  await expect(save).toBeDisabled();
  await button('Отмена').click();
  await button('Настроить иллюстрацию').click();
  await button('Полуреалистичное аниме').click();
  await save.click();
  await expect(page.locator('.portrait-dialog')).toHaveCount(0);
  expect((await stored()).descriptor).toEqual({ ...before, art_style: 'semi_realistic' });
  await open();
  await expect(button('Полуреалистичное аниме')).toHaveAttribute('aria-pressed', 'true');
  await page.keyboard.press('Escape');
  await button('Готово').click();
  await button('Портреты').click();
  const dialog = page.locator('.portrait-commission'),
    scroll = dialog.locator('.commission-body');
  await expect(dialog.getByRole('checkbox')).toHaveCount(72);
  await scroll.evaluate((el) => (el.scrollTop = el.scrollHeight));
  await expect(dialog.getByText('Житель 71', { exact: true })).toBeInViewport();
  await chooseOption(page.getByRole('combobox', { name: 'Действие с портретами' }), 'style');
  const search = dialog.getByRole('textbox', { name: 'Поиск по имени или роли' });
  await search.fill(base.name);
  await dialog.getByRole('checkbox', { name: base.name, exact: true }).check();
  await search.fill('Житель 71');
  await dialog.getByRole('checkbox', { name: 'Житель 71', exact: true }).check();
  await button('Сравнить стиль').click();
  await expect(dialog.locator('.commission-result')).toHaveCount(2);
  await dialog.getByRole('checkbox', { name: 'Применить для ' + base.name, exact: true }).check();
  await button('Применить выбранные · 1').click();
  await expect(dialog).toHaveCount(0);
  expect((await stored()).descriptor).toEqual(before);
  expect(dispatches).toBe(0);
});
