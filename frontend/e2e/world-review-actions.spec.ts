import {expect, test} from '@playwright/test';
import {defaults} from '../src/types';
import {nav} from './navigation';
import {authorView, workshopNav} from './workshop-navigation';

async function setupReview(page:import('@playwright/test').Page,request:import('@playwright/test').APIRequestContext,mobile:boolean,scenario=''){
  if(mobile)await page.addInitScript(()=>Object.defineProperty(crypto,'randomUUID',{value:undefined}));
  await page.setViewportSize({width:mobile?360:1280,height:820});
  const {wid}=await(await request.post('/test/review-actions?scenario='+scenario)).json();
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
  return {before,url,openReview,skin,panel:page.getByRole('region',{name:'Работа с замечаниями'})};
}

test('review saved world, confirm targeted changes, recheck and roll back',async({page,request},info)=>{
  const mobile=info.project.name==='mobile';
  const {before,url,openReview,skin,panel}=await setupReview(page,request,mobile);
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

for(const scenario of ['empty-conflicts','invalid-write']){
  test('review result survives reload: '+scenario,async({page,request},info)=>{
    const {panel,openReview,url,before}=await setupReview(page,request,info.project.name==='mobile',scenario);
    await panel.getByRole('button',{name:'Исправить замечания с помощью ИИ'}).click();
    const empty=scenario==='empty-conflicts';
    const heading=panel.getByRole('heading',{name:empty?'Рассмотрено без изменений':'Не удалось применить'});
    await expect(heading).toBeVisible();
    await openReview();
    await expect(heading).toBeVisible();
    if(empty){
      await expect(panel.getByRole('alert')).toHaveCount(0);
      await expect(panel.getByRole('region',{name:'Неоднозначности'})).toContainText('Дата окончания брака условна.');
      await panel.getByText('Отклонено как неоднозначное',{exact:true}).first().click();
      await expect(panel.getByText(/Нужна точная дата от автора/).first()).toBeVisible();
    }else{
      await expect(panel.getByRole('alert').first()).toBeVisible();
    }
    await expect(panel.getByRole('button',{name:'Применить пакет…'})).toHaveCount(0);
    await expect(panel.getByText('Запросы и расходы · 1')).toBeVisible();
    const current=await(await request.get(url+'?author=true')).json();
    expect(current.version_id).toEqual(before.version_id);
    expect(current.state).toEqual(before.state);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    await heading.scrollIntoViewIfNeeded();
    await page.screenshot({path:info.outputPath('assessment.png'),scale:'css'});
    if(empty){
      await panel.getByRole('button',{name:'Уточнить данные в карточках персонажей'}).click();
      await expect(page.getByRole('textbox',{name:'Поиск персонажей'})).toBeVisible();
    }
  });
}

test('family dates and invented details are visible before accepting the complete chronology',async({page,request},info)=>{
  const {panel,url,before,openReview}=await setupReview(page,request,info.project.name==='mobile','family');
  await panel.getByRole('button',{name:'Исправить замечания с помощью ИИ'}).click();
  const family=panel.getByRole('region',{name:'Семейная хронология'});
  await expect(family.getByText('Новые вымышленные детали')).toBeVisible();
  await expect(family).toContainText('2015-06-12');
  await expect(family).toContainText('возраст при родах: 19');
  await expect(family).toContainText('возраст при родах: 18');
  await expect(family).toContainText('Дата окончания брака');
  await openReview();
  await expect(family).toContainText('191');
  expect((await(await request.get(url+'?author=true')).json()).state).toEqual(before.state);
  await family.scrollIntoViewIfNeeded();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.screenshot({path:info.outputPath('chronology.png'),scale:'css'});
  await panel.getByRole('button',{name:'Применить пакет…'}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Подтвердить изменения'}).click();
  await expect(panel.getByRole('heading',{name:'Применено',exact:true})).toBeVisible();
  const saved=await(await request.get(url+'?author=true')).json();
  expect(saved.state.world.characters.character_2.birth_date).toBe('2015-06-12');
  expect(saved.state.world.characters.character_3.death_date).toBe('2015-06-12');
  expect(saved.state.world.objective_relations.old_marriage.until_date).toBe('2015-06-12');
});

test('author refines a legacy paid date proposal offline',async({page,request},info)=>{
  const {panel,url,before}=await setupReview(page,request,info.project.name==='mobile','legacy-family');
  await expect(panel.getByRole('button',{name:'Применить пакет…'})).toBeEnabled();
  await panel.getByText('Лиза · сведения о родителе').click();
  const fields=panel.locator('details[open]').filter({hasText:'Лиза · сведения о родителе'});
  await fields.getByLabel('Подтверждённый год рождения родителя').fill('1996');
  await fields.getByRole('combobox',{name:'Связь с родами · Лиза'}).click();
  await page.getByRole('option',{name:'Смерть при этих родах',exact:true}).click();
  await fields.getByRole('checkbox').check();
  await panel.getByRole('button',{name:'Пересчитать без нового запроса'}).click();
  await expect(panel.getByRole('region',{name:'Семейная хронология'})).toContainText('191');
  await expect(panel.getByRole('button',{name:'Применить пакет…'})).toBeEnabled();
  expect((await(await request.get(url+'?author=true')).json()).state).toEqual(before.state);
});

test('author adjusts a disputed proposal, reloads it, and accepts the displayed dates',async({page,request},info)=>{
 const {panel,url,before,openReview}=await setupReview(page,request,info.project.name==='mobile','direct-family');
 await panel.getByRole('button',{name:'Исправить замечания с помощью ИИ'}).click();
 await expect(panel.getByRole('region',{name:'Неоднозначности'})).toContainText('Илье 18');
 await panel.getByRole('button',{name:'Скорректировать значения'}).click();
 const dialog=page.getByRole('dialog');
 const date=dialog.getByRole('textbox').last();
 await date.fill('2015-02-31');
 await dialog.getByRole('button',{name:'Обновить предпросмотр'}).click();
 await expect(dialog.getByRole('alert')).toBeVisible();
 expect((await(await request.get(url+'?author=true')).json()).state).toEqual(before.state);
 await date.fill('2015-07-10');
 await page.screenshot({path:info.outputPath('adjust-family.png'),scale:'css'});
 await dialog.getByRole('button',{name:'Обновить предпросмотр'}).click();
 await expect(dialog).toHaveCount(0);
 await openReview();
 await expect(panel.getByText('Исходные значения модели')).toBeVisible();
 const saved=await(await request.get(url+'/edits?author=true')).json();
 expect(saved.edits[0].requests).toHaveLength(1);
 await panel.getByRole('button',{name:'Применить пакет…'}).click();
 await page.getByRole('button',{name:'Подтвердить изменения',exact:true}).click();
 await expect(panel.getByRole('heading',{name:'Применено',exact:true})).toBeVisible();
 const accepted=await(await request.get(url+'?author=true')).json();
 expect(accepted.state.world.characters.character_2.birth_date).toBe('2015-07-10');
 expect(accepted.state.world.characters.character_3.death_date).toBe('2015-06-15');
 expect(accepted.state.world.knowledge).toEqual(before.state.world.knowledge);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
