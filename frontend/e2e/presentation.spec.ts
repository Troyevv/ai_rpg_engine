import {test,expect,type Page} from '@playwright/test';
import {nav,actor,diagnostics} from './navigation';

const palette=['graphite','gothic','parchment','noir','neon'];
async function noOverflow(page:Page){
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 const dialog=page.getByRole('dialog');
 if(await dialog.count()) expect(await dialog.last().evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
}
async function capture(page:Page,path:string){
 // Capture the final UI, not a translucent frame halfway through a dialog transition.
 await expect(page.locator('.dialog-content[data-state=closed]')).toHaveCount(0);
 for(const el of await page.locator('.dialog-content[data-state=open],.turn').all())await expect(el).toHaveCSS('opacity','1');
 await expect.poll(()=>page.locator('.tab-indicator').evaluateAll(nodes=>nodes.every(el=>{
  const a=el.getBoundingClientRect(),b=el.parentElement!.getBoundingClientRect();
  return Math.abs(a.x-b.x)<2&&Math.abs(a.y-b.y)<2&&Math.abs(a.width-b.width)<3&&Math.abs(a.height-b.height)<3;
 }))).toBe(true);
 await page.screenshot({path,animations:'disabled'});
}
async function themeControl(page:Page){
 await nav(page,'Мир');await page.locator('.theme-disclosure > summary').click();
 return page.getByLabel('Тема мира',{exact:true}).filter({has:page.locator('option')});
}

test('world themes persist across reload and devices; portals inherit theme; all palettes remain playable',async({page,request,browser},info)=>{
 const selection=await(await request.post('/test/seed')).json();
 await request.put(`/api/worlds/${selection.world}/presentation`,{data:{theme_id:'graphite'}});
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selection);
 await page.goto('/');
 await expect(page.locator('html')).toHaveAttribute('data-theme','graphite');
 await page.getByRole('button',{name:'Начать игру',exact:true}).click();
 await expect(page.locator('.choices button')).toHaveCount(6);
 for(const id of palette){
  await themeControl(page);await page.locator('.theme-selector select').selectOption(id);
  await expect(page.locator('html')).toHaveAttribute('data-theme',id);
  expect(await page.getByRole('dialog').evaluate(el=>getComputedStyle(el).getPropertyValue('--bg').trim())).toBe(await page.locator('html').evaluate(el=>getComputedStyle(el).getPropertyValue('--bg').trim()));
  const contrast=await page.locator('html').evaluate(el=>{
   const css=getComputedStyle(el);
   const luminance=(token:string)=>{
    const hex=css.getPropertyValue(token).trim().slice(1);
    const rgb=[0,2,4].map(i=>parseInt(hex.slice(i,i+2),16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);
    return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;
   };
   return [['--text','--bg'],['--text-muted','--surface-2'],['--text-subtle','--bg'],['--accent','--accent-soft'],['--accent-contrast','--accent']].map(([a,b])=>{
    const values=[luminance(a),luminance(b)].sort((a,b)=>a-b);return (values[1]+.05)/(values[0]+.05);
   });
  });
  for(const ratio of contrast)expect(ratio).toBeGreaterThanOrEqual(4.5);
  await noOverflow(page);await page.getByRole('button',{name:'Закрыть',exact:true}).click();
  await expect(page.locator('.choices button').first()).toBeEnabled();
  await page.locator('.story-scroll').evaluate(el=>el.scrollTop=0);
  await capture(page,info.outputPath(`${id}.png`));
  await page.getByRole('textbox',{name:'Своё действие или реплика'}).fill(`Мой ход в ${id}`);
  await expect(page.getByRole('button',{name:'Отправить действие'})).toBeEnabled();
  await diagnostics(page);await page.getByRole('tab',{name:'Производительность',exact:true}).click();
  await expect(page.locator('.diagnostic-history')).toContainText('2 LLM');
  await noOverflow(page);await page.getByRole('button',{name:'Закрыть',exact:true}).click();
 }
 await page.reload();await expect(page.locator('html')).toHaveAttribute('data-theme','neon');
 const other=await browser.newContext();const p=await other.newPage();
 await p.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selection);
 await p.goto('http://127.0.0.1:8011/');await expect(p.locator('html')).toHaveAttribute('data-theme','neon');await other.close();
 await page.getByRole('textbox',{name:'Своё действие или реплика'}).fill('Подхожу к окну');
 await page.getByRole('button',{name:'Отправить действие'}).click();await expect(page.locator('.turn')).toHaveCount(2);
 await page.locator('.choices button').first().click();await expect(page.locator('.turn')).toHaveCount(3);
 await page.reload();await expect(page.locator('.turn').first()).toHaveCSS('opacity','1');
});

