import {test,expect} from '@playwright/test';
import {nav} from './navigation';

test('genealogy controls, relationship details, geometry and responsive skins',async({page,request},info)=>{
 test.setTimeout(120000);
 const s=await(await request.post('/test/ui-completion-seed?checkpoint=ui-family')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);
 const before=await(await request.get(`/api/saves/${s.save}`)).json();
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.emulateMedia({reducedMotion:'reduce'});
 for(const [width,skin] of (info.project.name==='mobile'?[[360,'graphite'],[393,'parchment']]:[[1440,'graphite'],[768,'parchment']]) as [number,string][]){
  await page.setViewportSize({width,height:1000});
  await request.put(`/api/worlds/${s.world}/presentation`,{data:{theme_id:skin}});
  await page.goto('/');await nav(page,'Родословная');
  const area=page.locator('.save-workspace');
  await area.getByLabel('Найти персонажа').fill('Тимур');
  await area.getByLabel('Семья персонажа').selectOption('qa_timur');
  await expect(area.locator('.family-node')).toHaveCount(5);
  await expect(area.locator('.family-generation').first()).toBeVisible();
  await area.getByLabel('Глубина родословной').fill('6');
  await expect(area.locator('.family-node')).toHaveCount(5);
  await area.getByLabel('Найти персонажа').fill('');
  const edge=area.locator('.react-flow__edge').first();await edge.focus();await edge.press('Enter');
  await expect(area.locator('.family-relationship-detail')).toBeVisible();
  await area.getByLabel('Закрыть сведения о связи').click();
  const boxes=await area.locator('.react-flow__node').evaluateAll(ns=>ns.map(n=>{const r=n.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}}));
  for(let i=0;i<boxes.length;i++)for(let j=i+1;j<boxes.length;j++){const a=boxes[i],b=boxes[j];expect(a.x+a.w<=b.x+1||b.x+b.w<=a.x+1||a.y+a.h<=b.y+1||b.y+b.h<=a.y+1).toBe(true)}
  await area.getByRole('button',{name:'Увеличить',exact:true}).click();
  const viewport=area.locator('.react-flow__viewport');
  const original=await viewport.getAttribute('style');
  await area.getByRole('button',{name:'Список',exact:true}).click();
  await area.getByRole('button',{name:'Дерево',exact:true}).click();
  await expect(viewport).toHaveAttribute('style',original!);
  await area.getByRole('button',{name:'Вся семья',exact:true}).click();
  await area.locator('.family-center').first().click();
  await expect(area.locator('.family-root')).toHaveCount(1);
  await area.getByRole('button',{name:'Сбросить',exact:true}).click();
  await expect(area.getByLabel('Глубина родословной')).toHaveValue('3');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  // 200% CSS zoom exercises the effective half-width responsive composition.
  await area.evaluate(el=>(el as HTMLElement).style.zoom='2');
  const overflow=await area.evaluate(el=>({width:el.clientWidth,scroll:el.scrollWidth,offenders:[...el.querySelectorAll('*')].filter(n=>n.getBoundingClientRect().right>el.getBoundingClientRect().right+1&&!n.closest('.react-flow')).map(n=>n.className).slice(0,12)}));
  expect(overflow.scroll,JSON.stringify(overflow)).toBeLessThanOrEqual(overflow.width+1);
  await area.evaluate(el=>(el as HTMLElement).style.zoom='1');
  if(process.env.GENEALOGY_QA==='1'&&[1440,393].includes(width)){await area.getByLabel('Семья персонажа').selectOption('qa_timur');await area.getByRole('button',{name:'Вся семья',exact:true}).click();await area.locator('.family-graph').scrollIntoViewIfNeeded();await page.screenshot({path:`/tmp/issue156-final-${width}.png`})}
 }
 const after=await(await request.get(`/api/saves/${s.save}`)).json();
 expect(after.revision).toBe(before.revision);expect(after.state).toEqual(before.state);expect(errors).toEqual([]);
});

test('six generations retain all supplied relations and fit with fixed portrait geometry',async({page,request})=>{
 const s=await(await request.post('/test/ui-completion-seed?checkpoint=ui-family-dense')).json();
 const original=await(await request.get(`/api/saves/${s.save}/genealogy?root_id=qa_timur&depth=6&limit=80`)).json();
 const nodes=original.nodes.slice(0,18).map((n:any,i:number)=>({...n,name:i===0?'Александра-Мария Константинопольская-Долгорукова':n.name,life_status:i===0?'dead':n.life_status}));
 const edges=nodes.slice(3).map((n:any,i:number)=>({id:`test-lineage-${i}`,source_id:nodes[i].id,target_id:n.id,kind:i===0?'adoptive_parent':i===1?'guardian':i===3?'foster_parent':i===4?'step_parent':'parent',certainty:i===2?'suspected':'known',status:'active',outcome:''}));
 for(let i=0;i<18;i+=3)edges.push({id:`test-partners-${i}`,source_id:nodes[i].id,target_id:nodes[i+1].id,kind:'spouse',certainty:'known',status:i===0?'closed':'active',outcome:i===0?'divorced':''});
 await page.route('**/genealogy?*',r=>r.fulfill({json:{nodes,edges,kinship:[],truncated:true}}));
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);await page.goto('/');await nav(page,'Родословная');
 const area=page.locator('.save-workspace');await expect(area.locator('.family-node')).toHaveCount(18);await expect(area.locator('.family-accessible-list>p')).toHaveCount(edges.length);
 await expect(area.locator('.family-generation')).toHaveCount(6);await expect(area).toContainText('Показана часть семьи');
 await area.getByRole('button',{name:'Вся семья',exact:true}).click();
 await expect.poll(()=>area.locator('.family-graph').evaluate(el=>{const a=el.getBoundingClientRect();return [...el.querySelectorAll('.react-flow__node')].every(n=>{const b=n.getBoundingClientRect();return b.left>=a.left&&b.right<=a.right&&b.top>=a.top&&b.bottom<=a.bottom})})).toBe(true);
 await area.getByRole('button',{name:'Список',exact:true}).click();await expect(area).toContainText('Александра-Мария Константинопольская-Долгорукова');await expect(area).toContainText('Усыновление');await expect(area).toContainText('Опека');await expect(area).toContainText('Развод');
 await page.reload();await nav(page,'Родословная');await expect(area.locator('.family-node')).toHaveCount(18);
});

