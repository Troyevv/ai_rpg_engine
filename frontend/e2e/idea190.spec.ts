import {draftsMenu} from './workshop-navigation';
import {test,expect,type Page} from '@playwright/test';
import {nav} from './navigation';
import {defaults} from '../src/types';
const idea='В княжестве Валлор письма носят гонцы, но у каждой гильдии есть мобильный телефон. Башни связи принадлежат короне. Я играю за ученицу картографа. Накануне ярмарки на телефон мастера приходит звонок с башни, сгоревшей десять лет назад.';
async function group(page:Page,name:string){await page.locator('.atelier-param').filter({hasText:name}).click()}
async function done(page:Page){await page.getByRole('dialog').getByRole('button',{name:'Готово',exact:true}).click();await expect(page.locator('.atelier-dialog')).toHaveCount(0)}
for(const skin of ['graphite','parchment'])test(`idea190: visual, panels, validation, persistence · ${skin}`,async({page,request},info)=>{
 await page.setViewportSize(info.project.name==='mobile'?{width:390,height:844}:{width:1363,height:936});
 await page.addInitScript(skin=>{localStorage.setItem('workshop-theme',JSON.stringify({theme_id:skin,mode:'manual'}))},skin);
 await page.goto('/');await nav(page,'Создать');
 await page.evaluate(skin=>document.documentElement.dataset.theme=skin,skin);
 await page.getByLabel('Название черновика').fill('Последняя вышка Валлора');
 await page.getByLabel('Описание мира или текст импорта').fill(idea);
 await page.getByLabel('Набор технологий связи',{exact:true}).selectOption('letters');
 await page.getByRole('checkbox',{name:'Мобильные звонки',exact:true}).check();
 await expect(page.getByRole('checkbox',{name:'Письма',exact:true})).toBeChecked();
 await expect(page.getByRole('checkbox',{name:'Гонцы',exact:true})).toBeChecked();
 await expect(page.getByLabel('Набор технологий связи',{exact:true})).toHaveValue('custom');
 await page.evaluate(()=>document.fonts.ready);
 await expect.poll(()=>page.locator('.atelier-hero img').evaluate(el=>(el as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
 await page.locator('.ww-scroll, .atelier-editor textarea').evaluateAll(elements=>elements.forEach(el=>{el.scrollTop=0}));
 const shot=info.outputPath(`idea190-${skin}-${info.project.name}.png`);await page.screenshot({path:shot});await info.attach('Эталонный экран '+skin,{path:shot,contentType:'image/png'});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
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
 await request.post('/test/idea190',{data:{fail_review:true,custom_calendar:true}});
 await page.goto('/');
 const profile=await page.evaluate(()=>localStorage.getItem('profile'));
 expect((await request.put(`/api/settings/${profile}`,{data:{...defaults,summary:{...defaults.summary,provider:'deepseek',model:'deepseek-flash',thinking:'off',context_length:131072,max_tokens:24000}}})).ok()).toBeTruthy();
 await request.put('/api/credentials/deepseek',{data:{api_key:'offline-idea190'}});
 await page.reload();await nav(page,'Создать');
 await page.getByLabel('Описание мира или текст импорта').fill('ATELIER190. Компания друзей у моря.');
 await page.getByLabel('Набор технологий связи',{exact:true}).selectOption('letters');await page.getByRole('checkbox',{name:'Мобильные звонки',exact:true}).check();
 await group(page,'Персонажи');await page.getByLabel('Масштаб состава').selectOption('custom');await page.getByLabel('Важные NPC',{exact:true}).fill('4');await page.getByLabel('Второстепенные NPC',{exact:true}).fill('7');await done(page);
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
 await page.reload();await nav(page,'Создать');await expect(page.getByRole('region',{name:'Этапы создания мира'})).toBeVisible();
 await request.post('/test/idea190/release');await expect(page.getByRole('alert')).toContainText('HTTP 502');
 await expect(page.getByText(/известной причиной HTTP 400/)).toHaveCount(0);
 await page.reload();await nav(page,'Создать');
 await page.getByRole('button',{name:'Повторить проверку',exact:true}).click();
 await expect.poll(async()=> (await(await request.get(url)).json()).job.status).toBe('saved');
 const after=await(await request.get(url+'?author=true')).json();expect(after.job.id).toBe(job.id);expect(after.review.status).toBe('completed');
 expect(after.creation_settings.calendar_start).toMatchObject({mode:'custom',date:'2026-02-30',time:'18:30',profile:{month_lengths:[30,40]}});
 expect(after.creation_settings.communication).toMatchObject({preset:'custom',letter:true,courier:true,voice_call:true,presentation:'phone'});
 expect(after.creation_settings).toMatchObject({primary_genre:'custom',custom_genre:'Драма',cast_preset:'custom',core_npcs:4,secondary_npcs:7});
 const counts=await(await request.post('/test/idea190/release')).json();expect(counts.world_calls).toBe(1);expect(counts.review_calls).toBe(2);
 await page.getByRole('button',{name:'Открыть в редакторе',exact:true}).click();await page.getByRole('button',{name:'Показать всё',exact:true}).click();
 await expect(page.locator('.ww-hero h1')).toBeVisible();
 // Edit through the existing author editor, preserving revision protection.
 if(info.project.name==='mobile'){await page.getByRole('button',{name:'Разделы мастерской',exact:true}).click();await page.getByRole('dialog').getByRole('button',{name:'Сцена и правила',exact:true}).click()}
 else await page.locator('.ww-sidebar').getByRole('button',{name:'Сцена и правила',exact:true}).click();
 await page.locator('summary').filter({hasText:'Описание и правила мира'}).click();
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
