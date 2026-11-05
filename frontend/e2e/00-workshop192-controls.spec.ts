import {test,expect,type Page,type APIRequestContext} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {nav} from './navigation';
import {authorView,workshopNav} from './workshop-navigation';

const fixture=()=>JSON.parse(readFileSync(new URL('../../tests/fixtures/initial_world/workshop188.json',import.meta.url),'utf8'));
async function create(request:APIRequestContext,state=fixture()){
 const w=await(await request.post('/api/workspaces',{data:{name:'Одноимённый мир'}})).json();
 const url=`/api/workspaces/${w.id}/draft`;
 expect((await request.post(url+'/import',{data:{revision:0,format:'json',text:JSON.stringify(state)}})).ok()).toBe(true);
 return {id:w.id,url};
}
async function open(page:Page,id:string){
 await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),id);
 await page.goto('/');await nav(page,'Создать');await authorView(page);
}

test('W01 W02 all five search types open by keyboard and player search excludes hidden canon',async({page,request})=>{
 const state=fixture();
 state.characters[0].fields.Биография+=' Поисковыйкодперсонажа.';
 state.locations[0].text+=' Поисковыйкодместа.';
 state.world.organizations.search_club={id:'search_club',name:'Клуб садоводов',context:'Поисковыйкодсообщества.'};
 state.world.threads.thread_weekend.description+=' Поисковыйкодсюжета.';
 state.world.facts.fact_friendship.text+=' Поисковыйкодфакта.';
 state.world.facts.fact_maxim_sale.text+=' Скрытыйкодпродажи.';
 const {id,url}=await create(request,state);await open(page,id);
 const search=async()=>{
  if((page.viewportSize()?.width||1440)>760)await page.locator('.ww-topbar').getByRole('button',{name:'Поиск по миру',exact:true}).click();
  else {await page.getByRole('button',{name:'Разделы мастерской',exact:true}).click();await page.locator('.ww-menu-dialog').getByRole('button',{name:'Поиск по миру',exact:true}).click()}
  return page.getByRole('dialog',{name:'Поиск по миру',exact:true});
 };
 for(const [query,kind,title] of [['Поисковыйкодперсонажа','Персонаж','Илья Соколов'],['Поисковыйкодместа','Место','Посёлок Сосновка'],['Поисковыйкодсообщества','Сообщество','Клуб садоводов'],['Поисковыйкодсюжета','Сюжетная линия','Поисковыйкодсюжета'],['Поисковыйкодфакта','Факт','Поисковыйкодфакта']]){
  const dialog=await search();await dialog.getByRole('textbox').fill(query);
  const result=dialog.locator('.ww-search-results button');await expect(result).toHaveCount(1);await expect(result.locator('small')).toHaveText(kind);
  await page.keyboard.press('Tab');await expect(result).toBeFocused();await page.keyboard.press('Enter');
  const target=page.locator(kind==='Персонаж'?'.ww-dossier-dialog':'.ww-record-dialog');await expect(target).toContainText(title);
  await page.keyboard.press('Escape');await expect(target).toHaveCount(0);
 }
 await page.getByRole('button',{name:'Игрок',exact:true}).click();await expect(page.getByRole('button',{name:'Игрок',exact:true})).toHaveAttribute('aria-pressed','true');
 const reader=await(await request.get(url)).json();expect(JSON.stringify(reader)).not.toContain('Скрытыйкодпродажи');
 const dialog=await search();await dialog.getByRole('textbox').fill('Скрытыйкодпродажи');await expect(dialog.locator('.ww-search-results button')).toHaveCount(0);await expect(dialog.getByRole('status')).toContainText('Ничего не найдено');
 await dialog.getByRole('textbox').fill('');await expect(dialog.getByText('Объекты вашего мира',{exact:true})).toBeVisible();await expect(dialog.locator('.ww-search-results button').first()).toBeVisible();
});

