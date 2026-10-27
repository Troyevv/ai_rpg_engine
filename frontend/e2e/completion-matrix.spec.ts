import {test,expect} from '@playwright/test';
import {nav,pickCharacter} from './navigation';
test.use({video:'on'});
async function seed(page:any,request:any,checkpoint:string){
 const response=await request.post(`/test/ui-completion-seed?checkpoint=${checkpoint}`);expect(response.ok()).toBe(true);
 const selected=await response.json();await page.addInitScript((s:any)=>localStorage.setItem('selection',JSON.stringify(s)),selected);return selected;
}
test('T04-T08 calendar agenda, empty dates, private observance and two skins',async({page,request},info)=>{
 if(info.project.name==='mobile')await page.setViewportSize({width:360,height:800});
 const s=await seed(page,request,'ui-calendar');
 const before=await(await request.get(`/api/saves/${s.save}`)).json();
 expect(JSON.stringify(before)).not.toContain('Скрытая личная дата');
 for(const skin of ['graphite','parchment']){
  await request.put(`/api/worlds/${s.world}/presentation`,{data:{theme_id:skin}});await page.goto('/');
  await nav(page,'Календарь');const area=page.locator('.save-workspace');
  await expect(area.getByText('Годовщина первой восстановленной карты',{exact:true})).toBeVisible();
  await expect(area.getByText('Завершено',{exact:false})).toBeVisible();
  await expect(area.getByText('Отменено',{exact:false})).toBeVisible();
  await expect(area.getByText('срок прошёл',{exact:false})).toBeVisible();
  await page.screenshot({path:info.outputPath(`calendar-events-${skin}.png`),animations:'disabled'});
  await area.getByLabel('Следующий месяц',{exact:true}).click();await expect(area.getByText('Известных событий нет.',{exact:true})).toBeVisible();
  await page.screenshot({path:info.outputPath(`calendar-empty-${skin}.png`),animations:'disabled'});
  await area.getByLabel('Предыдущий месяц',{exact:true}).click();await expect(area.locator('.calendar-detail h4')).toContainText('1 октября');
  await area.getByRole('button',{name:'Год',exact:true}).click();await expect(area.locator('.calendar-mini')).toHaveCount(12);
  await page.screenshot({path:info.outputPath(`calendar-year-${skin}.png`),animations:'disabled'});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 }
 const after=await(await request.get(`/api/saves/${s.save}`)).json();expect(after.revision).toBe(before.revision);expect(after.state.world_clock).toEqual(before.state.world_clock);
});
test('T06 custom calendar has two months, five weekdays and a real year boundary',async({page,request},info)=>{
 const s=await seed(page,request,'ui-calendar-custom');await page.goto('/');await nav(page,'Календарь');const area=page.locator('.save-workspace');
 await expect(area.getByText('Годовщина клятвы',{exact:true})).toBeVisible();
 await expect(area.locator('.custom-calendar>small')).toHaveCount(5);
 await area.getByLabel('Следующий месяц',{exact:true}).click();await expect(area.getByRole('heading',{name:'Свет · 43',exact:true})).toBeVisible();
 await expect(area.locator('.custom-calendar>button')).toHaveCount(20);
 await area.getByRole('button',{name:'Год',exact:true}).click();await expect(area.locator('.calendar-mini')).toHaveCount(2);
 await expect(area.locator('.calendar-mini').first().getByRole('button')).toHaveCount(20);
 await expect(area.locator('.calendar-mini').last().getByRole('button')).toHaveCount(25);
 await page.screenshot({path:info.outputPath('custom-year-after.png'),animations:'disabled'});
 const after=await(await request.get(`/api/saves/${s.save}`)).json();expect(after.state.world_clock.projection.date).toBe('0042-02-25');
});
test('T10-T13 separate family, known empty family, secrecy and accessible graph',async({page,request},info)=>{
 if(info.project.name==='mobile')await page.setViewportSize({width:393,height:852});
 const s=await seed(page,request,'ui-family');const before=await(await request.get(`/api/saves/${s.save}`)).json();
 for(const skin of ['graphite','parchment']){
  await request.put(`/api/worlds/${s.world}/presentation`,{data:{theme_id:skin}});await page.goto('/');await nav(page,'Родословная');const area=page.locator('.save-workspace');
  await area.getByLabel('Семья персонажа').selectOption('qa_timur');await expect(area.locator('.react-flow__node')).toHaveCount(5);
  await expect(area).toContainText('Зоя');
  await page.screenshot({path:info.outputPath(`family-other-${skin}.png`),animations:'disabled'});
  await area.getByText('Доступный список связей',{exact:true}).click();await expect(area.getByRole('button',{name:'Роман Луговой',exact:true})).toBeVisible();
  await area.getByLabel('Семья персонажа').selectOption('qa_oleg');await expect(area.getByText('Семейные связи не указаны.',{exact:true})).toBeVisible();
  await page.screenshot({path:info.outputPath(`family-empty-${skin}.png`),animations:'disabled'});
  await page.keyboard.press('Escape');await expect(page.locator('.save-workspace')).toHaveCount(0);
 }
 const after=await(await request.get(`/api/saves/${s.save}`)).json();expect(after.revision).toBe(before.revision);expect(after.state.controlled_actor_id).toBe(before.state.controlled_actor_id);
});
test('T12 dense family is bounded and can be recentered from accessible list',async({page,request},info)=>{
 await seed(page,request,'ui-family-dense');await page.goto('/');await nav(page,'Родословная');const area=page.locator('.save-workspace');
 const start=Date.now();await area.getByLabel('Семья персонажа').selectOption('qa_timur');await expect(area.locator('.react-flow__node')).toHaveCount(80);
 await expect(area.getByText('Показана часть семьи.',{exact:false})).toBeVisible();
 await (await import('node:fs/promises')).writeFile(info.outputPath('graph-metrics.json'),JSON.stringify({viewport:page.viewportSize(),nodes:80,render_ms:Date.now()-start}));
 await area.getByRole('button',{name:'Увеличить',exact:true}).click();await area.getByRole('button',{name:'Вся семья',exact:true}).click();
 await area.getByText('Доступный список связей',{exact:true}).click();await area.getByRole('button',{name:'Родственник 1 с длинным именем',exact:true}).click();
 await expect(area.locator('.react-flow__node').first()).toBeVisible();expect(await area.locator('.react-flow__node').count()).toBeLessThanOrEqual(80);
 await page.screenshot({path:info.outputPath('family-dense-after.png'),animations:'disabled'});
});

