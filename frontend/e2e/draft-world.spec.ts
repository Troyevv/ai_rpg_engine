import {test,expect} from '@playwright/test';
import {nav} from './navigation';
for(const width of [360,390,412,430,1440]){
 test(`world draft creation and editor ${width}`,async({page,request})=>{
  await page.setViewportSize({width,height:900});
  const workspace=await (await request.post('/api/workspaces',{data:{name:`Черновик ${width}`}})).json();
  await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),workspace.id);
  await page.goto('/');await nav(page,'Создать');
  await page.getByLabel('Описание мира или текст импорта').fill('Драмеди. Восемь соседей собрались на кухне; один скрывает встречу у маяка. Сохрани направленные отношения.');
  await page.getByRole('button',{name:'Развить идею и создать мир',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Посмотри, что получилось'})).toBeVisible();
  await expect(page.locator('main')).not.toContainText('Тайная встреча у маяка');
  await page.getByRole('button',{name:'Редактировать мир',exact:true}).click();
  await page.getByRole('button',{name:'Показать всё',exact:true}).click();
  await page.locator('.workshop-tabs').getByRole('button',{name:'Персонажи',exact:true}).click();
  const first=page.locator('.workshop-person').first();
  await first.getByRole('button',{name:'Изменить fields.Внешность',exact:true}).click();
  await page.getByRole('dialog').getByLabel('Внешность',{exact:true}).fill('Рыжие волосы, зелёный шарф.');
  await page.getByRole('button',{name:'Сохранить поле',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  const draft=await (await request.get(`/api/workspaces/${workspace.id}/draft?author=true`)).json();
  expect(draft.state.characters[0].fields.Внешность).toContain('зелёный шарф');
  const exported=await request.get(`/api/workspaces/${workspace.id}/draft/export?version_id=${draft.version_id}&format=txt`);
  expect(exported.ok()).toBeTruthy();expect(await exported.text()).toContain('зелёный шарф');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.screenshot({path:`test-results/draft-${width}.png`,fullPage:true});
  await page.reload();await nav(page,'Создать');
  await expect(page.getByRole('heading',{name:'Посмотри, что получилось'})).toBeVisible();
  await page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true}).click();
  await page.getByRole('button',{name:'Подтвердить и открыть игру',exact:true}).click();
  await expect(page.getByRole('button',{name:'Начать игру',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Начать игру',exact:true}).click();
  await expect(page.locator('.choices button')).toHaveCount(6);
 });
}

test('new visitor can begin with an idea without making a workspace', async ({page}) => {
  await page.goto('/');
  await nav(page,'Создать');
  await expect(page.getByRole('heading',{name:'Придумай свою историю'})).toBeVisible();
  await page.getByLabel('Название черновика').fill('Вечер в клинике');
  await page.getByLabel('Описание мира или текст импорта').fill('Вечером врач заканчивает дежурство. Придумай коллег, привычки, отношения и начало истории.');
  await page.getByRole('button',{name:'Развить идею и создать мир'}).click();
  await expect(page.getByRole('heading',{name:'Посмотри, что получилось'})).toBeVisible();
  await expect(page.locator('.workshop-content')).toBeVisible();
  await expect(page.locator('main')).not.toContainText('Тайная встреча у маяка');
  await page.reload();await nav(page,'Создать');
  await expect(page.getByRole('heading',{name:'Посмотри, что получилось'})).toBeVisible();
});
