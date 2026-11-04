import {test,expect} from '@playwright/test';
import {nav} from './navigation';
import {defaults} from '../src/types';

for(const skin of ['graphite','parchment']) for(const mode of ['complete','empty','correction']) {
 const fail=mode==='empty';
 test(`creative stage, refresh and ${mode} in ${skin}`,async({page,request})=>{
  const theme=await(await request.post('/test/seed')).json();
  await request.put(`/api/worlds/${theme.world}/presentation`,{data:{theme_id:skin}});
  await request.put('/api/credentials/deepseek',{data:{api_key:'offline-creative172'}});
  const workspace=await(await request.post('/test/creative172',{data:{fail,invalid:mode==='correction'}})).json();
  const url=`/api/workspaces/${workspace.id}/draft`;
  // Seed once: init scripts run again on every reload and would overwrite
  // the world/save selected by confirmation with the unrelated theme world.
  await page.goto('/');
  await page.evaluate(({wid,world})=>{localStorage.setItem('draftWorkspace',wid);localStorage.setItem('selection',JSON.stringify({world}));},{wid:workspace.id,world:theme.world});
  await page.goto('/');await nav(page,'Создать');
  const generated=await request.post(url+'/generate',{data:{revision:0,text:'CREATIVE172: В приморском городе восстанавливают мастерскую после пожара. Происхождение героя неизвестно.',config:{...defaults.summary,provider:'deepseek',model:'deepseek-flash',thinking:'off',max_tokens:24000,context_length:131072},api_key:'offline'}});
  expect(generated.ok()).toBeTruthy();
  await page.reload();await nav(page,'Создать');
  const progress=page.getByRole('status',{name:'Ход проверки мира'});
  await expect(progress).toContainText('Творческое развитие мира');
  await expect(page.locator('html')).toHaveAttribute('data-theme',skin);
  const before=await(await request.get(url+'?author=true')).json();expect(before.candidate).toBeTruthy();
  await page.reload();await nav(page,'Создать');
  await expect(progress).toContainText('Творческое развитие мира');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(await page.evaluate(()=>innerWidth));
  expect((await(await request.post('/test/creative172/release')).json()).calls).toBe(1);
  await expect(progress).toHaveCount(0);
  if(fail){
   await expect(page.getByRole('alert')).toContainText('Провайдер завершил запрос без видимого текста');
   const failed=await(await request.get(url+'?author=true')).json();expect(failed.candidate).toEqual(before.candidate);
   await page.reload();await nav(page,'Создать');
   await expect(page.getByText('Творческое развитие не завершено.',{exact:false})).toBeVisible();
   await page.getByRole('button',{name:'Повторить после сбоя провайдера'}).click();
   await page.getByRole('button',{name:'Подтвердить одну повторную проверку'}).click();
  }
  await expect(page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true})).toBeEnabled();
  const completed=await(await request.get(url+'?author=true')).json();
  expect(completed.creative_status).toBe('applied');expect(completed.review.status).toBe('completed');
  expect(completed.state.world.organizations.workshop.name).toBe('Мастерская Веры');
  const raw=await(await request.get(url+'/raw')).json();
  expect(raw.requests.filter((r:{stage:string})=>r.stage==='draft_world_creative').length).toBe(fail?2:1);
  expect(raw.requests.filter((r:{stage:string})=>r.stage==='draft_world_creative_repair')).toHaveLength(mode==='correction'?1:0);
  if(mode==='correction'){
   expect(raw.creative.original_reply).toContain('missing');
   expect(raw.creative.corrections).toHaveLength(1);
  }
  await page.reload();await nav(page,'Создать');
  await page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true}).click();
  await page.getByRole('button',{name:'Подтвердить и открыть игру',exact:true}).click();
  await expect(page.getByRole('button',{name:'Начать игру',exact:true})).toBeVisible();
  const selected=await page.evaluate(()=>JSON.parse(localStorage.getItem('selection')!));
  expect(selected.world).not.toBe(theme.world);expect(selected.save).toBeTruthy();
  // Confirmation creates a new world with its own presentation. Exercise the
  // requested skin in the game too, not only on the seed world's draft screen.
  expect((await request.put(`/api/worlds/${selected.world}/presentation`,{data:{theme_id:skin}})).ok()).toBeTruthy();
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme',skin);
  const canonical=async()=>{
   const response=await request.post(`/test/creative172/saves/${selected.save}/canonical`);
   expect(response.ok()).toBeTruthy();return await response.json();
  };
  const initial=await canonical();
  expect(initial.world_state.organizations.workshop.name).toBe('Мастерская Веры');
  expect(initial.world_state.roles.craft).toMatchObject({actor_id:'craftswoman',organization_id:'workshop'});
  expect(initial.world_state.knowledge['craftswoman:fire']).toMatchObject({fact_id:'fire',source_event_id:'fire'});
  expect(initial.events.find((e:{id:string})=>e.id==='fire')).toMatchObject({fact_ids:['fire']});
  const records=[['organizations','workshop'],['roles','craft'],['objective_relations','friend'],['facts','fire'],['knowledge','craftswoman:fire'],['threads','rebuild']];
  for(const [section,id] of records)expect(initial.world_state[section][id]).toBeTruthy();
  await page.getByRole('button',{name:'Начать игру',exact:true}).click();
  await expect(page.locator('.turn')).toHaveCount(1);
  await expect(page.locator('.choices button')).toHaveCount(6);
  const view=async()=>await(await request.get(`/api/saves/${selected.save}`)).json();
  for(const turnCount of [2,3]){
   await page.locator('.choices button').first().click();
   // Choices from the preceding turn can remain mounted while a job starts.
   await expect(page.locator('.turn')).toHaveCount(turnCount);
   await expect.poll(async()=>(await view()).job.status).toBe('saved');
   await expect(page.locator('.choices button')).toHaveCount(6);
   const current=await canonical();
   for(const [section,id] of records)expect(current.world_state[section][id]).toEqual(initial.world_state[section][id]);
   expect(current.events.find((e:{id:string})=>e.id==='fire')).toEqual(initial.events.find((e:{id:string})=>e.id==='fire'));
  }
  const saved=await view();expect(saved.turns).toHaveLength(3);
  // GET /saves exposes ui_view, not the draft or canonical world schema.
  // The role has no knowledge fact and must remain absent from the public view.
  expect(saved.state.world).not.toHaveProperty('organizations');
  expect(saved.state.residence_roles.roles).not.toEqual(expect.arrayContaining([expect.objectContaining({id:'craft'})]));
  expect(saved.state.characters).toEqual(expect.arrayContaining([expect.objectContaining({id:'craftswoman',name:'Вера'})]));
  expect(saved.state.world.facts.fire.text).toBe(initial.world_state.facts.fire.text);
  expect(saved.state.world.knowledge['craftswoman:fire']).toEqual(initial.world_state.knowledge['craftswoman:fire']);
  expect(saved.state.world.threads.rebuild).toEqual(initial.world_state.threads.rebuild);
  const savedCanonical=await canonical();
  await page.reload();
  await expect(page.locator('.turn')).toHaveCount(3);
  await expect(page.locator('.choices button')).toHaveCount(6);
  await expect(page.locator('html')).toHaveAttribute('data-theme',skin);
  expect(await page.evaluate(()=>JSON.parse(localStorage.getItem('selection')!))).toEqual(selected);
  const reloaded=await view();
  expect(reloaded.turns).toEqual(saved.turns);expect(reloaded.state).toEqual(saved.state);
  expect(await canonical()).toEqual(savedCanonical);
  expect((await(await request.get(url+'/raw')).json()).requests).toEqual(raw.requests);
 });
}
