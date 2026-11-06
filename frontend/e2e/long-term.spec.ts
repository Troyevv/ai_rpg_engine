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
  const stopped = await advance();
  expect(stopped.actual_target).toBe(1980);
  expect(stopped.interruption.kind).toBe('pregnancy_due');
  await page.reload();
  await page.getByLabel('Своё действие или реплика').fill('Я остаюсь рядом с Верой и держу её за руку.');
  await page.getByRole('button', {name: 'Отправить действие', exact: true}).click();
  await expect(page.locator('.turn').last()).toContainText('Вера родила.');
  await expect.poll(async () => (await saved()).job.status).toBe('saved');
  const resumed = await advance();
  expect(resumed.interruption).toBeNull();
  expect(resumed.actual_target).toBe(1981 + 14 * 1440);
});
