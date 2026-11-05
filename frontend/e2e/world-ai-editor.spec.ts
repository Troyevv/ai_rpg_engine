import {confirmWorkshopStart} from './workshop-navigation';
import {generateIdea} from './idea-navigation';
import {workshopNav,draftsMenu} from './workshop-navigation';
import {test,expect} from '@playwright/test';
import {nav} from './navigation';
import {defaults} from '../src/types';

for(const skin of ['graphite','parchment']) test(`AI editor preview, confirmation, rollback and game in ${skin}`,async({page,request},info)=>{
 const theme=await(await request.post('/test/seed')).json();
 await request.put(`/api/worlds/${theme.world}/presentation`,{data:{theme_id:skin}});
 const workspace=await(await request.post('/test/editor173',{data:{fail:false}})).json();
 const url=`/api/workspaces/${workspace.id}/draft`;
 await page.goto('/');
 const profile=await page.evaluate(()=>localStorage.getItem('profile'));
 const settings=await request.put(`/api/settings/${profile}`,{data:{...defaults,summary:{...defaults.summary,provider:'deepseek',model:'deepseek-flash',thinking:'off',context_length:131072,max_tokens:24000}}});expect(settings.ok(),await settings.text()).toBeTruthy();
 await request.put('/api/credentials/deepseek',{data:{api_key:'offline-editor173'}});
 await page.evaluate(({wid,world})=>{localStorage.setItem('draftWorkspace',wid);localStorage.setItem('selection',JSON.stringify({world}))},{wid:workspace.id,world:theme.world});
 await page.evaluate(skin=>localStorage.setItem('workshop-theme',JSON.stringify({theme_id:skin,mode:'manual'})),skin);
 await page.reload();await nav(page,'Создать');
 await page.getByLabel('Описание мира или текст импорта').fill('EDITOR173: Город и друзья после пожара.');
 await generateIdea(page);
 await expect(page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true})).toBeEnabled();
 const before=await(await request.get(url+'?author=true')).json();
 await expect(page.getByRole('heading',{name:'AI-редактор мира',exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Открыть вид автора',exact:true}).click();await page.getByRole('button',{name:'Показать всё',exact:true}).click();await workshopNav(page,'Изменить с ИИ');
 const editor=page.locator('.world-ai-editor');
 const instruction='Добавь Веру, её биографию, отношения, мастерскую, события и сюжетную линию. Измени историю организации. '+ 'Сохрани свободу будущего выбора героя. '.repeat(80);
 await editor.getByLabel('Что изменить в мире?').fill(instruction);
 await editor.getByRole('button',{name:'Предложить изменения',exact:true}).click();
 await expect(page.getByRole('status',{name:'Ход проверки мира'})).toContainText('Готовим предложение');
 await page.reload();await nav(page,'Создать');
 await expect(page.getByRole('status',{name:'Ход проверки мира'})).toBeVisible();
 expect((await(await request.get(url+'?author=true')).json()).state).toEqual(before.state);
 expect((await(await request.post('/test/editor173/release')).json()).calls).toBe(1);
 await expect(page.getByRole('status',{name:'Ход проверки мира'})).toHaveCount(0);
 await page.getByRole('button',{name:'Автор мира',exact:true}).click();await page.getByRole('button',{name:'Показать всё',exact:true}).click();await workshopNav(page,'Изменить с ИИ');
 await expect(editor.getByLabel('Что изменить в мире?')).toHaveValue(instruction);
 await expect(editor.getByRole('heading',{name:'Ожидает решения',exact:true})).toBeVisible();
 await expect(editor.getByLabel('Состав изменений')).toContainText('Добавление: 9');
 await expect(editor.locator('.ai-diff-entity').first()).toHaveAttribute('open','');
 await expect(editor.locator('.ai-diff-values').first()).toContainText('До');
 await expect(editor.locator('.ai-diff-values').first()).toContainText('Вера');
 await expect(page.locator('html')).toHaveAttribute('data-theme',skin);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(await page.evaluate(()=>innerWidth));
 await editor.scrollIntoViewIfNeeded();
 if(skin==='graphite')await page.screenshot({path:`/tmp/173-${info.project.name}.png`});
 const preview=await(await request.get(url+'?author=true')).json();expect(preview.version_id).toBe(before.version_id);
 // Keyboard-accessible confirmation, cancel preserves the candidate.
 await editor.getByRole('button',{name:'Применить пакет…'}).focus();await page.keyboard.press('Enter');
 await expect(page.getByRole('dialog')).toBeVisible();await page.keyboard.press('Escape');
 await expect(editor.getByRole('button',{name:'Применить пакет…'})).toBeFocused();
 expect((await(await request.get(url+'?author=true')).json()).state).toEqual(before.state);
 // Drop the first acknowledgement after the server has committed it.
 let dropped=false;
 if(skin==='graphite')await page.route(/\/draft\/edits\/[^/?]+$/,async route=>{
  if(dropped)return route.continue();
  dropped=true;const response=await route.fetch();expect(response.ok()).toBeTruthy();await route.abort('failed');
 });
 await editor.getByRole('button',{name:'Применить пакет…'}).click();await page.getByRole('button',{name:'Подтвердить изменения',exact:true}).click();
 if(skin==='graphite'){
  await expect(page.getByRole('dialog').getByRole('alert')).toBeVisible();
  await page.getByRole('button',{name:'Подтвердить изменения',exact:true}).click();
 }
 await expect(editor.getByText('Изменения сохранены.',{exact:false})).toBeVisible();
 const accepted=await(await request.get(url+'?author=true')).json();expect(accepted.state.world.roles.craft.organization_id).toBe('workshop');
 expect(accepted.history.filter((v:{reason:string})=>v.reason==='ai_edit')).toHaveLength(1);
 expect((await(await request.get(url+'/edits')).json()).edits).toEqual([]);
 // Existing history UI supplies rollback; restore creates a new immutable version.
 await workshopNav(page,'История и файлы');
 await page.getByText(`История версий · ${accepted.history.length}`,{exact:true}).click();
 const previous=page.locator('.workshop-version').filter({hasText:`Версия ${before.history.length} ·`});
 await previous.getByRole('button',{name:'Посмотреть версию',exact:true}).click();const versionPreview=page.locator('.ww-version-preview');await expect(versionPreview.getByRole('heading',{name:before.state.campaign.title,exact:true})).toBeVisible();expect((await(await request.get(url+'?author=true')).json()).revision).toBe(accepted.revision);await versionPreview.getByRole('checkbox').check();await versionPreview.getByRole('button',{name:'Восстановить выбранную версию',exact:true}).click();
 await expect.poll(async()=>(await(await request.get(url+'?author=true')).json()).state).toEqual(before.state);
 const restored=await(await request.get(url+'?author=true')).json();
 // Restore the accepted version through the same public history API, then play it.
 expect((await request.patch(url,{data:{revision:restored.revision,operation:'restore',source_id:accepted.version_id}})).ok()).toBeTruthy();
 await page.reload();await nav(page,'Создать');
 await page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true}).click();await confirmWorkshopStart(page);
 await page.getByRole('button',{name:'Начать игру',exact:true}).click();await expect(page.locator('.choices button')).toHaveCount(6);
 await page.locator('.choices button').first().click();await expect(page.locator('.turn')).toHaveCount(2);
 await expect(page.locator('.choices button')).toHaveCount(6);
 const selected=await page.evaluate(()=>JSON.parse(localStorage.getItem('selection')!));
 const canonical=await(await request.post(`/test/creative172/saves/${selected.save}/canonical`)).json();
 expect(canonical.world_state.roles.craft.actor_id).toBe('craftswoman');expect(canonical.world_state.knowledge['craftswoman:fire'].fact_id).toBe('fire');
 const saved=await(await request.get(`/api/saves/${selected.save}`)).json();
 await page.reload();await expect(page.locator('.turn')).toHaveCount(2);
 expect((await(await request.get(`/api/saves/${selected.save}`)).json()).state).toEqual(saved.state);
 expect((await(await request.post(`/test/creative172/saves/${selected.save}/canonical`)).json()).world_state).toEqual(canonical.world_state);
});

