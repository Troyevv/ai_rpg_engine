import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {nav} from './navigation';
import {authorView,workshopNav} from './workshop-navigation';

test('dossier rows fit the available panel and retain editable details without nesting a catalogue', async({page,request})=>{
 const state=JSON.parse(readFileSync(new URL('../../tests/fixtures/runtime_handoff/world.json',import.meta.url),'utf8'));
 const w=await(await request.post('/api/workspaces',{data:{name:'Досье и роли'}})).json();
 const path=`/api/workspaces/${w.id}/draft`;
 expect((await request.post(path+'/import',{data:{revision:0,format:'json',text:JSON.stringify(state)}})).ok()).toBe(true);
 await page.addInitScript(wid=>localStorage.setItem('draftWorkspace',wid),w.id);
 await page.goto('/');await nav(page,'Создать');await authorView(page);await workshopNav(page,'Персонажи');
 const open=async()=>{
  await page.getByLabel('Поиск персонажей').fill('Илья Александров');
  await page.getByRole('button',{name:'Досье Илья Александров',exact:true}).click();
  await page.getByRole('tab',{name:'Сейчас',exact:true}).click();
 };
 await open();
 const dossier=page.getByRole('dialog',{name:'Досье персонажа',exact:true});
 const role=dossier.getByRole('region',{name:'Профессии и роли',exact:true});
 const residence=dossier.getByRole('region',{name:'Проживание',exact:true});
 const roleButton=role.getByRole('button',{name:/Государственный адвокат по назначению/});
 await expect(roleButton).toBeVisible();
 await expect(residence).toContainText(state.locations.find((l:{id:string})=>l.id==='ilya_cabinet').name);
 await expect(dossier.getByRole('heading',{name:/Обстоятельства/})).toHaveCount(0);
 await expect(dossier.getByPlaceholder('Поиск по разделу')).toHaveCount(0);
 await expect(dossier.getByText('Группировать по')).toHaveCount(0);
 const width=await roleButton.evaluate(el=>el.getBoundingClientRect().width/el.closest('.ww-dossier-fields')!.getBoundingClientRect().width);
 expect(width).toBeGreaterThan(.92);
 await roleButton.click();
 await expect(role).toContainText('арендует кабинет');
 const edit=role.locator('.draft-field').filter({hasText:'Государственный адвокат по назначению'}).getByRole('button');
 await edit.click();
 const field=page.locator('.ww-field-dialog');
 const title='Адвокат по назначению городского суда';
 await field.getByRole('textbox').first().fill(title);
 const saved=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().endsWith(path)&&r.ok());
 await field.getByRole('button',{name:'Сохранить поле'}).click();await saved;
 await expect(field).toHaveCount(0);
 await expect(role.getByRole('button',{name:new RegExp(title)})).toBeVisible();
 await dossier.getByRole('button',{name:'Готово'}).click();
 await page.getByRole('button',{name:'Игрок',exact:true}).click();await open();
 await role.getByRole('button',{name:new RegExp(title)}).click();
 await expect(role).toContainText('арендует кабинет');
 await expect(role.getByRole('button',{name:/Изменить/})).toHaveCount(0);
 await expect(dossier.getByText('Технические сведения',{exact:true})).toHaveCount(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('author can publish a safe field or bind it to a secret in the same revision as the text',async({page,request})=>{
 const state=JSON.parse(readFileSync(new URL('../../tests/fixtures/initial_world/workshop188.json',import.meta.url),'utf8'));
 const w=await(await request.post('/api/workspaces',{data:{name:'Видимость досье'}})).json(), path=`/api/workspaces/${w.id}/draft`;
 expect((await request.post(path+'/import',{data:{revision:0,format:'json',text:JSON.stringify(state)}})).ok()).toBe(true);
 await page.addInitScript(wid=>localStorage.setItem('draftWorkspace',wid),w.id);
 await page.goto('/');await nav(page,'Создать');await authorView(page);await workshopNav(page,'Персонажи');
 await page.getByRole('button',{name:'Досье Максим Ковалёв',exact:true}).click();
 const dossier=page.getByRole('dialog',{name:'Досье персонажа',exact:true}), label='Страхи и уязвимости';
 await dossier.getByRole('tab',{name:'Личность',exact:true}).click();
 const open=()=>dossier.getByRole('button',{name:'Изменить fields.'+label,exact:true}).click();
 await open();
 const field=page.locator('.ww-field-dialog'),rule=field.getByLabel('Правило показа'),
 save=field.getByRole('button',{name:'Сохранить поле',exact:true});
 await field.getByText('Видимость для игрока',{exact:true}).click();
 await rule.selectOption('public');await expect(save).toBeEnabled();
 await page.keyboard.press('Escape');await open();
 await field.getByText('Видимость для игрока',{exact:true}).click();
 await expect(rule).toHaveValue('public');await expect(field.locator('.ww-field-status')).toContainText('несохранённые');
 const safe='Боится выступать перед большой аудиторией.';
 await field.getByRole('textbox',{name:label,exact:true}).fill(safe);
 const commit=async()=>{
  const done=page.waitForResponse(r=>r.url().endsWith(path)&&r.request().method()==='PATCH');
  await save.click();const result=await done;expect(result.ok(),await result.text()).toBe(true);
  await expect(field).toHaveCount(0);return result.request().postDataJSON();
 };
 expect(await commit()).toMatchObject({value:safe,field_visibility:[]});
 const playerFields=async()=>{
  const d=(await(await request.get(path)).json()).state;
  expect(d.card_field_facts).toBeUndefined();
  return d.characters.find((c:{id:string})=>c.id==='maxim').fields;
 };
 expect((await playerFields())[label]).toBe(safe);
 await open();await field.getByText('Видимость для игрока',{exact:true}).click();
 await expect(rule).toHaveValue('public');await rule.selectOption('after');
 await expect(save).toBeDisabled();
 await field.getByRole('checkbox',{name:/Максим тайно готовит продажу/}).check();
 expect(await commit()).toMatchObject({value:safe,field_visibility:['fact_maxim_sale']});
 expect((await playerFields())[label]).toBeUndefined();
});
