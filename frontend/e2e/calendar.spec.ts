import {test,expect} from '@playwright/test';

test('canonical date, observances and server time skip preview survive reload',async({page,request})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const selected=await(await request.post('/test/calendar-seed')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selected);
 await page.goto('/');
 await expect(page.locator('.scene-bar, .mobile-scene-line')).toContainText('2026-10-08');
 await page.getByText('Ближайшие даты',{exact:true}).click();
 await expect(page.getByText('2026-10-09 · День рождения: Вера Ларина')).toBeVisible();
 const before=await(await request.get(`/api/saves/${selected.save}`)).json();
 await page.getByRole('button',{name:'Пропустить время',exact:true}).click();
 const dialog=page.getByRole('dialog');
 await dialog.getByRole('button',{name:'До полуночи',exact:true}).click();
 await expect(dialog).toContainText('2026-10-09 · Пт · 00:00');
 const unchanged=await(await request.get(`/api/saves/${selected.save}`)).json();
 expect(unchanged.revision).toBe(before.revision);
 expect(unchanged.state.world_clock.minute).toBe(before.state.world_clock.minute);
 await page.getByRole('button',{name:'Закрыть',exact:true}).click();
 await page.reload();
 await expect(page.locator('.scene-bar, .mobile-scene-line')).toContainText('2026-10-08');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
 expect(errors).toEqual([]);
});