test('AI editor empty response recovery, rejection and stale preview',async({page,request})=>{
 const workspace=await(await request.post('/test/editor173',{data:{fail:true}})).json();const url=`/api/workspaces/${workspace.id}/draft`;
 await page.goto('/');await page.evaluate(wid=>localStorage.setItem('draftWorkspace',wid),workspace.id);await page.reload();await nav(page,'Создать');
 await page.getByLabel('Описание мира или текст импорта').fill('EDITOR173: Друзья в городе.');await generateIdea(page);
 await expect(page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true})).toBeEnabled();
 await page.getByRole('button',{name:'Открыть вид автора',exact:true}).click();await page.getByRole('button',{name:'Показать всё',exact:true}).click();await workshopNav(page,'Изменить с ИИ');
 const editor=page.locator('.world-ai-editor');await editor.getByLabel('Что изменить в мире?').fill('Добавь Веру.');await editor.getByRole('button',{name:'Предложить изменения',exact:true}).click();
 await request.post('/test/editor173/release');
 await expect(page.getByRole('button',{name:'Повторить после сбоя провайдера'})).toBeVisible();
 await page.getByRole('button',{name:'Повторить после сбоя провайдера'}).click();await page.getByRole('button',{name:'Подтвердить одну повторную проверку'}).click();
 await expect(editor.getByRole('button',{name:'Применить пакет…'})).toBeEnabled();
 const draft=await(await request.get(url+'?author=true')).json();
 await request.patch(url,{data:{revision:draft.revision,operation:'patch',kind:'campaign',field:'title',value:'Ручной мир'}});
 await editor.getByRole('button',{name:'Применить пакет…'}).click();await page.getByRole('button',{name:'Подтвердить изменения',exact:true}).click();
 await expect(page.getByRole('dialog').getByRole('alert')).toContainText('Конфликт ревизий');
 await page.keyboard.press('Escape');await page.reload();await nav(page,'Создать');await page.getByRole('button',{name:'Автор мира',exact:true}).click();await page.getByRole('button',{name:'Показать всё',exact:true}).click();await workshopNav(page,'Изменить с ИИ');
 await expect(editor.getByRole('button',{name:'Применить пакет…'})).toBeDisabled();
 await editor.getByRole('button',{name:'Отклонить пакет'}).click();await expect(editor.getByRole('heading',{name:'Отклонено',exact:true})).toBeVisible();
 expect((await(await request.get(url+'?author=true')).json()).state.campaign.title).toBe('Ручной мир');
});

