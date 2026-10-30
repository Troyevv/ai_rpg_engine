import {test,expect,type Page,type APIRequestContext} from '@playwright/test';
const phone=(page:Page)=>page.getByRole('region',{name:'Телефон персонажа'});
async function seed(page:Page,request:APIRequestContext,query='incoming=false&polish=true') {
 const selected=await(await request.post(`/test/phone-seed?${query}`)).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selected);
 await page.goto('/');await page.getByRole('button',{name:/^Телефон/}).click();return selected;
}
async function chat(page:Page){
 await phone(page).getByRole('button',{name:'Переписки',exact:true}).click();
 await phone(page).locator('.phone-thread').filter({hasText:'Вера Ларина'}).click();
}
test('158 Back, focus, drafts, groups, real timestamps and isolated scroll',async({page,request},info)=>{
 const selected=await seed(page,request);
 await phone(page).getByRole('button',{name:'Свернуть телефон'}).click();
 await page.getByLabel('Своё действие или реплика').fill('Мой основной черновик');
 await page.getByRole('button',{name:/^Телефон/}).click();
 await chat(page);
 await expect(phone(page).locator('.phone-message.incoming')).not.toHaveCount(0);
 await expect(phone(page).locator('.phone-message.outgoing')).not.toHaveCount(0);
 await expect(phone(page).locator('.phone-day')).toBeVisible();
 await phone(page).getByLabel('Сообщение в телефоне').fill('Черновик Вере');
 await page.keyboard.press('Escape');
 await expect(phone(page).locator('.phone-conversations')).toBeVisible();
 await expect(phone(page).locator('.phone-thread').filter({hasText:'Вера Ларина'})).toBeFocused();
 await phone(page).locator('.phone-thread').filter({hasText:'Общая переписка'}).click();
 await expect(phone(page).getByLabel('Сообщение в телефоне')).toHaveValue('');
 await expect(phone(page).locator('.phone-message-sender').first()).toBeVisible();
 await phone(page).getByLabel('Сообщение в телефоне').fill('Черновик группе');
 await phone(page).getByRole('button',{name:'Управление участниками'}).click();
 await page.keyboard.press('Escape');
 await expect(phone(page).getByRole('button',{name:'Управление участниками'})).toBeFocused();
 await page.goBack();await expect(phone(page).locator('.phone-conversations')).toBeVisible();
 await phone(page).locator('.phone-thread').filter({hasText:'Вера Ларина'}).click();
 await expect(phone(page).getByLabel('Сообщение в телефоне')).toHaveValue('Черновик Вере');
 await phone(page).getByRole('button',{name:'Свернуть телефон'}).click();
 await expect(page.getByLabel('Своё действие или реплика')).toHaveValue('Мой основной черновик');
 await expect(page.locator('.choices button').first()).toBeVisible();
 await page.getByRole('button',{name:/^Телефон/}).click();
 await expect(phone(page).getByLabel('Сообщение в телефоне')).toHaveValue('Черновик Вере');
 await phone(page).getByRole('button',{name:'Свернуть телефон'}).click();
 await page.reload();await page.getByRole('button',{name:/^Телефон/}).click();await chat(page);
 await expect(phone(page).getByLabel('Сообщение в телефоне')).toHaveValue('Черновик Вере');
 const save=await(await request.get(`/api/saves/${selected.save}`)).json();
 expect(save.state.phone.events.filter((e:any)=>e.content==='Черновик Вере')).toHaveLength(0);
 await page.screenshot({path:info.outputPath('chat.png'),animations:'disabled'});
});
test('158 request failure, explicit retry and rapid double submit keep one operation',async({page,request})=>{
 const selected=await seed(page,request,'incoming=false&decision=silent&strangers=true');
 await phone(page).getByLabel('Поиск адресата').fill('Вера');
 await phone(page).getByRole('button',{name:/Написать: Вера/}).click();
 const input=phone(page).getByLabel('Сообщение в телефоне');await input.fill('Один канонический текст');
 const ids:string[]=[];
 await page.route('**/phone/dispatch',async route=>{ids.push(route.request().postDataJSON().command.operation_id);await route.abort('failed')});
 const send=phone(page).getByRole('button',{name:'Отправить сообщение',exact:true});
 await send.click();await expect(phone(page).getByRole('alert')).toBeVisible();
 await expect(input).toHaveValue('Один канонический текст');await page.unroute('**/phone/dispatch');
 // A successful, unrelated mutation must not erase the uncertain send's ID.
 await phone(page).getByRole('button',{name:'К перепискам'}).click();
 await phone(page).getByRole('button',{name:'Создать группу',exact:true}).click();
 await phone(page).getByLabel('Название группы').fill('Проверка Retry');
 await phone(page).getByLabel('Вера Ларина',{exact:true}).check();
 await phone(page).getByRole('button',{name:'Создать переписку',exact:true}).click();
 await expect(phone(page).locator('.phone-thread').filter({hasText:'Проверка Retry'})).toBeVisible();
 await phone(page).getByRole('button',{name:'Контакты',exact:true}).click();
 await phone(page).getByRole('button',{name:/Написать: Вера/}).click();
 await expect(input).toHaveValue('Один канонический текст');
 await page.route('**/phone/dispatch',async route=>{ids.push(route.request().postDataJSON().command.operation_id);await route.continue()});
 await send.evaluate((el:HTMLButtonElement)=>{el.click();el.click()});
 await expect(phone(page).locator('.phone-message.outgoing')).toContainText('Один канонический текст');
 expect(ids).toHaveLength(2);expect(ids[1]).toBe(ids[0]);
 const saved=await(await request.get(`/api/saves/${selected.save}`)).json();
 expect(saved.state.phone.events.filter((e:any)=>e.content==='Один канонический текст')).toHaveLength(1);
});
test('158 responsive browser QA: skins, long text, scroll, keyboard and reduced motion',async({page,request},info)=>{
 test.setTimeout(120000);
 const selected=await seed(page,request,'incoming=false&polish=true');
 let save=await(await request.get(`/api/saves/${selected.save}`)).json();
 for(let i=0;i<10;i++){
  const response=await request.post(`/api/saves/${selected.save}/phone`,{data:{revision:save.revision,command:{action:'send',character_id:'qa_vera',operation_id:`158-long-message-${i}`,content:`${i} Длинный текст\n`+'Подробности разговора и длинноесловобезпробелов. '.repeat(20)}}});
  expect(response.ok()).toBeTruthy();save=await response.json();
 }
 const renamed=await request.post(`/api/saves/${selected.save}/phone`,{data:{revision:save.revision,command:{action:'edit_contact',contact_id:'phone-qa_kirill-qa-vera',label:'Вера Ларина — Александровна, руководитель исследовательской лаборатории',blocked:false,operation_id:'158-long-label'}}});
 expect(renamed.ok()).toBeTruthy();
 for(const [width,height,skin,zoom] of [[1440,1000,'graphite',1],[768,1024,'parchment',1],[360,800,'graphite',1],[393,850,'parchment',2]] as const){
  await request.put(`/api/worlds/${selected.world}/presentation`,{data:{theme_id:skin}});
  await page.setViewportSize({width,height});await page.emulateMedia({reducedMotion:'reduce'});await page.reload();
  await page.evaluate(z=>document.documentElement.style.fontSize=`${z*100}%`,zoom);
  await page.getByRole('button',{name:/^Телефон/}).click();await chat(page);
  await expect(phone(page).getByRole('button',{name:'Отправить сообщение',exact:true})).toBeInViewport({ratio:1});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  const layout=await phone(page).evaluate(el=>({w:el.clientWidth,overflow:el.scrollWidth,scroll:el.scrollHeight>el.clientHeight+1,bodyScroll:el.querySelector('.phone-body')!.scrollHeight>el.querySelector('.phone-body')!.clientHeight+1}));
  expect(layout.overflow).toBeLessThanOrEqual(layout.w);expect(layout.scroll).toBe(false);expect(layout.bodyScroll).toBe(false);
  const messages=phone(page).getByLabel('Сообщения',{exact:true});
  await messages.evaluate(el=>{el.scrollTop=100;el.dispatchEvent(new Event('scroll',{bubbles:true}))});
  await phone(page).getByRole('button',{name:'К перепискам'}).click();
  await phone(page).locator('.phone-thread').filter({hasText:'Вера Ларина'}).click();
  await expect.poll(()=>messages.evaluate(el=>el.scrollTop)).toBe(100);
  await page.screenshot({path:info.outputPath(`phone-${width}-${skin}.png`),animations:'disabled'});
 }
 await page.evaluate(()=>document.documentElement.style.fontSize='100%');
 await phone(page).getByLabel('Сообщение в телефоне').fill('Клавиатура и черновик');
 await page.evaluate(()=>{Object.defineProperty(visualViewport,'height',{configurable:true,value:400});visualViewport!.dispatchEvent(new Event('resize'))});
 await expect(phone(page).getByLabel('Сообщение в телефоне')).toBeInViewport({ratio:1});
 await expect(phone(page).getByRole('button',{name:'Отправить сообщение',exact:true})).toBeInViewport({ratio:1});
});

