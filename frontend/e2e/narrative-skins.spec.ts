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
