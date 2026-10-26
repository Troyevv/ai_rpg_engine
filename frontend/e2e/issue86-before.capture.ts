import {test,expect} from '@playwright/test';
import {nav} from './navigation';
test('before inspector inventory',async({page,request},info)=>{
 test.skip(info.project.name!=='desktop');test.setTimeout(120000);
 const s=await(await request.post('/test/ui-completion-seed?checkpoint=ui-dossier')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);
 for(const width of [1440,768,393,360])for(const skin of ['graphite','parchment']){
 await page.setViewportSize({width,height:900});await request.put(`/api/worlds/${s.world}/presentation`,{data:{theme_id:skin}});await page.goto('/');await nav(page,'Мир');
 for(const section of ['Мир','Сцена','Персонажи','Отношения','Тайны','Сюжет','Память']){
 await page.locator('.panel-tabs').getByRole('button',{name:section,exact:true}).click();
 if(section==='Персонажи'&&width>=768&&await page.getByRole('button',{name:'Расширить досье'}).isVisible())await page.getByRole('button',{name:'Расширить досье'}).click();
 await page.locator('.inspector-dialog').evaluate(e=>e.scrollTop=0);
 await page.screenshot({path:`../docs/manual_qa/narrative_v4/issue86-evidence/before-${width}-${skin}-${section}.png`,animations:'disabled'});
 }
 }
});
