import {test,expect} from '@playwright/test';
import {nav} from './navigation';
import {localDate} from '../src/dates';
test('ISO and SQLite dates',()=>{
 expect(localDate('2026-09-17T12:30:00.000Z')).toBe(localDate('2026-09-17 12:30:00'));
 expect(localDate('2026-09-17T14:30:00+02:00')).toBe(localDate('2026-09-17T12:30:00Z'));
 expect(localDate(null)).toBe('Дата неизвестна');expect(localDate('broken')).toBe('Дата неизвестна');
 expect(localDate('2026-09-17T12:30:00Z')).not.toContain('Invalid');
});
for(const width of [360,390,412,430,1440])test(`inspector layout ${width}px`,async({page,request},info)=>{
 test.skip(info.project.name!=='desktop');await page.setViewportSize({width,height:900});
 const selected=await(await request.post('/test/seed')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selected);
 const full='Подробная внешность без потери текста. '.repeat(35);
 await page.route(`**/api/saves/${selected.save}`,async route=>{
  const response=await route.fetch();const body=await response.json();
  body.state.characters[0].fields['Внешность']=full;
  body.state.locations=[{name:'Современный город, район вокруг клиники',text:full}];
  body.state.sections.tone='Особые инструкции ведущему';
  body.state.memory={...body.state.memory,summary:'Полная исходная память. '.repeat(35)};
  await route.fulfill({response,json:body});
 });
 await page.goto('/');await page.locator('.breadcrumb').click();
 const library=page.locator('.library-dialog');await expect(library.locator('.world-card').first()).toBeVisible();
 await expect(library).not.toContainText('Invalid Date');
 expect(await library.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
 await page.screenshot({path:`test-results/library-${width}.png`});
 await page.keyboard.press('Escape');await nav(page,'Мир');const dialog=page.locator('.inspector-dialog');
 for(const tab of ['Мир','Сцена','Персонажи','Отношения','Тайны','Сюжет','Память']){
  await dialog.locator('.panel-tabs').getByRole('button',{name:tab,exact:true}).click();
  expect(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  // No-overflow alone missed the previous bug: headings were squeezed beside previews.
  for(const summary of await dialog.locator('.inspect-reveal > summary:visible').all()){
   const title=await summary.locator('.inspect-title').boundingBox();
   const box=await summary.boundingBox();expect(title!.width).toBeGreaterThan(box!.width-40);
   const preview=summary.locator('.inspect-preview');
   if(await preview.isVisible()){
    const p=await preview.boundingBox();expect(p!.y).toBeGreaterThanOrEqual(title!.y+title!.height);
   }
  }
  if(tab==='Персонажи'){
   const appearance=dialog.locator('.character-profile > details').filter({has:page.locator('summary',{hasText:/^Внешность$/})});
   await expect(appearance.locator('.prose')).not.toBeVisible();
   await appearance.locator('summary').click();await expect(appearance).toContainText(full.trim());
   await appearance.locator('summary').click();
  }
  if(tab==='Память'){
   const source=dialog.locator('details').filter({has:page.locator('summary',{hasText:/^Исходная выжимка$/})});
   await expect(source.locator('.prose').first()).not.toBeVisible();
   await source.locator('summary').first().click();await expect(source.locator('.prose').first()).toBeVisible();await expect(source).toContainText('Полная исходная память.');
   await source.locator('summary').first().click();
  }
  await page.screenshot({path:`test-results/inspector-${width}-${tab}.png`});
 }
});
test('card deletion cancellation and restore',async({page,request})=>{
 const selected=await(await request.post('/test/seed')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selected);
 await page.goto('/');await page.locator('.breadcrumb').click();
 const card=page.locator('.world-card-wrap').first();const name=await card.locator('strong').innerText();
 await card.locator('.world-remove').click();
 const confirmation=page.getByRole('dialog').filter({has:page.getByRole('heading',{name:`Удалить «${name}»?`})});
 await expect(confirmation).toBeVisible();await expect(page.locator('.save-list')).toHaveCount(0);
 await confirmation.getByRole('button',{name:'Отмена',exact:true}).click();await expect(card).toBeVisible();
 await card.locator('.world-remove').click();await confirmation.getByRole('button',{name:'Удалить',exact:true}).click();
 await expect(confirmation).toHaveCount(0);await expect(page.locator('.world-card strong').filter({hasText:name})).toHaveCount(0);
 await page.getByText('Удалённые выжимки',{exact:true}).click();
 await page.getByRole('button',{name:'Восстановить',exact:true}).last().click();
 await expect(page.locator('.world-card strong').filter({hasText:name})).toBeVisible();
});
