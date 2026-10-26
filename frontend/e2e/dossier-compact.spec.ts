import {test,expect} from '@playwright/test';
import {nav} from './navigation';
test('all tabs in compact desktop and sparse restricted mobile, both skins',async({page,request},info)=>{
 const s=await(await request.post('/test/ui-completion-seed?checkpoint=ui-dossier')).json();await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);
 const mobile=info.project.name==='mobile';if(mobile)await page.setViewportSize({width:360,height:800});
 for(const skin of ['graphite','parchment']){
  await request.put(`/api/worlds/${s.world}/presentation`,{data:{theme_id:skin}});await page.goto('/');await nav(page,'Мир');await page.locator('.panel-tabs').getByRole('button',{name:'Персонажи',exact:true}).click();const d=page.locator('.inspector-dialog');
  if(mobile)await d.getByLabel('Персонаж',{exact:true}).selectOption('qa_vera');else await expect.poll(async()=>Math.round((await d.boundingBox())!.width)).toBe(440);
  for(const [i,tab] of ['Обзор','Личность','Отношения','Семья','История'].entries()){
   await d.getByRole('tab',{name:tab,exact:true}).click();await expect(d.getByRole('tabpanel')).toBeVisible();await expect(d).not.toContainText('PRIVATE');
   if(tab==='История'){await d.getByText(/^Знания и подозрения/).click();await expect(d).not.toContainText('PRIVATE')}
   await d.evaluate(el=>el.scrollTop=0);await page.screenshot({path:`../docs/manual_qa/narrative_v4/issue83-evidence/after-${mobile?'sparse-360':'compact-440'}-${skin}-${i}.png`,animations:'disabled'});
  }
 }
});
