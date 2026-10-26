import {test,expect} from '@playwright/test';
import {nav} from './navigation';

test('grounded correction shows current and old beliefs after reload without gossip',async({page,request})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const response=await request.post('/test/knowledge-seed');expect(response.ok()).toBeTruthy();
 const selection=await response.json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selection);
 await page.goto('/');
 for(let n=0;n<2;n++){
  await nav(page,'Мир');
  await page.locator('.panel-tabs').getByRole('button',{name:'Персонажи',exact:true}).click();
  await page.getByLabel('Персонаж',{exact:true}).selectOption('qa_kirill');
  const panel=page.locator('.character-profile');
  await panel.getByRole('tab',{name:'История',exact:true}).click();
  await panel.locator('summary').filter({hasText:/^Знания и подозрения/}).click();
  await panel.getByText('Прежние убеждения · 1',{exact:true}).click();
  const retired=panel.locator('details').filter({has:page.locator('summary').getByText('Исправлено',{exact:true})}).last();
  await retired.locator('summary').first().click();
  await expect(retired).toContainText('Олег работает в Мастерской карт.');
  await expect(retired).toContainText('Новое убеждение: Олег теперь работает в Академии двух берегов.');
  await expect(retired).toContainText('Основание: Олег сообщил Кириллу');
  const saved=await(await request.get(`/api/saves/${selection.save}`)).json();
  expect(saved.state.world.knowledge['qa_kirill:qa_oleg_workshop'].status).toBe('superseded');
  expect(saved.state.world.knowledge['qa_kirill:qa_oleg_academy'].status).toBe('known');
  expect(saved.state.world.knowledge['qa_vera:qa_oleg_workshop'].status).toBe('known');
  expect(saved.state.world.knowledge['qa_vera:qa_oleg_academy']).toBeUndefined();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
  await page.getByRole('button',{name:'Закрыть',exact:true}).click();
  if(n===0)await page.reload();
 }
 expect(errors).toEqual([]);
});
