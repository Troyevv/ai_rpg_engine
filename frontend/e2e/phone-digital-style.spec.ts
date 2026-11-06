import {test,expect} from '@playwright/test';

// Deliberately authored fixture content, NOT a requirement on model output.
const text='Да 🙂 / okay... 👩🏽‍💻 ❤️ — e\u0301\n\n'+'Русский + English; без шаблона!.. '.repeat(90);
for(const group of [false,true]) {
 test(`literal Unicode survives ${group?'group':'direct'} author, Retry and reload`,async({page,request},info)=>{
  const seed=await(await request.post('/test/group152-seed?digital_style=true&fail_semantic=true')).json();
  await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),seed);
  await page.goto('/');
  const view=async()=>await(await request.get(`/api/saves/${seed.save}`)).json();
  await page.getByRole('button',{name:'Начать игру',exact:true}).click();
  await expect.poll(async()=>(await view()).job?.status).toBe('saved');
  if(group){
   const joined=await request.post(`/api/saves/${seed.save}/phone`,{data:{revision:(await view()).revision,
    command:{action:'join',operation_id:'unicode-join',conversation_id:'qa-group',member_ids:['qa_timur','qa_oleg']}}});
   expect(joined.ok()).toBeTruthy();
  }
  await page.reload();await page.getByRole('button',{name:/^Телефон/}).click();
  const phone=page.getByRole('region',{name:'Телефон персонажа'});
  const openHistory=async()=>{
   await phone.getByRole('button',{name:/^Переписки/}).click();
   await phone.locator('.phone-thread').filter({hasText:group?'Общая переписка':'Вера работа'}).click();
  };
  if(group)await openHistory();
  else {
   await phone.getByRole('button',{name:'Вера работа',exact:true}).click();
   await phone.getByRole('button',{name:'Написать',exact:true}).click();
  }
  const outgoing='Привет! Are you there?.. 👋🏽';
  await phone.getByLabel('Сообщение в телефоне').fill(outgoing);
  await phone.getByRole('button',{name:'Отправить сообщение',exact:true}).click();
  await expect(phone.getByRole('button',{name:'Повторить',exact:true})).toBeVisible();
  await expect(phone.locator('.phone-message')).toHaveCount(1);
  await phone.getByRole('button',{name:'Повторить',exact:true}).click();
  await expect(phone.locator('.phone-message')).toHaveCount(group?4:2);
  const saved=await view();expect(saved.job.status).toBe('saved');
  const rows=saved.state.phone.events;
  expect(rows[0].content).toBe(outgoing);expect(rows[1].content).toBe(text);
  expect(await phone.locator(`[data-event-id="${rows[1].id}"] p`).textContent()).toBe(text);
  if(group)expect(rows[2].content).toBe('Понял. Обсудим позже.');
  const usage=await(await request.get(`/api/saves/${seed.save}/accounting`)).json();
  const attempts=usage.requests.filter((r:any)=>r.job_id===saved.job.id);
  expect(attempts.filter((r:any)=>r.stage==='remote_initiative')).toHaveLength(group?1:2);
  expect(attempts.filter((r:any)=>r.stage==='remote_semantics')).toHaveLength(2);
  await page.reload();await page.getByRole('button',{name:/^Телефон/}).click();await openHistory();
  await expect(phone.locator('.phone-message')).toHaveCount(group?4:2);
  await expect(phone.locator('.phone-message-arrival')).toHaveCount(0);
  expect(await phone.locator(`[data-event-id="${rows[1].id}"] p`).textContent()).toBe(text);
  const all=await view();expect(all.state.phone.events.map((e:any)=>e.id)).toEqual(rows.map((e:any)=>e.id));
  await phone.locator(`[data-event-id="${rows[1].id}"]`).evaluate(el=>el.scrollIntoView({block:'start'}));
  await page.screenshot({path:`/tmp/digital-style-${group?'group':'direct'}-${info.project.name}.png`});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
 });
}
