import {test,expect} from '@playwright/test';
import {nav} from './navigation';
test('capture original dossier and family',async({page,request},info)=>{
 const s=await(await request.post('/test/ui-completion-seed?checkpoint=ui-family')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);
 if(info.project.name==='mobile')await page.setViewportSize({width:360,height:800});
 for(const skin of ['graphite','parchment']){
 await request.put(`/api/worlds/${s.world}/presentation`,{data:{theme_id:skin}});
 await page.goto('/');await nav(page,'Мир');await page.locator('.panel-tabs').getByRole('button',{name:'Персонажи',exact:true}).click();
 await expect(page.locator('.character-header')).toBeVisible();
 await page.screenshot({path:`../docs/manual_qa/narrative_v4/issue83-evidence/before-${info.project.name}-${skin}.png`,animations:'disabled'});
 await page.keyboard.press('Escape');await nav(page,'Родословная');
 await expect(page.locator('.react-flow__node').first()).toBeVisible();
 await page.screenshot({path:`../docs/manual_qa/narrative_v4/issue83-evidence/before-family-${info.project.name}-${skin}.png`,animations:'disabled'});
 }
});
