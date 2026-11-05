import {test,expect,type Page,type TestInfo} from '@playwright/test';
import {nav,gameAction} from './navigation';
import {chooseGenre} from './genre-navigation';
import {defaults} from '../src/types';
// Issue #193 requires reviewable recordings of successful transitions, not videos.
test.use({trace:'on'});
async function capture(page:Page,info:TestInfo,name:string){
 await page.evaluate(()=>document.fonts.ready);
 await expect(page.locator('.genre-results')).toHaveCSS('opacity','1');
 const path=info.outputPath(`${name}-${info.project.name}.png`);
 await page.screenshot({path,animations:'disabled'});await info.attach(name,{path,contentType:'image/png'});
}
async function top(page:Page){await page.getByTestId('primary-genre').scrollIntoViewIfNeeded()}
async function open(page:Page){await page.goto('/');await nav(page,'Создать');await page.locator('.atelier-param').filter({hasText:'Жанры истории'}).click()}
async function done(page:Page){await page.getByRole('dialog').getByRole('button',{name:/^(Готово|К параметрам)$/}).click();await expect(page.locator('.atelier-dialog')).toHaveCount(0)}
async function noOverflow(page:Page){
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
 const overflow=await page.locator('.genre-settings, .atelier-dialog').evaluateAll(els=>els.filter(el=>el.scrollWidth>el.clientWidth+1).map(el=>el.className));
 expect(overflow).toEqual([]);
}
for(const skin of ['graphite','parchment','cyberpunk'])test(`genre catalog visual states · ${skin}`,async({page},info)=>{
 await page.setViewportSize({width:info.project.name==='mobile'?390:1440,height:900});
 await page.addInitScript(s=>localStorage.setItem('workshop-theme',JSON.stringify({theme_id:s,mode:'manual'})),skin);
 await open(page);await capture(page,info,`default-${skin}`);
 if(info.project.name==='mobile'){const card=await page.locator('.genre-card').first().boundingBox();expect(card!.y+card!.height).toBeLessThan(820)}
 await page.locator('.genre-group-picker .atelier-disclosure-trigger').click();await capture(page,info,`groups-${skin}`);
 await page.locator('.genre-group-picker .atelier-disclosure-trigger').click();
 await page.locator('.genre-card').first().evaluate(el=>el.scrollIntoView({block:'center'}));await capture(page,info,`cards-${skin}`);
 // Same policy as the pre-change screenshots, in all three skins.
 await chooseGenre(page,'Романтика');await chooseGenre(page,'Драма','secondary');await top(page);await capture(page,info,`after-baseline-${skin}`);
 await page.getByLabel('Найти жанр').fill('темное фентези');
 await expect(page.locator('.genre-card')).toHaveCount(1);await expect(page.locator('.genre-card')).toContainText('Тёмное фэнтези');
 await page.getByLabel('Найти жанр').scrollIntoViewIfNeeded();await capture(page,info,`search-${skin}`);
 await page.getByLabel('Найти жанр').fill('жанр которого не существует');await expect(page.getByText('Жанры не найдены',{exact:true})).toBeVisible();await page.locator('.genre-no-results').evaluate(el=>el.scrollIntoView({block:'center'}));await capture(page,info,`empty-${skin}`);
 await page.getByRole('button',{name:'Сбросить поиск и группы',exact:true}).click();await expect(page.getByLabel('Найти жанр')).toBeFocused();
 await chooseGenre(page,'Сверхъестественный триллер');await chooseGenre(page,'Династическая сага','secondary');await chooseGenre(page,'Музыкальная драма','secondary');
 await top(page);await capture(page,info,`selected-${skin}`);
 await page.getByLabel('Найти жанр').fill('морские');
 const capped=page.getByRole('button',{name:'Дополнительный жанр: Морские приключения',exact:true});await expect(capped).toHaveAttribute('aria-disabled','true');
 await capped.focus();await capped.press('Enter');await expect(page.locator('.genre-count')).toHaveText('3 из 3');
 await capped.scrollIntoViewIfNeeded();await capture(page,info,`limit-${skin}`);
 await page.getByRole('button',{name:'Убрать Драма',exact:true}).click();await expect(page.getByRole('button',{name:'Убрать Династическая сага',exact:true})).toBeFocused();
 await chooseGenre(page,'Морские приключения','secondary');
 // Promote an accent without duplicates; no mandatory secondary replacement.
 await chooseGenre(page,'Морские приключения');await expect(page.locator('.genre-count')).toHaveText('2 из 3');
 await chooseGenre(page,'Свой жанр');await top(page);await capture(page,info,`invalid-custom-${skin}`);
 await expect(page.getByLabel('Описание своего жанра')).toHaveAttribute('aria-invalid','true');
 await page.getByLabel('Описание своего жанра').fill('Медленная история о музыке, дружбе и необычных совпадениях. '.repeat(25));
 await page.getByLabel('Описание своего жанра').scrollIntoViewIfNeeded();await capture(page,info,`custom-long-${skin}`);
 await done(page);await page.reload();await nav(page,'Создать');await page.locator('.atelier-param').filter({hasText:'Жанры истории'}).click();
 await expect(page.getByLabel('Описание своего жанра')).toHaveValue('Медленная история о музыке, дружбе и необычных совпадениях. '.repeat(25));
 await expect(page.locator('.genre-count')).toHaveText('2 из 3');
 await page.getByRole('button',{name:'Сбросить выбор',exact:true}).click();await expect(page.getByTestId('primary-genre')).toHaveText('Из описания мира');
 await page.getByRole('button',{name:'Восстановить выбор',exact:true}).click();await expect(page.getByTestId('primary-genre')).toHaveText('Свой жанр');
 await noOverflow(page);
});

