import {test,expect} from '@playwright/test';
test.use({video:'on'});
test('direct calendar and family navigation preserves story draft',async({page,request},info)=>{
 const selected=await(await request.post('/test/family-seed')).json();await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selected);
 if(info.project.name==='mobile')await page.setViewportSize({width:360,height:800});
 await page.goto('/');await page.getByLabel('Своё действие или реплика').fill('Мой черновик');
 const open=async(name:string)=>{if(info.project.name==='mobile')await page.getByRole('button',{name:'Меню игры'}).click();await page.getByRole('navigation',{name:info.project.name==='mobile'?'Мобильная навигация':'Главная навигация'}).getByRole('button',{name,exact:true}).click()};
 await open('Календарь');const area=page.locator('.save-workspace');await expect(area.locator('.rdp-root')).toBeVisible();
 const before=await(await request.get(`/api/saves/${selected.save}`)).json();
 await page.screenshot({path:info.outputPath('calendar-after.png'),animations:'disabled'});
 await area.getByLabel('Следующий месяц',{exact:true}).click();await expect(area.locator('.calendar-detail h4')).toContainText('ноября');
 await area.getByRole('button',{name:'Год',exact:true}).click();await expect(area.locator('.calendar-mini')).toHaveCount(12);
 await page.screenshot({path:info.outputPath('year-after.png'),animations:'disabled'});
 await page.keyboard.press('Escape');await expect(page.getByLabel('Своё действие или реплика')).toHaveValue('Мой черновик');
 await open('Родословная');await expect(area.locator('.react-flow__node').first()).toBeVisible();
 await area.getByLabel('Семья персонажа').selectOption('qa_vera');await expect(area.locator('.react-flow__node').first()).toBeVisible();await page.screenshot({path:info.outputPath('family-after.png'),animations:'disabled'});
 expect((await(await request.get(`/api/saves/${selected.save}`)).json()).revision).toBe(before.revision);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
