import {test,expect,type Page} from '@playwright/test';
import {nav,pickCharacter,searchCharacter} from './navigation';
import {writeFile} from 'node:fs/promises';
const capture=process.env.UI_EVIDENCE==='1';
test.use({video:capture?'on':'off'});
const evidence=process.env.DOSSIER_EVIDENCE||'../docs/manual_qa/narrative_v4/issue83-evidence';
const tabs=['Обзор','Личность','Отношения','Семья','История'];
async function expectFitted(page:Page){
 await expect.poll(async()=>page.locator('.family-graph').evaluate(el=>{
  const area=el.getBoundingClientRect();
  return [...el.querySelectorAll('.react-flow__node,.family-edge-label')].every(n=>{const r=n.getBoundingClientRect();return r.left>=area.left&&r.right<=area.right&&r.top>=area.top&&r.bottom<=area.bottom});
 })).toBe(true);
 await page.locator('.save-workspace').evaluate(el=>el.scrollTop=0);
}
async function open(page:Page){await nav(page,'Мир');await nav(page,'Персонажи')}
for(const width of [360,393,768,1440])test(`five tabs, widths, two skins and preservation ${width}`,async({page,request},info)=>{
 test.skip(info.project.name!=='desktop');test.setTimeout(120000);
 await page.setViewportSize({width,height:900});
 const s=await(await request.post('/test/ui-completion-seed?checkpoint=ui-dossier')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 for(const skin of ['graphite','parchment']){
 await request.put(`/api/worlds/${s.world}/presentation`,{data:{theme_id:skin}});await page.goto('/');await open(page);
 const d=page.locator('.inspector-workspace');
 await expect(d.getByRole('tab')).toHaveCount(5);
 await expect(d.getByRole('img',{name:'Мужской пол',exact:true})).toBeVisible();
 await expect(d.locator('.character-header')).toContainText('Кирилл Ларин');
 const header=await d.locator('.dossier-header').boundingBox();expect(header!.y+header!.height).toBeLessThan(900);
 await expect(d).toContainText('Повреждение ноги');await expect(d).toContainText('Устал после дороги');
 if(width>=768){if(await d.getByRole('button',{name:'Расширить панель',exact:true}).isVisible())await d.getByRole('button',{name:'Расширить панель',exact:true}).click();await expect(d.locator('.inspector-scroll')).toHaveClass(/dossier-expanded/)}
 for(let i=0;i<tabs.length;i++){
 await d.getByRole('tab',{name:tabs[i],exact:true}).click();await expect(d.getByRole('tab',{name:tabs[i],exact:true})).toHaveAttribute('aria-selected','true');
 await expect(d.getByRole('tabpanel')).toBeVisible();
 expect(await d.evaluate(e=>e.scrollWidth<=e.clientWidth+1)).toBe(true);
 if(i===1)await expect(d.locator('.motivation-editor')).toBeVisible();
 if(i===2)await expect(d.getByRole('button',{name:'+ Добавить отношение',exact:true})).toBeVisible();
 if(i===3)await expect(d.getByRole('button',{name:'Открыть родословную',exact:true})).toBeVisible();
 await d.locator('.inspector-scroll').evaluate(el=>el.scrollTop=0);
 if(capture)await page.screenshot({path:`${evidence}/after-${width}-${skin}-${i}.png`,animations:'disabled'});
 }
 // Arrow keys and restoration after close/reopen; width changes do not remount editors.
 await d.getByRole('tab',{name:'История',exact:true}).press('Home');await expect(d.getByRole('tab',{name:'Обзор',exact:true})).toBeFocused();
 await d.getByRole('tab',{name:'Обзор',exact:true}).press('ArrowRight');
 await d.getByRole('button',{name:'Закрыть',exact:true}).click();await open(page);await expect(d.getByRole('tab',{name:'Личность',exact:true})).toHaveAttribute('aria-selected','true');
 await pickCharacter(page,'qa_vera');await d.getByRole('tab',{name:'Обзор',exact:true}).click();
 await expect(d.getByRole('img',{name:'Женский пол',exact:true})).toBeVisible();await expect(d).not.toContainText('PRIVATE');await expect(d).toContainText('Нет данных');
 if(width>=768){await d.getByRole('button',{name:'Компактная панель'}).click();await expect(d.locator('.inspector-scroll')).toHaveClass(/inspector-compact/);expect((await d.locator('.inspector-page').boundingBox())!.width).toBeLessThanOrEqual(680);if(capture)await page.screenshot({path:`${evidence}/after-${width}-${skin}-compact.png`,animations:'disabled'})}
 }
 expect(errors).toEqual([]);
});

test('public family opens dossier and returns to graph, no speculative nodes, bounded dense layout',async({page,request},info)=>{
 const s=await(await request.post('/test/ui-completion-seed?checkpoint=ui-family-dense')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);
 if(info.project.name==='mobile')await page.setViewportSize({width:360,height:800});
 await page.goto('/');await page.getByLabel('Своё действие или реплика').fill('Сохранить мой черновик');await nav(page,'Родословная');
 const area=page.locator('.save-workspace');const start=Date.now();await area.getByLabel('Семья персонажа').selectOption('qa_timur');await expect(area.locator('.react-flow__node')).toHaveCount(80);
 const metrics=await page.evaluate(()=>({nodes:document.querySelectorAll('.react-flow__node').length,heap:(performance as any).memory?.usedJSHeapSize||null}));
 if(capture)await writeFile(`${evidence}/performance-${info.project.name}.json`,JSON.stringify({...metrics,render_ms:Date.now()-start,viewport:page.viewportSize()},null,2));
 // Node rectangles have fixed geometry and cannot overlap, even with long names.
 const boxes=await area.locator('.react-flow__node').evaluateAll(nodes=>nodes.map(n=>{const r=n.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}}));
 for(let i=0;i<boxes.length;i++)for(let j=i+1;j<boxes.length;j++){const a=boxes[i],b=boxes[j];expect(a.x+a.w<=b.x+1||b.x+b.w<=a.x+1||a.y+a.h<=b.y+1||b.y+b.h<=a.y+1).toBe(true)}
 await area.getByRole('button',{name:'Увеличить',exact:true}).click();await area.getByRole('button',{name:'Вся семья',exact:true}).click();
 await expectFitted(page);if(capture)await page.screenshot({path:`${evidence}/after-family-dense-${info.project.name}.png`,animations:'disabled'});
 await area.getByRole('button',{name:'Список',exact:true}).click();await area.getByRole('button',{name:'Открыть досье: Тимур Серов',exact:true}).click();
 await expect(page.locator('.character-header')).toContainText('Тимур Серов');await page.keyboard.press('Escape');await expect(area).toBeVisible();
 await area.getByLabel('Семья персонажа').selectOption('qa_oleg');await area.getByRole('button',{name:'Дерево',exact:true}).click();await expect(area.locator('.react-flow__node')).toHaveCount(1);await expect(area.locator('.react-flow__edge')).toHaveCount(0);
 await area.locator('.react-flow__node').press('Enter');await expect(page.locator('.character-header')).toContainText('Олег');await page.keyboard.press('Escape');await page.keyboard.press('Escape');await expect(page.getByLabel('Своё действие или реплика')).toHaveValue('Сохранить мой черновик');
});