test('genre catalog responsive, keyboard, English and motion',async({page},info)=>{
 await open(page);
 await page.locator('.genre-group-picker .atelier-disclosure-trigger').click();
 await page.getByRole('group',{name:'Группы жанров'}).getByRole('button',{name:'Фэнтези',exact:true}).click();
 await expect(page.locator('.genre-card')).toHaveCount(4);
 await page.locator('.genre-group-picker .atelier-disclosure-trigger').click();
 for(const width of info.project.name==='mobile'?[360,390,430,768]:[1280,1440,1920]){
  await page.setViewportSize({width,height:900});await chooseGenre(page,'Сверхъестественный триллер');await noOverflow(page);
  await page.getByLabel('Найти жанр').focus();await page.keyboard.type('cyberpunk');
  await expect(page.locator('.genre-card')).toHaveCount(1);
  await page.getByRole('button',{name:'Основной жанр: Киберпанк',exact:true}).focus();await page.keyboard.press('Space');
  await expect(page.getByTestId('primary-genre')).toHaveText('Киберпанк');
  await page.getByRole('button',{name:'Очистить поиск',exact:true}).click();await expect(page.getByLabel('Найти жанр')).toBeFocused();
 }
 if(info.project.name==='mobile'){
  await page.setViewportSize({width:360,height:480});await page.getByLabel('Найти жанр').fill('комедия');await page.getByLabel('Найти жанр').focus();
  await noOverflow(page);await capture(page,info,'compact-input-viewport');await page.setViewportSize({width:390,height:900});
 }
 // Real frame samples prove the entry transition moves through intermediate states.
 await page.getByLabel('Найти жанр').scrollIntoViewIfNeeded();
 await page.evaluate(()=>{
  const samples:{opacity:number;transform:string}[]=[];(window as any).genreMotion=samples;
  const observer=new MutationObserver(()=>{
   const node=document.querySelector('.genre-results');if(!node)return;observer.disconnect();
   const start=performance.now();const frame=()=>{const css=getComputedStyle(node);samples.push({opacity:Number(css.opacity),transform:css.transform});if(performance.now()-start<350)requestAnimationFrame(frame)};requestAnimationFrame(frame);
  });observer.observe(document.querySelector('.genre-settings')!,{childList:true});
 });
 await page.getByLabel('Найти жанр').fill('сатир');await expect(page.locator('.genre-results')).toHaveCSS('opacity','1');
 await expect.poll(()=>page.evaluate(()=>(window as any).genreMotion.length)).toBeGreaterThan(4);
 const samples=await page.evaluate(()=>(window as any).genreMotion as {opacity:number;transform:string}[]);
 expect(samples.some(s=>s.opacity>0&&s.opacity<.99)).toBe(true);expect(samples.some(s=>s.transform!=='none')).toBe(true);
 await info.attach('motion-frame-samples',{body:JSON.stringify(samples),contentType:'application/json'});
 await page.emulateMedia({reducedMotion:'reduce'});await page.getByLabel('Найти жанр').fill('gothic');
 await expect(page.locator('.genre-results')).toHaveCSS('opacity','1');await expect(page.locator('.genre-results')).toHaveCSS('transform','none');
 await expect(page.locator('.genre-card')).toHaveCSS('transition-duration','0s');
 await done(page);await page.evaluate(()=>document.documentElement.lang='en');await page.locator('.atelier-param').filter({hasText:'Жанры истории'}).click();
 await page.getByLabel('Find a genre').fill('supernatural');await page.getByRole('button',{name:'Primary genre: Supernatural thriller',exact:true}).click();
 await expect(page.getByTestId('primary-genre')).toHaveText('Supernatural thriller');
 await page.setViewportSize({width:info.project.name==='mobile'?360:1440,height:900});
 // Text zoom, not a screenshot scale: all catalog text doubles and must reflow.
 await page.locator('.genre-settings').evaluate(el=>{
  const sizes=Array.from(el.querySelectorAll('*')).map(node=>[node,getComputedStyle(node).fontSize] as const);
  for(const [node,size] of sizes)(node as HTMLElement).style.fontSize=`${parseFloat(size)*2}px`;
 });
 await noOverflow(page);await top(page);await capture(page,info,'english-text-zoom');
 await page.keyboard.press('Escape');await expect(page.locator('.atelier-param').filter({hasText:'Жанры истории'})).toBeFocused();
});

