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
  await page.getByRole('button',{name:'Начать игру',exact:true}).click();
  await expect(page.locator('.turn')).toHaveCount(1);
  await expect(page.locator('.choices button')).toHaveCount(6);
  const view=async()=>await(await request.get(`/api/saves/${selected.save}`)).json();
  await page.locator('.choices button').first().click();
  // Choices from the preceding turn can remain mounted while a job starts.
  await expect(page.locator('.turn')).toHaveCount(2);
  await expect.poll(async()=>(await view()).job.status).toBe('saved');
  await expect(page.locator('.choices button')).toHaveCount(6);
  const saved=await view();expect(saved.turns).toHaveLength(2);
  expect(saved.state.world.organizations.workshop.name).toBe('Мастерская Веры');
  await page.reload();
  await expect(page.locator('.turn')).toHaveCount(2);
  await expect(page.locator('.choices button')).toHaveCount(6);
  await expect(page.locator('html')).toHaveAttribute('data-theme',skin);
  expect(await page.evaluate(()=>JSON.parse(localStorage.getItem('selection')!))).toEqual(selected);
  const reloaded=await view();
  expect(reloaded.turns).toEqual(saved.turns);expect(reloaded.state).toEqual(saved.state);
  expect((await(await request.get(url+'/raw')).json()).requests).toEqual(raw.requests);
 });
}
