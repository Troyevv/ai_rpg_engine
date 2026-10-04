import {test,expect} from '@playwright/test';
import {themes} from '../src/lib/skins';
test('all skins, four mobile widths, time skip and rollback',async({page,request},info)=>{
 test.setTimeout(180000);
 const selection=await(await request.post('/test/seed')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selection);
 await page.goto('/');
 await page.getByRole('button',{name:'Начать игру',exact:true}).click();
 await expect(page.locator('.choices button')).toHaveCount(6);
 const baseline=await(await request.get(`/api/saves/${selection.save}`)).json();
 const fingerprints=new Set<string>();
 for(const theme of themes){
  expect((await request.put(`/api/worlds/${selection.world}/presentation`,{data:{theme_id:theme.id}})).ok()).toBe(true);
  await page.reload();await expect(page.locator('html')).toHaveAttribute('data-theme',theme.id);
  if(theme.decoration!=='none')await expect(page.locator('.theme-decoration')).toHaveCSS('pointer-events','none');
  for(const width of info.project.name==='mobile'?[360,390,412,430]:[1440]){
   await page.setViewportSize({width,height:900});
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
   await page.getByRole('button',{name:'Пропустить время',exact:true}).click();
   await expect(page.getByRole('dialog')).toBeVisible();
   expect(await page.getByRole('dialog').evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
   if(width===390||width===1440){
    fingerprints.add(await page.getByRole('dialog').evaluate(el=>{const c=getComputedStyle(el);return [c.borderRadius,c.borderWidth,c.borderStyle,c.backgroundImage,getComputedStyle(document.querySelector('h1')!).fontFamily].join('|')}));
    if(['industrial','parchment','cyberpunk','biotech'].includes(theme.id))await page.screenshot({path:info.outputPath(`${theme.id}-${width}.png`),animations:'disabled'});
   }
   await page.getByRole('button',{name:'Закрыть',exact:true}).click();
  }
 }
 expect(fingerprints.size).toBeGreaterThanOrEqual(9);
 await page.getByRole('button',{name:'Пропустить время',exact:true}).click();
 await page.getByRole('button',{name:'+10 мин',exact:true}).click();
 await page.getByRole('button',{name:'Пропустить 0 ч 10 мин',exact:true}).click();
 await expect(page.locator('.turn')).toHaveCount(2);await expect(page.locator('.choices button')).toHaveCount(6);
 const after=await(await request.get(`/api/saves/${selection.save}`)).json();
 expect(after.state.world_clock.minute-baseline.state.world_clock.minute).toBe(10);
 expect(after.state.last_time_skip.living_world_llm_calls).toBe(0);
 await expect(page.locator('.skip-diagnostics')).toContainText('10 мин');
 page.once('dialog',dialog=>dialog.accept());await page.getByRole('button',{name:'Откатить',exact:true}).click();
 await expect(page.locator('.turn')).toHaveCount(1);
 expect((await(await request.get(`/api/saves/${selection.save}`)).json()).state.world_clock.minute).toBe(baseline.state.world_clock.minute);
});

// Screenshots are CI artifacts; assertions catch missing/intrusive art as well as borders.
test('skin artwork is visible, distinct and outside the reading surface',async({page,request},info)=>{
 const selection=await(await request.post('/test/seed')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selection);
 await page.emulateMedia({reducedMotion:'reduce'});
 await page.goto('/');await page.getByRole('button',{name:'Начать игру',exact:true}).click();
 await expect(page.locator('.choices button')).toHaveCount(6);
 const drawings=new Set<string>();
 for(const id of ['graphite','cyberpunk','medieval','noir','arcane','terminal']){
  await request.put(`/api/worlds/${selection.world}/presentation`,{data:{theme_id:id}});
  await page.reload();await expect(page.locator('html')).toHaveAttribute('data-theme',id);
  await page.locator('.story-scroll').evaluate(el=>el.scrollTop=0);
  const art=page.locator('.skin-header-art');
  if(id==='graphite'){
   await expect(art).toHaveCount(0);await expect(page.locator('.theme-decoration')).toHaveCount(0);
  }else{
   await expect(art).toBeVisible();await expect(art).toHaveCSS('pointer-events','none');
   const bounds=await art.boundingBox();expect(bounds!.height).toBeGreaterThanOrEqual(56);
   const title=await page.locator('.story-heading h1').boundingBox();
   expect(bounds!.y+bounds!.height).toBeLessThanOrEqual(title!.y);
   expect(await art.evaluate(el=>getComputedStyle(el).opacity)).toBe('1');
   const paths=await art.locator('path').evaluateAll(nodes=>nodes.map(el=>el.getAttribute('d')).join('|'));
   expect(paths.length).toBeGreaterThan(100);drawings.add(paths);
   await expect(page.locator('.theme-decoration')).toHaveCSS('pointer-events','none');
  }
  for(const selector of ['.pov-controls','.scene-bar','.composer','.topbar']){
   const widths=await page.locator(selector).evaluateAll(nodes=>nodes.map(el=>{const c=getComputedStyle(el);return [c.borderLeftWidth,c.borderRightWidth]}));
   for(const sides of widths)expect(sides).toEqual(['0px','0px']);
  }
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.getByRole('textbox',{name:'Своё действие или реплика'}).fill('Осматриваюсь');
  await expect(page.getByRole('button',{name:'Отправить действие'})).toBeEnabled();
  await page.screenshot({path:info.outputPath(`skin-${id}.png`),animations:'disabled'});
  await page.getByRole('button',{name:'Пропустить время',exact:true}).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button',{name:'Закрыть',exact:true}).click();
 }
 expect(drawings.size).toBe(5);
});