test('T03 T11 contextual date and empty character card open the shared workspace',async({page,request},info)=>{
 await seed(page,request,'ui-family');await page.goto('/');
 await page.getByLabel('Своё действие или реплика').fill('Контекстный черновик');
 if(info.project.name==='mobile')await page.locator('.mobile-scene-line').click();
 await page.getByRole('button',{name:'Открыть календарь',exact:true}).click();
 const area=page.locator('.save-workspace');await expect(area.locator('.rdp-root')).toBeVisible();
 await page.keyboard.press('Escape');await expect(page.getByLabel('Своё действие или реплика')).toHaveValue('Контекстный черновик');
 await nav(page,'Мир');await nav(page,'Персонажи');
 await pickCharacter(page,'qa_oleg');
 await page.getByRole('tab',{name:'Семья',exact:true}).click();
 await page.getByRole('button',{name:'Открыть родословную',exact:true}).click();
 await expect(area.getByLabel('Семья персонажа')).toHaveValue('qa_oleg');
 await expect(area.getByText('Семейные связи не указаны.',{exact:true})).toBeVisible();
 await area.getByLabel('Найти персонажа').fill('Зоя');
 await expect(area.getByLabel('Семья персонажа').locator('option')).toHaveCount(2);
 await expect(area.getByLabel('Семья персонажа')).toHaveValue('');
 await page.screenshot({path:info.outputPath('empty-card-context-after.png'),animations:'disabled'});
});

test('public family and birthday directory works without Knowledge or contacts',async({page,request},info)=>{
 const s=await seed(page,request,'ui-public-directory');await page.goto('/');
 const before=await(await request.get(`/api/saves/${s.save}`)).json();
 const calendar=await(await request.get(`/api/saves/${s.save}/calendar?start_date=2026-10-01&end_date=2026-10-31`)).json();
 expect(calendar.events.some((e:any)=>e.kind==='birthday'&&e.character_ids.includes('qa_zoya'))).toBe(true);
 await nav(page,'Родословная');const area=page.locator('.save-workspace');
 await area.getByLabel('Семья персонажа').selectOption('qa_zoya');await expect(area.locator('.react-flow__node')).toHaveCount(5);
 await page.screenshot({path:info.outputPath('public-family.png'),animations:'disabled'});
 await page.keyboard.press('Escape');await nav(page,'Календарь');
 await area.getByRole('button',{name:'Год',exact:true}).click();await expect(area.locator('.calendar-mini')).toHaveCount(12);
 await page.screenshot({path:info.outputPath('public-calendar.png'),animations:'disabled'});
 const after=await(await request.get(`/api/saves/${s.save}`)).json();expect(after.revision).toBe(before.revision);
});
