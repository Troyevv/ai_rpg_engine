import {test,expect} from '@playwright/test';
import {nav} from './navigation';

test('canonical snapshot imports through Workshop without generation or secret leakage', async ({page,request}) => {
  const source={schema_version:3,world_state:{
    meta:{world_time:6120,current_protagonist_id:'mira'},
    camera:{mode:'actor',controlled_actor_id:'mira',pov_actor_id:'mira',location_id:'road',
      present_character_ids:['mira'],situation:'Мира идёт с сумками к станции.'},
    characters:{mira:{id:'mira',display_name:'Мира',location_id:'road',situation:'Идёт с сумками к станции.'},
      anna:{id:'anna',display_name:'Анна'}},
    locations:{road:{id:'road',name:'Дорога к станции'}},
    facts:{private:{id:'private',text:'Закрытый банковский договор',visibility:'secret',character_ids:['anna']}},
    knowledge:{'anna:private':{actor_id:'anna',fact_id:'private',status:'known'}}},
    campaign:{campaign:{title:'Пятничное утро'}}};
  let generationRequests=0;
  page.on('request',r=>{if(r.url().includes('/generate'))generationRequests++;});
  await page.goto('/');await nav(page,'Создать');
  await page.getByRole('button',{name:'Импортировать',exact:true}).click();
  await page.getByLabel('Название черновика').fill('Пятничное утро');
  await page.getByLabel('Описание мира или текст импорта').fill(JSON.stringify(source));
  await page.getByRole('button',{name:'Открыть в редакторе',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Посмотри, что получилось'})).toBeVisible();
  await expect(page.locator('main')).not.toContainText('Закрытый банковский договор');
  await page.locator('.workshop-tabs').getByRole('button',{name:'Начало',exact:true}).click();
  await expect(page.locator('.workshop-content')).toContainText('06:00');
  await expect(page.locator('.workshop-content')).toContainText('Дорога к станции');
  const wid=await page.evaluate(()=>localStorage.getItem('draftWorkspace'));
  await page.reload();await nav(page,'Создать');
  await expect(page.getByRole('heading',{name:'Посмотри, что получилось'})).toBeVisible();
  await page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true}).click();
  const confirmed=page.waitForResponse(r=>r.url().endsWith('/draft/confirm')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Подтвердить и открыть игру',exact:true}).click();
  const result=await (await confirmed).json();
  await expect(page.getByRole('button',{name:'Начать игру',exact:true})).toBeVisible();
  const game=await (await request.get(`/api/saves/${result.save}`)).json();
  expect(game.state.world_state.camera.location_id).toBe('road');
  expect(game.state.world_state.camera.controlled_actor_id).toBe('mira');
  expect(game.state.world_state.meta.world_time).toBe(6120);
  expect(game.state.world_state.knowledge['anna:private'].status).toBe('known');
  expect(game.state.world_state.knowledge['mira:private']).toBeUndefined();
  expect(generationRequests).toBe(0);
  const publicDraft=await (await request.get(`/api/workspaces/${wid}/draft`)).json();
  expect(JSON.stringify(publicDraft)).not.toContain('Закрытый банковский договор');
});
