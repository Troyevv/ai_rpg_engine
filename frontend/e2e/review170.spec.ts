import {workshopNav} from './workshop-navigation';
import {test,expect} from '@playwright/test';
import {nav} from './navigation';
import {defaults} from '../src/types';

for(const skin of ['graphite','parchment']) for(const fail of [false,true]) {
 test(`saved review pending, running, refresh and ${fail?'failure':'success'} in ${skin}`,async({page,request},info)=>{
  const theme=await(await request.post('/test/seed')).json();
  await request.put(`/api/worlds/${theme.world}/presentation`,{data:{theme_id:skin}});
  const seed=await(await request.post('/test/review170',{data:{fail}})).json();
  const profile=`review170-${seed.workspace}`;
  await request.put('/api/credentials/deepseek',{data:{api_key:'offline-review170'}});
  expect((await request.put(`/api/settings/${profile}`,{data:{...defaults,summary:{...defaults.summary,provider:'deepseek',model:'deepseek-flash',thinking:'off',temperature:.7,max_tokens:24000,context_length:65536}}})).ok()).toBeTruthy();
  const url=`/api/workspaces/${seed.workspace}/draft`;
  await page.addInitScript(({wid,world,profile,skin})=>{
   localStorage.setItem('workshop-theme',JSON.stringify({theme_id:skin,mode:'manual'}));
   localStorage.setItem('profile',profile);localStorage.setItem('draftWorkspace',wid);localStorage.setItem('selection',JSON.stringify({world}));
  },{wid:seed.workspace,world:theme.world,profile,skin});
  await page.goto('/');await nav(page,'Создать');
  await expect(page.locator('html')).toHaveAttribute('data-theme',skin);
  await workshopNav(page,'Проверка мира');
  await expect(page.getByRole('heading',{name:'Смысловая проверка не завершена'})).toBeVisible();
  const before=await(await request.get(url+'?author=true')).json();
  let releasePost!:()=>void;const held=new Promise<void>(resolve=>{releasePost=resolve});let posts=0;
  await page.route(`**/workspaces/${seed.workspace}/draft/resume`,async route=>{posts++;await held;await route.continue()});
  const button=page.getByRole('button',{name:'Повторить проверку',exact:true});
  await button.click();
  const progress=page.getByRole('status',{name:'Ход проверки мира'});
  await expect(progress).toContainText('Запускаем повторную проверку');
  await expect(button).toBeDisabled();
  // A second DOM click cannot send another paid operation.
  await button.evaluate((el:HTMLButtonElement)=>el.click());expect(posts).toBe(1);
  releasePost();
  await expect.poll(async()=>(await(await request.get(url+'?author=true')).json()).job.phase).toBe('reviewing');
  await expect(progress).toContainText('Проверяем смысловую согласованность');
  await expect(page.getByLabel('Фактические параметры запроса')).toContainText('Thinking: off');
  await expect(page.getByLabel('Фактические параметры запроса')).toContainText('Попытка: 2');
  await page.reload();await nav(page,'Создать');
  await expect(progress).toContainText('Проверяем смысловую согласованность');
  await expect(page.getByRole('button',{name:'Повторить проверку',exact:true})).toHaveCount(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(await page.evaluate(()=>innerWidth));
  if(!fail)await progress.screenshot({path:info.outputPath(`running-${skin}.png`)});
  const release=await(await request.post('/test/review170/release')).json();expect(release.calls).toBe(1);
  await expect(progress).toHaveCount(0);
  const final=await(await request.get(url+'?author=true')).json();
  expect(final.candidate || final.state).toEqual(before.candidate);
  if(fail){
   await workshopNav(page,'Проверка мира');
  await expect(page.getByRole('heading',{name:'Смысловая проверка не завершена'})).toBeVisible();
   await expect(page.getByRole('alert').filter({hasText:'Лимит ответа исчерпан на reasoning'})).toBeVisible();
   await expect(page.getByRole('button',{name:'Начать с предупреждениями',exact:true})).toBeEnabled();
   expect(final.review.status).toBe('failed');expect(final.job.resumable).toBe(false);
   const player=await(await request.get(url)).json();
   expect(player.job.error).toBe(final.job.response_diagnostic.message);
   expect(final.review.reason).toBe(final.job.response_diagnostic.message);
   await expect(page.getByRole('button',{name:'Повторить после сбоя провайдера'})).toHaveCount(0);
  }else{
   await expect(page.getByText('Смысловая проверка завершена. Результат сохранён.',{exact:true})).toBeVisible();
   expect(final.review.status).toBe('completed');
   await expect(page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true})).toBeEnabled();
  }
  if(fail && skin==='graphite')await page.screenshot({path:info.outputPath(`terminal-${skin}.png`),fullPage:true});
  await page.reload();await nav(page,'Создать');
  await expect(page.getByRole('button',{name:fail?'Начать с предупреждениями':'Подтвердить мир и начать игру',exact:true})).toBeEnabled();
 });
}

