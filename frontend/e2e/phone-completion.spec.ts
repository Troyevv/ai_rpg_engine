import {test,expect} from '@playwright/test';
test.use({video:'on'});
const screen=(page:any)=>page.getByRole('region',{name:'Телефон персонажа'});
async function seed(page:any,request:any,query='incoming=false&decision=answer'){
 const selected=await(await request.post(`/test/phone-seed?${query}`)).json();
 await page.addInitScript((s:any)=>localStorage.setItem('selection',JSON.stringify(s)),selected);
 await page.goto('/');
 await expect(page.getByLabel('Своё действие или реплика')).toBeEnabled();
 return selected;
}
async function openContact(page:any){
 await page.getByRole('button',{name:/^Телефон/}).click();
 await screen(page).getByRole('button',{name:'Контакты',exact:true}).click();
 await screen(page).getByRole('button',{name:'Вера работа',exact:true}).click();
}
test('T15 T18 outgoing call and automatic read reply through real jobs',async({page,request},info)=>{
 if(info.project.name==='mobile')await page.setViewportSize({width:360,height:800});
 const selected=await seed(page,request);
 const before=await(await request.get(`/api/saves/${selected.save}`)).json();
 await page.getByLabel('Своё действие или реплика').fill('Алло, Вера, ты меня слышишь?');
 await openContact(page);
 await page.screenshot({path:info.outputPath('contact-after.png'),animations:'disabled'});
 await screen(page).getByRole('button',{name:'Позвонить',exact:true}).click();
 await expect(screen(page).getByRole('button',{name:'Перейти к разговору'})).toBeVisible();
 await expect(page.getByLabel('Канал действия')).toHaveValue('call');
 await page.screenshot({path:info.outputPath('call-active-after.png'),animations:'disabled'});
 await screen(page).getByRole('button',{name:'Перейти к разговору'}).click();
 await expect(page.getByLabel('Своё действие или реплика')).toHaveValue('Алло, Вера, ты меня слышишь?');
 await expect(page.getByLabel('Своё действие или реплика')).toBeEnabled();
 await page.getByLabel('Своё действие или реплика').press('Control+Enter');
 await expect(page.locator('.story-scroll').getByText('Вера отвечает по телефону:',{exact:false})).toBeVisible();
 await expect(page.getByLabel('Своё действие или реплика')).toBeEnabled();
 await page.getByLabel('Канал действия').selectOption('physical');
 await expect(page.getByLabel('Канал действия')).toHaveValue('physical');
 await page.getByLabel('Канал действия').selectOption('call');
 await page.getByRole('button',{name:/^Телефон/}).click();
 await screen(page).getByRole('button',{name:'Завершить разговор',exact:true}).click();
 await expect(page.getByLabel('Канал действия')).toHaveCount(0);
 await screen(page).getByRole('button',{name:'Контакты',exact:true}).click();
 await screen(page).getByRole('button',{name:'Написать',exact:true}).click();
 await screen(page).getByLabel('Сообщение в телефоне').fill('Встретимся завтра?');
 await screen(page).getByRole('button',{name:'Отправить сообщение',exact:true}).click();
 await expect(screen(page).getByText('Да, увидимся завтра. Напиши, когда освободишься.',{exact:true})).toBeVisible();
 await expect(screen(page).getByText('Прочитано: 1 из 1')).toBeVisible();
 await page.screenshot({path:info.outputPath('chat-reply-after.png'),animations:'disabled'});
 await screen(page).getByLabel('Сообщение в телефоне').fill('Ещё один черновик');
 await page.keyboard.press('Escape');
 await page.reload();
 await page.getByRole('button',{name:/^Телефон/}).click();
 await screen(page).getByRole('button',{name:'Переписки',exact:true}).click();
 await screen(page).getByRole('button').filter({hasText:'Вера работа'}).click();
 await expect(screen(page).getByLabel('Сообщение в телефоне')).toHaveValue('Ещё один черновик');
 const after=await(await request.get(`/api/saves/${selected.save}`)).json();
 expect(after.state.scene.location).toEqual(before.state.scene.location);
 expect(after.state.phone.events.filter((e:any)=>e.channel==='VOICE_CALL')[0].status).toBe('ended');
 expect(after.state.phone.events.filter((e:any)=>e.channel==='TEXT_MESSAGE')).toHaveLength(2);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

for(const [mode,status] of [['decline','Отклонён'],['silent','Пропущен']] as const){
 test(`T16 ${mode} completes without a manual turn`,async({page,request},info)=>{
  await seed(page,request,`incoming=false&decision=${mode}`);await openContact(page);
  await screen(page).getByRole('button',{name:'Позвонить',exact:true}).click();
  await expect(screen(page).getByText(new RegExp(`Исходящий · ${status}`))).toBeVisible();
  await expect(screen(page).getByLabel('Текущий звонок')).toHaveCount(0);
  await expect(page.getByLabel('Своё действие или реплика')).toBeEnabled();
  await page.screenshot({path:info.outputPath(`call-${mode}-after.png`),animations:'disabled'});
 });
}

test('T19 read without reply stops and explicit wait is bounded',async({page,request})=>{
 const selected=await seed(page,request,'incoming=false&decision=read_only');await openContact(page);
 await screen(page).getByRole('button',{name:'Написать',exact:true}).click();
 await screen(page).getByLabel('Сообщение в телефоне').fill('Напиши, когда будет удобно.');
 await screen(page).getByRole('button',{name:'Отправить сообщение',exact:true}).click();
 await expect(screen(page).getByText('Прочитано: 1 из 1')).toBeVisible();
 const wait=screen(page).getByRole('button',{name:'Подождать ещё · 1 мин'});await expect(wait).toBeEnabled();
 const before=await(await request.get(`/api/saves/${selected.save}`)).json();
 await wait.click();
 await expect.poll(async()=> (await(await request.get(`/api/saves/${selected.save}`)).json()).revision).toBe(before.revision+1);
 await expect(wait).toBeEnabled();
 const after=await(await request.get(`/api/saves/${selected.save}`)).json();
 expect(after.state.phone.events).toHaveLength(1);
 expect(after.revision).toBe(before.revision+1);
});

test('T22 provider failure retains send, retry/reload does not resend',async({page,request})=>{
 const s=await seed(page,request,'incoming=false&decision=error_once');await openContact(page);
 await screen(page).getByRole('button',{name:'Написать',exact:true}).click();
 await screen(page).getByLabel('Сообщение в телефоне').fill('Сообщение при ошибке провайдера.');
 const sent=page.waitForRequest(r=>r.url().endsWith('/phone/dispatch'));
 await screen(page).getByRole('button',{name:'Отправить сообщение',exact:true}).click();
 const body=(await sent).postDataJSON();
 const duplicate=await request.post(`/api/saves/${s.save}/phone/dispatch`,{data:body});expect(duplicate.ok()).toBe(true);
 await expect(screen(page).getByRole('button',{name:'Повторить обработку',exact:true})).toBeVisible();
 await page.reload();await page.getByRole('button',{name:/^Телефон/}).click();
 await screen(page).getByRole('button',{name:'Повторить обработку',exact:true}).click();
 await screen(page).getByRole('button',{name:'Переписки',exact:true}).click();
 await screen(page).getByRole('button').filter({hasText:'Вера работа'}).click();
 await expect(screen(page).getByText('Да, увидимся завтра. Напиши, когда освободишься.',{exact:true})).toBeVisible();
 const after=await(await request.get(`/api/saves/${s.save}`)).json();expect(after.state.phone.events.filter((e:any)=>e.outgoing)).toHaveLength(1);
 expect(after.turns.filter((t:any)=>t.kind==='communication')).toHaveLength(1);
});

test('T14 T17 T25 incoming call preserves physical turn and phone draft in two skins',async({page,request},info)=>{
 if(info.project.name==='mobile')await page.setViewportSize({width:360,height:800});
 let s=await seed(page,request,'incoming=true&unread=true&decision=answer');
 for(const skin of ['graphite','parchment']){
  if(skin==='parchment')s=await seed(page,request,'incoming=true&unread=true&decision=answer');
  await request.put(`/api/worlds/${s.world}/presentation`,{data:{theme_id:skin}});await page.goto('/');
  await page.getByRole('button',{name:/^Телефон/}).click();
  await expect(screen(page).getByRole('button',{name:'Ответить',exact:true})).toBeVisible();
  await page.screenshot({path:info.outputPath(`phone-incoming-${skin}-after.png`),animations:'disabled'});
  await screen(page).getByRole('button',{name:'Контакты',exact:true}).click();
  await page.screenshot({path:info.outputPath(`phone-contacts-${skin}-after.png`),animations:'disabled'});
  await screen(page).getByRole('button',{name:'Вера работа',exact:true}).click();
  await screen(page).getByRole('button',{name:'Написать',exact:true}).click();
  await expect(screen(page).getByText('Прочти, когда будет удобно.',{exact:true})).toBeVisible();
  await screen(page).getByLabel('Сообщение в телефоне').fill('Черновик на время входящего вызова');
  await page.screenshot({path:info.outputPath(`phone-chat-${skin}-after.png`),animations:'disabled'});
  await screen(page).getByRole('button',{name:'Звонки',exact:true}).click();
  await screen(page).getByRole('button',{name:'Переписки',exact:true}).click();
  await expect(screen(page).getByLabel('Сообщение в телефоне')).toHaveValue('Черновик на время входящего вызова');
  await page.keyboard.press('Escape');
 }
 await page.getByLabel('Своё действие или реплика').fill('Смотрю в окно, не отвечая на звонок.');
 await page.getByLabel('Своё действие или реплика').press('Control+Enter');
 await expect(page.getByLabel('Своё действие или реплика')).toBeEnabled();
 await page.getByRole('button',{name:/^Телефон/}).click();
 await screen(page).getByRole('button',{name:'Звонки',exact:true}).click();
 await expect(screen(page).getByRole('button',{name:'Ответить',exact:true})).toBeVisible();
 await screen(page).getByRole('button',{name:'Ответить',exact:true}).click();
 await expect(page.getByLabel('Канал действия')).toHaveValue('call');
 await screen(page).getByRole('button',{name:'Перейти к разговору'}).click();
 await page.getByLabel('Канал действия').selectOption('physical');await expect(page.getByLabel('Канал действия')).toHaveValue('physical');
 await page.getByLabel('Канал действия').selectOption('call');await page.getByRole('button',{name:/^Телефон/}).click();
 await screen(page).getByRole('button',{name:'Завершить разговор',exact:true}).click();
 await expect(page.getByLabel('Канал действия')).toHaveCount(0);
 await screen(page).getByRole('button',{name:'Переписки',exact:true}).click();
 await expect(screen(page).getByLabel('Сообщение в телефоне')).toBeVisible();
 await page.setViewportSize({width:393,height:500});await page.emulateMedia({reducedMotion:'reduce'});
 await screen(page).getByLabel('Сообщение в телефоне').focus();
 await expect(screen(page).getByLabel('Сообщение в телефоне')).toBeInViewport();
 await expect(screen(page).getByRole('button',{name:'Отправить сообщение',exact:true})).toBeInViewport();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:info.outputPath('phone-keyboard-after.png'),animations:'disabled'});
});
