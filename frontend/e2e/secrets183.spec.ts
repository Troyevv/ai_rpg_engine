import {test,expect,type Page,type APIRequestContext} from '@playwright/test';
import {nav,pickCharacter} from './navigation';
const SONYA='Соня несколько лет влюблена в Илью.', MAXIM='Максим тайно готовит продажу семейного дома.', OWN='Илья выпускает музыку под псевдонимом.', WORLD='Под городом скрыта древняя обсерватория.';
const area=(p:Page)=>p.locator('.inspector-workspace');
const control=(p:Page)=>area(p).getByRole('switch',{name:'Показать спойлеры'});
async function dossier(p:Page,id:string){await nav(p,'Персонажи');await pickCharacter(p,id);await area(p).getByRole('tab',{name:'Тайны',exact:true}).click()}
async function view(r:APIRequestContext,s:any){return (await r.get(`/api/saves/${s.save}`)).json()}
async function setup(p:Page,r:APIRequestContext,theme='graphite'){
 const w=await(await r.post('/api/workspaces',{data:{name:'Secrets183'}})).json();
 expect((await r.post(`/test/secret183-candidate/${w.id}`)).ok()).toBe(true);
 const path=`/api/workspaces/${w.id}/draft`,d=await(await r.get(path+'?author=true')).json();
 const response=await r.post(path+'/confirm',{data:{revision:d.revision,version_id:d.version_id,accept_warnings:true}});
 expect(response.ok(),await response.text()).toBe(true);const s=await response.json();
 await r.put(`/api/worlds/${s.world}/presentation`,{data:{theme_id:theme}});
 await p.addInitScript(s=>localStorage.setItem('selection',JSON.stringify({world:s.world,save:s.save})),s);
 await p.goto('/');return s;
}
async function clean(p:Page){
 const html=await p.content();for(const value of [SONYA,MAXIM,WORLD,'fact_sonya_love','fact_maxim_sale','private183','world183','AUTHOR_EVIDENCE_181'])expect(html).not.toContain(value);
}
// Keep the real server projection; hold only delivery so loading/cancel cannot
// accidentally be tested after a fast local response has already arrived.
async function delaySpoilers(p:Page){
 let release!:()=>void, started!:()=>void;
 const received=new Promise<void>(resolve=>started=resolve), gate=new Promise<void>(resolve=>release=resolve);
 await p.route('**/story-secret-spoilers?**',async route=>{
  const response=await route.fetch();started();await gate;
  // The user may cancel or navigate away while this response is held.
  await route.fulfill({response}).catch(()=>{});
 },{times:1});
 return {received,release};
}
for(const theme of ['graphite','parchment'])test(`explicit spoiler scopes, reset, search and canonical knowledge: ${theme}`,async({page,request})=>{
 test.setTimeout(120000);const s=await setup(page,request,theme),before=await view(request,s);
 const canonical=await(await request.get(`/api/saves/${s.save}/author-state`)).json();
 let calls=0;page.on('request',r=>{if(r.url().includes('story-secret-spoilers'))calls++});
 await dossier(page,'ilya');await expect(area(page)).toContainText('Мои тайны');await expect(area(page)).toContainText(OWN);await expect(area(page)).toContainText('Неизвестное обо мне');
 await expect(page.locator('.secret-browser:visible .secret-entry.is-revealing')).toHaveCount(0);await clean(page);expect(calls).toBe(0);
 await control(page).click();await expect(area(page)).toContainText(SONYA);await expect(area(page)).toContainText('Спойлер · ГГ не знает');
 await dossier(page,'sonya');await expect(control(page)).toHaveAttribute('aria-checked','false');await clean(page);
 const bitmap=()=>page.locator('.secret-browser:visible .secret-entry.is-hidden canvas').first().evaluate((c:HTMLCanvasElement)=>c.toDataURL());
 const frame=await bitmap();await expect.poll(bitmap).not.toBe(frame);
 await control(page).focus();await page.keyboard.press('Space');await expect(area(page)).toContainText(SONYA);
 await expect(area(page)).toContainText(MAXIM);await expect(area(page)).toContainText('ГГ только подозревает');await expect(area(page)).not.toContainText(WORLD);
 await expect(area(page)).toContainText('Спойлеры включены');await expect(page.locator('.secret-browser:visible .secret-entry.is-revealing')).toHaveCount(0);
 if(process.env.SECRET183_VISUAL)await page.screenshot({path:`/tmp/183-${theme}-${test.info().project.name}-spoilers.png`});
 await control(page).click();await clean(page);await expect(page.locator('.secret-browser:visible .secret-entry.is-hidden')).toHaveCount(2);
 await nav(page,'Тайны');await expect(control(page)).toHaveAttribute('aria-checked','false');await clean(page);
 const search=area(page).getByRole('textbox',{name:'Поиск тайн'});
 await search.fill('Соня');await expect(page.locator('.secret-browser:visible .secret-entry')).toHaveCount(0);await search.fill('');
 await control(page).click();await expect(area(page)).toContainText(WORLD);await expect(area(page).getByText(MAXIM,{exact:true})).toHaveCount(1);
 await search.fill('обсерватория');await expect(page.locator('.secret-browser:visible .secret-entry')).toHaveCount(1);
 await expect(area(page)).toContainText('Конец длинной тайны 183.');
 expect(await area(page).locator('.secret-browser:visible .secret-prose').evaluate(e=>e.scrollHeight>e.clientHeight)).toBe(true);
 await control(page).click();await expect(search).toHaveValue('');await clean(page);
 await control(page).click();await expect(area(page)).toContainText(WORLD);await page.reload();await nav(page,'Тайны');await expect(control(page)).toHaveAttribute('aria-checked','false');await clean(page);
 expect((await view(request,s)).state.world.knowledge).toEqual(before.state.world.knowledge);
 expect(await(await request.get(`/api/saves/${s.save}/author-state`)).json()).toEqual(canonical);
 const storage=await page.evaluate(()=>JSON.stringify([localStorage,sessionStorage]));for(const text of [SONYA,MAXIM,WORLD])expect(storage).not.toContain(text);
 // Real actor commands, not mocked projections. Reload verifies durable ownership.
 for(const [operation,actor] of [['temporary','sonya'],['temporary','ilya'],['observe','sonya'],['resume','ilya']]){
  const v=await view(request,s);const response=await request.post(`/api/saves/${s.save}/protagonist`,{data:{revision:v.revision,operation,actor_id:actor,operation_id:`control183-${v.revision}`}});
  expect(response.ok(),await response.text()).toBe(true);await page.reload();await dossier(page,actor);
  await expect(control(page)).toHaveAttribute('aria-checked','false');
  if(operation==='temporary'&&actor==='sonya'){await expect(area(page)).toContainText(SONYA);await expect(area(page)).toContainText('Мои тайны');await expect(area(page)).not.toContainText(MAXIM)}
  else await clean(page);
  expect((await view(request,s)).state.notification_history).toHaveLength(0);
 }
 await page.emulateMedia({reducedMotion:'reduce'});await dossier(page,'sonya');await expect(page.locator('[data-fog-active=true]')).toHaveCount(0);
 await control(page).click();await expect(area(page)).toContainText(SONYA);
 await expect(area(page).locator('.is-preview-revealing, [data-fog-active=true]')).toHaveCount(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('spoiler fog disperses over the same card without collapsing the list or consuming a reveal',async({page,request})=>{
 const s=await setup(page,request);await dossier(page,'sonya');
 const browser=area(page).locator('.secret-browser:visible'), toggle=control(page);
 const first=browser.locator('.secret-entry.is-hidden').first();
 await expect(first).toBeVisible();await toggle.focus();
 const slotId=await first.getAttribute('data-secret-id');
 expect(slotId).toBeTruthy();
 const card=browser.locator(`[data-secret-id="${slotId}"]`);
 const top=()=>card.evaluate(e=>e.getBoundingClientRect().top);
 const previousTop=await top(), previousHeight=await card.evaluate(e=>e.getBoundingClientRect().height);
 const delayed=await delaySpoilers(page);
 await toggle.press('Space');await delayed.received;
 try {
  // Before the network reply there is still a full, anonymous, fogged card.
  await expect(card.locator('canvas')).toBeVisible();await expect(toggle).toBeFocused();await clean(page);
  expect(Math.abs((await top())-previousTop)).toBeLessThanOrEqual(2);
  expect(await card.evaluate(e=>e.getBoundingClientRect().height)).toBe(previousHeight);
 } finally { delayed.release(); }
 await expect(card).toHaveClass(/is-preview-revealing/);
 expect(Math.abs((await top())-previousTop)).toBeLessThanOrEqual(4);
 await expect(toggle).toBeFocused();
 // Inspect the actual painted canvas during the dissolve: the opaque base veil
 // must become translucent. An idle fog canvas or a CSS-only fade cannot pass.
 const alphaSamples=new Set<number>();
 await expect.poll(async()=>{
  const alpha=await card.locator('canvas').evaluateAll(nodes=>
   (nodes[0] as HTMLCanvasElement|undefined)?.getContext('2d')?.getImageData(0,0,1,1).data[3]);
  if(alpha!==undefined && alpha>0 && alpha<235)alphaSamples.add(alpha);
  return alphaSamples.size;
 },{intervals:[50,80,100],timeout:4000}).toBeGreaterThan(1);
 const sale=browser.locator('.secret-entry').filter({hasText:MAXIM});
 await expect(sale).toContainText(/Знают[\s:]*Максим/);
 await expect(sale).toContainText(/Подозревают[\s:]*Илья/);
 await expect(card.locator('canvas')).toHaveCount(0);
 await expect(browser.locator('.is-revealing')).toHaveCount(0);
 expect(await page.evaluate(()=>Object.keys(localStorage).filter(k=>k.includes(':fog:')))).toEqual([]);
 await toggle.press('Space');
 await expect(card).toHaveClass(/is-hidden/);await clean(page);
 await expect(browser.locator('.secret-entry').filter({hasText:/Максим|Соня|Илья|Подозревают|Знают/})).toHaveCount(0);
 expect((await view(request,s)).state.notification_history).toHaveLength(0);
});

test('late responses, cancel, scope change, failure and retry cannot restore author data',async({page,request})=>{
 const s=await setup(page,request);await dossier(page,'sonya');
 let release!:()=>void;
 async function hold(){
  const delayed=await delaySpoilers(page);release=delayed.release;
  await control(page).click();await delayed.received;
 }
 await hold();await control(page).click();release();await expect(control(page)).toHaveAttribute('aria-checked','false');await clean(page);
 await hold();await dossier(page,'ilya');release();await expect(control(page)).toHaveAttribute('aria-checked','false');await clean(page);
 await hold();await nav(page,'Тайны');release();await expect(control(page)).toHaveAttribute('aria-checked','false');await clean(page);
 await page.route('**/story-secret-spoilers?**',route=>route.fulfill({status:500,json:{detail:'PRIVATE_SERVER_ERROR_183'}}),{times:1});
 await control(page).click();await expect(area(page).getByRole('alert')).toBeVisible();
 await expect(area(page).locator('.secret-entry.is-hidden').first()).toBeVisible();await clean(page);
 expect(await page.content()).not.toContain('PRIVATE_SERVER_ERROR_183');
 await area(page).getByRole('button',{name:'Повторить',exact:true}).click();await expect(area(page)).toContainText(WORLD);
 await control(page).click();await clean(page);
 expect((await view(request,s)).state.notification_history).toHaveLength(0);
});

test('spoiler reading leaves real reveal, fog receipt, regeneration and rollback intact',async({page,request})=>{
 test.setTimeout(120000);const s=await setup(page,request);const path=`/api/saves/${s.save}`;
 const config={provider:'local',model:'test',context_length:32768,max_tokens:2000,update_tokens:4096};
 const commit=async(kind:string,reveal:boolean,target_turn_id?:number)=>{
  await request.post(`/test/secret181-prepare/${s.save}?reveal=${reveal}${target_turn_id?`&target_turn_id=${target_turn_id}`:''}`);
  const v=await view(request,s);const response=await request.post(path+'/turns',{data:{kind,text:'Я слушаю Соню.',revision:v.revision,config,...(target_turn_id?{target_turn_id}:{})}});
  expect(response.ok(),await response.text()).toBe(true);const job=await response.json();
  await expect.poll(async()=> (await(await request.get(`/api/jobs/${job.id}`)).json()).status).toBe('saved');
  return view(request,s);
 };
 await commit('start',false);await page.reload();await dossier(page,'sonya');
 await control(page).click();const preview=area(page).locator('.secret-entry').filter({hasText:SONYA});
 await expect(preview).toHaveClass(/is-preview-revealing/);await preview.scrollIntoViewIfNeeded();
 await expect(preview).not.toHaveClass(/is-preview-revealing/);
 await control(page).click();await clean(page);
 const stored=await page.evaluate(()=>Object.keys(localStorage).filter(k=>k.includes(':fog:')));expect(stored).toHaveLength(0);
 // Keep App mounted with the pre-commit baseline; poll through the real UI.
 await page.goBack();await nav(page,'Игра');
 await request.post(`/test/secret181-prepare/${s.save}`);
 await page.getByLabel('Своё действие или реплика').fill('Я слушаю Соню.');await page.getByRole('button',{name:'Отправить действие',exact:true}).click();
 await expect(page.locator('.story-toast')).toContainText(SONYA);
 const after=await view(request,s);expect(after.state.notification_history).toHaveLength(1);
 await page.locator('.story-toast').getByRole('button',{name:'Подробнее'}).click();
 await expect(page.locator('.secret-browser:visible .secret-entry.is-revealing')).toHaveCount(1);await expect(page.locator('.secret-browser:visible .secret-entry.is-revealing')).toHaveCount(0);
 await page.reload();await dossier(page,'sonya');await expect(area(page)).toContainText(SONYA);await expect(page.locator('.secret-browser:visible .secret-entry.is-revealing')).toHaveCount(0);
 const tid=after.turns.at(-1).id,variant=after.turns.at(-1).active_variant_id;
 await commit('regenerate',false,tid);await page.reload();await dossier(page,'sonya');await clean(page);await expect(control(page)).toHaveAttribute('aria-checked','false');
 let v=await view(request,s);const chosen=await request.post(path+`/turns/${tid}/variant`,{data:{revision:v.revision,variant_id:variant}});expect(chosen.ok(),await chosen.text()).toBe(true);
 await page.reload();await dossier(page,'sonya');await expect(area(page)).toContainText(SONYA);await expect(page.locator('.secret-browser:visible .secret-entry.is-revealing')).toHaveCount(0);
 v=await view(request,s);expect((await request.post(path+'/rollback',{data:{revision:v.revision}})).ok()).toBe(true);
 await page.reload();await dossier(page,'sonya');await clean(page);expect((await view(request,s)).state.notification_history).toHaveLength(0);
});

test('confirmed new protagonist with empty holders knows own secret before first turn',async({page,request})=>{
 const s=await setup(page,request),path=`/api/saves/${s.save}`,operation_id='new-hero183';
 const response=await request.get(path+`/protagonist/draft?operation_id=${operation_id}`);expect(response.ok()).toBe(true);
 const {draft}=await response.json();const v=await view(request,s);
 draft.card.name='Новая героиня';
 // Author state supplies the canonical location identifier; gameplay's legacy
 // character alias intentionally exposes a display label instead.
 const author=await(await request.get(path+'/author-state')).json();draft.character.location_id=author.snapshot.world_state.camera.location_id;
 draft.starting_scene='В гостиной.';
 draft.secrets=[{text:'Я тайно перевожу древние рукописи.',evidence:'Подтверждённая личная биография.',approved:true,holders:[]}];
 const created=await request.post(path+'/protagonist',{data:{revision:v.revision,operation_id,operation:'permanent',draft}});
 expect(created.ok(),await created.text()).toBe(true);await page.reload();await dossier(page,draft.character.id);
 await expect(area(page)).toContainText('Мои тайны');await expect(area(page)).toContainText(draft.secrets[0].text);
 await expect(control(page)).toHaveAttribute('aria-checked','false');await expect(page.locator('.secret-entry.is-revealing')).toHaveCount(0);
 expect((await view(request,s)).state.notification_history).toHaveLength(0);
 await page.reload();await dossier(page,draft.character.id);await expect(area(page)).toContainText(draft.secrets[0].text);
});
