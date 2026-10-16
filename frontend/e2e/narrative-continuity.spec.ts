import {test,expect} from '@playwright/test';

test('completed meeting does not restart after departure and reload',async({page,request})=>{
  const seed=await request.post('/test/continuity-seed');expect(seed.ok()).toBeTruthy();
  const selected=await seed.json();
  await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selected);
  await page.goto('/');
  await expect(page.locator('.turn').last()).toContainText('встретились в «Гвозде»');
  const input=page.getByLabel('Своё действие или реплика');
  await input.fill('Разойтись.');
  await page.getByRole('button',{name:'Отправить действие',exact:true}).click();
  await expect(page.locator('.turn').last()).toContainText('попрощались и разошлись');
  await page.reload();
  await input.fill('Осматриваюсь.');
  await page.getByRole('button',{name:'Отправить действие',exact:true}).click();
  await expect(page.locator('.turn').last()).toContainText('Илья смотрит на улицу.');
  const saved=await (await request.get(`/api/saves/${selected.save}`)).json();
  expect(saved.state.world.threads.qa_meeting.status).toBe('developing');
  expect(saved.state.world.threads.qa_meeting.state).not.toContain('ждёт');
  expect(saved.state.world.characters.qa_vera.situation).toBe('');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
});
