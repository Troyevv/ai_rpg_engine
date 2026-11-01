import {test,expect} from '@playwright/test';
import {nav} from './navigation';
import {defaults} from '../src/types';

for(const skin of ['graphite','parchment']) for(const fail of [false,true]) {
 test(`creative stage, refresh and ${fail?'empty recovery':'completion'} in ${skin}`,async({page,request})=>{
  const theme=await(await request.post('/test/seed')).json();
  await request.put(`/api/worlds/${theme.world}/presentation`,{data:{theme_id:skin}});
  await request.put('/api/credentials/deepseek',{data:{api_key:'offline-creative172'}});
  const workspace=await(await request.post('/test/creative172',{data:{fail}})).json();
  const url=`/api/workspaces/${workspace.id}/draft`;
  await page.addInitScript(({wid,world})=>{localStorage.setItem('draftWorkspace',wid);localStorage.setItem('selection',JSON.stringify({world}));},{wid:workspace.id,world:theme.world});
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
  await page.reload();await nav(page,'Создать');
  await expect(page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true})).toBeEnabled();
 });
}
