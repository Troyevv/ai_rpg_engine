import {test,expect} from '@playwright/test';
import {nav,actor,diagnostics} from './navigation';

test('general relationships support CRUD and follow POV without LLM for edits',async({page,request})=>{
 const selection=await(await request.post('/test/seed')).json();
 let save=await(await request.get(`/api/saves/${selection.save}`)).json();
 const actorName=save.state.characters.find((c:any)=>c.id==='character_1').name;
 const targetName=save.state.characters.find((c:any)=>c.id==='character_2').name;
 for(const r of Object.values(save.state.world.relationships) as any[]){
  if(r.source_id==='character_1') save=await(await request.patch(`/api/saves/${selection.save}/characters/character_1/relationships`,{data:{revision:save.revision,target_id:r.target_id,delete:true}})).json();
 }
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selection);
 await page.goto('/');
 const open=async()=>{await nav(page,'Мир');await page.locator('.panel-tabs').getByRole('button',{name:'Отношения',exact:true}).click()};
 await open();
 const panel=page.locator('.inspector-dialog');
 await panel.getByRole('button',{name:'+ Добавить отношение',exact:true}).click();
 const editor=page.getByRole('dialog').filter({has:page.getByRole('heading',{name:'Отношение персонажа',exact:true})});
 await editor.getByLabel('Персонаж-адресат').selectOption('character_2');
 await editor.getByLabel('Контекст отношения').fill('Саша доверяет другу');
 await editor.getByLabel('Доверие',{exact:true}).fill('55');
 await editor.getByRole('button',{name:'Сохранить',exact:true}).click();
 await expect(editor).toHaveCount(0);
 await expect(panel.locator('.motivation-editor')).toContainText('Саша доверяет другу');
 save=await(await request.get(`/api/saves/${selection.save}`)).json();
 expect(save.state.world.relationships['character_1:character_2'].dimensions.trust).toBe(55);
 expect((await(await request.get(`/api/saves/${selection.save}/accounting`)).json()).requests).toHaveLength(0);
 await panel.getByLabel(`Действия с отношением к ${targetName}`).click();
 await panel.getByRole('button',{name:'Редактировать',exact:true}).click();
 await editor.getByLabel('Контекст отношения').fill('Теперь сомневается');
 await editor.getByRole('button',{name:'Сохранить',exact:true}).click();await expect(editor).toHaveCount(0);
 await panel.getByRole('button',{name:'Закрыть',exact:true}).click();
 await page.getByRole('button',{name:'Начать игру',exact:true}).click();await expect(page.locator('.turn')).toHaveCount(1);
 await actor(page,'character_2',targetName);await expect(page.locator('.turn')).toHaveCount(2);
 await open();
 await expect(panel.locator('.motivation-editor')).not.toContainText('Теперь сомневается');
 await expect(panel).toContainText('Теперь сомневается');
 await panel.getByRole('button',{name:'Закрыть',exact:true}).click();
 await actor(page,'character_1',actorName);await expect(page.locator('.turn')).toHaveCount(3);
 await open();await expect(panel.locator('.motivation-editor')).toContainText('Теперь сомневается');
 await panel.getByLabel(`Действия с отношением к ${targetName}`).click();await panel.getByRole('button',{name:'Удалить',exact:true}).click();
 const confirm=page.getByRole('dialog').filter({has:page.getByRole('heading',{name:'Удалить отношение?',exact:true})});
 await confirm.getByRole('button',{name:'Удалить',exact:true}).click();await expect(confirm).toHaveCount(0);
 await expect(panel.locator('.motivation-editor')).not.toContainText('Теперь сомневается');
 save=await(await request.get(`/api/saves/${selection.save}`)).json();
 expect(save.state.world.relationships['character_1:character_2']).toBeUndefined();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
});

