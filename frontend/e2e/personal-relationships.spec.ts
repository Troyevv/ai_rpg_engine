import {test,expect,type Page} from '@playwright/test';
import {nav,pickCharacter,searchCharacter,actor} from './navigation';
const dossier=(page:Page)=>page.locator('.inspector-workspace');
const partner=(page:Page,id:string)=>page.locator(`[data-partner-id="${id}"]`);
async function seed(page:Page,request:any,checkpoint='ui-personal'){
 const s=await(await request.post(`/test/ui-completion-seed?checkpoint=${checkpoint}`)).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);
 await page.goto('/');return s;
}

test('known partners, keyboard/touch, nested Back, tabs, search and scroll',async({page,request},info)=>{
 const s=await seed(page,request);await nav(page,'Персонажи');
 const d=dossier(page);const before=await(await request.get(`/api/saves/${s.save}`)).json();
 await expect(d.locator('.dossier-personal')).toContainText('В браке с:');
 await expect(d.locator('.dossier-personal')).toContainText('Встречается с:');
 await expect(d.locator('.dossier-partner-link')).toHaveCount(2);
 await expect(partner(page,'qa_marina')).toHaveCount(0);
 await searchCharacter(page,'Кирилл');
 await partner(page,'qa_vera').focus();await page.keyboard.press('Enter');
 await expect(d.locator('.dossier-name')).toHaveText(/Вера Ларина/);
 await partner(page,'qa_kirill').focus();await page.keyboard.press('Space');
 await expect(d.locator('.dossier-name')).toHaveText(/Кирилл Ларин/);
 await d.getByRole('button',{name:'Вернуться к досье: Вера Ларина',exact:true}).click();
 await expect(d.locator('.dossier-name')).toHaveText(/Вера Ларина/);
 await page.keyboard.press('Escape');
 await expect(d.locator('.dossier-name')).toHaveText(/Кирилл Ларин/);
 await expect(partner(page,'qa_vera')).toBeFocused();
 await d.getByRole('combobox',{name:'Персонаж',exact:true}).click();
 await expect(page.getByLabel('Найти персонажа')).toHaveValue('Кирилл');await page.keyboard.press('Escape');
 if(info.project.name==='mobile')await partner(page,'qa_elena').tap();else await partner(page,'qa_elena').click();
 await expect(d.getByRole('combobox',{name:'Персонаж',exact:true})).toHaveAttribute('data-value','qa_elena');
 await page.goBack();await expect(d.getByRole('combobox',{name:'Персонаж',exact:true})).toHaveAttribute('data-value','qa_kirill');
 // Existing relationship links keep their tab and local scroll on return.
 await d.getByRole('tab',{name:'Отношения',exact:true}).click();
 const link=d.locator('.dossier-person').first();await link.scrollIntoViewIfNeeded();
 const scroll=await d.locator('.inspector-scroll').evaluate(el=>el.scrollTop);
 await link.click();await expect(d.getByRole('tab',{name:'Обзор',exact:true})).toHaveAttribute('aria-selected','true');
 await page.keyboard.press('Escape');await expect(d.getByRole('tab',{name:'Отношения',exact:true})).toHaveAttribute('aria-selected','true');
 await expect.poll(()=>d.locator('.inspector-scroll').evaluate(el=>el.scrollTop)).toBe(scroll);
 await page.keyboard.press('Escape');await nav(page,'Сцена');
 await d.locator('.inspector-person-row').filter({hasText:'Кирилл Ларин'}).click();
 await partner(page,'qa_vera').click();await page.keyboard.press('Escape');
 await expect(d.locator('.dossier-name')).toContainText('Кирилл Ларин');
 await page.keyboard.press('Escape');await expect(d).toHaveAttribute('aria-label','Сцена');
 const after=await(await request.get(`/api/saves/${s.save}`)).json();
 expect(after.revision).toBe(before.revision);expect(after.state).toEqual(before.state);
});

