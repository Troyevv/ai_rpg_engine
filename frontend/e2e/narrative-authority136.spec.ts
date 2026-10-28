import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {defaults} from '../src/types';
import {diagnostics} from './navigation';

for (const scenario of ['entry','doorway','optional-annotation','semantic-retry']) {
 test(`scene authority 136 ${scenario}: real jobs turn reload turn`,async({page,request},info)=>{
  const source=JSON.parse(readFileSync(new URL('../../tests/fixtures/runtime_handoff/world.json',import.meta.url),'utf8'));
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  const w=await(await request.post('/api/workspaces',{data:{name:`Arrival134 ${scenario}`}})).json();
  expect((await request.post(`/api/workspaces/${w.id}/draft/import`,{data:{revision:w.revision,text:JSON.stringify(source),format:'json'}})).ok()).toBeTruthy();
  const d=await(await request.get(`/api/workspaces/${w.id}/draft?author=true`)).json();
  const selected=await(await request.post(`/api/workspaces/${w.id}/draft/confirm`,{data:{revision:d.revision,version_id:d.version_id,accept_warnings:true}})).json();
  const profile=`arrival134-${info.project.name}-${scenario}`;
  await request.put(`/api/settings/${profile}`,{data:{...defaults,game:{...defaults.game,model:'handoff-test',context_length:131072,max_tokens:2000,update_tokens:4096}}});
  await page.addInitScript(({selected,profile})=>{localStorage.setItem('selection',JSON.stringify(selected));localStorage.setItem('profile',profile);},{selected,profile});
  const view=async()=> (await(await request.get(`/api/saves/${selected.save}`)).json());
  const first=await view();
  await request.post(`/test/runtime-handoff-provider?scenario=${scenario}`);
  let calls:{narratives:number;extractions:number}|undefined;
  try {
   await page.goto('/');await page.getByRole('button',{name:'Начать игру',exact:true}).click();
   if(scenario==='semantic-retry') {
    await expect(page.getByRole('button',{name:'Повторить обработку состояния',exact:true})).toBeEnabled();
    const rejected=await view();expect(rejected.turns).toHaveLength(0);
    expect(rejected.state.world.characters.viktoria_solovyova.life_status).toBe('alive');
    await page.reload();
    await page.getByRole('button',{name:'Повторить обработку состояния',exact:true}).click();
   }
   await expect(page.locator('.turn')).toHaveCount(1,{timeout:30000});
   const accepted=await view();const job=await(await request.get(`/api/jobs/${accepted.job.id}`)).json();
   expect(job.status).toBe('saved');const text=job.narrative;
   expect(text).toContain(scenario==='doorway'?'Виктория стоит в проёме':'вошла внутрь');
   expect(accepted.state.scene_meta.present_ids).toEqual(scenario==='doorway'?['ilya']:['ilya','viktoria_solovyova']);
   expect(accepted.state.world.characters.viktoria_solovyova.life_status).toBe('alive');
   if(scenario==='optional-annotation')expect(job.warnings.some((w:{code:string})=>w.code==='initiative_knowledge_invalid')).toBe(true);
   if(scenario==='semantic-retry')expect(job.warnings.some((w:{code:string;section:string})=>w.code==='extraction_revised'&&w.section==='life_changes')).toBe(true);
   if(scenario==='semantic-retry') {
    await diagnostics(page);
    const dialog=page.getByRole('dialog');
    await dialog.getByRole('tab',{name:'Производительность',exact:true}).click();
    await expect(dialog.locator('section.delta-warnings')).toContainText('Применён исправленный результат Extraction.');
    await expect(dialog.locator('section.delta-warnings')).not.toContainText('Запись отброшена.');
    await page.keyboard.press('Escape');
   }
   if(scenario==='doorway') {
    expect(accepted.state.scene_meta.observed_ids).toEqual(['viktoria_solovyova']);
    expect(accepted.state.world.characters.viktoria_solovyova.location_id).toBe(first.state.world.characters.viktoria_solovyova.location_id);
   }
   await page.locator('.choices button').filter({hasText:'Ждать ответа'}).click();
   await expect(page.locator('.turn')).toHaveCount(2);
   await page.reload();await expect(page.locator('.turn')).toHaveCount(2);
   await page.locator('.choices button').filter({hasText:'Ждать ответа'}).click();
   await expect(page.locator('.turn')).toHaveCount(3);
   const last=await view();expect(last.state.characters).toHaveLength(19);
   expect(last.state.world_clock.minute).toBe(first.state.world_clock.minute+3);
   for(const [id,c] of Object.entries(first.state.world.characters) as [string,{location_id:string}][]) {
    if(id!=='viktoria_solovyova')expect(last.state.world.characters[id].location_id).toBe(c.location_id);
   }
   expect(last.turns[0].assistant_text).toBe(text);
   await page.screenshot({path:`test-results/authority136-${scenario}-${info.project.name}.png`,fullPage:true,animations:'disabled'});
   expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
  } finally {
   calls=await(await request.post('/test/runtime-handoff-provider?enabled=false')).json();
  }
  expect(calls?.narratives).toBe(3);expect(calls?.extractions).toBe(scenario==='semantic-retry'?5:3);
  expect(errors).toEqual([]);
 });
}

