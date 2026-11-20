import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { nav, pickCharacter } from './navigation';
import { authorView, workshopNav } from './workshop-navigation';
import { themes } from '../src/lib/skins';
import { chooseOption } from './choice-navigation';

test('portrait collection with a long cast', async ({ page, request }, info) => {
  test.setTimeout(180000);
  const mobile = info.project.name === 'mobile';
  await page.setViewportSize({ width: mobile ? 360 : 1280, height: mobile ? 720 : 850 });
  const state = JSON.parse(
    readFileSync(
      new URL('../../tests/fixtures/initial_world/runtime_presentation.json', import.meta.url),
      'utf8',
    ),
  );
  const given = ['Анна', 'Борис', 'Вера', 'Денис', 'Елена', 'Михаил', 'Софья', 'Павел'];
  const surnames = ['Маркова', 'Левин', 'Миронова', 'Зорин', 'Волкова', 'Рощин', 'Карелина', 'Титов'];
  const hair = ['braid', 'short', 'pixie', 'buzz', 'bun', 'parted', 'curly', 'undercut'];
  const roles = [
    'Врач',
    'Архитектор',
    'Учитель',
    'Фотограф',
    'Музыкант',
    'Эколог',
    'Редактор',
    'Водитель',
  ];
  const base = state.characters[0],
    actor = state.world.characters[base.id];
  for (let i = 0; i < 72; i++) {
    const id = state.characters[i]?.id || 'cast_' + i;
    const card = state.characters[i] || structuredClone(base);
    card.id = id;
    card.name =
      given[i % 8] +
      ' ' +
      surnames[((i % 8) + Math.floor(i / 8) * 2) % 8] +
      (i >= 32 ? ' ' + (i + 1) : '');
    card.fields = {
      ...card.fields,
      Роль: roles[i % 8],
      Внешность: i === 2 ? 'QA_SKIP_PORTRAIT' : 'Открытое описание внешности',
    };
    card.portrait_traits = { hair: hair[i % 8], face: ['broad', 'oval', 'round', 'long'][i % 4] };
    state.characters[i] = card;
    state.world.characters[id] = {
      ...(state.world.characters[id] || actor),
      id,
      developmental_stage: 'adult',
    };
  }
  const w = await (await request.post('/api/workspaces', { data: { name: 'Истории у моря' } })).json(),
    url = '/api/workspaces/' + w.id + '/draft';
  const imported = await request.post(url + '/import', {
    data: { revision: 0, format: 'json', text: JSON.stringify(state) },
  });
  expect(imported.ok(), await imported.text()).toBeTruthy();
  await page.addInitScript((id) => localStorage.setItem('draftWorkspace', id), w.id);
  await page.goto('/');
  await nav(page, 'Создать');
  await authorView(page);
  await workshopNav(page, 'Персонажи');
  if (mobile) await page.getByRole('button', { name: 'Разделы мастерской', exact: true }).click();
  await page
    .locator(mobile ? '.ww-menu-dialog' : '.ww-sidebar')
    .getByRole('button', { name: 'Оформление', exact: true })
    .click();
  await chooseOption(
    page.getByRole('combobox', { name: 'Тема мира', exact: true }),
    mobile ? 'parchment' : 'graphite',
  );
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog', { name: 'Оформление мастерской' })).toHaveCount(0);
  if (mobile) {
    await page.keyboard.press('Escape');
    await expect(page.locator('.ww-menu-dialog')).toHaveCount(0);
  }
  const button = (name: string) => page.getByRole('button', { name, exact: true });
  await button('Портреты').scrollIntoViewIfNeeded();
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: info.outputPath('entry.jpg'), scale: 'css' });
  await button('Портреты').click();
  const dialog = page.getByRole('dialog', { name: 'Портретная мастерская' }),
    body = dialog.locator('.commission-body');
  const search = dialog.getByRole('textbox', { name: 'Поиск по имени или роли' }),
    primary = button('Рассчитать расход');
  const shot = async (name: string) => {
    await expect(dialog).toBeVisible();
    await page.screenshot({
      path: info.outputPath(name + '.jpg'),
      scale: 'css',
      animations: 'disabled',
    });
  };
  const checkLayout = async () => {
    expect(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    const box = await primary.boundingBox();
    expect(box).toBeTruthy();
    expect(box!.y + box!.height).toBeLessThanOrEqual(page.viewportSize()!.height);
  };
  await expect(dialog.getByRole('checkbox')).toHaveCount(72);
  await button('Выбрать до 64').click();
  await expect(dialog.locator('input:checked')).toHaveCount(64);
  await expect(dialog.locator('input:disabled')).toHaveCount(8);
  await button('Снять выбор').click();
  await search.fill('Врач');
  await expect(dialog.getByRole('checkbox')).toHaveCount(9);
  await button('Выбрать найденных').click();
  await search.fill('');
  await button('Показать выбранных').click();
  await expect(dialog.getByRole('checkbox')).toHaveCount(9);
  await button('Снять выбор').click();
  await button('Все').click();
  const check = (name: string) => dialog.getByRole('checkbox', { name, exact: true });
  for (const name of ['Анна Маркова', 'Борис Левин', 'Вера Миронова']) await check(name).first().check();
  await body.evaluate((el) => (el.scrollTop = 0));
  await checkLayout();
  await shot('selection');
  await body.evaluate((el) => (el.scrollTop = el.scrollHeight));
  expect(await body.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
  await checkLayout();
  if (mobile) {
    await page.setViewportSize({ width: 393, height: 500 });
    await body.evaluate((el) => (el.scrollTop = 0));
    await checkLayout();
    await shot('short');
    await page.setViewportSize({ width: 393, height: 780 });
  }
  await dialog.getByRole('button', { name: 'Закрыть', exact: true }).click();
  await button('Портреты').click();
  await button('Показать выбранных').click();
  await expect(dialog.getByRole('checkbox')).toHaveCount(3);
  await page.route(
    '**/portrait-proposals/workspace/' + w.id,
    (r) => r.fulfill({ status: 503, json: { detail: 'Расчёт временно недоступен' } }),
    { times: 1 },
  );
  await primary.click();
  await expect(dialog.getByRole('alert')).toHaveText('Расчёт временно недоступен');
  await expect(dialog.getByRole('checkbox', { checked: true })).toHaveCount(3);
  await primary.click();
  await expect(button('Подтвердить запрос')).toBeVisible();
  await shot('quote');
  await button('Изменить выбор').click();
  await primary.click();
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(
    '**/portrait-proposals/**/generate',
    async (route) => {
      await held;
      await route.continue();
    },
    { times: 1 },
  );
  await button('Подтвердить запрос').click();
  await expect(dialog.getByRole('status')).toContainText('Подбираем');
  await button('Остановить запрос').click();
  await expect(dialog.getByRole('heading', { name: 'Запрос остановлен' })).toBeVisible();
  release();
  await button('Новый запрос').click();
  await primary.click();
  await button('Подтвердить запрос').click();
  const rows = dialog.locator('.commission-result');
  await expect(rows).toHaveCount(2);
  await expect(dialog.locator('.commission-errors')).toContainText('Не удалось подготовить · 1');
  await rows.first().getByRole('checkbox').check();
  await shot('results');
  await dialog.getByRole('button', { name: 'Закрыть', exact: true }).click();
  await button('Портреты').click();
  await expect(button('Применить выбранные · 1')).toBeEnabled();
  await dialog.getByRole('button', { name: 'Закрыть', exact: true }).click();
  await page.route(
    '**/portrait-proposals/workspace/' + w.id + '/*',
    (r) => r.fulfill({ status: 503, json: { detail: 'Повторите загрузку' } }),
    { times: 1 },
  );
  await button('Портреты').click();
  await expect(primary).toHaveCount(0);
  await button('Восстановить запрос').click();
  await expect(button('Применить выбранные · 1')).toBeEnabled();
  await button('Применить выбранные · 1').click();
  await expect(dialog).toHaveCount(0);
  if (mobile) {
    await page.setViewportSize({ width: 360, height: 690 });
    for (const theme of themes) {
      await button('Разделы мастерской').click();
      await page
        .locator('.ww-menu-dialog')
        .getByRole('button', { name: 'Оформление', exact: true })
        .click();
      await chooseOption(page.getByRole('combobox', { name: 'Тема мира', exact: true }), theme.id);
      await page.keyboard.press('Escape');
      await expect(page.getByRole('dialog', { name: 'Оформление мастерской' })).toHaveCount(0);
      await page.keyboard.press('Escape');
      await button('Портреты').click();
      await checkLayout();
      await check('Анна Маркова').first().check();
      await body.evaluate((el) => (el.scrollTop = 0));
      await shot('skin-' + theme.id);
      await dialog.getByRole('button', { name: 'Закрыть', exact: true }).click();
    }
  }
});

