import {test,expect} from '@playwright/test';
import {nav} from './navigation';
for(const skin of ['graphite','parchment','cyberpunk'])test(`genre catalog visual states · ${skin}`,async({page},info)=>{
 await page.setViewportSize({width:info.project.name==='mobile'?390:1440,height:900});
 await page.addInitScript(s=>localStorage.setItem('workshop-theme',JSON.stringify({theme_id:s,mode:'manual'})),skin);
 await page.goto('/');await nav(page,'Создать');
 await page.locator('.atelier-param').filter({hasText:'Жанры истории'}).click();
 await page.getByLabel('Основной жанр',{exact:true}).selectOption('romance');
 await page.getByRole('checkbox',{name:'Драма',exact:true}).check();
 const path=info.outputPath(`before-${skin}-${info.project.name}.png`);
 await page.screenshot({path,animations:'disabled'});await info.attach('baseline',{path,contentType:'image/png'});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
});