test('136 complete journey: arrival, interaction, threshold, call, agreement, reload, next turn',async({page,request},info)=>{
 test.setTimeout(120000);
 const seed=await(await request.post('/test/phone-seed?incoming=false&decision=office-authority136')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),seed);
 await page.goto('/');
 const view=async()=>await(await request.get(`/api/saves/${seed.save}`)).json();
 const initial=await view();
 expect(initial.job.status).toBe('saved');
 expect(initial.state.scene_meta.present_ids).toContain('qa_marina');
 expect(initial.state.world.characters.qa_marina.location_id).toBe(initial.state.world.characters.qa_kirill.location_id);
 const input=page.getByLabel('Своё действие или реплика');
 const physical=async(text:string)=>{
  const previous=(await view()).revision;
  await input.fill(text);await page.getByRole('button',{name:'Отправить действие',exact:true}).click();
  await expect.poll(async()=>(await view()).revision).toBeGreaterThan(previous);
  await expect(input).toBeEnabled();
 };
 await physical('Спрашиваю, как дела.');
 expect((await view()).state.scene_meta.present_ids).toContain('qa_marina');
 await physical('Подождать у двери.');
 const threshold=await view();
 expect(threshold.state.scene_meta.observed_ids).toEqual(['qa_marina']);
 expect(threshold.state.world.characters.qa_marina.location_id).toBeNull();
 await page.getByRole('button',{name:/^Телефон/}).click();
 const phone=page.getByRole('region',{name:'Телефон персонажа'});
 await phone.getByRole('button',{name:'Катя',exact:true}).click();
 await phone.getByRole('button',{name:'Позвонить',exact:true}).click();
 const call=page.getByRole('dialog',{name:'Сцена звонка'});await expect(call).toBeVisible();
 const speech=async(text:string)=>{
  await call.getByLabel('Реплика в звонке').fill(text);
  await call.getByLabel('Сказать собеседнику').click();
  await expect.poll(async()=>(await view()).job.status).toBe('saved');
 };
 await speech('Встретимся через час?');
 await expect(call).toContainText('Да, договорились');
 await speech('Тогда до встречи.');await expect(call).toHaveCount(0);
 const agreed=await view();expect(agreed.state.world.scheduled_events['office-meeting'].status).toBe('pending');
 expect(agreed.state.scene_meta.present_ids).not.toContain('qa_vera');
 await page.reload();await expect(input).toBeEnabled();
 expect((await view()).state.world.scheduled_events).toEqual(agreed.state.world.scheduled_events);
 await physical('Продолжить после звонка.');
 const after=await view();expect(after.job.status).toBe('saved');
 expect(after.state.scene_meta.observed_ids).toEqual(['qa_marina']);
 expect(after.state.world.scheduled_events['office-meeting']).toEqual(agreed.state.world.scheduled_events['office-meeting']);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:`test-results/authority136-journey-${info.project.name}.png`,fullPage:true,animations:'disabled'});
});
