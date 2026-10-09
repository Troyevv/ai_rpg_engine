import {test,expect} from '@playwright/test';
import {nav} from './navigation';

test('known residence and roles survive reload without exposing hidden residence',async({page,request})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const selected=await(await request.post('/test/residence-seed')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selected);
 await page.goto('/');await nav(page,'Мир');
 const region=page.getByRole('region',{name:'Семья и социальные связи'});
 await expect(region).toBeVisible();
 await expect(region).toContainText('Проживание');
 await expect(region).toContainText('Озёрск — дом Лариных');
 await expect(region).toContainText('Мастерская карт');
 await expect(region).toContainText('Ученица');
 await expect(region).not.toContainText('Речной Посад — сад');
 const before=await(await request.get(`/api/saves/${selected.save}`)).json();
 expect(JSON.stringify(before.state.residence_roles)).not.toContain('qa_elena_residence');
 await page.getByRole('button',{name:'Закрыть',exact:true}).click();
 await page.reload();await nav(page,'Мир');
 await expect(region).toContainText('Мастерская карт');
 const after=await(await request.get(`/api/saves/${selected.save}`)).json();
 expect(after.revision).toBe(before.revision);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
 expect(errors).toEqual([]);
});
