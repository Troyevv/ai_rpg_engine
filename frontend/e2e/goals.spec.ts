import {test,expect} from '@playwright/test';
import {nav,pickCharacter} from './navigation';

test('completed intention stays historical; goal and value survive reload',async({page,request})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const selection=await(await request.post('/test/goals-seed')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selection);
 await page.goto('/');
 for(let n=0;n<2;n++){
  await nav(page,'Мир');
  await nav(page,'Персонажи');
  await pickCharacter(page,'qa_ilya');
  const panel=page.locator('.character-profile');
  await panel.getByRole('tab',{name:'Личность',exact:true}).click();
  await expect(panel.locator('.motivation-editor')).toContainText('Развивать отношения с Соней.');
  await expect(panel.locator('.motivation-editor')).not.toContainText('После «Критического успеха»');
  await panel.getByText('История целей и намерений',{exact:true}).click();
  await expect(panel).toContainText('Завершено · После «Критического успеха» встретиться с Соней');
  await panel.getByText('Ценности',{exact:true}).first().click();
  await expect(panel).toContainText('Ценит честность в близких отношениях.');
  const saved=await(await request.get(`/api/saves/${selection.save}`)).json();
  expect(saved.state.world.characters.qa_ilya.intentions).toEqual([]);
  expect(saved.state.world.characters.qa_ilya.lifecycle.intentions[0].id).toBe('intentions_4d05e847cba4c0a38a98');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
  await page.getByRole('button',{name:'Закрыть',exact:true}).click();
  if(n===0) await page.reload();
 }
 expect(errors).toEqual([]);
});