test('W31 feeling keyboard endpoints, unknown, two-field save and rollback preserve reverse edge',async({page,request})=>{
 const state=fixture();
 const {id,url}=await create(request,state),before=await(await request.get(url+'?author=true')).json();
 const find=(s:any,source:string,target:string)=>Object.entries(s.world.relationships).find(([,r]:any)=>r.source_id===source&&r.target_id===target)!;
 const [edge,original]=find(before.state,'ilya','sonya'),[reverse,reverseOriginal]=find(before.state,'sonya','ilya');
 await open(page,id);await workshopNav(page,'Связи и семьи');
 await page.getByLabel('Чьи отношения показать').selectOption('ilya');
 await page.locator('.ww-records-relationship .ww-record-card').filter({has:page.getByRole('heading',{name:'Илья Соколов → Соня Ковалёва',exact:true})}).getByRole('button',{name:'Открыть запись →',exact:true}).click();
 await page.locator('.ww-record-dialog').getByRole('button',{name:'Редактировать запись',exact:true}).click();
 const editor=page.locator('.ww-record-editor'),trust=editor.getByRole('slider',{name:'Доверие',exact:true});
 await expect(editor.getByRole('slider',{name:'Страх',exact:true})).toHaveAttribute('aria-valuetext','Не задано');
 await trust.focus();await page.keyboard.press('Home');await expect(trust).toHaveValue('-100');
 await page.keyboard.press('End');await expect(trust).toHaveValue('100');
 await page.keyboard.press('ArrowLeft');await expect(trust).toHaveValue('99');
 await editor.getByLabel('Доверие · число',{exact:true}).fill('0');await expect(trust).toHaveAttribute('aria-valuetext','0');
 const affection=editor.getByRole('slider',{name:'Привязанность',exact:true});await affection.focus();await page.keyboard.press('Home');await expect(affection).toHaveValue('-100');
 const fear=editor.getByRole('slider',{name:'Страх',exact:true});await fear.focus();await page.keyboard.press('ArrowRight');await expect(fear).toHaveValue('1');
 await editor.locator('.ww-feeling').filter({has:page.getByRole('slider',{name:'Страх',exact:true})}).getByRole('button',{name:'Не задано',exact:true}).click();await expect(fear).toHaveAttribute('aria-valuetext','Не задано');
 expect((await(await request.get(url+'?author=true')).json()).state).toEqual(before.state);
 await editor.getByLabel('Принять семантические предупреждения при сохранении').check();await editor.getByRole('button',{name:'Сохранить изменения',exact:true}).click();await expect(editor).toHaveCount(0);
 const saved=await(await request.get(url+'?author=true')).json();
 expect(saved.revision).toBe(before.revision+1);expect(saved.history).toHaveLength(before.history.length+1);
 expect(saved.state.world.relationships[edge]).toEqual({...original as object,dimensions:{...(original as any).dimensions,trust:0,affection:-100}});
 expect(saved.state.world.relationships[reverse]).toEqual(reverseOriginal);
 await page.keyboard.press('Escape');await workshopNav(page,'История и файлы');
 await page.getByText(`История версий · ${saved.history.length}`,{exact:true}).click();
 await page.locator('.workshop-version').last().getByRole('button',{name:'Посмотреть версию',exact:true}).click();
 const preview=page.locator('.ww-version-preview');await preview.getByRole('checkbox').check();
 await preview.getByRole('button',{name:'Восстановить выбранную версию',exact:true}).click();await expect(preview).toHaveCount(0);
 const restored=await(await request.get(url+'?author=true')).json();expect(restored.state).toEqual(before.state);expect(restored.revision).toBe(saved.revision+1);
});

