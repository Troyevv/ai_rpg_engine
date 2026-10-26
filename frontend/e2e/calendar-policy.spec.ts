import {test,expect} from '@playwright/test';
import {nav} from './navigation';

test('E5 starts with warnings in Player View without new review',async({page,request},info)=>{
 const w=await(await request.post('/test/calendar-policy-e5')).json();
 await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),w.id);
 await page.goto('/');await nav(page,'Создать');
 await expect(page.getByRole('button',{name:'Начать с предупреждениями',exact:true})).toBeEnabled();
 await expect(page.getByText('Согласованность сюжета не подтверждена. Можно начать с предупреждениями.',{exact:true})).toBeVisible();
 const before=await(await request.get(`/api/workspaces/${w.id}/requests`)).json();
 await page.screenshot({path:`test-results/e5-warning-${info.project.name}.png`,fullPage:true});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(await page.evaluate(()=>innerWidth));
 await page.getByRole('button',{name:'Начать с предупреждениями',exact:true}).click();
 await page.getByRole('button',{name:'Подтвердить и открыть игру',exact:true}).click();
 await expect(page.getByRole('button',{name:'Начать с предупреждениями',exact:true})).toHaveCount(0);
 expect(await(await request.get(`/api/workspaces/${w.id}/requests`)).json()).toEqual(before);
 const d=await(await request.get(`/api/workspaces/${w.id}/draft?author=true`)).json();
 expect(d.review.status).toBe('failed');
 await page.getByRole('button',{name:'Начать игру',exact:true}).click();
 await expect(page.locator('.choices button')).toHaveCount(6);
 await page.reload();
 await expect(page.locator('.choices button')).toHaveCount(6);
});

test('regional presets preview apply and custom edit preserve E5 authorship',async({page,request},info)=>{
 const w=await(await request.post('/test/calendar-policy-e5')).json();
 await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),w.id);
 await page.goto('/');await nav(page,'Создать');
 await page.getByRole('button',{name:'Автор мира',exact:true}).click();
 await page.getByRole('button',{name:'Показать всё',exact:true}).click();
 await page.getByRole('button',{name:/Начало игры/}).click();
 await page.getByText('Праздники и сезоны мира',{exact:true}).click();
 await page.getByRole('button',{name:'Предпросмотр набора',exact:true}).click();
 await expect(page.getByLabel('Предпросмотр календаря')).toContainText('Россия');
 await page.getByRole('button',{name:'Применить набор',exact:true}).click();
 await expect.poll(async()=> (await(await request.get(`/api/workspaces/${w.id}/draft?author=true`)).json()).candidate.world_clock.calendar.profile.regional?.country).toBe('RU');
 await page.getByLabel('Праздники',{exact:true}).selectOption('country');
 await page.getByLabel('Страна праздников',{exact:true}).selectOption('US');
 await page.getByRole('button',{name:'Применить набор',exact:true}).click();
 await expect.poll(async()=> (await(await request.get(`/api/workspaces/${w.id}/draft?author=true`)).json()).candidate.world_clock.calendar.profile.regional?.country).toBe('US');
 await page.getByRole('button',{name:'Добавить праздник',exact:true}).click();
 await page.getByLabel('observances 1 название').fill('Семейная встреча');
 await page.getByRole('button',{name:'Сохранить свои даты',exact:true}).click();
 await expect.poll(async()=> (await(await request.get(`/api/workspaces/${w.id}/draft?author=true`)).json()).candidate.world_clock.calendar.profile.observances.length).toBe(1);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(await page.evaluate(()=>innerWidth));
 await page.screenshot({path:`test-results/e5-presets-${info.project.name}.png`,fullPage:true});
});

test('Quick and Scenario share independent presets and preview',async({page},info)=>{
 await page.goto('/');await nav(page,'Создать');
 await page.getByText('Настройки генератора',{exact:true}).click();
 await page.getByLabel('Тип мира',{exact:true}).selectOption('real_world');
 await page.getByLabel('География',{exact:true}).fill('Россия, Москва');
 await page.getByLabel('Дата начала',{exact:true}).fill('2026-10-23');
 await page.getByRole('button',{name:'Предпросмотр календаря',exact:true}).click();
 await expect(page.getByLabel('Предпросмотр календаря')).toContainText('Россия');
 await page.getByLabel('Праздники',{exact:true}).selectOption('country');
 await page.getByLabel('Страна праздников',{exact:true}).selectOption('BR');
 await page.getByLabel('Сезоны',{exact:true}).selectOption('south');
 await page.getByRole('button',{name:'Со Сценаристом',exact:true}).click();
 await page.getByText('Настройки генератора',{exact:true}).click();
 await expect(page.getByLabel('Страна праздников',{exact:true})).toHaveValue('BR');
 await expect(page.getByLabel('Сезоны',{exact:true})).toHaveValue('south');
 await page.getByRole('button',{name:'Предпросмотр календаря',exact:true}).click();
 await expect(page.getByLabel('Предпросмотр календаря')).toContainText('Бразилия');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(await page.evaluate(()=>innerWidth));
 await page.screenshot({path:`test-results/scenario-presets-${info.project.name}.png`,fullPage:true});
});
