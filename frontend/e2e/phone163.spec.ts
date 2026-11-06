import {test,expect} from '@playwright/test';
import {nav} from './navigation';

for (const mode of ['new_place','unknown_place']) test(`163 ${mode}: exchange, calendar and reload`,async({page,request},info)=>{
 const s=await(await request.post(`/test/phone-seed?incoming=false&decision=${mode}`)).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);
 await page.goto('/');
 const state=async()=>await(await request.get(`/api/saves/${s.save}`)).json();
 await expect(page.getByLabel('Своё действие или реплика')).toBeEnabled();
 const source=(await state()).physical_choice_source;
 await page.getByRole('button',{name:/^Телефон/}).click();
 const phone=page.getByRole('region',{name:'Телефон персонажа'});
 await phone.getByRole('button',{name:'Вера работа',exact:true}).click();
 await phone.getByRole('button',{name:'Написать',exact:true}).click();
 await phone.getByLabel('Сообщение в телефоне').fill('Встретимся через два часа?');
 await phone.getByRole('button',{name:'Отправить сообщение',exact:true}).click();
 await expect.poll(async()=>(await state()).job?.status).toBe('saved');
 await expect(phone.locator('.phone-message.incoming')).toHaveCount(1);
 await expect(phone.locator('.phone-message.outgoing')).toHaveCount(1);
 await expect.poll(async()=>Object.keys((await state()).state.world.scheduled_events).length).toBe(mode==='new_place'?1:0);
 const after=await state();
 expect(after.physical_choice_source).toEqual(source);
 if(mode==='new_place') expect(Object.values(after.state.world.scheduled_events).map((e:any)=>e.location_id)).toEqual(['cafe-lipa']);
 else {
  const requests=await(await request.get(`/api/saves/${s.save}/accounting`)).json();
  // API/UI completion must not represent failed interpretation as NPC refusal.
  expect(after.job.error).toBeFalsy();
  expect(JSON.stringify(requests)).toContain('remote_semantics_repair');
 }
 await phone.getByRole('button',{name:'Свернуть телефон'}).click();
 await nav(page,'Календарь');
 if(mode==='new_place') await expect(page.locator('.save-workspace')).toContainText('Встреча по договорённости');
 else await expect(page.locator('.save-workspace')).not.toContainText('Встреча по договорённости');
 await page.screenshot({path:`/tmp/phone163-${mode}-${info.project.name}.png`,animations:'disabled'});
 await page.reload();
 await expect(page.getByLabel('Своё действие или реплика')).toBeEnabled();
 const loaded=await state();
 expect(loaded.state.world.scheduled_events).toEqual(after.state.world.scheduled_events);
 expect(loaded.state.phone.events).toHaveLength(2);
 expect(loaded.state.world_clock).toEqual(after.state.world_clock);
});
