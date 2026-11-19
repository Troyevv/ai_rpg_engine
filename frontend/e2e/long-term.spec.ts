import {gameAction} from './navigation';
import {test,expect} from '@playwright/test';

test('long-term advance preview, zero-budget commit, reload and responsive results',async({page,request})=>{
  const seed=await request.post('/test/long-term-seed');expect(seed.ok()).toBeTruthy();
  const selected=await seed.json();
  await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selected);
  await page.goto('/');
  await gameAction(page,'Длительный переход');
  const dialog=page.getByRole('dialog').last();
  await dialog.getByLabel('Количество единиц перехода').fill('15');
  await dialog.getByText(/Подробности симуляции/).click();
  await dialog.getByLabel('Лимит обращений к модели').fill('0');
  const submit=dialog.getByRole('button',{name:'Подтвердить длительный переход'});
  await expect(submit).toBeEnabled();
  await submit.click();
  await expect(page.locator('.skip-diagnostics').filter({hasText:'Длительный переход'})).toBeVisible();
  await page.reload();
  await expect(page.locator('.skip-diagnostics').filter({hasText:'Длительный переход'})).toContainText('0 / 0');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
  const saved=await(await request.get(`/api/saves/${selected.save}`)).json();
  expect(saved.state.last_long_term_advance.llm_calls).toBe(0);
});

test('209: father can play the delivery scene and advance again', async ({ page, request }) => {
  const seed = await request.post('/test/long-term-seed?pregnancy=true');
  expect(seed.ok()).toBeTruthy();
  const selected = await seed.json();
  await page.addInitScript(s => localStorage.setItem('selection', JSON.stringify(s)), selected);
  const saved = async () => (await request.get(`/api/saves/${selected.save}`)).json();
  await page.goto('/');
  async function advance() {
    await gameAction(page, 'Длительный переход');
    const dialog = page.getByRole('dialog').last();
    await dialog.getByLabel('Единица перехода').selectOption('weeks');
    await dialog.getByLabel('Количество единиц перехода').fill('2');
    await dialog.getByText(/Подробности симуляции/).click();
    await dialog.getByLabel('Лимит обращений к модели').fill('0');
    const before = await saved();
    await dialog.getByRole('button', {name: 'Подтвердить длительный переход'}).click();
    await expect.poll(async () => (await saved()).turns.length).toBe(before.turns.length + 1);
    return (await saved()).state.last_long_term_advance;
  }
  const previewResponse = await request.post(`/api/saves/${selected.save}/long-term/preview`, {
    data: {amount: 2, unit: 'weeks', max_llm_calls: 0},
  });
  expect(previewResponse.ok()).toBeTruthy();
  const preview = await previewResponse.json();
  const stopped = await advance();
  expect(stopped.actual_target).toBe(1980);
  for (const report of [preview, stopped]) {
    expect(report.interruption).toEqual({kind: 'scene', minute: 1980});
    expect(JSON.stringify(report)).not.toContain('pregnancy_');
    const choice = report.decisions.find((row: {kind: string}) => row.kind === 'scene');
    expect(choice).toBeDefined();
    expect(choice).not.toHaveProperty('actor_ids');
  }
  await expect(page.locator('.advance-result')).toContainText('Можно остаться наблюдать');
  await page.reload();
  await page.getByLabel('Своё действие или реплика').fill('Я остаюсь рядом с Верой и держу её за руку.');
  await page.getByRole('button', {name: 'Отправить действие', exact: true}).click();
  await expect(page.locator('.turn').last()).toContainText('Вера родила.');
  await expect.poll(async () => (await saved()).job.status).toBe('saved');
  const resumed = await advance();
  expect(resumed.interruption).toBeNull();
  expect(resumed.actual_target).toBe(1981 + 14 * 1440);
});

test('#250 rejected LTA groups show incomplete coverage after reload', async ({page, request}) => {
  const {defaults} = await import('../src/types');
  const seed = await request.post('/test/long-term-seed');
  expect(seed.ok()).toBeTruthy();
  const selected = await seed.json();
  const profile = `lta250-${selected.save}`;
  await request.put(`/api/settings/${profile}`, {data: {...defaults, game: {
    ...defaults.game, model: 'lta250-test', context_length: 49152,
  }}});
  await page.addInitScript(({selected, profile}) => {
    localStorage.setItem('selection', JSON.stringify(selected));
    localStorage.setItem('profile', profile);
  }, {selected, profile});
  await page.goto('/');
  await gameAction(page, 'Длительный переход');
  const dialog = page.getByRole('dialog').last();
  await dialog.getByLabel('Количество единиц перехода').fill('15');
  await dialog.getByText(/Подробности симуляции/).click();
  await dialog.getByLabel('Лимит обращений к модели').fill('4');
  await dialog.getByRole('button', {name: 'Подтвердить длительный переход'}).click();
  const view = async () => (await request.get(`/api/saves/${selected.save}`)).json();
  await expect.poll(async () => (await view()).state.last_long_term_advance?.status).toBe('incomplete');
  const before = await view();
  expect(before.state.last_long_term_advance.coverage.rejected_causes).toBeGreaterThan(0);
  expect(before.state.last_long_term_advance.llm_calls).toBeLessThanOrEqual(4);
  await page.reload();
  const result = page.locator('.advance-result');
  await expect(result).toContainText('Симуляция неполная');
  await expect(result).toContainText('Отклонено причин:');
  expect((await view()).state.last_long_term_advance).toEqual(before.state.last_long_term_advance);
  await expect(page.getByLabel('Своё действие или реплика')).toBeEnabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
});
