import {test,expect} from '@playwright/test';
import {nav} from './navigation';

test('paused generation survives reload with author-only inspection and safe cancellation',async({page,request})=>{
  const seeded=await(await request.post('/test/staged-checkpoint')).json();
  await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),seeded.workspace);
  await page.goto('/');await nav(page,'Создать');
  const panel=page.getByRole('region',{name:'Этапы генерации мира'});
  await expect(panel.getByRole('heading',{name:'На паузе'})).toBeVisible();
  await expect(panel.getByRole('progressbar',{name:'Общий прогресс генерации'})).toHaveAttribute('value','0.125');
  await expect(panel).not.toContainText('удочер');
  await expect(panel.getByRole('button',{name:'Посмотреть результат'})).toHaveCount(0);
  await page.reload();await nav(page,'Создать');
  await expect(panel.getByRole('heading',{name:'На паузе'})).toBeVisible();
  await panel.getByLabel('Авторский просмотр:',{exact:false}).check();
  await panel.locator('summary').filter({hasText:'Понимание замысла'}).click();
  await panel.getByRole('button',{name:'Посмотреть результат'}).click();
  await expect(page.getByRole('dialog')).toContainText('удочер');
  expect((await(await request.get(`/api/jobs/${seeded.job}`)).json()).status).toBe('paused');
  await page.keyboard.press('Escape');
  await panel.getByRole('button',{name:'Отменить генерацию'}).click();
  await expect(panel.getByRole('heading',{name:'Отменено'})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
});