test('158 revision conflict retains draft; refresh and actor switch preserve privacy',async({page,request})=>{
 const selected=await seed(page,request,'incoming=false&decision=silent');
 await phone(page).getByRole('button',{name:'Вера работа',exact:true}).click();
 await phone(page).getByRole('button',{name:'Написать',exact:true}).click();
 const input=phone(page).getByLabel('Сообщение в телефоне');await input.fill('После конфликта');
 const before=await(await request.get(`/api/saves/${selected.save}`)).json();
 const changed=await request.post(`/api/saves/${selected.save}/phone`,{data:{revision:before.revision,command:{action:'edit_contact',contact_id:'phone-qa_kirill-qa-vera',label:'Вера работа',blocked:false,operation_id:'158-concurrent-label'}}});
 expect(changed.ok()).toBeTruthy();
 await phone(page).getByRole('button',{name:'Отправить сообщение',exact:true}).click();
 await expect(phone(page).getByRole('alert')).toBeVisible();await expect(input).toHaveValue('После конфликта');
 await phone(page).getByRole('button',{name:'Обновить состояние'}).click();
 await expect(phone(page).getByRole('alert')).toHaveCount(0);await expect(input).toHaveValue('После конфликта');
 await phone(page).getByRole('button',{name:'Отправить сообщение',exact:true}).click();
 await expect(phone(page).locator('.phone-message')).toContainText('После конфликта');
 await input.fill('Приватный черновик Кирилла');
 await phone(page).getByRole('button',{name:'Свернуть телефон'}).click();
 const {actor}=await import('./navigation');await actor(page,'qa_timur','Тимур Серов');
 await page.getByRole('button',{name:/^Телефон/}).click();
 await expect(phone(page)).not.toContainText('После конфликта');
 await phone(page).getByRole('button',{name:'Переписки',exact:true}).click();
 await expect(phone(page)).not.toContainText('После конфликта');
 expect(await phone(page).getByLabel('Сообщение в телефоне').count()).toBe(0);
});

test('158 call surface takes over Back without leaving a phantom phone screen',async({page,request})=>{
 await seed(page,request,'incoming=false&decision=answer');
 await phone(page).getByRole('button',{name:'Вера работа',exact:true}).click();
 await phone(page).getByRole('button',{name:'Позвонить',exact:true}).click();
 const call=page.getByRole('dialog',{name:'Сцена звонка'});await expect(call).toBeVisible();
 expect(await page.evaluate(()=>history.state.phoneUI)).toBeUndefined();
 await page.goBack();await expect(call).toBeHidden();
 expect(await page.evaluate(()=>history.state?.phoneUI)).toBeUndefined();
 await page.getByRole('button',{name:/^Телефон/}).click();
 await phone(page).getByRole('button',{name:'Перейти к разговору'}).click();
 await expect(call).toBeVisible();expect(await page.evaluate(()=>history.state.phoneUI)).toBeUndefined();
 await call.getByRole('button',{name:'Завершить звонок',exact:true}).click();await expect(call).toHaveCount(0);
 await expect(page.locator('.choices button').first()).toBeVisible();
});
