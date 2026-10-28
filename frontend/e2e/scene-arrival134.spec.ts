import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {defaults} from '../src/types';

for (const scenario of ['entry','doorway','retry']) {
 test(`scene arrival 134 ${scenario}: real jobs turn reload turn`,async({page,request},info)=>{
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
  try {
   await page.goto('/');await page.getByRole('button',{name:'Начать игру',exact:true}).click();
   if(scenario==='retry') {
    const retry=page.getByRole('button',{name:'Повторить обработку состояния',exact:true});
    await expect(retry).toBeEnabled();
    const failed=await view();expect(failed.turns).toHaveLength(0);
    expect(failed.state.world_clock.minute).toBe(first.state.world_clock.minute);
    expect(failed.job.repairs.at(-1).stage).toBe('validation_failed');
    expect(failed.job.repairs.at(-1).condition).toBe('completed_arrival_required');
    expect(JSON.stringify(failed.job)).not.toContain('before_camera');
    await expect(page.getByText('Повторная обработка не создаёт новую сцену.',{exact:false})).toBeVisible();
    await page.screenshot({path:`test-results/arrival134-failure-${info.project.name}.png`,fullPage:true});
    await page.reload();await retry.click();
   }
   await expect(page.locator('.turn')).toHaveCount(1);
   const accepted=await view();const job=await(await request.get(`/api/jobs/${accepted.job.id}`)).json();
   expect(job.status).toBe('saved');const text=job.narrative;
   expect(text).toContain(scenario==='entry'?'вошла внутрь':'Виктория стоит в проёме');
   expect(accepted.state.scene_meta.present_ids).toEqual(scenario==='entry'?['ilya','viktoria_solovyova']:['ilya']);
   if(scenario!=='entry') {
    expect(accepted.state.scene_meta.observed_ids).toEqual(['viktoria_solovyova']);
    expect(accepted.state.world.characters.viktoria_solovyova.location_id).toBe('cabinet_threshold');
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
   await page.screenshot({path:`test-results/arrival134-${scenario}-${info.project.name}.png`,fullPage:true,animations:'disabled'});
   expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
  } finally {
   const calls=await(await request.post('/test/runtime-handoff-provider?enabled=false')).json();
   expect(calls.narratives).toBe(3);expect(calls.extractions).toBe(scenario==='retry'?5:3);
  }
  expect(errors).toEqual([]);
 });
}