for(const skin of ['graphite','parchment']) test(`confirmed transient empty retry in ${skin}`,async({page,request},info)=>{
 const theme=await(await request.post('/test/seed')).json();
 await request.put(`/api/worlds/${theme.world}/presentation`,{data:{theme_id:skin}});
 const seed=await(await request.post('/test/review170',{data:{fail:true,transient:true}})).json();
 await request.put('/api/credentials/deepseek',{data:{api_key:'offline-review170'}});
 await page.addInitScript(({wid,world,skin})=>{localStorage.setItem('workshop-theme',JSON.stringify({theme_id:skin,mode:'manual'}));localStorage.setItem('draftWorkspace',wid);localStorage.setItem('selection',JSON.stringify({world}));},{wid:seed.workspace,world:theme.world,skin});
 const url=`/api/workspaces/${seed.workspace}/draft`;
 await page.goto('/');await nav(page,'Создать');
 await workshopNav(page,'Проверка мира');
 await page.getByRole('button',{name:'Повторить проверку',exact:true}).click();
 await expect(page.getByRole('status',{name:'Ход проверки мира'})).toContainText('Проверяем смысловую согласованность');
 await request.post('/test/review170/release');
 await expect(page.getByRole('alert')).toContainText('Провайдер завершил запрос без видимого текста');
 const before=await(await request.get(url+'/raw')).json();
 const original=await(await request.get(url+'?author=true')).json();
 await page.reload();await nav(page,'Создать');
 await workshopNav(page,'Проверка мира');
 await expect(page.getByRole('alert')).toContainText('Провайдер завершил запрос без видимого текста');
 const retry=page.getByRole('button',{name:'Повторить после сбоя провайдера'});
 await retry.click();await expect(page.getByRole('dialog')).toContainText('может быть оплачен');
 await page.getByRole('button',{name:'Отмена',exact:true}).click();
 expect((await(await request.post('/test/review170/release')).json()).calls).toBe(1);
 await retry.click();
 if(skin==='parchment')await page.getByRole('dialog').screenshot({path:info.outputPath('confirmed-retry.png')});
 await page.getByRole('button',{name:'Подтвердить одну повторную проверку'}).click();
 await expect(page.getByText('Смысловая проверка завершена. Результат сохранён.',{exact:true})).toBeVisible();
 expect((await(await request.post('/test/review170/release')).json()).calls).toBe(2);
 const after=await(await request.get(url+'/raw')).json();
 for(const [slot,record] of Object.entries(before.responses))expect(after.responses[slot]).toEqual(record);
 const completed=await(await request.get(url+'?author=true')).json();
 expect(completed.state).toEqual(original.candidate);
 await expect(retry).toHaveCount(0);await expect(page.getByRole('alert')).toHaveCount(0);
 await page.reload();await nav(page,'Создать');
 await expect(page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true})).toBeEnabled();
});