test('W04 W54 W55 overview edit and same-name drafts require a fresh decision after concurrent deletion conflict',async({page,request})=>{
 const current=await create(request),other=await create(request);
 await open(page,current.id);
 await page.getByRole('button',{name:'Изменить описание и правила',exact:true}).click();
 const editor=page.locator('.ww-record-editor');await editor.getByLabel('Название',{exact:true}).fill('Авторская новая обложка');
 await editor.getByLabel('Принять семантические предупреждения при сохранении').check();await editor.getByRole('button',{name:'Сохранить изменения',exact:true}).click();await expect(editor).toHaveCount(0);
 await expect(page.locator('.ww-hero h1')).toHaveText('Авторская новая обложка');
 const own=await(await request.get(current.url+'?author=true')).json(),otherBefore=await(await request.get(other.url+'?author=true')).json();
 expect((await request.patch(other.url,{data:{revision:otherBefore.revision,operation:'patch',kind:'campaign',field:'tone',value:'Другой мир',warnings_ack:true}})).ok()).toBe(true);
 const otherChanged=await(await request.get(other.url+'?author=true')).json();
 // Use the history shortcut, not the sidebar: every entry path must refresh metadata.
 await workshopNav(page,'История и файлы');await page.getByRole('button',{name:'Мои черновики и корзина',exact:true}).click();
 const row=page.locator(`.workshop-draft-list [data-workspace-id="${current.id}"]`);
 await expect(page.locator(`.workshop-draft-list [data-workspace-id="${other.id}"]`)).toContainText(`Ревизия ${otherChanged.revision}`);
 await expect(row).toContainText(`Ревизия ${own.revision} · Открыт`);
 await row.getByRole('button',{name:'Удалить черновик «Одноимённый мир»',exact:true}).click();
 const confirmation=page.getByRole('dialog',{name:'Удалить «Одноимённый мир»?',exact:true});
 await expect(confirmation).toContainText(`Ревизия ${own.revision}.`);
 expect((await request.patch(current.url,{data:{revision:own.revision,operation:'patch',kind:'campaign',field:'tone',value:'Конкурентная правка',warnings_ack:true}})).ok()).toBe(true);
 const newer=await(await request.get(current.url+'?author=true')).json();
 const deletes:number[]=[];page.on('response',r=>{if(r.url().endsWith(`/api/workspaces/${current.id}`)&&r.request().method()==='DELETE')deletes.push(r.status())});
 await confirmation.getByRole('button',{name:'Удалить',exact:true}).click();
 await expect(confirmation.getByRole('alert')).toContainText(`теперь ревизия ${newer.revision}`);expect(deletes).toEqual([409]);
 expect((await(await request.get('/api/workspaces')).json()).some((w:any)=>w.id===current.id)).toBe(true);
 await confirmation.getByRole('button',{name:'Отмена',exact:true}).click();await expect(confirmation).toHaveCount(0);
 expect((await(await request.get(current.url+'?author=true')).json()).state).toEqual(newer.state);
 // Reopening refreshes the current draft; only a second explicit decision deletes it.
 await page.reload();await nav(page,'Создать');await authorView(page);await workshopNav(page,'История и файлы');await page.getByRole('button',{name:'Мои черновики и корзина',exact:true}).click();
 await row.getByRole('button',{name:'Удалить черновик «Одноимённый мир»',exact:true}).click();await expect(confirmation).toContainText(`Ревизия ${newer.revision}.`);
 await confirmation.getByRole('button',{name:'Удалить',exact:true}).click();await expect(row).toHaveCount(0);
 await page.locator('.workshop-trash > summary').click();await page.locator(`.workshop-trash [data-workspace-id="${current.id}"]`).getByRole('button',{name:'Восстановить',exact:true}).click();await expect(row).toBeVisible();
 expect((await(await request.get(current.url+'?author=true')).json()).state).toEqual(newer.state);
 expect((await(await request.get(other.url+'?author=true')).json()).state).toEqual(otherChanged.state);
});

test('W43 custom calendar rejects an invalid day and crosses the month boundary without changing agency',async({page,request})=>{
 const state=fixture();
 state.world_clock.calendar={...state.world_clock.calendar,start_date:'2026-10-30',start_weekday:1,profile:{id:'custom',system:'custom',month_lengths:Array(12).fill(30),month_names:Array.from({length:12},(_,i)=>`Месяц ${i+1}`),weekday_names:['Один','Два','Три'],observances:[],seasons:[],regional:null}};
 const {id,url}=await create(request,state),before=await(await request.get(url+'?author=true')).json();
 await open(page,id);await workshopNav(page,'Сцена и правила');
 const editTime=page.getByRole('button',{name:'Изменить Минута мира',exact:true});await editTime.click();
 const editor=page.locator('.ww-field-dialog'),date=editor.getByLabel('Минута мира · дата',{exact:true}),time=editor.getByLabel('Минута мира · время',{exact:true}),save=editor.getByRole('button',{name:'Сохранить поле',exact:true});
 await expect(date).toHaveAttribute('type','text');await expect(date).toHaveValue('2026-10-30');
 await date.fill('2026-10-31');await date.press('Tab');await expect(editor.getByRole('alert')).toBeVisible();await expect(save).toBeDisabled();
 expect((await(await request.get(url+'?author=true')).json()).state).toEqual(before.state);
 await date.fill('2026-11-01');await date.press('Tab');await expect(editor.locator('.ww-time-editor [role=status]')).toContainText('1 Месяц 11');
 await time.fill('00:10');await expect(editor.locator('.ww-time-editor [role=status]')).toContainText('00:10');await expect(save).toBeEnabled();
 expect((await(await request.get(url+'?author=true')).json()).revision).toBe(before.revision);
 await save.click();await expect(editor).toHaveCount(0);
 const saved=await(await request.get(url+'?author=true')).json();expect(saved.state.world_clock.minute).toBe(1450);expect(saved.revision).toBe(before.revision+1);
 expect(saved.state.camera).toEqual(before.state.camera);expect(saved.state.controlled_actor_id).toBe(before.state.controlled_actor_id);expect(saved.state.protagonist_id).toBe(before.state.protagonist_id);
 await page.reload();await nav(page,'Создать');await authorView(page);await workshopNav(page,'Сцена и правила');await editTime.click();
 await expect(date).toHaveValue('2026-11-01');await expect(time).toHaveValue('00:10');await expect(save).toBeDisabled();
});