test('game portrait collection protects a newer revision and refreshes the dossier', async ({
  page,
  request,
}) => {
  const save = await (await request.post('/test/appearance-seed')).json();
  await page.addInitScript((s) => localStorage.setItem('selection', JSON.stringify(s)), save);
  await page.goto('/');
  await nav(page, 'Мир');
  await nav(page, 'Персонажи');
  await pickCharacter(page, 'qa_vera');
  const button = (name: string) => page.getByRole('button', { name, exact: true });
  const path = '/api/saves/' + save.save + '/characters/qa_vera/portraits';
  const saved = async () => await (await request.get(path)).json();
  const start = async () => {
    await button('Редактировать портрет').click();
    await button('Все портреты').click();
    await page.getByRole('checkbox', { name: 'Вера Ларина', exact: true }).check();
    await button('Рассчитать расход').click();
    await button('Подтвердить запрос').click();
    await page.locator('.commission-result').getByRole('checkbox').check();
  };
  await start();
  const original = await saved();
  const update = await request.put(path + '/procedural', {
    data: { revision: original.revision, mode: 'procedural', descriptor: original.descriptor },
  });
  expect(update.ok(), await update.text()).toBe(true);
  await button('Применить выбранные · 1').click();
  await expect(page.getByRole('alert')).toContainText('изменил');
  expect((await saved()).descriptor).toEqual(original.descriptor);
  await button('Обновить карточки').click();
  await start();
  await button('Применить выбранные · 1').click();
  await expect(page.locator('.portrait-dialog')).toHaveCount(0);
  const now = await saved();
  // A commissioned hairstyle preserves the existing head drawing revision.
  expect(now.descriptor.face_revision).toBe(original.descriptor.face_revision);
  expect(now.descriptor.seed).toBe(original.descriptor.seed);
  expect(now.descriptor.hairstyle).toBe('bun');
  await button('Редактировать портрет').click();
  await button('Настроить иллюстрацию').click();
  await button('Одежда').click();
  await page.getByRole('searchbox', {name:'Поиск · Одежда'}).fill('фартук');
  await button('Рабочий фартук').click();
  await button('Сохранить иллюстрацию').click();
  await expect(page.locator('.portrait-dialog')).toHaveCount(0);
  const edited = (await saved()).descriptor;
  expect(edited).toMatchObject({garment:'work_apron', hairstyle:'bun', seed:original.descriptor.seed});
  await page.reload();
  expect((await saved()).descriptor).toEqual(edited);
});
