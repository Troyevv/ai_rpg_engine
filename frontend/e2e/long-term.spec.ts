import {test,expect} from '@playwright/test';

test('long-term advance preview, zero-budget commit, reload and responsive results',async({page,request})=>{
  const seed=await request.post('/test/long-term-seed');expect(seed.ok()).toBeTruthy();
  const selected=await seed.json();
  await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selected);
  await page.goto('/');
  await page.getByRole('button',{name:'Длительный переход',exact:true}).click();
  const dialog=page.getByRole('dialog');
  await dialog.getByLabel('Количество единиц перехода').fill('15');
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
