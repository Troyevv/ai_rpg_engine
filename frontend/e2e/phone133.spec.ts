import {test,expect} from '@playwright/test';
import {mkdirSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {diagnostics} from './navigation';
test.use({video:'on'});
const baseline=process.env.PHONE133_BASELINE==='1';
for(const theme of ['graphite','parchment'])test(`133 A B E F ${theme}: messages, choices, call and continuation`,async({page,request},info)=>{
 test.setTimeout(120000);
 if(info.project.name==='mobile')await page.setViewportSize({width:theme==='graphite'?360:393,height:800});
 const s=await(await request.post('/test/phone-seed?incoming=false&decision=greeting')).json();
 await request.put(`/api/worlds/${s.world}/presentation`,{data:{theme_id:theme}});
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);await page.goto('/');
 const state=async()=>await(await request.get(`/api/saves/${s.save}`)).json();
 const main=page.getByLabel('Своё действие или реплика'), story=page.locator('.story-scroll');
 await expect(page.locator('.choices button').first()).toBeVisible();
 await main.fill('Посмотреть в окно');await page.getByRole('button',{name:'Отправить действие',exact:true}).click();
 await expect(story.locator('.turn')).toHaveCount(2);
 await expect(main).toBeEnabled();
 await expect(page.locator('.choices button').first()).toBeVisible();
 const choices=await page.locator('.choices button strong').allTextContents();expect(choices.length).toBeGreaterThan(0);
 const source=(await state()).physical_choice_source;
 await main.fill('Черновик основной сцены');
 const check=async()=>{if(!baseline){await expect.poll(()=>page.locator('.choices button strong').allTextContents()).toEqual(choices);expect((await state()).physical_choice_source).toEqual(source)}};
 const capture=async(name:string)=>{const dir=process.env.PHONE133_EVIDENCE;if(!dir)return;mkdirSync(dir,{recursive:true});const prefix=`${baseline?'before':'after'}-${info.project.name}-${theme}-${name}`;await page.screenshot({path:join(dir,prefix+'.png'),animations:'disabled'});const x=await state();writeFileSync(join(dir,prefix+'.json'),JSON.stringify({clock:x.state.world_clock,source:x.physical_choice_source,events:x.state.phone.events,turns:x.turns.map((t:any)=>({id:t.id,kind:t.kind,choices:t.choices,presentation:t.presentation}))},null,2))};
 const phone=page.getByRole('region',{name:'Телефон персонажа'});
 await page.getByRole('button',{name:/^Телефон/}).click();await phone.getByRole('button',{name:'Вера работа',exact:true}).click();await phone.getByRole('button',{name:'Написать',exact:true}).click();
 for(let i=0;i<2;i++){
  await phone.getByLabel('Сообщение в телефоне').fill(i?'Спасибо. Напишу позже.':'Привет. Ты занята сегодня?');
  await phone.getByRole('button',{name:'Отправить сообщение',exact:true}).click();
  await expect.poll(async()=>{const x=await state();return x.job?.status==='saved'?x.state.phone.events.filter((e:any)=>e.channel==='TEXT_MESSAGE').length:-1}).toBe(2*(i+1));
  await expect(phone.getByText('Привет. Ещё в офисе, разгребаю бумаги. А что, есть планы?',{exact:true}).first()).toBeVisible();
  await check();
 }
 if(!baseline){await expect(phone).not.toContainText(/История обработки|диагностика|Технические|решений за цикл|remote_semantics/);await expect(phone.locator('pre')).toHaveCount(0)}
 await capture('messages');await phone.getByRole('button',{name:'Свернуть телефон'}).click();await check();
 await expect(main).toHaveValue('Черновик основной сцены');await capture('choices');
 await page.getByRole('button',{name:/^Телефон/}).click();await phone.getByRole('button',{name:'Контакты',exact:true}).click();await phone.getByRole('button',{name:'Позвонить',exact:true}).click();
 const call=page.getByRole('dialog',{name:'Сцена звонка'});await expect(call).toBeVisible();await check();
 await call.getByLabel('Реплика в звонке').fill('Алло, слышишь меня?');await call.getByLabel('Сказать собеседнику').click();
 await expect(call).toContainText('Вера отвечает по телефону');await expect(call.getByRole('button',{name:'Завершить звонок',exact:true})).toBeEnabled();await check();
 if(!baseline){await expect(call).not.toContainText(/Контекст \/ usage|Вариант|Время хода/);await expect(story).not.toContainText('Вера отвечает по телефону')}
 await capture('call');await call.getByLabel('Свернуть звонок').click();await check();await expect(main).toHaveValue('Черновик основной сцены');
 await page.getByRole('button',{name:/Вернуться к звонку/}).click();await call.getByRole('button',{name:'Завершить звонок',exact:true}).click();await expect(call).toHaveCount(0);await check();
 await expect(main).toHaveValue('Черновик основной сцены');await capture('return');
 if(!baseline){
  await diagnostics(page);await page.getByRole('tab',{name:'История и восстановление'}).click();
  await expect(page.locator('.diagnostics').getByRole('button',{name:'Контекст / usage',exact:true}).first()).toBeVisible();
  await page.locator('.dialog-content .dialog-close').click();
 }
 await main.fill('Посмотреть в окно');await page.getByRole('button',{name:'Отправить действие',exact:true}).click();await expect(story.locator('.turn')).toHaveCount(3);await expect(main).toBeEnabled();
 await page.reload();await expect(page.locator('.choices button').first()).toBeVisible();
 await main.fill('Продолжить осмотр');await page.getByRole('button',{name:'Отправить действие',exact:true}).click();await expect(story.locator('.turn')).toHaveCount(4);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('133 D: semantic failure and Retry preserve one response, one minute and choices',async({page,request})=>{
 test.skip(baseline,'Recovery assertion for the fixed UI.');
 const s=await(await request.post('/test/phone-seed?incoming=false&decision=semantic_error_once')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);await page.goto('/');
 const state=async()=>await(await request.get(`/api/saves/${s.save}`)).json();const before=await state();
 const phone=page.getByRole('region',{name:'Телефон персонажа'});
 await page.getByRole('button',{name:/^Телефон/}).click();await phone.getByRole('button',{name:'Вера работа',exact:true}).click();await phone.getByRole('button',{name:'Написать',exact:true}).click();
 await phone.getByLabel('Сообщение в телефоне').fill('Привет. Ты занята сегодня?');await phone.getByRole('button',{name:'Отправить сообщение',exact:true}).click();
 await expect(phone.getByRole('button',{name:'Повторить',exact:true})).toBeVisible();
 const failed=await state();expect(failed.state.world_clock.minute).toBe(before.state.world_clock.minute);expect(failed.physical_choice_source).toEqual(before.physical_choice_source);
 await expect(phone).not.toContainText(/Controlled semantic|remote_semantics|Технические подробности/);
 await page.reload();await page.getByRole('button',{name:/^Телефон/}).click();
 await phone.getByRole('button',{name:'Переписки',exact:true}).click();await phone.getByRole('button').filter({hasText:'Вера работа'}).click();
 await phone.getByRole('button',{name:'Повторить',exact:true}).click();
 await expect.poll(async()=>{const x=await state();return x.job?.status}).toBe('saved');
 const after=await state();expect(after.state.phone.events).toHaveLength(2);expect(after.state.world_clock.minute).toBe(before.state.world_clock.minute+1);expect(after.physical_choice_source).toEqual(before.physical_choice_source);
 const accounting=await(await request.get(`/api/saves/${s.save}/accounting`)).json();
 const rows=accounting.requests.filter((r:any)=>r.job_id===after.job.id);
 expect(rows.filter((r:any)=>r.stage==='remote_initiative')).toHaveLength(2);
 expect(rows.filter((r:any)=>r.stage==='remote_semantics')).toHaveLength(2);
});

test('133 canonical agency repair commits once without narrative confirmation',async({page,request})=>{
 const s=await(await request.post('/test/phone-seed?incoming=false&decision=agency_missing_once')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);await page.goto('/');
 const state=async()=>await(await request.get(`/api/saves/${s.save}`)).json();
 const before=await state();
 await page.getByRole('button',{name:/^Телефон/}).click();const phone=page.getByRole('region',{name:'Телефон персонажа'});
 await phone.getByRole('button',{name:'Вера работа',exact:true}).click();await phone.getByRole('button',{name:'Написать',exact:true}).click();
 await phone.getByLabel('Сообщение в телефоне').fill('Встретимся через два часа?');await phone.getByRole('button',{name:'Отправить сообщение',exact:true}).click();
 await expect.poll(async()=>(await state()).job?.status).toBe('saved');
 await expect.poll(async()=>Object.keys((await state()).state.world.scheduled_events).length).toBe(1);
 await expect(phone).not.toContainText(/controlled_actor_unsupported|Семантическая проверка/);
 const after=await state();expect(after.state.phone.events).toHaveLength(2);expect(after.state.world_clock.minute).toBe(before.state.world_clock.minute+1);
 await expect(page.locator('.story-scroll .turn')).toHaveCount(1);
 const accounting=await(await request.get(`/api/saves/${s.save}/accounting`)).json();
 const rows=accounting.requests.filter((r:any)=>r.job_id===after.job.id);
 expect(rows.filter((r:any)=>r.stage==='remote_initiative')).toHaveLength(2);
 expect(rows.filter((r:any)=>r.stage==='remote_semantics')).toHaveLength(1);
 expect(rows.filter((r:any)=>r.stage==='remote_semantics_repair')).toHaveLength(1);
 await page.reload();expect((await state()).state.phone.events).toHaveLength(2);
 expect(Object.keys((await state()).state.world.scheduled_events)).toHaveLength(1);
});