test('legacy world defaults, auto selection, keyboard tabs and reduced motion retain POV and camera',async({page,request})=>{
 const selection=await(await request.post('/test/seed')).json();
 await page.emulateMedia({reducedMotion:'reduce'});
 // A legacy API response with no presentation metadata must still render Graphite.
 await page.route(`**/api/worlds/${selection.world}`,async route=>{
  const response=await route.fetch();const value=await response.json();delete value.presentation;
  await route.fulfill({response,json:value});
 });
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selection);
 await page.goto('/');await expect(page.locator('html')).toHaveAttribute('data-theme','graphite');
 await themeControl(page);await page.locator('.theme-selector select').selectOption('auto');
 await expect(page.locator('.theme-selector')).toContainText('Автовыбор закреплён');
 await page.getByRole('button',{name:'Закрыть',exact:true}).click();
 await page.getByRole('button',{name:'Начать игру',exact:true}).click();await expect(page.locator('.turn')).toHaveCount(1);
 const save=await(await request.get(`/api/saves/${selection.save}`)).json();
 const target=save.state.characters.find((c:any)=>c.id==='character_2');
 await actor(page,target.id,target.name);await expect(page.locator('.turn')).toHaveCount(2);
 await expect(page.locator('.pov-divider')).toContainText(target.name);
 await expect(page.locator('.pov-divider')).toHaveCSS('transform','none');
 if((page.viewportSize()?.width||1440)<768){await page.locator('.mobile-pov button').last().click();}
 else await page.getByRole('button',{name:'Камера · Журнал'}).click();
 await expect(page.getByRole('heading',{name:'Камера мира'})).toBeVisible();
 await page.locator('.camera-tabs button').first().focus();await page.keyboard.press('End');
 await expect(page.locator('.camera-tabs button').last()).toHaveAttribute('aria-pressed','true');
 await page.keyboard.press('Home');await page.locator('.camera-cast').getByRole('button',{name:'Наблюдать',exact:true}).first().click();
 await expect(page.locator('.background-turn')).toHaveCount(1);
 await expect(page.locator('.narrative-divider')).toHaveText('Тем временем');
 await noOverflow(page);
 await nav(page,'Создать');await expect(page.getByRole('heading',{name:'Придумай свою историю'})).toBeVisible();
});

for(const size of [{width:1920,height:1080},{width:1366,height:768},{width:360,height:800},{width:430,height:932}]){
 test(`long content smoke ${size.width}`,async({page,request},info)=>{
  await page.setViewportSize(size);
  const selection=await(await request.post('/test/seed')).json();
  await request.put(`/api/worlds/${selection.world}/presentation`,{data:{theme_id:'parchment'}});
  await page.route(`**/api/worlds/${selection.world}`,async route=>{
   const response=await route.fetch();const data=await response.json();data.name='Город на краю бесконечно длинной ночи: история одного неожиданного возвращения';await route.fulfill({response,json:data});
  });
  await page.route(`**/api/saves/${selection.save}`,async route=>{
   const response=await route.fetch();const data=await response.json();
   data.scene_meta.location='Дом у старой набережной · очень длинное название гостиной с окнами во внутренний двор';
   data.state.characters[1].name='Константин Александрович Очень-Длинное-Имя';
   for(const r of Object.values(data.state.world.relationships) as any[])r.context='Давно знакомы, но доверие требует времени. '.repeat(30);
   for(const turn of data.turns)turn.assistant_text+='\n\n'+('За окном медленно зажигаются огни. '.repeat(70));
   await route.fulfill({response,json:data});
  });
  await page.route(`**/api/saves/${selection.save}/accounting`,async route=>{
   const response=await route.fetch();const data=await response.json();
   if(data.turns[0])data.turns[0].warnings=[{section:'knowledge',index:2,reason:'Нет подтверждённого пути передачи знания. '.repeat(25)}];
   await route.fulfill({response,json:data});
  });
  await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selection);
  await page.goto('/');await page.getByRole('button',{name:'Начать игру',exact:true}).click();await expect(page.locator('.choices button')).toHaveCount(6);
  await noOverflow(page);await page.locator('.story-scroll').evaluate(el=>el.scrollTop=0);
  await capture(page,info.outputPath('game.png'));
  await nav(page,'Мир');await page.locator('.panel-tabs').getByRole('button',{name:'Персонажи',exact:true}).click();
  await page.getByLabel('Персонаж',{exact:true}).selectOption('character_2');await noOverflow(page);
  await capture(page,info.outputPath('inspector.png'));
  await page.locator('.panel-tabs').getByRole('button',{name:'Отношения',exact:true}).click();await noOverflow(page);
  await capture(page,info.outputPath('relationships.png'));await page.getByRole('button',{name:'Закрыть',exact:true}).click();
  await diagnostics(page);await page.getByRole('tab',{name:'Производительность'}).click();await noOverflow(page);
  await capture(page,info.outputPath('diagnostics.png'));
 });
}
