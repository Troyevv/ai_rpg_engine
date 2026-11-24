import { test, expect } from '@playwright/test';

test('277 real phone catalogs, discussions, inbox, plans and applications', async ({
  page,
  request,
}, info) => {
  test.setTimeout(180000);
  const seed = await (
    await request.post('/test/phone-seed?smartphone=true&incoming=false&decision=phone277')
  ).json();
  await request.put(`/api/worlds/${seed.world}/presentation`, {
    data: { theme_id: info.project.name === 'mobile' ? 'parchment' : 'neon' },
  });
  await page.addInitScript((s) => localStorage.setItem('selection', JSON.stringify(s)), seed);
  await page.goto('/');
  const phone = page.getByRole('region', { name: 'Телефон персонажа' });
  const b = (name: string) => phone.getByRole('button', { name, exact: true });
  const submit = async (button: string) => {
    const [response] = await Promise.all([
      page.waitForResponse(
        (r) => r.request().method() === 'POST' && /\/(apps|phone)\/dispatch$/.test(r.url()),
      ),
      b(button).click(),
    ]);
    expect(response.ok(), await response.text()).toBe(true);
    const { job } = await response.json();
    await expect
      .poll(async () => (await (await request.get('/api/jobs/' + job.id)).json()).status)
      .toBe('saved');
  };
  const open = () => page.getByRole('button', { name: /^Телефон/ }).click();
  const list = (s: string) => phone.locator('.listing-preview').filter({ hasText: s }).first();
  const overflow = async () =>
    expect(
      await phone.evaluate(
        (el) => el.scrollWidth <= el.clientWidth && document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  await page.getByLabel('Своё действие или реплика').fill('Сохраняю основной черновик.');
  await open();
  await b('Новости').click();
  await submit('Новые статьи');
  await list('Хроника набережной').click();
  await expect(phone.getByText('Издание сообщает о поиске утраченной коллекции.')).toBeVisible();
  await phone.getByLabel('Ваш комментарий').fill('Сохраним коллекцию вместе!');
  await submit('Отправить комментарий');
  await expect(phone.getByText('Сохраним коллекцию вместе!', { exact: true })).toBeVisible();
  await overflow();
  await b('Домой').click();
  await b('Вопросы').click();
  await b('Страницы персонажей').click();
  const actor = await (await request.get('/api/saves/' + seed.save)).json();
  const npc = actor.state.characters.find((p: any) => p.id === 'qa_vera');
  await b(npc.name).click();
  await b('Задать вопрос').click();
  await phone.getByLabel('Ваш вопрос').fill('Что сыграешь на бис?');
  await submit('Отправить вопрос');
  await list('Что сыграешь').click();
  await expect(phone.getByText('Аноним', { exact: true })).toBeVisible();
  await overflow();
  await b('Домой').click();
  await b('Афиша').click();
  await submit('Найти мероприятия');
  await list('Вечер музыки').click();
  await b('Запланировать').click();
  await expect(phone.getByText('В вашем календаре')).toBeVisible();
  await b('Пригласить').click();
  await phone
    .getByLabel(actor.state.phone.recipients.find((r: any) => r.id === npc.id).subject.name, { exact: true })
    .check();
  await phone
    .getByLabel(actor.state.phone.recipients.find((r: any) => r.id === 'qa_oleg').subject.name, {
      exact: true,
    })
    .check();
  await submit('Отправить приглашение');
  await expect(b('Пригласить')).toBeVisible();
  await overflow();
  await b('Отправиться').click();
  await page.getByRole('button', { name: 'Добавить к черновику' }).click();
  await expect(page.getByLabel('Своё действие или реплика')).toHaveValue(
    /Сохраняю основной черновик.[\s\S]+Отправляюсь на/,
  );
  const turns = page.locator('.story-scroll .turn');
  const turnCount = await turns.count();
  const composer = page.getByLabel('Своё действие или реплика');
  await composer.fill((await composer.inputValue()) + ' Беру с собой программу.');
  await page.getByRole('button', { name: 'Отправить действие', exact: true }).click();
  await expect(turns).toHaveCount(turnCount + 1);
  await expect(turns.last()).toContainText('Беру с собой программу.');
  await expect(composer).toBeEnabled();
  await open();
  await b('Работа и вакансии').click();
  await submit('Найти ещё вакансии');
  await phone.getByLabel('Поиск вакансий').fill('переплёт');
  await list('Мастер переплёта').click();
  await b('В избранное').click();
  await expect(b('Убрать из избранного')).toBeVisible();
  await b('Откликнуться').click();
  await phone.getByLabel('Текст отклика').fill('Расскажите об условиях работы.');
  await submit('Отправить отклик');
  await expect(b('Переписка с работодателем')).toBeVisible();
  await b('Переписка с работодателем').click();
  await expect(phone.locator('.phone-message.outgoing')).toContainText('Расскажите об условиях работы.');
  await expect(phone.locator('.phone-message.incoming').last()).toContainText('Предлагаю начать сегодня');
  await phone.getByLabel('Сообщение в телефоне').fill('Условия подходят. Принимаю работу и начинаю сегодня.');
  await submit('Отправить сообщение');
  await overflow();
  await page.reload();
  await open();
  await b('Работа и вакансии').click();
  await b('Мои отклики').click();
  await expect(list('Мастер переплёта')).toBeVisible();
  await b('Моя работа').click();
  await expect(phone.locator('.smart-post').first()).toContainText('Мастер переплёта');
});

test('277 anonymous inbox stays private across three owners and a published answer', async ({
  page,
  request,
}, info) => {
  test.setTimeout(100000);
  const seed = await (await request.post('/test/phone-seed?smartphone=true&incoming=true')).json();
  const path = '/api/saves/' + seed.save;
  const state = async () => (await request.get(path)).json();
  const switchTo = async (id: string) => {
    const resp = await request.post(path + '/protagonist', {
      data: {
        revision: (await state()).revision,
        actor_id: id,
        operation: 'temporary',
        operation_id: crypto.randomUUID(),
      },
    });
    expect(resp.ok(), await resp.text()).toBe(true);
  };
  const send = async (anonymous: boolean, text: string) => {
    const r = await request.post(path + '/apps/command', {
      data: {
        revision: (await state()).revision,
        command: {
          actor_id: 'qa_kirill',
          operation_id: crypto.randomUUID(),
          app: 'questions',
          action: 'ask',
          desired: anonymous,
          target: 'qa_vera',
          text,
        },
      },
    });
    expect(r.ok(), await r.text()).toBe(true);
  };
  await send(true, 'Что поставить на бис?');
  await send(false, 'Когда откроется сцена?');
  await switchTo('qa_oleg');
  expect((await (await request.get(path + '/apps/questions?tab=inbox')).json()).items).toEqual([]);
  expect((await (await request.get(path + '/apps/questions')).json()).items).toEqual([]);
  await switchTo('qa_vera');
  const inbox = (await (await request.get(path + '/apps/questions?tab=inbox')).json()).items;
  expect(inbox.find((q: any) => q.text === 'Когда откроется сцена?').sender.id).toBe('qa_kirill');
  expect(JSON.stringify(inbox.find((q: any) => q.text === 'Что поставить на бис?'))).not.toContain(
    'qa_kirill',
  );
  await request.put(`/api/worlds/${seed.world}/presentation`, {
    data: { theme_id: info.project.name === 'desktop' ? 'graphite' : 'parchment' },
  });
  await page.addInitScript((s) => localStorage.setItem('selection', JSON.stringify(s)), seed);
  await page.goto('/');
  const phone = page.getByRole('region', { name: 'Телефон персонажа' }),
    b = (name: string) => phone.getByRole('button', { name, exact: true });
  await page.getByRole('button', { name: /^Телефон/ }).click();
  await b('Вопросы').click();
  await b('Входящие').click();
  await phone.locator('.listing-preview').filter({ hasText: 'Что поставить на бис?' }).click();
  expect(await phone.locator('.smart-app').innerHTML()).not.toContain('qa_kirill');
  await b('Ответить на вопрос').click();
  await phone.getByLabel('Ваш ответ').fill('Сыграю вальс!');
  await page.getByRole('button', { name: 'Свернуть телефон' }).click();
  await page.getByRole('button', { name: /^Телефон/ }).click();
  await b('Вопросы').click();
  await expect(phone.getByLabel('Ваш ответ')).toHaveValue('Сыграю вальс!');
  await b('Опубликовать ответ').click();
  await expect(phone.getByText('Сыграю вальс!', { exact: true })).toBeVisible();
  await expect(phone.getByText('Аноним', { exact: true })).toBeVisible();
  if (info.project.name === 'mobile') {
    for (const width of [320, 360, 393]) {
      await page.setViewportSize({ width, height: 800 });
      await expect(phone.getByLabel('Ваш комментарий')).toBeVisible();
      expect(
        await phone.evaluate(
          (el) => el.scrollWidth <= el.clientWidth && document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
  }
  await page.screenshot({ path: info.outputPath('published-answer.png') });
  await switchTo('qa_oleg');
  await page.reload();
  await page.getByRole('button', { name: /^Телефон/ }).click();
  await b('Вопросы').click();
  await phone.locator('.listing-preview').filter({ hasText: 'Что поставить на бис?' }).click();
  await expect(phone.getByText('Сыграю вальс!', { exact: true })).toBeVisible();
  expect(await phone.locator('.smart-app').innerHTML()).not.toContain('qa_kirill');
});

test('277 five news badges reset on entry, retry survives minimize, reload and another owner', async ({
  page,
  request,
}, info) => {
  const seed = await (
    await request.post('/test/phone-seed?smartphone=true&incoming=false&decision=app_error_once')
  ).json();
  const path = '/api/saves/' + seed.save,
    state = async () => (await request.get(path)).json();
  await page.addInitScript((s) => localStorage.setItem('selection', JSON.stringify(s)), seed);
  await page.goto('/');
  const phone = page.getByRole('region', { name: 'Телефон персонажа' }),
    b = (name: string) => phone.getByRole('button', { name, exact: true });
  await page.getByRole('button', { name: /^Телефон/ }).click();
  await b('Новости').click();
  await b('Новые статьи').click();
  await b('Домой').click();
  await expect.poll(async () => (await state()).job.status).toBe('error');
  await b('Новости').click();
  await b('Повторить генерацию').click();
  await expect(phone.locator('.listing-preview')).toHaveCount(5);
  await b('Домой').click();
  await expect(b('Новости').getByLabel('5 новых')).toBeVisible();
  await b('Афиша').click();
  await b('Домой').click();
  await expect(b('Новости').getByLabel('5 новых')).toBeVisible();
  await b('Новости').click();
  await b('Домой').click();
  await expect(b('Новости').locator('small')).toHaveCount(0);
  await expect.poll(async () => (await state()).state.phone.badges.news).toBe(0);
  await page.reload();
  await page.getByRole('button', { name: /^Телефон/ }).click();
  await expect(b('Новости').locator('small')).toHaveCount(0);
  await request.post(path + '/protagonist', {
    data: {
      revision: (await state()).revision,
      actor_id: 'qa_vera',
      operation: 'temporary',
      operation_id: crypto.randomUUID(),
    },
  });
  await page.reload();
  await page.getByRole('button', { name: /^Телефон/ }).click();
  await expect(b('Новости').getByLabel('5 новых')).toBeVisible();
  await page.screenshot({ path: info.outputPath('launcher.png') });
});

test('277 incoming call restores the question draft, main draft and physical choices', async ({
  page,
  request,
}) => {
  const seed = await (await request.post('/test/phone-seed?smartphone=true&incoming=true')).json();
  const save = await (await request.get('/api/saves/' + seed.save)).json();
  const recipient = save.state.characters.find((c: { id: string }) => c.id === 'qa_vera');
  await page.addInitScript((s) => localStorage.setItem('selection', JSON.stringify(s)), seed);
  await page.goto('/');
  const main = page.getByLabel('Своё действие или реплика');
  await main.fill('Читаю программу концерта.');
  const choices = page.locator('.choices button');
  const before = await choices.allTextContents();
  expect(before.length).toBeGreaterThan(0);
  const phone = page.getByRole('region', { name: 'Телефон персонажа' });
  const b = (name: string) => phone.getByRole('button', { name, exact: true });
  await page.getByRole('button', { name: /^Телефон/ }).click();
  await b('Вопросы').click();
  await b('Страницы персонажей').click();
  await b(recipient.name).click();
  await b('Задать вопрос').click();
  const draft = phone.getByLabel('Ваш вопрос');
  await draft.fill('Что будут играть?');
  await b('Ответить').click();
  const call = page.getByRole('dialog', { name: 'Сцена звонка' });
  await call.getByRole('button', { name: 'Завершить звонок', exact: true }).click();
  await expect(draft).toHaveValue('Что будут играть?');
  await page.getByRole('button', { name: 'Свернуть телефон' }).click();
  await expect(main).toHaveValue('Читаю программу концерта.');
  expect(await choices.allTextContents()).toEqual(before);
});

test('nine distinct launcher artworks keep unread counts visible in the active skin', async ({
  page,
  request,
}, info) => {
  const seed = await (await request.post('/test/phone-seed?smartphone=true&unread=true&incoming=false')).json();
  const theme = info.project.name === 'mobile' ? 'parchment' : 'graphite';
  const changed = await request.put('/api/worlds/' + seed.world + '/presentation', {
    data: { theme_id: theme },
  });
  expect(changed.ok()).toBe(true);
  await page.addInitScript((s) => localStorage.setItem('selection', JSON.stringify(s)), seed);
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
  await page.getByRole('button', { name: /^Телефон/ }).click();
  const device = page.getByTestId('phone-device');
  const artworks = device.locator('.smart-icon .smart-artwork use');
  await expect(artworks).toHaveCount(9);
  await expect.poll(() => artworks.evaluateAll((uses) => uses.every((el) => (el as SVGUseElement).getBBox().width > 0))).toBe(true);
  const targets = await artworks.evaluateAll((uses) => uses.map((el) => el.getAttribute('href')));
  expect(new Set(targets).size).toBe(9);
  await expect(device.locator('.app-messages small')).toHaveText(/^[1-9]/);
  await expect(device.getByRole('button', { name: 'Работа и вакансии' })).toBeInViewport();
  await device.screenshot({ path: info.outputPath('launcher-' + theme + '.png'), animations: 'disabled' });
});

test('opening receipt cannot interrupt a composed message before dispatch', async ({ page, request }) => {
  const seed = await (
    await request.post('/test/phone-seed?smartphone=true&incoming=false&unread=true')
  ).json();
  const path = '/api/saves/' + seed.save;
  const save = await (await request.get(path)).json();
  const conversation = save.state.phone.events.find((e: { unread: boolean }) => e.unread).conversation_id;
  const read = await request.post(path + '/phone', {
    data: {
      revision: save.revision,
      command: { action: 'read', conversation_id: conversation, operation_id: 'mark-chat-read' },
    },
  });
  expect(read.ok(), await read.text()).toBe(true);
  await page.addInitScript((s) => localStorage.setItem('selection', JSON.stringify(s)), seed);
  await page.goto('/');
  await page.getByRole('button', { name: /^Телефон/ }).click();
  const phone = page.getByRole('region', { name: 'Телефон персонажа' });
  await expect(phone.locator('.app-messages small')).toHaveText('1');

  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  let acknowledge!: () => void;
  const received = new Promise<void>((resolve) => {
    acknowledge = resolve;
  });
  await page.route('**' + path + '/apps/command', async (route) => {
    if (route.request().postDataJSON().command.action !== 'open') return route.continue();
    const response = await route.fetch();
    acknowledge();
    await gate;
    await route.fulfill({ response });
  });
  await phone.getByRole('button', { name: 'Чаты', exact: true }).click();
  await received;
  await phone.locator('.phone-thread').filter({ hasText: 'Вера работа' }).click();
  await phone.getByLabel('Сообщение в телефоне').fill('До встречи в архиве');
  const send = phone.getByRole('button', { name: 'Отправить сообщение' });
  await expect(send).toBeEnabled();

  // Hold the projection GET after the phone has received its committed revision.
  let finishGet!: () => void;
  const holdGet = new Promise<void>((resolve) => {
    finishGet = resolve;
  });
  await page.route('**' + path, async (route) => {
    await holdGet;
    await route.continue();
  });
  try {
    const refresh = page.waitForRequest((r) => r.method() === 'GET' && r.url().endsWith(path));
    release();
    await refresh;
    await expect(send).toBeEnabled();
    const dispatch = page.waitForResponse((r) => r.url().endsWith(path + '/phone/dispatch'));
    await send.click();
    expect((await dispatch).ok()).toBe(true);
  } finally {
    finishGet();
    release();
  }
});
