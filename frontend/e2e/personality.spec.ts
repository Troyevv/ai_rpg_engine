import {test,expect} from '@playwright/test';
import {nav} from './navigation';

test('sparse child card shows established preference and survives reload',async({page,request})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const selection=await(await request.post('/test/personality-seed')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selection);
 await page.goto('/');await nav(page,'Мир');
 await page.locator('.panel-tabs').getByRole('button',{name:'Персонажи',exact:true}).click();
 await page.getByLabel('Персонаж',{exact:true}).selectOption('qa_asya');
 const panel=page.locator('.character-profile');
 await expect(panel.getByRole('heading',{name:'Ася Ларина',exact:true})).toBeVisible();
 await panel.getByText('Предпочтения',{exact:true}).first().click();
 await expect(panel).toContainText('Любит рисовать.');
 const before=await(await request.get(`/api/saves/${selection.save}`)).json();
 const child=before.state.characters.find((c:{id:string})=>c.id==='qa_asya');
 expect(child.fields['Характер']).toBe('');
 expect(child.fields['Сильные стороны']).toBeFalsy();
 expect(JSON.stringify(before.state.world.characters.qa_asya)).not.toContain('seen_sources');
 await page.getByRole('button',{name:'Закрыть',exact:true}).click();
 await page.reload();await nav(page,'Мир');
 await page.locator('.panel-tabs').getByRole('button',{name:'Персонажи',exact:true}).click();
 await page.getByLabel('Персонаж',{exact:true}).selectOption('qa_asya');
 await panel.getByText('Предпочтения',{exact:true}).first().click();
 await expect(panel).toContainText('Любит рисовать.');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
 expect(errors).toEqual([]);
});
