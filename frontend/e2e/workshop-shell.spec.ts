import {expect, test, type Page} from '@playwright/test';
import {nav} from './navigation';

async function workshop(page: Page) {
  await expect(page.locator('.ww-topbar')).toHaveCount(1);
  await expect(page.locator('.topbar,.nav-rail')).toHaveCount(0);
  await expect(page.getByRole('button', {name: 'RP-чат', exact:true})).toHaveCount(0);
}
test('workshop owns its header through resizing, editing, Back, library, reload and Chat', async ({page,request})=>{
  const selected=await (await request.post('/test/phone-seed?incoming=false')).json();
  await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selected);
  await page.goto('/');
  const input=page.getByLabel('Своё действие или реплика');
  await input.fill('Оставляю письмо на столе.');
  await nav(page,'Создать');
  await workshop(page);
  await page.getByLabel('Описание мира или текст импорта').fill('История на берегу реки');
  for(const width of [320,1440,390]){
    await page.setViewportSize({width,height:844});
    await workshop(page);
    await expect(page.getByLabel('Описание мира или текст импорта')).toHaveValue('История на берегу реки');
  }
  await page.goBack();
  await expect(input).toHaveValue('Оставляю письмо на столе.');
  await page.locator('.nr-worldpicker').click();
  await page.getByRole('button',{name:'Создать историю'}).click();
  await workshop(page);
  await page.reload();
  await workshop(page);
  await expect(page.getByLabel('Описание мира или текст импорта')).toHaveValue('История на берегу реки');
  await nav(page,'Игра');
  await expect(page.locator('.nr-topbar')).toHaveCount(1);
  await expect(page.locator('.ww-topbar')).toHaveCount(0);
  await page.getByRole('button',{name:'RP-чат',exact:true}).click();
  await expect(page.locator('.nr-topbar')).toHaveCount(0);
  await page.getByRole('dialog').getByRole('button',{name:'Назад на один уровень'}).click();
  await page.getByRole('button',{name:'Вернуться в Narrative'}).click();
  await expect(page.locator('.nr-worldpicker')).toBeVisible();
  expect(await page.evaluate(()=>JSON.parse(localStorage.getItem('selection')!))).toEqual(selected);
});

test('direct workshop link isolates the preview from a saved world', async ({page,request})=>{
  const selected=await (await request.post('/test/seed')).json();
  await request.put('/api/worlds/'+selected.world+'/presentation',{data:{theme_id:'space'}});
  await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selected);
  await page.addInitScript(()=>{if(!sessionStorage.getItem('visited-workshop-link')){
    localStorage.setItem('active-mode','chat');
    sessionStorage.setItem('visited-workshop-link','true');
  }});
  await page.goto('/#workshop');
  await workshop(page);
  if((page.viewportSize()?.width || 1440)<=760)
    await page.getByRole('button',{name:'Разделы мастерской',exact:true}).click();
  await page.getByRole('button',{name:'Оформление',exact:true}).click();
  await page.getByRole('button',{name:'Тема Noir',exact:true}).click();
  await expect(page.locator('html')).toHaveAttribute('data-layout','index');
  await page.reload();
  await workshop(page);
  await expect(page.locator('html')).toHaveAttribute('data-theme','noir');
  await page.goBack();
  await expect(page.locator('.nr-topbar')).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-theme','space');
  await page.goForward();
  await workshop(page);
});