test('AI editor workspace switch isolates input, errors, preview and late responses',async({page,request})=>{
 const workspace=await(await request.post('/test/editor173',{data:{fail:false}})).json();
 const url=`/api/workspaces/${workspace.id}/draft`;
 await page.goto('/');await page.evaluate(wid=>localStorage.setItem('draftWorkspace',wid),workspace.id);
 await page.reload();await nav(page,'Создать');
 await page.getByLabel('Описание мира или текст импорта').fill('EDITOR173: Два разных мира.');
 await generateIdea(page);
 await expect(page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true})).toBeEnabled();
 const first=await(await request.get(url+'?author=true')).json();
 const second=await(await request.post('/api/workspaces',{data:{name:'Второй мир'}})).json();
 expect((await request.post(`/api/workspaces/${second.id}/draft/import`,{data:{revision:0,text:JSON.stringify(first.state),format:'json'}})).ok()).toBeTruthy();
 await page.evaluate(wid=>localStorage.setItem(`world-editor:${wid}`,'Несохранённая инструкция второго мира'),second.id);
 await page.reload();await nav(page,'Создать');
 await page.getByRole('button',{name:'Открыть вид автора',exact:true}).click();await page.getByRole('button',{name:'Показать всё',exact:true}).click();await workshopNav(page,'Изменить с ИИ');
 const editor=page.locator('.world-ai-editor');
 await editor.getByLabel('Что изменить в мире?').fill('Первый мир: добавь Веру.');
 await editor.getByRole('button',{name:'Предложить изменения',exact:true}).click();await request.post('/test/editor173/release');
 await expect(editor.getByRole('button',{name:'Применить пакет…'})).toBeEnabled();
 await editor.getByLabel('Что изменить в мире?').fill('Несохранённая инструкция первого мира');
 await page.route(/\/draft\/edits$/,route=>route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({detail:'Ошибка только первого мира'})}));
 await editor.getByRole('button',{name:'Предложить изменения',exact:true}).click();
 await expect(editor.getByRole('alert')).toHaveText('Ошибка только первого мира');
 await draftsMenu(page);
