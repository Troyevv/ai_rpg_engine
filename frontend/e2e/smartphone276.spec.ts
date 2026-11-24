import { test, expect } from '@playwright/test';

test('276 shared feed, NPC discussion, dating batch and direct chat survive reload', async ({
  page,
  request,
}, info) => {
  test.setTimeout(120000);
  const seed = await (await request.post('/test/phone-seed?smartphone=true&incoming=false')).json();
  const skin = info.project.name === 'mobile' ? 'parchment' : 'neon';
  await request.put(`/api/worlds/${seed.world}/presentation`, { data: { theme_id: skin } });
  await page.addInitScript((s) => localStorage.setItem('selection', JSON.stringify(s)), seed);
  await page.goto('/');
  const phone = page.getByRole('region', { name: 'Телефон персонажа' });
  const button = (name: string) => phone.getByRole('button', { name, exact: true });
  const open = () => page.getByRole('button', { name: /^Телефон/ }).click();
  const home = () => button('Домой').click();
  const state = async () => (await request.get(`/api/saves/${seed.save}`)).json();
  const revision = async () => (await state()).revision;
  const saved = async () => {
    await expect.poll(async () => (await state()).job?.status).toBe('saved');
  };
  const noOverflow = async () =>
    expect(
      await phone.evaluate(
        (el) => el.scrollWidth <= el.clientWidth && document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  await open();
  for (const width of info.project.name === 'mobile' ? [320, 360, 393] : [1440]) {
    await page.setViewportSize({ width, height: info.project.name === 'mobile' ? 820 : 1000 });
    await expect(phone.getByRole('navigation', { name: 'Приложения' }).getByRole('button')).toHaveCount(5);
    await noOverflow();
    await page.screenshot({ path: info.outputPath(`home-${width}.png`) });
  }
  for (const name of ['Звонки', 'Чаты', 'Контакты']) {
    await button(name).click();
    await expect(phone.getByRole('heading', { level: 2 })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(button('Соцсеть')).toBeVisible();
  }
  await button('Соцсеть').click();
  await expect(phone.getByText('Публикаций пока нет.')).toBeVisible();
  await button('Пост').click();
  const text = 'Вечером открывается выставка. ' + '📖Длинноеслово'.repeat(50);
  await phone.getByLabel('Текст публикации').fill(text);
  await button('Опубликовать').click();
  await saved();
  await expect(phone.locator('.smart-post')).toContainText([text]);
  await page.screenshot({ path: info.outputPath('feed.png') });
  await button('Открыть обсуждение').click();
  await expect(phone.getByText('Буду у галереи вечером. Кто ещё идёт?')).toBeVisible();
  await phone.getByLabel('Ваш комментарий').fill('Зайду после шести.');
  await phone.getByLabel('Ваш комментарий').focus();
  if (info.project.name === 'mobile') {
    await page.evaluate(() => {
      Object.defineProperty(visualViewport, 'height', { configurable: true, value: 420 });
      visualViewport!.dispatchEvent(new Event('resize'));
    });
    await phone.getByLabel('Ваш комментарий').scrollIntoViewIfNeeded();
    await expect(phone.getByLabel('Ваш комментарий')).toBeInViewport();
    await button('Отправить комментарий').scrollIntoViewIfNeeded();
    await expect(button('Отправить комментарий')).toBeInViewport();
    await page.screenshot({ path: info.outputPath('keyboard.png') });
    await page.evaluate(() => {
      delete (visualViewport as any).height;
      visualViewport!.dispatchEvent(new Event('resize'));
    });
  }
  await button('Отправить комментарий').click();
  await expect(phone.getByText('Зайду после шести.', { exact: true })).toBeVisible();
  await saved();
  const original = phone.locator('.smart-post').first();
  await original.getByLabel('Нравится').click();
  await expect(original.getByLabel('Нравится')).toHaveAttribute('aria-pressed', 'true');
  await original.getByLabel('Репост').click();
  await expect(original.getByLabel('Репост')).toHaveAttribute('aria-pressed', 'true');
  await noOverflow();
  await page.screenshot({ path: info.outputPath('discussion.png') });
  await original.getByRole('button').first().click();
  await expect(button('О себе')).toBeVisible();
  const bio = 'Собираю старые книги. ' + 'Длинноесловобезпробелов📚'.repeat(45);
  await button('О себе').click();
  await phone.getByLabel('Публичное описание').fill(bio);
  await button('Сохранить').click();
  await expect(phone.locator('.smart-profile p')).toHaveText(bio);
  await noOverflow();
  await page.screenshot({ path: info.outputPath('public-profile.png') });
  await home();
  await button('Знакомства').click();
  await button('Настроить поиск').click();
  await phone.getByLabel('Местоположение').fill('Москва');
  await phone.getByLabel('Возраст от').fill('24');
  await button('Женщин').click();
  await page.screenshot({ path: info.outputPath('filters.png') });
  await button('Найти анкеты').click();
  await saved();
  await expect(phone.locator('.dating-card')).toContainText('Ася Миронова');
  await button('Пропустить').click();
  await expect(phone.locator('.dating-card')).toContainText('Мария Орлова');
  await button('Подробнее').click();
  await expect(phone.getByText('Короткие каштановые волосы')).toBeVisible();
  await noOverflow();
  await page.screenshot({ path: info.outputPath('dating.png') });
  const before = await state();
  await button('Лайк').click();
  await saved();
  await expect(button('Карточка NPC')).toBeVisible();
  const after = await state();
  const npc = after.state.characters.find((c: any) => c.name === 'Мария Орлова');
  expect(npc).toBeTruthy();
  expect(after.state.characters.length).toBe(before.state.characters.length + 1);
  await button('Карточка NPC').click();
  await expect(phone).toBeHidden();
  await page.reload();
  await open();
  await button('Знакомства').click();
  await button('Понравившиеся анкеты').click();
  await button('Мария Орлова, 25').click();
  await button('Написать').click();
  await phone.getByLabel('Сообщение в телефоне').fill('Увидимся в галерее?');
  await button('Отправить сообщение').click();
  await expect(phone.locator('.phone-message.outgoing')).toContainText('Увидимся в галерее?');
  await saved();
  await page.reload();
  await open();
  await button('Чаты').click();
  await phone.locator('.phone-thread').filter({ hasText: 'Мария Орлова' }).click();
  await expect(phone.locator('.phone-message.outgoing')).toContainText('Увидимся в галерее?');
  await home();
  await button('Соцсеть').click();
  await expect(phone.locator('.smart-post').first().getByLabel('Репост')).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  expect(await revision()).toBeGreaterThan(before.revision);
});

for (const app of ['Соцсеть', 'Знакомства']) {
  test('276 incoming call restores ' + app + ' and physical choices', async ({ page, request }, info) => {
    const seed = await (await request.post('/test/phone-seed?smartphone=true&incoming=true')).json();
    await request.put(`/api/worlds/${seed.world}/presentation`, { data: { theme_id: 'graphite' } });
    await page.addInitScript((s) => localStorage.setItem('selection', JSON.stringify(s)), seed);
    await page.goto('/');
    const choices = page.locator('.choices button');
    const main = page.getByLabel('Своё действие или реплика');
    await main.fill('Читаю у окна.');
    const physical = await choices.allTextContents();
    expect(physical.length).toBeGreaterThan(0);
    const phone = page.getByRole('region', { name: 'Телефон персонажа' });
    const button = (name: string) => phone.getByRole('button', { name, exact: true });
    await page.getByRole('button', { name: /^Телефон/ }).click();
    await button(app).click();
    await button(app === 'Соцсеть' ? 'Пост' : 'Параметры поиска').click();
    const draft = phone.getByLabel(app === 'Соцсеть' ? 'Текст публикации' : 'Местоположение');
    await draft.fill('Черновик до звонка');
    await button('Ответить').click();
    const call = page.getByRole('dialog', { name: 'Сцена звонка' });
    await expect(call).toBeVisible();
    await page.screenshot({ path: info.outputPath('incoming.png') });
    if (app === 'Знакомства') {
      await call.getByRole('button', { name: 'Домой', exact: true }).click();
      await expect(button('Соцсеть')).toBeVisible();
      await button('Перейти к разговору').click();
    } else {
      await call.getByLabel('Свернуть звонок').click();
      await expect(main).toHaveValue('Читаю у окна.');
      await page.getByRole('button', { name: /Вернуться к звонку/ }).click();
    }
    await call.getByRole('button', { name: 'Завершить звонок', exact: true }).click();
    await expect(draft).toHaveValue('Черновик до звонка');
    await page.goBack();
    await expect(draft).toBeHidden();
    await page.goBack();
    await expect(button(app)).toBeVisible();
    await page.goBack();
    await expect(phone).toBeHidden();
    expect(await choices.allTextContents()).toEqual(physical);
    expect(await page.evaluate(() => history.state?.phoneUI || history.state?.phoneCall)).toBeFalsy();
  });
}

test('276 failed social reaction can be retried after navigating during generation', async ({
  page,
  request,
}, info) => {
  const seed = await (
    await request.post('/test/phone-seed?smartphone=true&incoming=false&decision=app_error_once')
  ).json();
  await page.addInitScript((s) => localStorage.setItem('selection', JSON.stringify(s)), seed);
  await page.goto('/');
  const phone = page.getByRole('region', { name: 'Телефон персонажа' });
  const button = (name: string) => phone.getByRole('button', { name, exact: true });
  await page.getByRole('button', { name: /^Телефон/ }).click();
  await button('Соцсеть').click();
  await button('Пост').click();
  const draft = phone.getByLabel('Текст публикации');
  await draft.fill('После дождя открываем галерею');
  await page.route('**/apps/dispatch', (route) => route.abort(), { times: 1 });
  await button('Опубликовать').click();
  await expect(phone.getByRole('alert')).toBeVisible();
  await expect(draft).toHaveValue('После дождя открываем галерею');
  await button('Опубликовать').click();
  await expect(phone.getByText('Ответы персонажей')).toBeVisible();
  await button('Домой').click();
  await button('Контакты').click();
  await expect(phone.getByLabel('Поиск адресата')).toBeVisible();
  await button('Домой').click();
  await button('Соцсеть').click();
  await expect(phone.locator('.smart-post')).toHaveCount(1);
  await expect(button('Повторить генерацию')).toBeVisible();
  await page.screenshot({ path: info.outputPath('provider-error.png') });
  await button('Повторить генерацию').click();
  await button('Открыть обсуждение').click();
  await expect(phone.getByText('Я приду после работы.')).toBeVisible();
  const feed = await (await request.get(`/api/saves/${seed.save}/apps/social`)).json();
  expect(feed.entries).toHaveLength(1);
  expect(feed.entries[0].post.comments).toBe(2);
});

test('276 five new posts, app badges and drafts are scoped to the actor, save and branch', async ({
  page,
  request,
}) => {
  test.setTimeout(90000);
  const seed = async () =>
    await (await request.post('/test/phone-seed?smartphone=true&incoming=false&unread=true')).json();
  const a = await seed(),
    b = await seed();
  await page.goto('/');
  const select = async (s: typeof a) => {
    await page.evaluate((s) => localStorage.setItem('selection', JSON.stringify(s)), s);
    await page.reload();
  };
  const state = async () => await (await request.get(`/api/saves/${a.save}`)).json();
  const control = async (path: string, body: Record<string, unknown>) => {
    const res = await request.post(`/api/saves/${a.save}/${path}`, {
      data: { revision: (await state()).revision, ...body },
    });
    expect(res.ok(), await res.text()).toBe(true);
  };
  const actor = (id: string) =>
    control('protagonist', { operation_id: crypto.randomUUID(), operation: 'temporary', actor_id: id });
  await actor('qa_vera');
  for (let i = 0; i < 5; i++)
    await control('apps/command', {
      command: {
        app: 'social',
        action: 'post',
        operation_id: 'badge-post-' + i,
        actor_id: 'qa_vera',
        text: 'Публичная запись ' + i,
      },
    });
  await actor('qa_kirill');
  await select(a);
  const phone = page.getByRole('region', { name: 'Телефон персонажа' });
  const button = (name: string) => phone.getByRole('button', { name, exact: true });
  const open = () => page.getByRole('button', { name: /^Телефон/ }).click();
  const home = () => button('Домой').click();
  const badge = () => phone.locator('[data-app=social] small');
  await open();
  await expect(badge()).toHaveText('5');
  await button('Контакты').click();
  await home();
  await expect(badge()).toHaveText('5');
  await button('Соцсеть').click();
  await home();
  await expect(badge()).toHaveCount(0);
  await expect(phone.locator('[data-app=messages] small')).toHaveText('1');
  await page.reload();
  await open();
  await expect(badge()).toHaveCount(0);
  await button('Соцсеть').click();
  await button('Пост').click();
  const draft = phone.getByLabel('Текст публикации');
  await draft.fill('Личный черновик Кирилла');
  await actor('qa_timur');
  await page.reload();
  await open();
  await expect(badge()).toHaveText('5');
  await button('Соцсеть').click();
  await button('Пост').click();
  await expect(draft).toHaveValue('');
  await select(b);
  await open();
  await expect(badge()).toHaveCount(0);
  await button('Соцсеть').click();
  await expect(phone.getByText('Публикаций пока нет.')).toBeVisible();
  await actor('qa_kirill');
  await select(a);
  await open();
  await button('Соцсеть').click();
  await button('Пост').click();
  await expect(draft).toHaveValue('Личный черновик Кирилла');
  await control('rollback', {});
  await page.reload();
  const restored = await (await request.get(`/api/saves/${a.save}/apps/social`)).json();
  expect(restored.entries || []).toHaveLength(0);
  expect(await phone.isVisible()).toBe(false);
});
