import {expect, test} from '@playwright/test';
import {defaults} from '../src/types';
import {nav} from './navigation';
import {authorView, workshopNav} from './workshop-navigation';

test('review saved world, confirm targeted changes, recheck and roll back',async({page,request},info)=>{
  const mobile=info.project.name==='mobile';
  if(mobile)await page.addInitScript(()=>Object.defineProperty(crypto,'randomUUID',{value:undefined}));
  await page.setViewportSize({width:mobile?360:1280,height:820});
  const {wid}=await(await request.post('/test/review-actions')).json();
  const url=`/api/workspaces/${wid}/draft`;
  const before=await(await request.get(url+'?author=true')).json();
  await page.goto('/');
  const profile=await page.evaluate(()=>localStorage.getItem('profile'));
  await request.put(`/api/settings/${profile}`,{data:{...defaults,summary:{...defaults.summary,
    provider:'deepseek',model:'deepseek-flash',thinking:'off',context_length:131072,max_tokens:16000}}});
  await request.put('/api/credentials/deepseek',{data:{api_key:'offline-review'}});
  const skin=mobile?'parchment':'graphite';
  await page.evaluate(({wid,skin})=>{
    localStorage.setItem('draftWorkspace',wid);
    localStorage.setItem('workshop-theme',JSON.stringify({theme_id:skin,mode:'manual'}));
  },{wid,skin});
  async function openReview(){
    await page.reload();await nav(page,'Создать');await authorView(page);await workshopNav(page,'Проверка мира');
  }
  await openReview();
  const panel=page.getByRole('region',{name:'Работа с замечаниями'});
  await panel.getByRole('button',{name:'Исправить замечания с помощью ИИ'}).click();
  await expect(panel.getByRole('heading',{name:'Ожидает решения'})).toBeVisible();
  const drafts=async()=>(await request.get(url+'?author=true')).json();
  expect((await drafts()).version_id).toBe(before.version_id);
  await openReview();
  await expect(panel.getByText('Отклонено как неоднозначное',{exact:true})).toBeVisible();
  await expect(panel.getByLabel('Состав изменений')).toContainText('Изменение: 1');
  await panel.getByRole('button',{name:'Применить пакет…'}).click();
  const dialog=page.getByRole('dialog',{name:'Применить изменения мира?'});
  await dialog.getByRole('button',{name:'Подтвердить изменения'}).click();
  await expect(panel.getByText('Правка применена',{exact:true}).first()).toBeVisible();
  await panel.getByRole('button',{name:'Повторить смысловую проверку'}).click();
  await expect(panel.getByRole('heading',{name:'Повторная проверка завершена'})).toBeVisible();
  const result=panel.getByLabel('Результаты по замечаниям');
  await expect(result.getByText('Исправлено',{exact:true})).toHaveCount(2);
  await expect(result.getByText('Замечание опровергнуто')).toBeVisible();
  await result.scrollIntoViewIfNeeded();
  expect(await page.locator('html').getAttribute('data-theme')).toBe(skin);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:info.outputPath('review.png'),scale:'css'});
  if(mobile){
    await page.setViewportSize({width:393,height:820});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  }
  await panel.getByText(/История AI-редакций/).click();
  await panel.getByRole('button',{name:/Применено.*Исправить замечания/}).click();
  await panel.getByRole('button',{name:'Посмотреть исходную версию и откатить'}).click();
  const restore=page.getByRole('dialog');
  await restore.getByRole('checkbox').check();
  await restore.getByRole('button',{name:'Восстановить выбранную версию'}).click();
  await expect.poll(async()=>(await drafts()).state).toEqual(before.state);
  const history=await(await request.get(url+'/edits?author=true')).json();
  expect(history.edits.map((e:{requests:unknown[]})=>e.requests.length)).toEqual([1,1]);
});