test('start, ordinary turn, dossier name link, persistent reload, next turn',async({page,request},info)=>{
 const s=await(await request.post('/test/seed')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);await page.goto('/');
 await page.getByRole('button',{name:'Начать игру',exact:true}).click();await expect(page.locator('.turn')).toHaveCount(1);
 await page.locator('.choices button').first().click();await expect(page.locator('.turn')).toHaveCount(2);
 const composer=page.getByLabel('Своё действие или реплика');await composer.fill('Несохранённый черновик');
 const link=page.locator('.turn [data-character-id]').first();await expect(link).toBeVisible();
 await link.scrollIntoViewIfNeeded();const before=await link.boundingBox();await link.click();await expect(page.locator('.character-profile')).toBeVisible();
 await page.getByRole('tab',{name:'История',exact:true}).click();await page.keyboard.press('Escape');
 await expect(composer).toHaveValue('Несохранённый черновик');const after=await link.boundingBox();expect(Math.abs(before!.y-after!.y)).toBeLessThan(2);
 const stored=await(await request.get(`/api/saves/${s.save}`)).json();expect(stored.turns).toHaveLength(2);
 await page.reload();await expect(page.locator('.turn')).toHaveCount(2);await page.locator('.choices button').first().click();await expect(page.locator('.turn')).toHaveCount(3);
 const last=await(await request.get(`/api/saves/${s.save}`)).json();expect(last.turns).toHaveLength(3);expect(last.revision).toBeGreaterThan(stored.revision);
 if(capture)await page.screenshot({path:`${evidence}/smoke-${info.project.name}.png`,animations:'disabled'});
});

