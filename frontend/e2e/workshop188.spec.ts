import {generateIdea} from './idea-navigation';
import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {nav} from './navigation';
import {authorView,workshopNav,draftsMenu} from './workshop-navigation';

test('new workspace retains the submitted idea without copying it into the next world',async({page,request})=>{
 await page.goto('/');await nav(page,'Создать');
 const idea='Друзья встречаются на кухне. Придумай их прошлое и отношения.';
 await page.getByLabel('Описание мира или текст импорта').fill(idea);
 await generateIdea(page);
 await expect(page.locator('.ww-hero h1, .fl-result h2')).toBeVisible();
 const wid=await page.evaluate(()=>localStorage.getItem('draftWorkspace'));
 await workshopNav(page,'Идея и генерация');
 await expect(page.getByLabel('Описание мира или текст импорта')).toHaveCount(0);
 await page.getByRole('button',{name:'Открыть замысел автора'}).click();
 await page.getByRole('button',{name:'Показать всё',exact:true}).click();
 await expect(page.getByLabel('Описание мира или текст импорта')).toHaveValue(idea);
 await page.reload();await nav(page,'Создать');await workshopNav(page,'Идея и генерация');
 await expect(page.getByLabel('Описание мира или текст импорта')).toHaveCount(0);
 await page.getByRole('button',{name:'Открыть замысел автора'}).click();
 await page.getByRole('button',{name:'Показать всё',exact:true}).click();
 await expect(page.getByLabel('Описание мира или текст импорта')).toHaveValue(idea);
 expect((await(await request.get(`/api/workspaces/${wid}/draft?author=true`)).json()).source_text).toContain(idea);
 await draftsMenu(page);await page.getByRole('button',{name:'+ Новая история',exact:true}).click();
 await expect(page.getByLabel('Описание мира или текст импорта')).toHaveValue('');
 await expect(page.getByLabel('Название черновика')).toHaveValue('');
});

