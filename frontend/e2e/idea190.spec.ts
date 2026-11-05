import {draftsMenu} from './workshop-navigation';
import {test,expect,type Page,type TestInfo} from '@playwright/test';
import {nav} from './navigation';
import {defaults} from '../src/types';
async function capture(page:Page,info:TestInfo,name:string){
 await page.mouse.move(0,0);
 await page.evaluate(()=>document.fonts.ready);
 const art=page.locator('.hero-art');
 if(await art.count())await art.evaluate(async el=>{const url=getComputedStyle(el).backgroundImage.match(/url\("?([^")]+)/)?.[1];if(url){const image=new Image();image.src=url;await image.decode()}});
 const brief=page.locator('.idea-atelier > div').filter({has:page.locator('.atelier-hero')});
 if(await brief.count())await expect(brief).toHaveCSS('opacity','1');
 const dialog=page.locator('.atelier-dialog:not(.drawer)');
 if(await dialog.count()){
  const bounds=await dialog.boundingBox(),close=await dialog.locator('.dialog-close').boundingBox();
  expect(bounds).not.toBeNull();expect(close).not.toBeNull();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);expect(bounds!.y).toBeGreaterThanOrEqual(0);
  expect(close!.x).toBeGreaterThanOrEqual(bounds!.x);expect(close!.y).toBeGreaterThanOrEqual(bounds!.y);
  expect(close!.x+close!.width).toBeLessThanOrEqual(bounds!.x+bounds!.width);
 }
 const review=page.getByRole('region',{name:'Сводка замысла'});
 if(await review.count())await expect(review).toHaveCSS('opacity','1');
 const path=info.outputPath(`${name}-${info.project.name}.png`);
 await page.screenshot({path,animations:'disabled'});await info.attach(name,{path,contentType:'image/png'});
}
const idea='В княжестве Валлор письма носят гонцы, но у каждой гильдии есть мобильный телефон. Башни связи принадлежат короне. Я играю за ученицу картографа. Накануне ярмарки на телефон мастера приходит звонок с башни, сгоревшей десять лет назад.';
async function group(page:Page,name:string){await page.locator('.atelier-param').filter({hasText:name}).click()}
async function done(page:Page){await page.getByRole('dialog').getByRole('button',{name:/^(Готово|К параметрам)$/,exact:true}).click();await expect(page.locator('.atelier-dialog')).toHaveCount(0)}
for(const skin of ['graphite','parchment'])test(`idea190: visual, panels, validation, persistence · ${skin}`,async({page,request},info)=>{
 await page.setViewportSize(info.project.name==='mobile'?{width:390,height:844}:{width:1440,height:900});
 await page.addInitScript(skin=>{localStorage.setItem('workshop-theme',JSON.stringify({theme_id:skin,mode:'manual'}))},skin);
 await page.goto('/');await nav(page,'Создать');
 await page.evaluate(skin=>document.documentElement.dataset.theme=skin,skin);
  if(skin==='graphite')await capture(page,info,'production-01-empty');
 await page.getByLabel('Название черновика').fill('Последняя вышка Валлора');
 await page.getByLabel('Описание мира или текст импорта').fill(idea);
 await page.getByLabel('Набор технологий связи',{exact:true}).selectOption('letters');
 await page.getByRole('checkbox',{name:'Мобильные звонки',exact:true}).check();
 await expect(page.getByRole('checkbox',{name:'Письма',exact:true})).toBeChecked();
 await expect(page.getByRole('checkbox',{name:'Гонцы',exact:true})).toBeChecked();
 await expect(page.getByLabel('Набор технологий связи',{exact:true})).toHaveValue('custom');
 await page.evaluate(()=>document.fonts.ready);
 await expect.poll(()=>page.locator('.hero-art').evaluate(async el=>{const url=getComputedStyle(el).backgroundImage.match(/url\("?([^")]+)/)?.[1];if(!url)return 0;const image=new Image();image.src=url;await image.decode();return image.naturalWidth})).toBeGreaterThan(0);
 await page.locator('.ww-scroll, .atelier-editor textarea').evaluateAll(elements=>elements.forEach(el=>{el.scrollTop=0}));
 const shot=info.outputPath(`idea190-${skin}-${info.project.name}.png`);await page.screenshot({path:shot});await info.attach('Эталонный экран '+skin,{path:shot,contentType:'image/png'});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
  if(skin==='graphite'){
   await capture(page,info,'production-02-filled');
   await page.emulateMedia({reducedMotion:'reduce'});
   expect(await page.locator('.channel').first().evaluate(el=>getComputedStyle(el).transitionDuration)).toBe('0s');
   await page.emulateMedia({reducedMotion:'no-preference'});
   for(const [key,title] of [['genre','Жанры истории'],['cast','Персонажи'],['world','Мир и география'],['calendar','Календарь и начало'],['narrative','Темп и последствия']]){
    await group(page,title);await capture(page,info,'production-panel-'+key);await done(page);
   }
   await page.getByRole('button',{name:'Примеры',exact:true}).click();await capture(page,info,'production-examples');await page.keyboard.press('Escape');await expect(page.locator('.atelier-dialog')).toHaveCount(0);
   await page.getByRole('button',{name:'Развернуть редактор идеи'}).click();await capture(page,info,'production-expanded');await done(page);
   await page.getByRole('button',{name:'Правила и особенности',exact:true}).click();await expect(page.locator('.comm-disclosure .atelier-disclosure-body')).toHaveCSS('opacity','1');await page.locator('.comm-extra').scrollIntoViewIfNeeded();await capture(page,info,'production-communication');
   await page.getByRole('button',{name:'Правила и особенности',exact:true}).click();await page.locator('.ww-scroll').evaluate(el=>el.scrollTop=0);
   await page.getByRole('button',{name:'Проверить замысел',exact:true}).click();await expect(page.getByRole('region',{name:'Сводка замысла'})).toBeVisible();await capture(page,info,'production-review');await page.getByRole('button',{name:'К замыслу',exact:true}).click();
  }
 await group(page,'Жанры истории');await page.getByLabel('Основной жанр',{exact:true}).selectOption('custom');await done(page);
 const before=await(await request.get('/api/workspaces')).json();
 await page.getByRole('button',{name:'Проверить замысел',exact:true}).click();
 await expect(page.getByRole('dialog')).toBeVisible();await expect(page.getByRole('dialog').getByRole('alert').first()).toContainText(/жанр/i);
 await expect(page.getByRole('dialog').locator('textarea')).toBeFocused();
 expect(await(await request.get('/api/workspaces')).json()).toEqual(before);
 await page.getByRole('dialog').locator('textarea').fill('Драма и загадка');await done(page);
 await group(page,'Календарь и начало');await page.getByLabel('Календарь начала игры').selectOption('custom');
 await page.getByLabel('Год начала',{exact:true}).pressSequentially('2026');await page.getByLabel('Месяц начала',{exact:true}).fill('01');await page.getByLabel('День начала',{exact:true}).fill('31');await done(page);
 await page.getByRole('button',{name:'Проверить замысел',exact:true}).click();await expect(page.getByRole('dialog').getByRole('alert').first()).toBeVisible();
 expect(await(await request.get('/api/workspaces')).json()).toEqual(before);
 await page.getByLabel('День начала',{exact:true}).fill('30');await done(page);
 await page.reload();await nav(page,'Создать');
 await expect(page.getByLabel('Описание мира или текст импорта')).toHaveValue(idea);
 await group(page,'Календарь и начало');await expect(page.getByLabel('День начала',{exact:true})).toHaveValue('30');await page.keyboard.press('Escape');
 await expect(page.locator('.atelier-param').filter({hasText:'Календарь и начало'})).toBeFocused();
 await page.getByRole('button',{name:'Проверить замысел',exact:true}).click();await expect(page.getByRole('region',{name:'Сводка замысла'})).toContainText('Свой жанр');
 await page.getByRole('button',{name:'К замыслу',exact:true}).click();
 await page.getByRole('button',{name:'Развернуть редактор идеи'}).click();await page.getByRole('dialog').locator('textarea').fill(idea.repeat(80));await done(page);
 await page.getByRole('button',{name:'Примеры',exact:true}).click();await page.getByRole('button',{name:'Заменить текущий текст',exact:true}).first().click();await expect(page.getByRole('button',{name:'Подтвердить замену текста'})).toBeVisible();await page.keyboard.press('Escape');
 await expect(page.getByLabel('Описание мира или текст импорта')).toHaveValue(idea.repeat(80));
 await page.getByLabel('Название черновика').fill('Очень длинное название будущей истории '.repeat(3).slice(0,120));
 await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
 await expect(page.getByLabel('Описание мира или текст импорта')).toHaveValue(idea.repeat(80));
});