test('responsive identity in graphite, parchment and terminal with long names',async({page,request},info)=>{
 test.skip(info.project.name!=='desktop');test.setTimeout(120000);
 const s=await seed(page,request);
 await page.route(`**/api/saves/${s.save}`,async route=>{
  const response=await route.fetch();const data=await response.json();
  for(const c of data.state.characters)if(['qa_vera','qa_elena'].includes(c.id))c.name+=' Александровна Константинопольская-Рождественская';
  await route.fulfill({response,json:data});
 });
 for(const [width,skin] of [[360,'parchment'],[393,'graphite'],[768,'parchment'],[1440,'graphite'],[1440,'terminal']] as const){
  await page.setViewportSize({width,height:900});await page.emulateMedia({reducedMotion:'reduce'});
  const response=await request.put(`/api/worlds/${s.world}/presentation`,{data:{theme_id:skin}});expect(response.ok()).toBe(true);
  await page.goto('/');await nav(page,'Персонажи');const d=dossier(page);
  await expect(d.locator('.dossier-partner-link')).toHaveCount(2);await expect(d.getByRole('tab')).toHaveCount(5);
  for(const compact of width>=768?[false,true]:[false]){
   const toggle=d.getByRole('button',{name:compact?'Компактная панель':'Расширить панель',exact:true});
   if(await toggle.isVisible())await toggle.click();
   expect(await d.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
   expect(await d.locator('.dossier-identity').evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
   for(const button of await d.locator('.dossier-partner-link').all()){
    const box=(await button.boundingBox())!;expect(box.height).toBeGreaterThanOrEqual(44);
    await expect(button).toContainText('Константинопольская-Рождественская');
   }
   await partner(page,'qa_elena').click();await expect(d.getByRole('combobox',{name:'Персонаж',exact:true})).toHaveAttribute('data-value','qa_elena');
   await page.keyboard.press('Escape');await expect(partner(page,'qa_elena')).toBeFocused();
  }
 }
});

test('fresh API projections, unavailable IDs, unknown closure, rename and POV',async({page,request})=>{
 const s=await seed(page,request);let mode='original';
 await page.route(`**/api/saves/${s.save}`,async route=>{
  const response=await route.fetch();const data=await response.json();
  const spouse=data.state.objective_relations.find((r:any)=>r.id==='qa_marriage');
  // A newer hidden World State closure must not override this authorized projection.
  if(spouse&&mode!=='original'){
   data.state.world.objective_relations={qa_marriage:{...spouse,status:'closed',outcome:'divorced'}};
   data.state.objective_relations=[spouse];
   if(mode==='missing')spouse.target_id='unavailable-person';
   if(mode==='divorced'){spouse.status='closed';spouse.outcome='divorced'}
   if(mode==='suspected')spouse.certainty='suspected';
   if(mode==='rename')data.state.characters.find((c:any)=>c.id==='qa_vera').name='Вера Новая';
  }
  await route.fulfill({response,json:data});
 });
 for(const [next,expected] of [['hidden','В браке с:'],['rename','Вера Новая'],['missing','Нет сведений'],['divorced','Разведён'],['suspected','Нет сведений']]){
  mode=next;await page.reload();await nav(page,'Персонажи');await expect(dossier(page).locator('.dossier-personal')).toContainText(expected);
  if(['missing','divorced','suspected'].includes(next))await expect(dossier(page).locator('.dossier-partner-link')).toHaveCount(0);
 }
 mode='original';await page.reload();await expect(page.locator('.pov-controls,.mobile-pov')).toBeVisible();await actor(page,'qa_vera','Вера Ларина');await nav(page,'Персонажи');await pickCharacter(page,'qa_kirill');
 await expect(dossier(page).locator('.dossier-partner-link')).toHaveCount(1);
 await expect(partner(page,'qa_vera')).toBeVisible();await expect(partner(page,'qa_elena')).toHaveCount(0);
});

test('genealogy and narrative entry, partner return, draft and persisted next turn',async({page,request})=>{
 const s=await seed(page,request,'ui-family');
 const composer=page.getByLabel('Своё действие или реплика');await composer.fill('Сохранить мой черновик');
 await nav(page,'Родословная');const family=page.locator('.save-workspace');
 await expect(family.getByLabel('Семья персонажа')).toHaveValue('qa_kirill');
 await family.getByRole('button',{name:'Список',exact:true}).click();
 await family.getByRole('button',{name:'Открыть досье: Кирилл Ларин',exact:true}).click();
 await partner(page,'qa_vera').click();await page.keyboard.press('Escape');
 await expect(dossier(page).locator('.dossier-name')).toContainText('Кирилл Ларин');
 await page.keyboard.press('Escape');await expect(family).toBeVisible();await page.keyboard.press('Escape');
 await expect(composer).toHaveValue('Сохранить мой черновик');
 const turns=await page.locator('.turn').count();await page.locator('.choices button').first().click();await expect(page.locator('.turn')).toHaveCount(turns+1);
 // The seeded ordinary narrative references Kirill or Vera, both linked spouses.
 const link=page.locator('.turn [data-character-id="qa_kirill"],.turn [data-character-id="qa_vera"]').first();
 await link.click();const original=await dossier(page).getByRole('combobox',{name:'Персонаж',exact:true}).getAttribute('data-value');
 await dossier(page).locator('.dossier-partner-link').first().click();await page.keyboard.press('Escape');
 await expect(dossier(page).getByRole('combobox',{name:'Персонаж',exact:true})).toHaveAttribute('data-value',original!);
 await page.keyboard.press('Escape');await page.reload();await expect(page.locator('.turn')).toHaveCount(turns+1);
 await page.locator('.choices button').first().click();await expect(page.locator('.turn')).toHaveCount(turns+2);
 const saved=await(await request.get(`/api/saves/${s.save}`)).json();expect(saved.turns).toHaveLength(turns+2);
});
