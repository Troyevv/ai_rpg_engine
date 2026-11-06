import {test,expect,type Page,type APIRequestContext} from '@playwright/test';

async function start(page:Page,request:APIRequestContext,failSemantic=false) {
 const seed=await(await request.post(`/test/group152-seed?fail_semantic=${failSemantic}`)).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),seed);
 await page.goto('/');
 const view=async()=>await(await request.get(`/api/saves/${seed.save}`)).json();
 await page.getByRole('button',{name:'Начать игру',exact:true}).click();
 await expect.poll(async()=>(await view()).job?.status).toBe('saved');
 const join=await request.post(`/api/saves/${seed.save}/phone`,{data:{revision:(await view()).revision,
  command:{action:'join',operation_id:'arrivals-join',conversation_id:'qa-group',member_ids:['qa_timur','qa_oleg']}}});
 expect(join.ok()).toBeTruthy();
 const other=await request.post(`/api/saves/${seed.save}/phone`,{data:{revision:(await view()).revision,
  command:{action:'create_group',operation_id:'arrivals-other',label:'Другая группа',member_ids:['qa_vera','qa_oleg']}}});
 expect(other.ok()).toBeTruthy();await page.reload();
 await page.getByRole('button',{name:/^Телефон/}).click();
 const phone=page.getByRole('region',{name:'Телефон персонажа'});
 const openGroup=async()=>{
  await phone.getByRole('button',{name:/^Переписки/}).click();
  await phone.locator('.phone-thread').filter({hasText:'Общая переписка'}).click();
 };
 await openGroup();
 const send=async(text='Привет, как у вас дела?')=>{
  await phone.getByLabel('Сообщение в телефоне').fill(text);
  await phone.getByRole('button',{name:'Отправить сообщение',exact:true}).click();
 };
 return {seed,phone,view,send,openGroup};
}

// Observe the real DOM before dispatch, rather than racing the worker or
// replacing API responses. Each row contains canonical event IDs and DOM time.
async function watch(page:Page,leave?:string) {
 await page.evaluate(leave=>{
  const w=window as any;w.arrivalLog=[];
  const node=document.querySelector('.phone-messages')!;
  let previous='';
  w.arrivalObserver=new MutationObserver(()=>{
   const ids=Array.from(node.querySelectorAll('.phone-message.incoming')).map(e=>e.getAttribute('data-event-id'));
   if(ids.join()===previous)return;previous=ids.join();
   w.arrivalLog.push({ids,at:performance.now()});
   if(leave&&ids.length===1)(document.querySelector(`[aria-label="${leave}"]`) as HTMLButtonElement).click();
  });
  w.arrivalObserver.observe(node,{childList:true,subtree:true});
 },leave);
}

test('fresh group replies arrive in order; long text preserves scroll; reload shows saved history immediately',async({page,request},info)=>{
 await page.emulateMedia({reducedMotion:'no-preference'});
 const {phone,view,send,openGroup}=await start(page,request);await watch(page);await send();
 await expect(phone.locator('.phone-message')).toHaveCount(4);
 const log=await page.evaluate(()=>(window as any).arrivalLog);
 expect(log.map((r:any)=>r.ids.length)).toEqual([1,2,3]);
 expect(log[1].at-log[0].at).toBeGreaterThan(150);expect(log[2].at-log[1].at).toBeGreaterThan(150);
 expect(log[2].at-log[0].at).toBeLessThan(3000);
 const saved=await view();const rows=saved.state.phone.events.filter((e:any)=>e.conversation_id==='qa-group');
 expect(await phone.locator('[data-event-id]').evaluateAll(els=>els.map(e=>e.getAttribute('data-event-id')))).toEqual(rows.map((e:any)=>e.id));
 expect(new Set(rows.slice(1).map((e:any)=>e.world_time)).size).toBe(1);
 expect(new Set(rows.slice(1).map((e:any)=>e.sender.id)).size).toBe(3);
 await send('Расскажи подробнее про фотографии.');
 await expect(phone.locator('.phone-message')).toHaveCount(8);
 // There is now genuinely scrollable old history. New bubbles must not pull it down.
 await phone.locator('.phone-messages').evaluate(el=>{el.scrollTop=0;el.dispatchEvent(new Event('scroll',{bubbles:true}))});
 await send();
 await expect(phone.locator('.phone-message')).toHaveCount(12);
 await expect.poll(()=>phone.locator('.phone-messages').evaluate(el=>el.scrollTop)).toBe(0);
 const full=await view();const long=full.state.phone.events.find((e:any)=>e.content?.startsWith('Фотография 1:'));
 expect(long.content.length).toBeGreaterThan(2000);
 expect(await phone.locator(`[data-event-id="${long.id}"] p`).textContent()).toBe(long.content);
 await page.screenshot({path:`/tmp/phone-arrivals-${info.project.name}.png`});
 await page.reload();await page.getByRole('button',{name:/^Телефон/}).click();await openGroup();
 await expect(phone.locator('.phone-message')).toHaveCount(12);
 await expect(phone.locator('.phone-message-arrival')).toHaveCount(0);
 expect((await view()).state.phone.events.map((e:any)=>e.id)).toEqual(full.state.phone.events.map((e:any)=>e.id));
});

