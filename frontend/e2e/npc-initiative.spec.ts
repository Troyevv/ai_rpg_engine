import {test,expect} from '@playwright/test';

test('NPC opens interaction without input; external refusal survives reload',async({page,request})=>{
  const seed=await request.post('/test/initiative-seed');expect(seed.ok()).toBeTruthy();
  const selected=await seed.json();
  await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selected);
  const saved=async()=> (await request.get(`/api/saves/${selected.save}`)).json();
  const before=await saved();
  await page.goto('/');
  await expect(page.locator('.turn').last()).toContainText('Побудем вечером вдвоём?');
  await expect(page.getByLabel('Своё действие или реплика')).toBeEnabled();
  await page.getByLabel('Своё действие или реплика').fill('Нет, сегодня не хочу.');
  await page.getByRole('button',{name:'Отправить действие',exact:true}).click();
  await expect(page.locator('.turn').last()).toContainText('Хорошо, тогда в другой раз');
  await page.reload();
  await expect(page.locator('.turn').last()).toContainText('Хорошо, тогда в другой раз');
  const after=await saved();
  expect(after.turns.length).toBe(before.turns.length+1);
  for(const field of ['goals','intentions','emotion'])
    expect(after.state.world.characters.qa_kirill[field]).toEqual(before.state.world.characters.qa_kirill[field]);
  expect(after.state.world.relationships).toEqual(before.state.world.relationships);
  expect(after.state.world.scheduled_events).toEqual(before.state.world.scheduled_events);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
});
