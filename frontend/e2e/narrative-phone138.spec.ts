import {test,expect} from '@playwright/test';

for (const theme of ['graphite','parchment']) {
 test(`138 narrative message and incoming call: ${theme}`,async({page,request},info)=>{
  test.setTimeout(120000);
  if(info.project.name==='mobile')await page.setViewportSize({width:360,height:800});
  await page.emulateMedia({reducedMotion:'reduce'});
  const seed=await(await request.post('/test/narrative-phone138-seed')).json();
  await request.put(`/api/worlds/${seed.world}/presentation`,{data:{theme_id:theme}});
  await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),seed);
  await page.goto('/');
  const view=async()=>await(await request.get(`/api/saves/${seed.save}`)).json();
  await page.getByRole('button',{name:'Начать игру',exact:true}).click();
  await expect.poll(async()=>(await view()).job?.status).toBe('saved');
  const initial=await view();
  expect(initial.state.phone.events).toHaveLength(0);
  const input=page.getByLabel('Своё действие или реплика');
  const physical=async(text:string)=>{
   const revision=(await view()).revision;
   await input.fill(text);await page.getByRole('button',{name:'Отправить действие',exact:true}).click();
   await expect.poll(async()=>(await view()).revision).toBeGreaterThan(revision);
   await expect.poll(async()=>(await view()).job.status).toBe('saved');
  };
  await physical('Посмотреть на дождь.');
  const delivered=await view();const message=delivered.state.phone.events[0];
  expect(message.unread).toBe(true);expect(message.content).toBeNull();
  expect(delivered.state.world_clock.minute).toBe(initial.state.world_clock.minute+1);
  await expect(page.locator('.story-scroll')).toContainText('Ты завтра свободен?');
  await page.getByRole('button',{name:/^Телефон/}).click();
  const phone=page.getByRole('region',{name:'Телефон персонажа'});
  await phone.getByRole('button',{name:'Катя',exact:true}).click();
  await phone.getByRole('button',{name:'Написать',exact:true}).click();
  await expect(phone.getByText('Ты завтра свободен?',{exact:true})).toBeVisible();
  await expect.poll(async()=>(await view()).state.phone.events[0].unread).toBe(false);
  await phone.getByLabel('Сообщение в телефоне').fill('Да, свободен.');
  await phone.getByRole('button',{name:'Отправить сообщение',exact:true}).click();
  await expect(phone.getByText('Да, свободен.',{exact:true})).toBeVisible();
  await expect.poll(async()=>(await view()).job.status).toBe('saved');
  await phone.getByRole('button',{name:'Свернуть телефон'}).click();
  await physical('Поставить чашку на стол.');
  const ringing=await view();
  expect(ringing.state.phone.events.filter((e:any)=>e.channel==='VOICE_CALL')).toHaveLength(1);
  expect(ringing.state.phone.events.find((e:any)=>e.channel==='VOICE_CALL').status).toBe('ringing');
  expect(ringing.state.world.characters.qa_vera.location_id).toBe(initial.state.world.characters.qa_vera.location_id);
  expect(ringing.state.scene_meta.present_ids).toEqual(initial.state.scene_meta.present_ids);
  await page.getByRole('button',{name:/^Телефон/}).click();
  await phone.getByRole('button',{name:'Звонки',exact:true}).click();
  await expect(phone.getByRole('button',{name:'Отклонить',exact:true})).toBeVisible();
  await expect(phone.getByRole('button',{name:'Игнорировать',exact:true})).toBeVisible();
  await page.screenshot({path:`test-results/phone138-${theme}-${info.project.name}-ringing.png`,animations:'disabled'});
  await phone.getByRole('button',{name:'Ответить',exact:true}).click();
  const call=page.getByRole('dialog',{name:'Сцена звонка'});
  await expect(call).toBeVisible();
  for(const text of ['Встретимся через час?','Я скоро освобожусь.','Тогда до встречи.']){
   const revision=(await view()).revision;
   await call.getByLabel('Реплика в звонке').fill(text);await call.getByLabel('Сказать собеседнику').click();
   await expect.poll(async()=>(await view()).revision).toBeGreaterThan(revision);
   await expect.poll(async()=>(await view()).job.status).toBe('saved');
  }
  await expect(call).toHaveCount(0);
  const ended=await view();
  expect(ended.state.phone.events).toHaveLength(3);
  expect(ended.state.phone.events.find((e:any)=>e.channel==='VOICE_CALL').status).toBe('ended');
  expect(ended.state.world.scheduled_events['office-meeting'].status).toBe('pending');
  await expect(page.locator('.story-scroll')).toContainText('Ты завтра свободен?');
  await page.reload();await expect(input).toBeEnabled();
  await physical('Продолжить обычную сцену.');
  const final=await view();expect(final.state.phone.events).toEqual(ended.state.phone.events);
  expect(final.state.world.scheduled_events['office-meeting']).toEqual(ended.state.world.scheduled_events['office-meeting']);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
  await page.screenshot({path:`test-results/phone138-${theme}-${info.project.name}-final.png`,animations:'disabled'});
 });
}
