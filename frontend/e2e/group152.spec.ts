import {test, expect} from '@playwright/test';

for (const theme of ['graphite','parchment']) {
 test(`166 group reaction, autonomous invitation and agreement: ${theme}`,async({page,request},info)=>{
  const seed=await(await request.post('/test/group152-seed')).json();
  await request.put(`/api/worlds/${seed.world}/presentation`,{data:{theme_id:theme}});
  await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),seed);
  if(info.project.name==='mobile')await page.setViewportSize({width:360,height:800});
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.goto('/');
  const view=async()=>await(await request.get(`/api/saves/${seed.save}`)).json();
  await page.getByRole('button',{name:'Начать игру',exact:true}).click();
  await expect.poll(async()=>(await view()).job?.status).toBe('saved');
  const joined=await request.post(`/api/saves/${seed.save}/phone`,{data:{revision:(await view()).revision,
   command:{action:'join',operation_id:'join-group-152-e2e',conversation_id:'qa-group',member_ids:['qa_timur','qa_oleg']}}});
  expect(joined.ok()).toBeTruthy();
  await page.reload();
  const physical=async()=>{
   const revision=(await view()).revision;
   await page.getByLabel('Своё действие или реплика').fill('Смотрю на дождь.');
   await page.getByRole('button',{name:'Отправить действие',exact:true}).click();
   await expect.poll(async()=>(await view()).revision).toBeGreaterThan(revision);
   await expect.poll(async()=>(await view()).job.status).toBe('saved');
  };
  await page.getByRole('button',{name:/^Телефон/}).click();
  const phone=page.getByRole('region',{name:'Телефон персонажа'});
  const openGroup=async()=>{
   await phone.getByRole('button',{name:/^Переписки/}).click();
   await phone.locator('.phone-thread').filter({hasText:'Общая переписка'}).click();
  };
  await openGroup();
  await phone.getByLabel('Сообщение в телефоне').fill('Привет всем! Как ваши дела?');
  await phone.getByRole('button',{name:'Отправить сообщение',exact:true}).click();
  await expect.poll(async()=>(await view()).job.status).toBe('saved');
  await expect(phone.locator('.phone-message')).toHaveCount(4);
  await expect(phone.getByText('Тимур, здорово! Покажешь потом?',{exact:true})).toBeVisible();
  await phone.getByRole('button',{name:'Свернуть телефон'}).click();
  await physical(); // the communication source is consumed, no second reaction
  expect((await view()).state.phone.events).toHaveLength(4);
  await physical(); // spontaneous attempt after thirty world minutes
  expect((await view()).state.phone.events).toHaveLength(6);
  expect(Object.keys((await view()).state.world.scheduled_events)).toHaveLength(0);
  await expect(page.locator('.story-scroll')).not.toContainText('Покажу завтра');
  await page.getByRole('button',{name:/^Телефон/}).click();
  // Phone preserves the open conversation across folding.
  await expect(phone.getByText('Ждут твоего ответа',{exact:true})).toBeVisible();
  await expect(phone.getByText('Покажу завтра. Кирилл, ты придёшь?',{exact:true})).toBeVisible();
  await page.screenshot({path:`/tmp/group166-${theme}-${info.project.name}.png`,animations:'disabled'});
  await phone.getByLabel('Сообщение в телефоне').fill('Да, Олег, завтра приду.');
  await phone.getByRole('button',{name:'Отправить сообщение',exact:true}).click();
  await expect.poll(async()=>(await view()).job.status).toBe('saved');
  await expect(phone.getByText('Ждут твоего ответа',{exact:true})).toHaveCount(0);
  await expect(phone.locator('.phone-message')).toHaveCount(10);
  expect(Object.keys((await view()).state.world.scheduled_events)).toHaveLength(1);
  await page.reload();
  expect((await view()).state.phone.events).toHaveLength(10);
  await physical();
  expect((await view()).state.phone.events).toHaveLength(10);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
 });
}
