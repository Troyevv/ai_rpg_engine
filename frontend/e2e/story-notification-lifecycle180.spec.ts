import {test,expect,type Page,type APIRequestContext} from '@playwright/test';
import {nav,pickCharacter} from './navigation';
const toast=(page:Page)=>page.locator('.story-toast');
const view=async(request:APIRequestContext,s:any)=>(await request.get(`/api/saves/${s.save}`)).json();
async function setup(page:Page,request:APIRequestContext,theme:string){
 const s=await(await request.post('/test/story168-seed')).json();
 await request.put(`/api/worlds/${s.world}/presentation`,{data:{theme_id:theme}});
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify({world:s.world,save:s.save})),s);
 await page.goto('/');await expect(page.getByLabel('Своё действие или реплика')).toBeVisible();return s;
}
async function turn(page:Page,request:APIRequestContext,s:any){
 await request.post(`/test/story168-prepare/${s.save}`);
 await page.getByLabel('Своё действие или реплика').fill('Расскажи о рукописи.');
 await page.getByRole('button',{name:'Отправить действие',exact:true}).click();
 await expect(toast(page)).toBeVisible();return view(request,s);
}
async function dossier(page:Page){await nav(page,'Персонажи');await pickCharacter(page,'qa_vera');await page.getByRole('tab',{name:'Тайны',exact:true}).click()}
async function acknowledged(page:Page,s:any,id:string,kind='toast'){
 return page.evaluate(({s,id,kind})=>localStorage.getItem(`story-presentation-v1:${s.save}:qa_kirill:${kind}:${id}`)==='1',{s,id,kind});
}
async function dismiss(page:Page,id:string){await expect(toast(page)).toHaveAttribute('data-notice-id',id);await toast(page).getByRole('button',{name:'Скрыть уведомление'}).click()}
for(const theme of ['graphite','parchment']){
 test(`visible deliveries survive phone, inactive workspace and reload, then settle once: ${theme}`,async({page,request})=>{
  test.setTimeout(90000);const s=await setup(page,request,theme);
  const after=await turn(page,request,s),events=after.state.notification_history;
  expect(events).toHaveLength(3);await expect(toast(page)).toHaveAttribute('data-notice-id',events[0].id);
  await expect(toast(page)).toContainText('Вера тайно написала роман.');
  expect(await acknowledged(page,s,events[0].id)).toBe(false);
  await page.locator('.phone-peek').click();await expect(page.locator('.phone-device')).toHaveClass(/is-open/);
  await expect(toast(page)).toHaveCount(0);
  await page.waitForTimeout(6800); // Exceeds the real delivery interval while covered.
  expect(await acknowledged(page,s,events[0].id)).toBe(false);
  await page.getByRole('region',{name:'Телефон персонажа'}).getByRole('button',{name:'Свернуть телефон',exact:true}).click();
  await expect(toast(page)).toHaveAttribute('data-notice-id',events[0].id);
  // Leaving the app unmounts Game, including the pending presentation queue.
  await page.goto('/offline.html');
  await expect(toast(page)).toHaveCount(0);
  expect(await acknowledged(page,s,events[0].id)).toBe(false);
  await page.goto('/');
  await expect(toast(page)).toHaveAttribute('data-notice-id',events[0].id);
  await nav(page,'Календарь');await expect(page.locator('.save-workspace')).toBeVisible();await expect(toast(page)).toHaveCount(0);
  expect(await acknowledged(page,s,events[0].id)).toBe(false);
  await page.reload();await expect(toast(page)).toHaveAttribute('data-notice-id',events[0].id);
  await dismiss(page,events[0].id);await dismiss(page,events[1].id);
  await expect(toast(page)).toHaveAttribute('data-notice-id',events[2].id);
  await page.mouse.move(0,0);await page.getByLabel('Своё действие или реплика').focus();
  await expect(toast(page)).toHaveCount(0,{timeout:10000});
  for(const e of events)expect(await acknowledged(page,s,e.id)).toBe(true);
  await page.reload();await expect(page.getByRole('button',{name:'История уведомлений, 3',exact:true})).toBeVisible();await expect(toast(page)).toHaveCount(0);
  await page.getByRole('button',{name:'История уведомлений, 3',exact:true}).click();await expect(page.locator('.story-journal-list li')).toHaveCount(3);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 });
 test(`first mount after canonical commit and interrupted first fog view: ${theme}`,async({page,request})=>{
  const s=await setup(page,request,theme);await nav(page,'Создать');
  const before=await view(request,s);
  const read=await request.post(`/api/saves/${s.save}/phone`,{data:{revision:before.revision,command:{action:'read',event_id:s.event,operation_id:'late-mount180'}}});expect(read.ok(),await read.text()).toBe(true);
  const after=await read.json(),event=after.state.notification_history[0];
  await page.reload(); // First notification component receiving this committed event.
  await expect(toast(page)).toHaveAttribute('data-notice-id',event.id);
  await toast(page).getByRole('button',{name:'Подробнее'}).click();
  await expect(page.locator('.secret-entry.is-revealing')).toHaveCount(1);
  await page.goBack();expect(await acknowledged(page,s,event.id,'fog')).toBe(false);
  await page.reload();await expect(toast(page)).toHaveCount(0);await dossier(page);
  await expect(page.locator('.secret-entry.is-revealing')).toHaveCount(1);
  await expect(page.locator('.secret-entry.is-revealing')).toHaveCount(0);
  expect(await acknowledged(page,s,event.id,'fog')).toBe(true);
  await page.reload();await dossier(page);await expect(page.locator('.secret-entry.is-revealing')).toHaveCount(0);
  expect(await page.content()).not.toContain('NEVER-EXPOSE');
 });
}
test('actor, regenerated siblings and rollback use current membership and independent presentation receipts',async({page,request})=>{
 test.setTimeout(120000);const s=await setup(page,request,'graphite'),original=await turn(page,request,s);
 const events=original.state.notification_history,tid=original.turns.at(-1).id,variant=original.turns.at(-1).active_variant_id;
 // Commit the real control command directly so the mobile pointer does not wait
 // behind the popup until its entire 3-item queue has naturally completed.
 const control=async(operation:string,actor_id?:string)=>{
  const before=await view(request,s);
  const r=await request.post(`/api/saves/${s.save}/protagonist`,{data:{revision:before.revision,operation,actor_id,operation_id:`control180-${before.revision}`}});
  expect(r.ok(),await r.text()).toBe(true);await page.reload();
 };
 await control('temporary','qa_timur');await expect(toast(page)).toHaveCount(0);
 expect((await view(request,s)).state.notification_history).toEqual([]);
 await dossier(page);await expect(page.locator('.secret-entry.is-revealing')).toHaveCount(0);await expect(page.locator('.secret-browser:visible')).not.toContainText('Вера тайно написала роман.');
 await control('resume');
 for(const e of events)await dismiss(page,e.id);
 await request.post(`/test/story168-prepare/${s.save}?reveal=false&target_turn_id=${tid}`);
 await page.locator('.turn').last().getByRole('button',{name:'Ещё вариант'}).click();
 await expect(toast(page)).toContainText('Новая сюжетная линия');
 const sibling=await view(request,s),other=sibling.state.notification_history[0],siblingVariant=sibling.turns.at(-1).active_variant_id;
 expect(sibling.state.notification_history).toHaveLength(1);expect(events.map((e:any)=>e.id)).not.toContain(other.id);
 await dossier(page);await expect(page.locator('.secret-entry.is-revealing')).toHaveCount(0);await expect(page.locator('.secret-browser:visible')).not.toContainText('Вера тайно написала роман.');
 const choose=async(id:string)=>{const current=await view(request,s);const r=await request.post(`/api/saves/${s.save}/turns/${tid}/variant`,{data:{revision:current.revision,variant_id:id}});expect(r.ok(),await r.text()).toBe(true);await page.reload()};
 await choose(variant);await expect(page.getByRole('button',{name:'История уведомлений, 3',exact:true})).toBeVisible();await expect(toast(page)).toHaveCount(0);
 await dossier(page);await expect(page.locator('.secret-entry.is-revealing')).toHaveCount(1);await expect(page.locator('.secret-entry.is-revealing')).toHaveCount(0);
 await choose(siblingVariant);await expect(toast(page)).toHaveAttribute('data-notice-id',other.id);await dismiss(page,other.id);
 const current=await view(request,s);const rollback=await request.post(`/api/saves/${s.save}/rollback`,{data:{revision:current.revision}});expect(rollback.ok(),await rollback.text()).toBe(true);
 await page.reload();await expect(page.getByRole('button',{name:'История уведомлений, 0',exact:true})).toBeVisible();await expect(toast(page)).toHaveCount(0);
 await dossier(page);await expect(page.locator('.secret-entry.is-revealing')).toHaveCount(0);await expect(page.locator('.secret-browser:visible')).not.toContainText('Вера тайно написала роман.');
 await page.goBack();const fresh=await turn(page,request,s);expect(events.map((e:any)=>e.id)).not.toContain(fresh.state.notification_history[0].id);
 await toast(page).getByRole('button',{name:'Подробнее'}).click();await expect(page.locator('.secret-entry.is-revealing')).toHaveCount(1);await expect(page.locator('.secret-entry.is-revealing')).toHaveCount(0);
 expect(JSON.stringify(await view(request,s))).not.toContain('NEVER-EXPOSE');
});