await page.locator(`[data-workspace-id="${second.id}"]`).getByRole('button',{name:'Второй мир',exact:true}).click();
 await page.getByRole('button',{name:'Автор мира',exact:true}).click();await workshopNav(page,'Изменить с ИИ');
 await expect(editor.getByLabel('Что изменить в мире?')).toHaveValue('Несохранённая инструкция второго мира');
 await expect(editor.locator('.ai-preview')).toHaveCount(0);await expect(editor.getByRole('alert')).toHaveCount(0);
 // Return to A, hold its history response, then switch back to B.
 let release!:()=>void;let captured!:()=>void;
 const held=new Promise<void>(resolve=>{release=resolve});const arrived=new Promise<void>(resolve=>{captured=resolve});
 await page.route(`**/workspaces/${workspace.id}/draft/edits?author=true`,async route=>{
  const response=await route.fetch();captured();await held;await route.fulfill({response}).catch(()=>{});
 });
 await draftsMenu(page);await page.locator(`[data-workspace-id="${workspace.id}"]`).getByRole('button',{name:'AI-редактор',exact:true}).click();
 await page.getByRole('button',{name:'Автор мира',exact:true}).click();await arrived;
 await expect(editor.getByLabel('Что изменить в мире?')).toHaveValue('Несохранённая инструкция первого мира');
 await draftsMenu(page);await page.locator(`[data-workspace-id="${second.id}"]`).getByRole('button',{name:'Второй мир',exact:true}).click();
 await page.getByRole('button',{name:'Автор мира',exact:true}).click();release();
 await expect(editor.getByLabel('Что изменить в мире?')).toHaveValue('Несохранённая инструкция второго мира');
 await expect(editor.locator('.ai-preview')).toHaveCount(0);
 expect(await page.evaluate(wid=>localStorage.getItem(`world-editor:${wid}`),workspace.id)).toBe('Несохранённая инструкция первого мира');
 await page.reload();await nav(page,'Создать');
 await page.getByRole('button',{name:'Автор мира',exact:true}).click();await page.getByRole('button',{name:'Показать всё',exact:true}).click();await workshopNav(page,'Изменить с ИИ');
 await expect(editor.getByLabel('Что изменить в мире?')).toHaveValue('Несохранённая инструкция второго мира');
});

test('AI editor refuses dangling locations and archived NPC references without mutating canon',async({page,request})=>{
 const workspace=await(await request.post('/test/editor173',{data:{fail:false}})).json();
 const url=`/api/workspaces/${workspace.id}/draft`;
 await page.goto('/');await page.evaluate(wid=>localStorage.setItem('draftWorkspace',wid),workspace.id);
 await page.reload();await nav(page,'Создать');
 await page.getByLabel('Описание мира или текст импорта').fill('EDITOR173: Проверка удаления.');
 await generateIdea(page);
 await expect(page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true})).toBeEnabled();
 const draft=await(await request.get(url+'?author=true')).json();const state=draft.state;
 state.characters.push({...structuredClone(state.characters.at(-1)),id:'archive184',name:'Архивный персонаж'});
 state.world.characters.archive184={id:'archive184',situation:'Уехал.',location:null,goals:[],intentions:[],obligations:[]};
 state.world.scene_records.archived={id:'archived',snapshot:{participants:['archive184']},text:'Запись прошлого остаётся.'};
 const imported=await request.post(url+'/import',{data:{revision:draft.revision,text:JSON.stringify(state),format:'json'}});
 expect(imported.ok(),await imported.text()).toBeTruthy();const before=await(await request.get(url+'?author=true')).json();
 await page.reload();await nav(page,'Создать');
 await page.getByRole('button',{name:'Открыть вид автора',exact:true}).click();await page.getByRole('button',{name:'Показать всё',exact:true}).click();await workshopNav(page,'Изменить с ИИ');
 const editor=page.locator('.world-ai-editor');await request.post('/test/editor173/release');
 for(const instruction of ['DELETE184_LOCATION','DELETE184_HISTORY']){
  await editor.getByLabel('Что изменить в мире?').fill(instruction);await editor.getByRole('button',{name:'Предложить изменения',exact:true}).click();
  await expect(editor.getByRole('heading',{name:'Запрос прерван',exact:true})).toBeVisible();
  await expect(editor.getByRole('alert')).toContainText('всё ещё связана');
  await expect(editor.getByRole('button',{name:'Применить пакет…'})).toHaveCount(0);
  const current=await(await request.get(url+'?author=true')).json();
  expect(current.state).toEqual(before.state);expect(current.version_id).toBe(before.version_id);
  expect((await(await request.get(url+'/edits')).json()).edits).toEqual([]);
 }
 await page.reload();await nav(page,'Создать');
 expect((await(await request.get(url+'?author=true')).json()).state.world.scene_records.archived).toEqual(state.world.scene_records.archived);
});
