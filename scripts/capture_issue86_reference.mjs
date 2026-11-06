// Capture the user-supplied approved HTML without changing its source/data.
// node scripts/capture_issue86_reference.mjs /absolute/path/to/index.html
import { chromium } from '../frontend/node_modules/playwright/index.mjs';
import { readFileSync } from 'node:fs';
const source=readFileSync(process.argv[2],'utf8');
const browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH,headless:true,args:['--no-sandbox']});
const sections={world:'Мир',scene:'Сцена',characters:'Персонажи',relationships:'Отношения',threads:'Сюжет',memory:'Память',secrets:'Тайны'};
const out='docs/manual_qa/narrative_v4/issue86-evidence';
for(const width of [1440,768,393,360]){
 const page=await browser.newPage({viewport:{width,height:900},deviceScaleFactor:1});
 await page.setContent(source);await page.emulateMedia({reducedMotion:'reduce'});
 for(const skin of ['graphite','parchment']){
  if(skin==='parchment')await page.locator('[data-action="theme"]').click();
  for(const mode of ['expanded','compact']){
   if(mode==='compact'){
    if(width<768)await page.setViewportSize({width:768,height:900});
    await page.locator('[data-action="width"]').click();
    await page.locator('.toast').waitFor({state:'hidden'});
    if(width<768)await page.setViewportSize({width,height:900});
   }
   for(const [id,name] of Object.entries(sections)){
    if(width<650)await page.locator('#mobile-menu-button').click();
    await page.locator(`#sidebar [data-nav="${id}"]`).click();
    await page.screenshot({path:`${out}/reference-${width}-${skin}-${name}-${mode}.png`,animations:'disabled'});
   }
  }
  if(width<768)await page.setViewportSize({width:768,height:900});
  await page.locator('[data-action="width"]').click();
  await page.locator('.toast').waitFor({state:'hidden'});
  if(width<768)await page.setViewportSize({width,height:900});
 }
 await page.close();
}
await browser.close();
