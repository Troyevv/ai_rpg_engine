import {test,expect} from '@playwright/test';
import {nav} from './navigation';
import {writeFile} from 'node:fs/promises';
// Rendering contracts use variants of a real API response; persistence and
// provenance gates are independently exercised in test_character_dossier.py.
test('physical state variants never imply health',async({page,request})=>{
 const s=await(await request.post('/test/ui-completion-seed?checkpoint=ui-dossier')).json();
 const saved=await(await request.get(`/api/saves/${s.save}`)).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);
 let variant='blank';
 await page.route(`**/api/saves/${s.save}`,async route=>{
  const data=structuredClone(saved),state=data.state,c=state.world.characters.qa_kirill;
  const card=state.characters.find((c:any)=>c.id==='qa_kirill');
  c.physical_state=['transient','both'].includes(variant)?'Промок под дождём':'';card.fields['Физическое состояние']='';
  if(['blank','transient','legacy'].includes(variant))card.dossier.conditions=[];
  if(variant==='resolved')card.dossier.conditions.forEach((c:any)=>c.status='resolved');
  if(variant==='incapacitated')card.dossier.restrictions=['can_act'];
  if(variant==='legacy')delete card.dossier;
  await route.fulfill({json:data});
 });
 for(variant of ['blank','transient','condition','both','resolved','incapacitated','legacy']){
  await page.goto('/');await nav(page,'Мир');await page.locator('.panel-tabs').getByRole('button',{name:'Персонажи',exact:true}).click();
  const panel=page.getByRole('tabpanel');await expect(panel).not.toContainText('Здоров');await expect(panel).not.toContainText('Без ограничений');await expect(panel).not.toContainText('PRIVATE');
  if(['transient','both'].includes(variant))await expect(panel).toContainText('Промок под дождём');else await expect(panel).toContainText('Нет данных');
  if(['condition','both','incapacitated'].includes(variant))await expect(panel).toContainText('Повреждение ноги');else await expect(panel).not.toContainText('Повреждение ноги');
  if(variant==='incapacitated')await expect(panel).toContainText('Не может действовать');
  if(variant==='resolved'){
   await page.getByRole('tab',{name:'История',exact:true}).click();await page.getByText('История физических состояний',{exact:true}).click();await expect(panel).toContainText('Повреждение ноги');await expect(panel).toContainText('Завершено');
  }
 }
});

test('large roster search and missing portrait asset stay usable',async({page,request},info)=>{
 const s=await(await request.post('/test/ui-completion-seed?checkpoint=ui-family-dense')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);await page.goto('/');await nav(page,'Мир');await page.locator('.panel-tabs').getByRole('button',{name:'Персонажи',exact:true}).click();
 const d=page.locator('.inspector-dialog'),count=await d.getByLabel('Персонаж',{exact:true}).locator('option').count(),start=Date.now();await d.getByLabel('Найти персонажа').fill('Родственник 99');await expect(d.locator('h2').filter({hasText:'Родственник 99 с длинным именем'})).toBeVisible();
 await writeFile(`../docs/manual_qa/narrative_v4/issue83-evidence/performance-roster-${info.project.name}.json`,JSON.stringify({roster:count,search_ms:Date.now()-start,heap:await page.evaluate(()=>(performance as any).memory?.usedJSHeapSize||null)},null,2));
 await d.getByLabel('Найти персонажа').fill('');await d.getByLabel('Персонаж',{exact:true}).selectOption('qa_vera');
 await page.getByRole('button',{name:'Редактировать портрет',exact:true}).click();
 const png=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=c.height=256;return c.toDataURL().split(',')[1]});
 await page.getByLabel('Файл портрета').setInputFiles({name:'qa.png',mimeType:'image/png',buffer:Buffer.from(png,'base64')});
 await page.route('**/portraits/assets/*',route=>route.fulfill({status:404}));await page.getByRole('button',{name:'Сохранить',exact:true}).click();
 await expect(d.locator('.portrait-control .portrait-initials')).toBeVisible();await expect(d.getByRole('button',{name:'Редактировать портрет'})).toBeEnabled();
});