test('diagnostic tabs use persisted turn timing and requests; old turns stay readable',async({page,request})=>{
 const selection=await(await request.post('/test/seed')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selection);
 await page.goto('/');await page.getByRole('button',{name:'Начать игру',exact:true}).click();
 await expect(page.locator('.turn')).toHaveCount(1);
 await expect(page.locator('.turn-timing')).toContainText('Время хода:');
 await page.locator('.turn-timing summary').click();
 await expect(page.locator('.turn-timing')).toContainText('Извлечение состояния');
 await expect(page.locator('.turn-timing')).not.toContainText('Фоновая симуляция');
 await diagnostics(page);
 const dialog=page.getByRole('dialog');
 await expect(dialog.getByRole('heading',{name:'Диагностика',exact:true})).toBeVisible();
 await expect(dialog).toContainText('GM-only');
 await dialog.getByRole('tab',{name:'Производительность',exact:true}).click();
 await expect(dialog.locator('.diagnostic-history')).toContainText('2 LLM');
 await expect(dialog).toContainText('Общее время');
 await expect(dialog).not.toContainText('Исправление extraction');
 await dialog.getByRole('tab',{name:'Расходы',exact:true}).click();
 await expect(dialog).toContainText('Текущая сессия');await expect(dialog).toContainText('Мир: все прохождения');
 await dialog.getByText('Расходы отдельных LLM requests',{exact:true}).click();
 await expect(dialog).toContainText('Художественная генерация');
 await dialog.getByRole('button',{name:'Закрыть',exact:true}).click();
 // Presentation of legacy timing and persisted warnings is independent of generation.
 await page.route(`**/api/saves/${selection.save}/accounting`,async route=>{
  const response=await route.fetch();const data=await response.json();
  data.turns[0].timing=null;
  data.turns[0].warnings=[{section:'knowledge',index:2,reason:'нет подтверждённого пути передачи знания'}];
  await route.fulfill({response,json:data});
 });
 await diagnostics(page);await dialog.getByRole('tab',{name:'Производительность',exact:true}).click();
 await expect(dialog).toContainText('Статистика времени для этого хода не сохранена');
 await expect(dialog.locator('.delta-warnings')).toContainText('knowledge[2]');
 await expect(dialog.locator('.delta-warnings')).toContainText('Остальной WorldDelta применён');
 await expect(dialog.locator('.diagnostic-history')).toContainText('⚠ 1');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
});

test('repair reasons and sanitization have separate statistics per selected variant',async({page,request})=>{
 const selection=await(await request.post('/test/seed')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selection);
 await page.goto('/');await page.getByRole('button',{name:'Начать игру',exact:true}).click();
 await expect(page.locator('.turn')).toHaveCount(1);
 await page.route(`**/api/saves/${selection.save}/accounting`,async route=>{
  const response=await route.fetch();const data=await response.json();const original=data.turns[0];
  const repaired={...original,id:999,sequence:99,active_variant_id:'repair-variant',job_id:'repair-job',
   requests:[...original.requests,{...original.requests[0],id:'repair-request',stage:'extraction_repair'}],
   repairs:[{stage:'extraction_repair',repair_error_code:'unknown_character',repair_error_type:'StructuralDeltaError',repair_reason:'Неизвестный персонаж в изменениях.'}],
   warnings:[{type:'sanitized_delta',code:'relationship_dimension_unknown',section:'relationships',index:0,field:'dimensions.sympathy',reason:'неизвестное измерение отношений'}]};
  data.turns=[repaired,{...original,repairs:[],warnings:[]}];
  await route.fulfill({response,json:data});
 });
 await diagnostics(page);const dialog=page.getByRole('dialog');
 await dialog.getByRole('tab',{name:'Производительность',exact:true}).click();
 await dialog.getByLabel('Ход диагностики').selectOption('repair-variant');
 await expect(dialog).toContainText('Причина repair');await expect(dialog).toContainText('StructuralDeltaError');
 await dialog.getByText('Статистика extraction · последние 2 ходов',{exact:true}).click();
 await expect(dialog).toContainText('Repair rate: 50.0%');
 await expect(dialog).toContainText('relationship_dimension_unknown: 1');
 const originalOption=await dialog.getByLabel('Ход диагностики').locator('option').last().getAttribute('value');
 await dialog.getByLabel('Ход диагностики').selectOption(originalOption!);
 await expect(dialog).toContainText('Repair: не выполнялся');
 await expect(dialog.getByRole('heading',{name:'Причина repair',exact:true})).toHaveCount(0);
 await expect(dialog.locator('.delta-warnings')).toHaveCount(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
});
