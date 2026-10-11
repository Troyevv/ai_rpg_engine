import {test,expect} from '@playwright/test';

test('choice proposals survive reload without committing action; free input remains available',async({page,request})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const response=await request.post('/test/choices-seed');expect(response.ok()).toBeTruthy();
 const selection=await response.json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selection);
 const saved=async()=> (await request.get(`/api/saves/${selection.save}`)).json();
 const before=await saved();
 await page.goto('/');
 await expect(page.locator('.choices button')).toHaveCount(6);
 await expect(page.locator('.choices')).toContainText('Предложить смелую версию');
 await expect(page.getByLabel('Своё действие или реплика')).toBeEnabled();
 await page.reload();
 await expect(page.locator('.choices button')).toHaveCount(6);
 expect((await saved()).state).toEqual(before.state);
 // Typed input is outside the suggestions and deliberately atypical.
 const input='Вопреки привычке, не проверяю детали, а предлагаю рискнуть.';
 await page.getByLabel('Своё действие или реплика').fill(input);
 await page.getByRole('button',{name:'Отправить действие',exact:true}).click();
 await expect(page.locator('.turn')).toHaveCount(4);
 await expect(page.locator('.turn').last().getByTestId('player-action')).toContainText(input);
 await expect(page.locator('.choices button')).toHaveCount(6);
 await page.reload();
 await expect(page.locator('.choices button')).toHaveCount(6);
 await page.locator('.choices button').first().click();
 await expect(page.locator('.turn')).toHaveCount(5);
 await expect(page.locator('.turn').last().getByTestId('player-action')).toContainText('Действие 0');
 const after=await saved();
 for(const key of ['goals','intentions','obligations','emotion','personality']){
  expect(after.state.world.characters.qa_kirill[key]).toEqual(before.state.world.characters.qa_kirill[key]);
 }
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
 expect(errors).toEqual([]);
});