test('idea190: real generation, reload, HTTP502 review recovery and author revision',async({page,request},info)=>{
 await page.setViewportSize(info.project.name==='mobile'?{width:390,height:844}:{width:1440,height:900});
 await request.post('/test/idea190',{data:{fail_review:true,custom_calendar:true}});
 await page.goto('/');
 const profile=await page.evaluate(()=>localStorage.getItem('profile'));
 expect((await request.put(`/api/settings/${profile}`,{data:{...defaults,summary:{...defaults.summary,provider:'deepseek',model:'deepseek-flash',thinking:'off',context_length:131072,max_tokens:24000}}})).ok()).toBeTruthy();
 await request.put('/api/credentials/deepseek',{data:{api_key:'offline-idea190'}});
 await page.reload();await nav(page,'Создать');
 await page.getByLabel('Описание мира или текст импорта').fill('ATELIER190. Компания друзей у моря.');
 await page.getByLabel('Набор технологий связи',{exact:true}).selectOption('letters');await page.getByRole('checkbox',{name:'Мобильные звонки',exact:true}).check();
 await group(page,'Персонажи');await page.getByRole('radio',{name:'Свой состав',exact:true}).check();await page.getByLabel('Важные NPC',{exact:true}).fill('4');await page.getByLabel('Второстепенные NPC',{exact:true}).fill('7');await done(page);
 await group(page,'Жанры истории');await page.getByLabel('Основной жанр',{exact:true}).selectOption('custom');await page.getByRole('dialog').locator('textarea').fill('Драма');await done(page);
 await group(page,'Календарь и начало');await page.getByLabel('Календарь начала игры').selectOption('custom');
 await page.getByLabel('Длины месяцев').fill('30, 40');await page.getByLabel('Названия месяцев').fill('Первый, Второй');
 await page.getByLabel('Год начала',{exact:true}).fill('2026');await page.getByLabel('Месяц начала',{exact:true}).fill('02');await page.getByLabel('День начала',{exact:true}).fill('30');
 await page.getByLabel('Время начала').fill('18:30');
 const preview=page.waitForResponse(r=>r.url().endsWith('/calendar/preview'));
 await page.getByRole('button',{name:'Предпросмотр календаря',exact:true}).click();expect((await preview).ok()).toBeTruthy();await done(page);
 await page.getByRole('button',{name:'Проверить замысел',exact:true}).click();
 const start=page.waitForResponse(r=>r.url().endsWith('/draft/generate')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Создать мир',exact:true}).dblclick();const response=await start;expect(response.ok(),await response.text()).toBeTruthy();const job=await response.json();
 const wid=await page.locator('.world-workshop').getAttribute('data-workspace-id');const url=`/api/workspaces/${wid}/draft`;
 await expect(page.getByRole('status',{name:'Ход проверки мира'})).toContainText('смысловую');
 const before=await(await request.get(url+'?author=true')).json();expect(before.version_id).toBeTruthy();
 await expect(page.locator('.fl-stages li[data-state=done]')).toHaveCount(3);await page.locator('.ww-scroll').evaluate(el=>el.scrollTop=0);await capture(page,info,'production-running');
 await page.reload();await nav(page,'Создать');await expect(page.getByRole('region',{name:'Этапы создания мира'})).toBeVisible();
 await request.post('/test/idea190/release');await expect(page.getByRole('alert')).toContainText('HTTP 502');
 await expect(page.getByText(/известной причиной HTTP 400/)).toHaveCount(0);
 await expect(page.locator('[data-sonner-toast]')).toHaveCount(0);await capture(page,info,'production-error');
 await page.reload();await nav(page,'Создать');
 await page.getByRole('button',{name:'Повторить проверку',exact:true}).click();
 await expect.poll(async()=> (await(await request.get(url)).json()).job.status).toBe('saved');
 const after=await(await request.get(url+'?author=true')).json();expect(after.job.id).toBe(job.id);expect(after.review.status).toBe('completed');
 expect(after.creation_settings.calendar_start).toMatchObject({mode:'custom',date:'2026-02-30',time:'18:30',profile:{month_lengths:[30,40]}});
 expect(after.creation_settings.communication).toMatchObject({preset:'custom',letter:true,courier:true,voice_call:true,presentation:'phone'});
 expect(after.creation_settings).toMatchObject({primary_genre:'custom',custom_genre:'Драма',cast_preset:'custom',core_npcs:4,secondary_npcs:7});
 await expect(page.getByRole('heading',{name:'Мир готов к редактированию'})).toBeVisible();await capture(page,info,'production-result');
 const counts=await(await request.post('/test/idea190/release')).json();expect(counts.world_calls).toBe(1);expect(counts.review_calls).toBe(2);
 await page.getByRole('button',{name:'Открыть в редакторе',exact:true}).click();await page.getByRole('button',{name:'Показать всё',exact:true}).click();
 await expect(page.locator('.ww-hero h1')).toBeVisible();
 // Edit through the existing author editor, preserving revision protection.
 if(info.project.name==='mobile'){await page.getByRole('button',{name:'Разделы мастерской',exact:true}).click();await page.getByRole('dialog').getByRole('button',{name:'Сцена и правила',exact:true}).click()}
 else await page.locator('.ww-sidebar').getByRole('button',{name:'Сцена и правила',exact:true}).click();
 await page.getByRole('button',{name:'Мир и повествование',exact:true}).click();await expect(page.getByRole('heading',{name:'Описание и правила мира',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Изменить Название',exact:true}).click();
 await page.getByRole('dialog').locator('input,textarea').first().fill('Отредактированный мир');
 await page.getByRole('dialog').getByRole('button',{name:'Сохранить поле',exact:true}).click();
 await expect.poll(async()=> (await(await request.get(url+'?author=true')).json()).state.campaign.title).toBe('Отредактированный мир');
 const edited=await(await request.get(url+'?author=true')).json();expect(edited.revision).toBeGreaterThan(after.revision);expect(edited.review.status).toBe('stale');
});


test('idea190: saved scenario, isolated drafts and reuse after a rejected launch',async({page,request})=>{
 const a=await(await request.post('/test/idea190',{data:{scenario:true,release:true}})).json();
 const b=await(await request.post('/api/workspaces',{data:{name:'Другой замысел'}})).json();
 await page.goto('/');const profile=await page.evaluate(()=>localStorage.getItem('profile'));
 await request.put(`/api/settings/${profile}`,{data:{...defaults,summary:{...defaults.summary,provider:'deepseek',model:'deepseek-flash',thinking:'off',context_length:131072,max_tokens:24000}}});
 await request.put('/api/credentials/deepseek',{data:{api_key:'offline-idea190'}});
 await page.evaluate(wid=>localStorage.setItem('draftWorkspace',wid),a.id);await page.reload();await nav(page,'Создать');
 await page.getByLabel('Взять за основу сценарий этого черновика').check();
 await group(page,'Мир и география');await page.getByLabel('География',{exact:true}).fill('Только мир А');await done(page);
 await draftsMenu(page);await page.locator(`[data-workspace-id="${b.id}"]`).getByRole('button',{name:'Другой замысел',exact:true}).click();
 await expect(page.getByLabel('Взять за основу сценарий этого черновика')).not.toBeChecked();
 await page.getByLabel('Описание мира или текст импорта').fill('Второй мир');
 await group(page,'Мир и география');await expect(page.getByLabel('География',{exact:true})).toHaveValue('');await page.getByLabel('География',{exact:true}).fill('Только мир Б');await done(page);
 await draftsMenu(page);await page.locator(`[data-workspace-id="${a.id}"]`).getByRole('button',{name:'Сценарий Валлора',exact:true}).click();
 await expect(page.getByLabel('Описание мира или текст импорта')).toHaveValue('');await expect(page.getByLabel('Взять за основу сценарий этого черновика')).toBeChecked();
 await group(page,'Мир и география');await expect(page.getByLabel('География',{exact:true})).toHaveValue('Только мир А');await done(page);
 await page.getByRole('button',{name:'Проверить замысел',exact:true}).click();await page.getByRole('button',{name:'Создать мир',exact:true}).click();
 await expect.poll(async()=> (await(await request.get(`/api/workspaces/${a.id}/draft`)).json()).job?.status).toBe('saved');
 // A new workspace must be adopted even when its first generation request fails.
 await draftsMenu(page);await page.getByRole('button',{name:'+ Новая история',exact:true}).click();
 await expect(page.getByLabel('Описание мира или текст импорта')).toHaveValue('');
 await page.getByLabel('Описание мира или текст импорта').fill('ATELIER190. Новая история после сбоя.');
 const before=(await(await request.get('/api/workspaces')).json()).length;
 let rejected=false;const used:string[]=[];
 await page.route('**/draft/generate',route=>{
  used.push(route.request().url());
  if(!rejected){rejected=true;return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Временный сбой запуска'})})}
  return route.continue();
 });
 await page.getByRole('button',{name:'Проверить замысел',exact:true}).click();await page.getByRole('button',{name:'Создать мир',exact:true}).click();
 await expect(page.getByRole('alert').first()).toContainText('Временный сбой запуска');
 const wid=await page.locator('.world-workshop').getAttribute('data-workspace-id');expect(wid).toBeTruthy();
 await page.getByRole('button',{name:'Проверить замысел',exact:true}).click();await page.getByRole('button',{name:'Создать мир',exact:true}).dblclick();
 await expect.poll(async()=> (await(await request.get(`/api/workspaces/${wid}/draft`)).json()).job?.status).toBe('saved');
 expect(used).toHaveLength(2);expect(used[0]).toBe(used[1]);expect((await(await request.get('/api/workspaces')).json()).length).toBe(before+1);
});

// Independent approved source, served exclusively by the test fixture server.
test('idea190: approved reference at the same viewports and interaction states',async({page},info)=>{
 test.setTimeout(120000);
 await page.setViewportSize(info.project.name==='mobile'?{width:390,height:844}:{width:1440,height:900});
 await page.goto('/test/idea190/reference/workspace.html');
 await capture(page,info,'reference-01-empty');
 await page.locator('#draft-name').fill('Последняя вышка Валлора');await page.locator('#idea').fill(idea);
 await page.locator('#era').selectOption('letters');await page.getByRole('checkbox',{name:'Мобильные звонки',exact:true}).check();
 await page.locator('.folio-scroll, #idea').evaluateAll(els=>els.forEach(el=>el.scrollTop=0));await capture(page,info,'reference-02-filled');
 for(const [key,title] of [['genre','Жанры истории'],['cast','Персонажи'],['world','Мир и география'],['calendar','Календарь и начало'],['narrative','Темп и последствия']]){
  await page.locator('.param').filter({hasText:title}).click();await capture(page,info,'reference-panel-'+key);await page.getByRole('button',{name:'Готово',exact:true}).click();
 }
 await page.getByRole('button',{name:'Примеры',exact:true}).click();await capture(page,info,'reference-examples');await page.getByRole('button',{name:'Закрыть окно',exact:true}).click();
 await page.getByRole('button',{name:'Развернуть редактор',exact:true}).click();await capture(page,info,'reference-expanded');await page.getByRole('button',{name:'К параметрам',exact:true}).click();
 await page.getByRole('button',{name:'Правила и особенности',exact:true}).click();await page.locator('.comm-extra').scrollIntoViewIfNeeded();await capture(page,info,'reference-communication');
 await page.getByRole('button',{name:'Правила и особенности',exact:true}).click();await page.getByRole('button',{name:'Проверить замысел',exact:true}).click();
 await capture(page,info,'reference-review');await page.locator('.fl-demo summary').click();await page.getByLabel('Исход запуска').selectOption('error');
 await page.getByRole('button',{name:'Запустить демогенерацию'}).click();
 await expect(page.locator('.fl-stages li.current strong')).toHaveText('Смысловая проверка');await capture(page,info,'reference-running');
 await expect(page.getByRole('heading',{name:'Проверка не получила ответ'})).toBeVisible();await capture(page,info,'reference-error');
 await page.getByRole('button',{name:'Повторить проверку',exact:true}).click();await page.getByRole('button',{name:'Подтвердить повтор',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Мир готов к редактированию'})).toBeVisible();await capture(page,info,'reference-result');
});
