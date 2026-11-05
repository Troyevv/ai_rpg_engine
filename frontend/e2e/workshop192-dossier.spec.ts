import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {nav} from './navigation';
import {authorView,workshopNav} from './workshop-navigation';

test('W21 W22 empty motives use their canonical editor; searchable people retain tab and focus',async({page,request},info)=>{
 const world=JSON.parse(readFileSync(new URL('../../tests/fixtures/initial_world/workshop188.json',import.meta.url),'utf8'));
 const first=world.characters[0],second=world.characters[1];
 first.fields['Намерения']='';world.world.characters[first.id].intentions=[];
 second.name='Соня Александровна Соколова';
 const w=await(await request.post('/api/workspaces',{data:{name:'Мотивы и переходы'}})).json(),url=`/api/workspaces/${w.id}/draft`;
 expect((await request.post(url+'/import',{data:{revision:0,format:'json',text:JSON.stringify(world)}})).ok()).toBe(true);
 const before=await(await request.get(url+'?author=true')).json();
 await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),w.id);
 await page.goto('/');await nav(page,'Создать');await authorView(page);await workshopNav(page,'Персонажи');
 for(const width of info.project.name==='mobile'?[360,390,430]:[1440]){
  await page.setViewportSize({width,height:width===360?800:width===390?844:width===430?932:1000});
  await page.locator('.ww-character-card').first().click();
  const dossier=page.locator('.ww-dossier-dialog');await dossier.getByRole('tab',{name:'Цели',exact:true}).click();
  const empty=dossier.locator('.ww-empty-motives');
  await expect(empty.locator(':scope > summary')).toBeVisible();
  await expect(dossier.getByRole('button',{name:'Изменить fields.Намерения',exact:true})).toHaveCount(0);
  await expect(empty.getByRole('button',{name:'Изменить Намерения',exact:true})).not.toBeVisible();
  await empty.locator(':scope > summary').click();
  await empty.getByRole('button',{name:'Изменить Намерения',exact:true}).click();
  await expect(page.locator('.ww-field-dialog').getByRole('button',{name:'Добавить запись',exact:true})).toBeVisible();
  await page.locator('.ww-field-dialog').getByRole('button',{name:'Закрыть',exact:true}).click();
  await expect(empty.getByRole('button',{name:'Изменить Намерения',exact:true})).toBeVisible();
  await dossier.getByLabel('Найти персонажа в досье').fill('Александровна');
  await dossier.getByLabel('Переключить досье').selectOption(second.id);
  await expect(dossier.locator('.ww-dossier-identity h2')).toHaveText(second.name);
  await expect(dossier.getByRole('tab',{name:'Цели',exact:true})).toHaveAttribute('aria-selected','true');
  await dossier.getByLabel('Найти персонажа в досье').fill('');
  await dossier.getByRole('button',{name:`Досье ${first.name}`,exact:true}).click();
  await expect(dossier.locator('.ww-dossier-identity h2')).toHaveText(first.name);
  await page.keyboard.press('Escape');await expect(page.locator('.ww-character-card').first()).toBeFocused();
 }
 const after=await(await request.get(url+'?author=true')).json();expect(after.state).toEqual(before.state);expect(after.revision).toBe(before.revision);
});

test('W23 W41 atomic editor retains a conflicting buffer across reload and explicitly discards it',async({page,request})=>{
 const world=JSON.parse(readFileSync(new URL('../../tests/fixtures/initial_world/workshop188.json',import.meta.url),'utf8'));
 const w=await(await request.post('/api/workspaces',{data:{name:'Атомарная правка'}})).json(),url=`/api/workspaces/${w.id}/draft`;
 expect((await request.post(url+'/import',{data:{revision:0,format:'json',text:JSON.stringify(world)}})).ok()).toBe(true);
 const before=await(await request.get(url+'?author=true')).json();
 await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),w.id);
 const open=async()=>{await page.goto('/');await nav(page,'Создать');await authorView(page);await workshopNav(page,'Персонажи');await page.locator('.ww-character-card').first().click();await page.getByRole('button',{name:'Редактировать карточку',exact:true}).click()};
 await open();const editor=page.locator('.ww-record-editor');
 await editor.getByLabel('Имя',{exact:true}).fill('Илья Константинович Соколов');
 await editor.getByLabel('Роль',{exact:true}).fill('Автор книг и музыкант');
 expect((await(await request.get(url+'?author=true')).json()).revision).toBe(before.revision);
 // Another client commits a real revision while this editor still owns its old base.
 const concurrent=await request.patch(url,{data:{revision:before.revision,operation:'patch',kind:'campaign',entity_id:'',field:'tone',value:'Спокойный вечер',warnings_ack:true}});
 expect(concurrent.ok(),await concurrent.text()).toBe(true);
 const newer=await(await request.get(url+'?author=true')).json();
 const conflict=page.waitForResponse(r=>r.url().endsWith(url)&&r.request().method()==='PATCH');
 await editor.getByRole('checkbox').check();await editor.getByRole('button',{name:'Сохранить изменения',exact:true}).click();expect((await conflict).status()).toBe(409);
 await expect(editor.getByRole('alert')).toBeVisible();await expect(editor.getByLabel('Имя',{exact:true})).toHaveValue('Илья Константинович Соколов');
 expect((await(await request.get(url+'?author=true')).json()).state).toEqual(newer.state);
 await open();await expect(editor.getByLabel('Имя',{exact:true})).toHaveValue('Илья Константинович Соколов');await expect(editor.getByRole('button',{name:'Сохранить изменения',exact:true})).toBeDisabled();
 await editor.getByRole('button',{name:'Отменить правки',exact:true}).click();
 await page.getByRole('button',{name:'Редактировать карточку',exact:true}).click();await expect(editor.getByLabel('Имя',{exact:true})).toHaveValue(world.characters[0].name);
 await editor.getByLabel('Имя',{exact:true}).fill('Илья Константинович Соколов');await editor.getByLabel('Роль',{exact:true}).fill('Автор книг и музыкант');
 await editor.getByRole('checkbox').check();await editor.getByRole('button',{name:'Сохранить изменения',exact:true}).click();await expect(editor).toHaveCount(0);
 const saved=await(await request.get(url+'?author=true')).json();
 expect(saved.revision).toBe(newer.revision+1);expect(saved.history).toHaveLength(newer.history.length+1);
 expect(saved.state.characters[0]).toEqual({...newer.state.characters[0],name:'Илья Константинович Соколов',fields:{...newer.state.characters[0].fields,Роль:'Автор книг и музыкант'}});
 expect(saved.state.world).toEqual(newer.state.world);
});