test('newborn family opens the standalone tree without mutating the save',async({page,request})=>{
 const s=await(await request.post('/test/newborn-seed')).json();
 const before=await(await request.get(`/api/saves/${s.save}`)).json();
 const graph=await(await request.get(`/api/saves/${s.save}/genealogy?depth=6`)).json();
 const newborns=graph.nodes.filter((n:{id:string})=>n.id.startsWith('character_'));
 expect(newborns).toHaveLength(2);
 const writes:string[]=[];page.on('request',r=>{if(r.url().includes('/api/saves/')&&r.method()!=='GET')writes.push(r.url())});
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);await page.goto('/');await nav(page,'Родословная');
 const area=page.locator('.save-workspace');await area.getByLabel('Глубина родословной').fill('6');
 for(const n of newborns)await expect(area.locator(`.react-flow__node[data-id="${n.id}"]`)).toContainText('Без имени');
 await area.getByRole('button',{name:'Список',exact:true}).click();await expect(area.locator('.family-list-person')).toHaveCount(graph.nodes.length);
 await page.reload();await nav(page,'Родословная');await expect(area.locator('.family-node')).toHaveCount(graph.nodes.length);
 const after=await(await request.get(`/api/saves/${s.save}`)).json();expect(after.state).toEqual(before.state);expect(after.revision).toBe(before.revision);expect(writes).toEqual([]);
});

test('screenshot family reads without legend and restores the selected central person',async({page,request},info)=>{
 const {screenshotFamily}=await import('../tests/fixtures/genealogy');
 const s=await(await request.post('/test/ui-completion-seed?checkpoint=ui-family')).json();
 await request.put(`/api/worlds/${s.world}/presentation`,{data:{theme_id:info.project.name==='mobile'?'parchment':'graphite'}});
 await page.route('**/genealogy-roots',r=>r.fulfill({json:screenshotFamily.nodes.map(n=>({id:n.id,name:n.name}))}));
 await page.route('**/genealogy?*',r=>r.fulfill({json:screenshotFamily}));
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);
 await page.emulateMedia({reducedMotion:'reduce'});
 await page.setViewportSize({width:info.project.name==='mobile'?393:1440,height:1000});
 await page.goto('/');await nav(page,'Родословная');const area=page.locator('.save-workspace');
 await area.getByLabel('Семья персонажа').selectOption('marina');
 await expect(area.locator('.family-node')).toHaveCount(6);
 await expect(area.locator('.family-root')).toContainText('Марина Волкова');
 await expect(area.locator('.react-flow__edge')).toHaveCount(2);
 await expect(area.locator('.family-connection-label',{hasText:'Брак'})).toBeVisible();
 await expect(area.locator('.family-connection-label',{hasText:'Общие дети'})).toBeVisible();
 const care=area.locator('[data-relation-id="care"]');await expect(care).toContainText('Опека');await expect(care).toContainText('Опекун');await expect(care).toContainText('Подопечный');await expect(care).toContainText('Марина Волкова');await expect(care).toContainText('Илья Александров');
 await expect(area.locator('.family-legend')).toHaveCount(0);
 await expect(area.locator('.family-accessible-list>p')).toHaveCount(screenshotFamily.edges.length);
 if(process.env.GENEALOGY_QA==='1'){await area.locator('.family-tree-layout').scrollIntoViewIfNeeded();await page.screenshot({path:`/tmp/161-family-${info.project.name}.png`})}
 await area.getByRole('button',{name:'В центре родословной: Катя Волкова',exact:true}).click();
 await expect(area.locator('.family-root')).toContainText('Катя Волкова');await expect(area.locator('.family-root')).toBeInViewport();
 await area.getByRole('button',{name:'Вернуться в историю',exact:true}).click();await nav(page,'Родословная');
 await expect(area.getByLabel('Семья персонажа')).toHaveValue('katya');await expect(area.locator('.family-root')).toContainText('Катя Волкова');
 await area.locator('.family-sibling-summary summary').click();await expect(area.locator('.family-sibling-summary')).toContainText('Соня Величкина');await expect(area.locator('.family-sibling-summary')).toContainText('Тимур Волков');
});