test('family gestures, two skins, reduced motion and unchanged game state',async({page,request},info)=>{
 const s=await(await request.post('/test/ui-completion-seed?checkpoint=ui-family')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);
 if(info.project.name==='mobile')await page.setViewportSize({width:393,height:852});
 const saved=await(await request.get(`/api/saves/${s.save}`)).json();
 const touchSession=info.project.name==='mobile'?await page.context().newCDPSession(page):null;
 for(const skin of ['graphite','parchment']){
 await request.put(`/api/worlds/${s.world}/presentation`,{data:{theme_id:skin}});await page.goto('/');await nav(page,'Родословная');
 const area=page.locator('.save-workspace');await area.getByLabel('Семья персонажа').selectOption('qa_timur');await expect(area.locator('.react-flow__node')).toHaveCount(5);
 await expect(area).toContainText('Зоя');
 const pane=area.locator('.react-flow__pane');const viewport=area.locator('.react-flow__viewport');
 // Wait for the intentional fit transition to settle before measuring gestures.
 await page.emulateMedia({reducedMotion:'reduce'});await area.getByRole('button',{name:'Вся семья',exact:true}).click();
 await expectFitted(page);const box=(await pane.boundingBox())!;
 const before=await viewport.getAttribute('style');
 if(info.project.name==='mobile'){
 const cdp=touchSession!;
 const x=box.x+box.width/2,y=box.y+40;
 await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:x-35,y,id:1},{x:x+35,y,id:2}]});
 for(let i=1;i<=5;i++)await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:x-35-i*9,y,id:1},{x:x+35+i*9,y,id:2}]});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
 }else{
 await page.mouse.move(box.x+20,box.y+20);await page.mouse.down();await page.mouse.move(box.x+85,box.y+65,{steps:6});await page.mouse.up();
 }
 await expect.poll(()=>viewport.getAttribute('style')).not.toBe(before);
 await area.getByRole('button',{name:'Вся семья',exact:true}).click();
 await expectFitted(page);if(capture)await page.screenshot({path:`${evidence}/after-family-${info.project.name}-${skin}.png`,animations:'disabled'});
 await area.getByRole('button',{name:'Список',exact:true}).click();await expect(area).toContainText('Усыновление');await expect(area).toContainText('Развод');
 if(capture)await page.screenshot({path:`${evidence}/after-family-list-${info.project.name}-${skin}.png`,animations:'disabled'});
 }
 await touchSession?.detach();
 const last=await(await request.get(`/api/saves/${s.save}`)).json();expect(last.revision).toBe(saved.revision);expect(last.state.world_clock).toEqual(saved.state.world_clock);
});

test('search selection and local dossier scroll survive close, resize and reopen',async({page,request},info)=>{
 const s=await(await request.post('/test/ui-completion-seed?checkpoint=ui-dossier')).json();await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);
 await page.goto('/');await open(page);const d=page.locator('.inspector-workspace');
 await searchCharacter(page,'Вера');await expect(d.getByRole('heading',{name:'Вера Ларина',exact:true})).toBeVisible();
 await page.keyboard.press('Escape');await open(page);await expect(d.getByLabel('Персонаж',{exact:true})).toHaveAttribute('data-value','qa_vera');
 await pickCharacter(page,'qa_kirill');await d.getByRole('tab',{name:'Обзор',exact:true}).click();
 await page.setViewportSize({width:info.project.name==='mobile'?360:1000,height:600});
 const scroll=d.locator('.inspector-scroll');
 // Close in the same frame: the browser's queued scroll event must not be the
 // only way to remember the position before the surface becomes hidden.
 const position=await scroll.evaluate(el=>{el.scrollTop=250;const position=el.scrollTop;window.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));return position});
 expect(position).toBeGreaterThan(0);await expect(d).toBeHidden();await open(page);await expect.poll(()=>scroll.evaluate(el=>el.scrollTop)).toBe(position);
 await page.setViewportSize({width:info.project.name==='mobile'?393:1000,height:850});await expect(d.getByLabel('Персонаж',{exact:true})).toHaveAttribute('data-value','qa_kirill');
 await page.keyboard.press('Escape');
 let failed=false;await page.route('**/genealogy?*',async route=>{if(!failed&&route.request().url().includes('root_id=qa_timur')){failed=true;await route.fulfill({status:503,json:{detail:'QA temporary failure'}})}else await route.continue()});
 await nav(page,'Родословная');await page.locator('.save-workspace').getByLabel('Семья персонажа').selectOption('qa_timur');await page.getByRole('button',{name:'Повторить загрузку',exact:true}).click();await expect(page.locator('.react-flow__node')).toHaveCount(5);
});
