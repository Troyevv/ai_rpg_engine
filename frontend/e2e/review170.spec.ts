import {test,expect} from '@playwright/test';
import {nav} from './navigation';

for(const skin of ['graphite','parchment']) for(const fail of [false,true]) {
 test(`saved review pending, running, refresh and ${fail?'failure':'success'} in ${skin}`,async({page,request},info)=>{
  const theme=await(await request.post('/test/seed')).json();
  await request.put(`/api/worlds/${theme.world}/presentation`,{data:{theme_id:skin}});
  const seed=await(await request.post('/test/review170',{data:{fail}})).json();
  const profile=`review170-${seed.workspace}`;
  await request.put('/api/credentials/deepseek',{data:{api_key:'offline-review170'}});
  await request.put(`/api/settings/${profile}`,{data:{summary:{provider:'deepseek',model:'deepseek-flash',thinking:'off',temperature:.7,max_tokens:24000,context_length:65536}}});
  const url=`/api/workspaces/${seed.workspace}/draft`;
  await page.addInitScript(({wid,world,profile})=>{
   localStorage.setItem('profile',profile);localStorage.setItem('draftWorkspace',wid);localStorage.setItem('selection',JSON.stringify({world}));
  },{wid:seed.workspace,world:theme.world,profile});
  await page.goto('/');await nav(page,'Создать');
  await expect(page.locator('html')).toHaveAttribute('data-theme',skin);
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
   await expect(page.getByRole('heading',{name:'Смысловая проверка не завершена'})).toBeVisible();
   await expect(page.getByRole('alert').filter({hasText:'Лимит ответа исчерпан на reasoning'})).toBeVisible();
   await expect(page.getByRole('button',{name:'Начать с предупреждениями',exact:true})).toBeEnabled();
   expect(final.review.status).toBe('failed');expect(final.job.resumable).toBe(false);
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
