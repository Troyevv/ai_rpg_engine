import {test,expect} from '@playwright/test';
import {nav} from './navigation';

test('canonical commitments and interval projection survive read-only browsing and reload',async({page,request})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const selected=await(await request.post('/test/commitments-seed')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selected);
 await page.goto('/');
 await nav(page,'Мир');
 const section=page.getByRole('region',{name:'Договорённости и периоды'});
 await expect(section).toBeVisible();
 await section.getByText('Поездка в сад в пятницу вечером.',{exact:true}).click();
 await expect(section).toContainText('Условие: После работы');
 await expect(section).toContainText('Окно:');
 await section.getByText('Возвращение из сада домой.',{exact:true}).click();
 await expect(section).toContainText('Зависит от: Поездка в сад в пятницу вечером.');
 const before=await(await request.get(`/api/saves/${selected.save}`)).json();
 const projection=await(await request.get(`/api/saves/${selected.save}/calendar?start_date=2026-10-01&end_date=2026-10-31`)).json();
 expect(projection.scheduled.items.find((e:{id:string})=>e.id==='qa_school_break').interval_state).toBe('planned');
 const after=await(await request.get(`/api/saves/${selected.save}`)).json();
 expect(after.revision).toBe(before.revision);
 await page.getByRole('button',{name:'Закрыть',exact:true}).click();
 await page.reload();await nav(page,'Мир');
 await expect(section).toContainText('Каникулы Аси.');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
 expect(errors).toEqual([]);
});
