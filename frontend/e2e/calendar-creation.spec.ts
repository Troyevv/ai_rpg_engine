import {test,expect} from '@playwright/test';
import {nav} from './navigation';

test('calendar settings persist and resolve exact time',async({page,request},info)=>{
 const workspace=await(await request.post('/api/workspaces',{data:{name:'Calendar settings'}})).json();
 await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),workspace.id);
 await page.goto('/');await nav(page,'Создать');
 await page.getByText('Настройки генератора',{exact:true}).click();
 await expect(page.getByLabel('Дата начала',{exact:true})).toHaveValue('');
 await page.getByLabel('Календарь начала игры').selectOption('gregorian');
 await page.getByLabel('Дата начала',{exact:true}).fill('1370-10-23');
 await page.getByLabel('Время начала',{exact:true}).fill('12:00');
 await page.reload();await nav(page,'Создать');
 await page.getByText('Настройки генератора',{exact:true}).click();
 await expect(page.getByLabel('Дата начала',{exact:true})).toHaveValue('1370-10-23');
 await expect(page.getByLabel('Время начала',{exact:true})).toHaveValue('12:00');
 await page.screenshot({path:`test-results/calendar-settings-${info.project.name}.png`,fullPage:true});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(await page.evaluate(()=>innerWidth));
 await page.getByLabel('Описание мира или текст импорта').fill('TEST_JSON_CONTINUATION. Сейчас 23.10.2026, 06:00, пятница. Соседи на кухне.');
 await page.getByRole('button',{name:'Развить идею и создать мир',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Посмотри, что получилось'})).toBeVisible();
 const draft=await(await request.get(`/api/workspaces/${workspace.id}/draft?author=true`)).json();
 expect(draft.state.world_clock.minute%1440).toBe(720);
 expect(draft.state.world_clock.calendar.start_date).toBe('1370-10-23');
 expect(draft.presentation.notices.length).toBeGreaterThan(0);
 expect(draft.validation.errors).toEqual([]);
 await page.getByRole('button',{name:'Автор мира',exact:true}).click();
 await page.getByRole('button',{name:'Показать всё',exact:true}).click();
 await expect(page.getByText(/применена настройка 1370-10-23/)).toBeVisible();
 await page.screenshot({path:`test-results/calendar-preview-${info.project.name}.png`,fullPage:true});
});

test('custom date and validation',async({page})=>{
 await page.goto('/');await nav(page,'Создать');
 await page.getByText('Настройки генератора',{exact:true}).click();
 await page.getByLabel('Календарь начала игры').selectOption('custom');
 await page.getByLabel('Длины месяцев',{exact:true}).fill('40');
 await page.getByLabel('Год начала',{exact:true}).fill('0042');
 await page.getByLabel('Месяц начала',{exact:true}).fill('01');
 await page.getByLabel('День начала',{exact:true}).fill('40');
 await expect(page.getByLabel('День начала',{exact:true})).toHaveValue('40');
 await page.getByLabel('Длины месяцев',{exact:true}).fill('0');
 await expect(page.getByRole('alert')).toContainText('Проверьте длины');
});