test('field status, failed save, restored input, required structured fields and scroll context',async({page,request},info)=>{
 const state=JSON.parse(readFileSync(new URL('../../tests/fixtures/runtime_handoff/world.json',import.meta.url),'utf8'));
 const w=await(await request.post('/api/workspaces',{data:{name:'UX regression'}})).json();const url=`/api/workspaces/${w.id}/draft`;
 expect((await request.post(url+'/import',{data:{revision:0,format:'json',text:JSON.stringify(state)}})).ok()).toBeTruthy();
 await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),w.id);await page.goto('/');await nav(page,'Создать');await authorView(page);await workshopNav(page,'Хронология');
 await expect(page.locator('.ww-timeline .ww-record-caption')).toHaveCount(6);
 await expect(page.locator('.ww-timeline .ww-record-caption').first()).toHaveText('Пятница, 23 октября 2026, 17:45');
 await expect(page.locator('.ww-timeline')).toContainText('Дата неизвестна');
 await workshopNav(page,'Персонажи');
 await page.setViewportSize({width:390,height:720});
 await page.locator('.ww-scroll').evaluate(e=>{e.scrollTop=1200;e.dispatchEvent(new Event('scroll'))});
 const scroll=await page.locator('.ww-scroll').evaluate(e=>e.scrollTop);expect(scroll).toBeGreaterThan(900);
 await workshopNav(page,'Проверка мира');await workshopNav(page,'Персонажи');
 await expect.poll(()=>page.locator('.ww-scroll').evaluate(e=>e.scrollTop)).toBe(scroll);
 await page.getByLabel('Поиск персонажей').fill('Виктория');await page.getByRole('button',{name:'Досье Виктория Соловьёва',exact:true}).click();
 await page.getByRole('button',{name:'Изменить fields.Внешность',exact:true}).click();
 const field=page.locator('.ww-field-dialog');const original=await field.getByLabel('Внешность',{exact:true}).inputValue();
 await expect(field.getByRole('button',{name:'Сохранить поле',exact:true})).toBeDisabled();
 await expect(field).toContainText('Виктория Соловьёва');
 const text=original+' Новая деталь для проверки сохранения.';
 await field.getByLabel('Внешность',{exact:true}).fill(text);await expect(field.getByRole('status')).toContainText('несохранённые изменения');
 await page.route('**/api/workspaces/*/draft',async route=>route.request().method()==='PATCH'?route.fulfill({status:409,json:{detail:'Версия изменилась: тест конфликта'}}):route.continue());
 await field.getByRole('button',{name:'Сохранить поле',exact:true}).click();await expect(field.getByRole('alert')).toContainText('Версия изменилась');
 expect((await(await request.get(url+'?author=true')).json()).state.characters.find((c:{id:string})=>c.id==='viktoria_solovyova').fields.Внешность).toBe(original);
 await page.unroute('**/api/workspaces/*/draft');await page.goBack();await expect(field).toHaveCount(0);
 await expect(page.getByRole('dialog',{name:'Досье персонажа',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Изменить fields.Внешность',exact:true}).click();await expect(field.getByLabel('Внешность',{exact:true})).toHaveValue(text);
 await field.getByRole('button',{name:'Сохранить поле',exact:true}).click();await expect(field).toHaveCount(0);await expect(page.getByText('Поле «Внешность» сохранено',{exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Изменить fields.Внешность',exact:true})).toBeFocused();
 await page.getByRole('button',{name:'Цели',exact:true}).click();await page.getByRole('button',{name:'Изменить Цели',exact:true}).click();await page.getByRole('button',{name:'Добавить запись',exact:true}).click();
 await expect(field.getByLabel('Идентификатор',{exact:true})).toHaveAttribute('aria-required','true');
 await field.getByLabel('Идентификатор',{exact:true}).fill('audit_goal');await field.getByLabel('Описание',{exact:true}).fill('Подготовить салон к открытию');
 await expect(field.getByText('Дополнительные поля · 9',{exact:true})).toBeVisible();
 await field.getByRole('button',{name:'Сохранить поле',exact:true}).click();await expect(field).toHaveCount(0);
 const saved=(await(await request.get(url+'?author=true')).json()).state.world.characters.viktoria_solovyova.goals;
 expect(saved[0]).toMatchObject({id:'audit_goal',text:'Подготовить салон к открытию',status:'active'});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:test.info().outputPath(`dossier-${info.project.name}.png`),animations:'disabled'});
 await page.goBack();await expect(page.getByRole('dialog')).toHaveCount(0);await expect(page.getByLabel('Поиск персонажей')).toHaveValue('Виктория');
 await page.goBack();await expect(page.locator('.world-workshop')).toHaveCount(0);expect(page.url()).not.toBe('about:blank');
});

test('reference relationship map uses existing directed edges and preserves dossier context',async({page,request})=>{
 const state=JSON.parse(readFileSync(new URL('../../tests/fixtures/runtime_handoff/world.json',import.meta.url),'utf8'));
 const w=await(await request.post('/api/workspaces',{data:{name:'Связи — аудит'}})).json();const url=`/api/workspaces/${w.id}/draft`;
 expect((await request.post(url+'/import',{data:{revision:0,format:'json',text:JSON.stringify(state)}})).ok()).toBeTruthy();
 const before=(await(await request.get(url+'?author=true')).json()).state;
 await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),w.id);await page.goto('/');await nav(page,'Создать');await authorView(page);await workshopNav(page,'Связи и семьи');
 for(const cid of ['sergey_volkov','ilya']){
  await page.getByRole('combobox',{name:'Чьи отношения показать'}).selectOption(cid);
  const outgoing=Object.values(state.world.relationships).filter((r:any)=>r.source_id===cid);
  await expect(page.locator('.ww-relation-list .ww-record-card')).toHaveCount(outgoing.length);
  const neighbors=[...new Set(Object.values(state.world.relationships).flatMap((r:any)=>r.source_id===cid?[r.target_id]:r.target_id===cid?[r.source_id]:[]))].filter(id=>id!==cid);
  await expect(page.locator('.ww-graph-node:not(.is-center)')).toHaveCount(Math.min(5,neighbors.length));
 }
 const center=page.locator('.ww-graph-node.is-center');await center.click();await expect(page.getByRole('dialog',{name:'Досье персонажа'})).toBeVisible();
 await page.getByRole('button',{name:'Готово',exact:true}).click();await expect(center).toBeFocused();
 await page.locator('.ww-relation-list .ww-record-card').first().getByRole('button',{name:'Открыть запись →'}).click();await expect(page.locator('.ww-record-dialog')).toContainText('Илья');await page.keyboard.press('Escape');
 await page.getByRole('button',{name:'Семья и связи',exact:true}).click();await expect(page.locator('.ww-records-objective_relations .ww-relation-pair')).not.toHaveCount(0);
 await workshopNav(page,'Хронология');await page.getByRole('button',{name:'Сцены',exact:true}).click();await expect(page.locator('.ww-records-scene .ww-record-card')).toHaveCount(Object.keys(state.world.scenes).length);
 await workshopNav(page,'Факты и знания');await expect(page.locator('.ww-fact-copy .ww-people-chips').first()).toBeVisible();
 await page.getByRole('button',{name:'Игрок',exact:true}).click();const player=(await(await request.get(url)).json()).state;
 const hidden=Object.values(before.world.facts).filter((f:any)=>!player.world.facts[f.id]) as {text:string}[];
 for(const fact of hidden)await expect(page.locator('.ww-content')).not.toContainText(fact.text);
 expect((await(await request.get(url+'?author=true')).json()).state).toEqual(before);
 await authorView(page);await workshopNav(page,'Связи и семьи');await page.getByRole('button',{name:'Направленные чувства',exact:true}).click();
 await page.getByRole('combobox',{name:'Чьи отношения показать'}).selectOption('ilya');
 await page.locator('.ww-relation-list .ww-record-card').first().getByRole('button',{name:'Открыть запись →'}).click();
 await page.getByRole('button',{name:'Изменить От кого',exact:true}).click();await page.locator('.ww-field-dialog').getByRole('combobox',{name:'От кого',exact:true}).selectOption('nina_petrovna');
 await page.getByRole('button',{name:'Сохранить поле',exact:true}).click();await expect(page.locator('.ww-field-dialog')).toHaveCount(0);
 await expect(page.locator('.ww-record-dialog')).toBeVisible();await expect(page.locator('.ww-record-dialog .dialog-title')).toContainText('Нина Петровна');await page.keyboard.press('Escape');
 await page.getByRole('combobox',{name:'Чьи отношения показать'}).selectOption('sergey_volkov');await page.locator('.ww-relation-list').getByRole('button',{name:'Добавить',exact:true}).click();
 await expect(page.locator('.ww-record-dialog')).toBeVisible();await expect(page.locator('.ww-record-dialog')).toContainText('От кого');await page.keyboard.press('Escape');
 await page.getByRole('combobox',{name:'Чьи отношения показать'}).selectOption('sergey_volkov');await expect(page.locator('.ww-record-dialog')).toHaveCount(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});


test('secret roles have named character selectors and survive Start Game independently',async({page,request})=>{
 const state=JSON.parse(readFileSync(new URL('../../tests/fixtures/runtime_handoff/world.json',import.meta.url),'utf8'));
 const fid='fact_ilya_orphan';state.world.facts[fid].story_secret=true;
 const w=await(await request.post('/api/workspaces',{data:{name:'Роли тайны'}})).json();const url=`/api/workspaces/${w.id}/draft`;
 expect((await request.post(url+'/import',{data:{revision:0,format:'json',text:JSON.stringify(state)}})).ok()).toBe(true);
 await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),w.id);await page.goto('/');await nav(page,'Создать');await authorView(page);await workshopNav(page,'Факты и знания');
 await page.locator('.ww-records-fact .ww-record-card').filter({hasText:state.world.facts[fid].text}).getByRole('button',{name:'Открыть запись →'}).click();
 for(const [label,name] of [['Кто хранит тайну','Илья Александров'],['Чья скрытая биография','Виктория Соловьёва']]){
  await page.getByRole('button',{name:`Изменить ${label}`,exact:true}).click();
  const dialog=page.locator('.ww-field-dialog');await dialog.getByRole('searchbox',{name:`Поиск: ${label}`}).fill(name);await dialog.getByRole('checkbox',{name,exact:true}).check();
  await dialog.getByRole('searchbox',{name:`Поиск: ${label}`}).fill('Нет такого имени');await expect(dialog).toContainText('Ничего не найдено');await expect(dialog).toContainText('Выбрано: 1');
  await dialog.getByRole('searchbox',{name:`Поиск: ${label}`}).fill('');await expect(dialog.getByRole('checkbox',{name,exact:true})).toBeChecked();
  await dialog.getByRole('button',{name:'Сохранить поле',exact:true}).click();await expect(dialog).toHaveCount(0);
  await expect(page.locator('.ww-record-dialog')).toContainText(name);
 }
 await page.keyboard.press('Escape');await workshopNav(page,'Персонажи');await page.getByLabel('Поиск персонажей').fill('Виктория');await page.getByRole('button',{name:'Досье Виктория Соловьёва',exact:true}).click();await page.getByRole('button',{name:'Знания',exact:true}).click();await expect(page.locator('.ww-dossier-fields')).toContainText(state.world.facts[fid].text);
 const draft=await(await request.get(url+'?author=true')).json();const fact=draft.state.world.facts[fid];
 expect(fact.secret_keeper_ids).toEqual(['ilya']);expect(fact.secret_biography_ids).toEqual(['viktoria_solovyova']);
 expect(fact.secret_subject_ids).toEqual(state.world.facts[fid].secret_subject_ids);
 const response=await request.post(url+'/confirm',{data:{revision:draft.revision,version_id:draft.version_id,accept_warnings:true}});expect(response.ok(),await response.text()).toBe(true);
 const save=await response.json(),author=await(await request.get(`/api/saves/${save.save}/author-state`)).json();
 expect(author.snapshot.world_state.facts[fid]).toMatchObject({secret_keeper_ids:['ilya'],secret_biography_ids:['viktoria_solovyova']});
 const game=await(await request.get(`/api/saves/${save.save}`)).json();
 expect(game.state.world.facts[fid]).toMatchObject({secret_keeper_ids:['ilya'],secret_biography_ids:['viktoria_solovyova']});
});
