import {test,expect} from '@playwright/test';
import {mkdirSync,writeFileSync} from 'node:fs';
import {nav,pickCharacter} from './navigation';
import {join} from 'node:path';
test.use({video:'on'});
const baseline=process.env.PHONE122_BASELINE==='1';
for(const theme of ['graphite','parchment']){
 test(`122 ${theme}: canonical meeting and separate call with preserved draft`,async({page,request},info)=>{
  if(info.project.name==='mobile')await page.setViewportSize({width:theme==='graphite'?360:393,height:800});
  const selected=await(await request.post('/test/phone-seed?incoming=false&decision=meeting')).json();
  await request.put(`/api/worlds/${selected.world}/presentation`,{data:{theme_id:theme}});
  await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selected);
  await page.goto('/');
  const story=page.locator('.story-scroll');
  const mainInput=page.getByLabel('Своё действие или реплика');
  await expect(mainInput).toBeEnabled();
  await mainInput.fill('Мой черновик основной сцены');
  const original=await story.locator('.turn').count();
  const screen=page.getByRole('region',{name:'Телефон персонажа'});
  const evidence=process.env.PHONE122_EVIDENCE;
  const capture=async(name:string)=>{
   if(!evidence)return;
   mkdirSync(evidence,{recursive:true});
   const prefix=`${baseline?'before':'after'}-${info.project.name}-${theme}-${name}`;
   await page.screenshot({path:join(evidence,`${prefix}.png`),animations:'disabled'});
   const s=await(await request.get(`/api/saves/${selected.save}`)).json();
   writeFileSync(join(evidence,`${prefix}.json`),JSON.stringify({revision:s.revision,clock:s.state.world_clock,plans:s.state.world.scheduled_events,phone:s.state.phone,turns:s.turns.map((t:any)=>({kind:t.kind,presentation:t.presentation,assistant_text:t.assistant_text}))},null,2));
  };
  await page.getByRole('button',{name:/^Телефон/}).click();
  await screen.getByRole('button',{name:'Вера работа',exact:true}).click();
  await screen.getByRole('button',{name:'Написать',exact:true}).click();
  await screen.getByLabel('Сообщение в телефоне').fill('Встретимся через два часа?');
  await screen.getByRole('button',{name:'Отправить сообщение',exact:true}).click();
  await expect(screen.getByText('Да, договорились.',{exact:true})).toBeVisible();
  await expect.poll(async()=>{const s=await(await request.get(`/api/saves/${selected.save}`)).json();return s.job?.status}).toBe('saved');
  if(!baseline){
   await expect(story.locator('.turn')).toHaveCount(original);
   await expect(story).not.toContainText('Обработка сообщения');
   await expect.poll(async()=>{const s=await(await request.get(`/api/saves/${selected.save}`)).json();return Object.keys(s.state.world.scheduled_events).length}).toBe(1);
  }
  await capture('message');
  await screen.getByRole('button',{name:'Свернуть телефон'}).click();
  await nav(page,'Календарь');
  if(!baseline)await expect(page.locator('.save-workspace')).toContainText('Встреча по договорённости');
  await capture('calendar');await page.keyboard.press('Escape');
  if(!baseline){
   await nav(page,'Персонажи');
   for(const id of ['qa_kirill','qa_vera']){await pickCharacter(page,id);await page.getByRole('tab',{name:'Личность',exact:true}).click();await expect(page.locator('.dossier-panel')).toContainText('Встреча по договорённости')}
   await capture('participant');await page.keyboard.press('Escape');
  }
  await page.getByRole('button',{name:/^Телефон/}).click();
  await screen.getByRole('button',{name:'Контакты',exact:true}).click();
  await screen.getByRole('button',{name:'Позвонить',exact:true}).click();
  if(baseline){
   await expect(screen.getByRole('button',{name:'Перейти к разговору'})).toBeVisible();
   await screen.getByRole('button',{name:'Перейти к разговору'}).click();
   await mainInput.fill('Алло, Вера, как дела?');
   await mainInput.press('Control+Enter');
   await expect(story).toContainText('Вера отвечает по телефону');
   await capture('call');
   await page.getByRole('button',{name:/^Телефон/}).click();
   await screen.getByRole('button',{name:'Завершить разговор',exact:true}).click();
   await page.keyboard.press('Escape');
  }else{
   const call=page.getByRole('dialog',{name:'Сцена звонка'});
   await expect(call).toBeVisible();
   await call.getByLabel('Реплика в звонке').fill('Алло, Вера, как дела?');
   await expect(call.getByLabel('Сказать собеседнику')).toBeEnabled();
   await call.getByLabel('Сказать собеседнику').click();
   await expect(call).toContainText('Вера отвечает по телефону');
   await expect(call.getByRole('button',{name:'Завершить звонок',exact:true})).toBeEnabled();
   await expect(story).not.toContainText('Вера отвечает по телефону');
   await call.getByLabel('Реплика в звонке').fill('Черновик разговора');
   await capture('call');
   await call.getByLabel('Свернуть звонок').click();
   await expect(mainInput).toHaveValue('Мой черновик основной сцены');
   await page.getByRole('button',{name:/Вернуться к звонку/}).click();
   await expect(call.getByLabel('Реплика в звонке')).toHaveValue('Черновик разговора');
   await call.getByRole('button',{name:'Завершить звонок',exact:true}).click();
   await expect(call).toHaveCount(0);
   await expect(mainInput).toHaveValue('Мой черновик основной сцены');
  }
  await capture('return');
  await page.reload();
  if(!baseline){
   await expect(mainInput).toHaveValue('Мой черновик основной сцены');
   await expect(story).not.toContainText('Вера отвечает по телефону');
   await expect(story).not.toContainText('Обработка сообщения');
  }
  await mainInput.fill('Посмотреть в окно');
  await page.getByRole('button',{name:'Отправить действие',exact:true}).click();
  await expect(story).toContainText('В комнате тихо');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 });
}

test('122 ten sequential messages leave no phone cards or story mutations',async({page,request})=>{
 const s=await(await request.post('/test/phone-seed?incoming=false&decision=answer')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);await page.goto('/');
 const story=page.locator('.story-scroll');await expect(story.locator('.turn')).toHaveCount(1);
 const text=(await story.locator('.narrative-text').allTextContents()).map(s=>s.trim());
 await page.getByRole('button',{name:/^Телефон/}).click();const phone=page.getByRole('region',{name:'Телефон персонажа'});
 await phone.getByRole('button',{name:'Вера работа',exact:true}).click();await phone.getByRole('button',{name:'Написать',exact:true}).click();
 for(let i=0;i<10;i++){
  await phone.getByLabel('Сообщение в телефоне').fill(`Сообщение ${i+1}. Подробности разговора.`);
  await phone.getByRole('button',{name:'Отправить сообщение',exact:true}).click();
  await expect.poll(async()=>{const x=await(await request.get(`/api/saves/${s.save}`)).json();return x.job?.status==='saved'?x.state.phone.events.filter((e:any)=>e.channel==='TEXT_MESSAGE').length:-1}).toBe(2*(i+1));
  await expect(story.locator('.turn')).toHaveCount(1);await expect(story.locator('.pending-turn')).toHaveCount(0);
  expect((await story.locator('.narrative-text').allTextContents()).map(s=>s.trim())).toEqual(text);
 }
 const after=await(await request.get(`/api/saves/${s.save}`)).json();expect(after.state.phone.events.filter((e:any)=>e.channel==='TEXT_MESSAGE')).toHaveLength(20);
});
