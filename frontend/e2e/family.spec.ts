import {test,expect} from '@playwright/test';
import {nav} from './navigation';

test('authorized family projection survives reload without hidden kinship',async({page,request})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const selected=await(await request.post('/test/family-seed')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selected);
 await page.goto('/');await nav(page,'Мир');
 const region=page.getByRole('region',{name:'Семья и социальные связи'});
 await expect(region).toBeVisible();await expect(region).toContainText('Брак');
 await expect(region).toContainText('Кирилл Ларин');await expect(region).not.toContainText('Зоя');
 const before=await(await request.get(`/api/saves/${selected.save}`)).json();
 const graph=await(await request.get(`/api/saves/${selected.save}/genealogy`)).json();
 expect(JSON.stringify(graph)).not.toContain('qa_secret_parent');
 expect(JSON.stringify(graph)).not.toContain('qa_zoya');
 expect(graph.kinship.some((r:{kind:string})=>r.kind==='ancestor')).toBe(true);
 await region.getByText('Родословная',{exact:true}).click();
 await expect(region).toContainText('Предок');
 await page.getByRole('button',{name:'Закрыть',exact:true}).click();
 await page.reload();await nav(page,'Мир');await expect(region).toContainText('Брак');
 const after=await(await request.get(`/api/saves/${selected.save}`)).json();expect(after.revision).toBe(before.revision);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
 expect(errors).toEqual([]);
});