test('new genres generate, hand off, edit and reload with a controlled provider',async({page,request})=>{
 await request.post('/test/idea190',{data:{release:true}});await page.goto('/');
 const profile=await page.evaluate(()=>localStorage.getItem('profile'));
 await request.put(`/api/settings/${profile}`,{data:{...defaults,summary:{...defaults.summary,provider:'deepseek',model:'deepseek-flash',thinking:'off',context_length:131072,max_tokens:24000}}});
 await request.put('/api/credentials/deepseek',{data:{api_key:'offline-genre193'}});
 await page.reload();await nav(page,'Создать');await page.getByLabel('Описание мира или текст импорта').fill('ATELIER190. Друзья создают музыкальную группу.');
 await page.locator('.atelier-param').filter({hasText:'Жанры истории'}).click();
 await chooseGenre(page,'Музыкальная драма');
 for(const name of ['Киберпанк','Придворные интриги','Чёрная комедия'])await chooseGenre(page,name,'secondary');
 await done(page);await page.getByRole('button',{name:'Проверить замысел',exact:true}).click();await page.getByRole('button',{name:'Создать мир',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Мир готов к редактированию'})).toBeVisible();
 const wid=await page.locator('.world-workshop').getAttribute('data-workspace-id');
 const draft=await(await request.get(`/api/workspaces/${wid}/draft?author=true`)).json();
 const expected={primary_genre:'music_drama',secondary_genres:['cyberpunk','court_intrigue','black_comedy'],custom_genre:''};
 expect(draft.creation_settings).toMatchObject(expected);
 // Existing confirm API performs the real atomic Narrative handoff.
 const confirmed=await request.post(`/api/workspaces/${wid}/draft/confirm`,{data:{revision:draft.revision,version_id:draft.version_id,accept_warnings:true}});
 expect(confirmed.ok(),await confirmed.text()).toBe(true);const selected=await confirmed.json();
 await page.evaluate(s=>{localStorage.setItem('selection',JSON.stringify({world:s.world,save:s.save}));localStorage.removeItem('draftWorkspace')},selected);
 await page.reload();await nav(page,'Игра');await gameAction(page,'Политика истории');
 const dialog=page.getByRole('dialog').last();await expect(dialog.getByTestId('primary-genre')).toHaveText('Музыкальная драма');
 await chooseGenre(dialog,'Киберпанк');await expect(dialog.locator('.genre-count')).toHaveText('2 из 3');
 await dialog.getByRole('button',{name:'Сохранить настройки истории',exact:true}).click();await page.reload();
 const state=await(await request.get(`/api/saves/${selected.save}`)).json();
 expect(state.state.narrative_policy.genre).toEqual({...expected,primary_genre:'cyberpunk',secondary_genres:['court_intrigue','black_comedy']});
});