for(const leave of ['Свернуть телефон','К перепискам']) {
 test(`leaving during a series flushes presentation: ${leave}`,async({page,request})=>{
  await page.emulateMedia({reducedMotion:'no-preference'});
  const {phone,view,send}=await start(page,request);await watch(page,leave);await send();
  await expect.poll(async()=>(await page.evaluate(()=>(window as any).arrivalLog)).length).toBeGreaterThan(0);
  if(leave==='Свернуть телефон') {
   await expect(phone).toBeHidden();await page.getByRole('button',{name:/^Телефон/}).click();
  } else {
   await expect(phone.locator('.phone-conversations')).toBeVisible();
   // Actually visit another chat, then return to the group.
   await phone.locator('.phone-thread').filter({hasNotText:'Общая переписка'}).first().click();
   await phone.getByRole('button',{name:'К перепискам',exact:true}).click();
   await phone.locator('.phone-thread').filter({hasText:'Общая переписка'}).click();
  }
  await expect(phone.locator('.phone-message')).toHaveCount(4);
  await expect(phone.locator('.phone-message-arrival')).toHaveCount(0);
  expect((await view()).state.phone.events.filter((e:any)=>e.conversation_id==='qa-group')).toHaveLength(4);
 });
}

test('reduced motion reveals the complete new series without stagger or motion',async({page,request})=>{
 await page.emulateMedia({reducedMotion:'reduce'});
 const {phone,send}=await start(page,request);await watch(page);await send();
 await expect(phone.locator('.phone-message')).toHaveCount(4);
 const log=await page.evaluate(()=>(window as any).arrivalLog);
 expect(log.map((r:any)=>r.ids.length)).toEqual([3]);
 await expect(phone.locator('.phone-message-arrival')).toHaveCount(0);
});


test('Retry reuses the group author, publishes one series and never replays it after reload',async({page,request})=>{
 await page.emulateMedia({reducedMotion:'no-preference'});
 const {phone,view,send,openGroup}=await start(page,request,true);
 await watch(page);await send();
 await expect(phone.getByRole('button',{name:'Повторить',exact:true})).toBeVisible();
 await expect(phone.locator('.phone-message')).toHaveCount(1);
 const failed=await view();expect(failed.job.status).toBe('error');
 await phone.getByRole('button',{name:'Повторить',exact:true}).click();
 await expect(phone.locator('.phone-message')).toHaveCount(4);
 const saved=await view();expect(saved.job.status).toBe('saved');
 expect(new Set(saved.state.phone.events.map((e:any)=>e.id)).size).toBe(4);
 expect((await page.evaluate(()=>(window as any).arrivalLog)).map((r:any)=>r.ids.length)).toEqual([1,2,3]);
 await page.reload();await page.getByRole('button',{name:/^Телефон/}).click();await openGroup();
 await expect(phone.locator('.phone-message')).toHaveCount(4);
 await expect(phone.locator('.phone-message-arrival')).toHaveCount(0);
});
