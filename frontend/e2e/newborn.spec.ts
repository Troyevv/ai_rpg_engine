import {test,expect} from '@playwright/test';
import {nav} from './navigation';

test('ordinary newborn Characters and independent genealogy survive reload',async({page,request})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const response=await request.post('/test/newborn-seed');expect(response.ok()).toBeTruthy();
 const selected=await response.json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selected);
 const graph=async()=> (await request.get(`/api/saves/${selected.save}/genealogy`)).json();
 const before=await graph();
 const children=before.nodes.filter((n:{id:string})=>n.id.startsWith('character_'));
 expect(children).toHaveLength(2);expect(new Set(children.map((n:{id:string})=>n.id)).size).toBe(2);
 for(const child of children) expect(before.edges.filter((e:{kind:string,target_id:string})=>e.kind==='parent'&&e.target_id===child.id)).toHaveLength(2);
 await page.goto('/');await nav(page,'Мир');
 const region=page.getByRole('region',{name:'Семья и социальные связи'});
 await expect(region).toBeVisible();await expect(region).toContainText('Без имени');
 await page.reload();await nav(page,'Мир');await expect(region).toContainText('Без имени');
 expect(await graph()).toEqual(before);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
 expect(errors).toEqual([]);
});
