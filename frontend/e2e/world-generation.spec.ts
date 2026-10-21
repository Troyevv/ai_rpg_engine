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


test('author edits personality on pause after dependency preview and reloads the accepted checkpoint',async({page,request})=>{
  const seeded=await(await request.post('/test/staged-checkpoint?characters=true')).json();
  await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),seeded.workspace);
  await page.goto('/');await nav(page,'Создать');
  const panel=page.getByRole('region',{name:'Этапы генерации мира'});
  await panel.getByLabel('Авторский просмотр:',{exact:false}).check();
  const stage=panel.locator('details').filter({has:page.locator('summary').filter({hasText:'Персонажи'})});
  await stage.locator('summary').click();
  await stage.getByRole('button',{name:'Посмотреть результат'}).click();
  const dialog=page.getByRole('dialog');
  await dialog.getByLabel('Описание черты').fill('Спокойная, внимательная и настойчивая');
  await dialog.getByRole('button',{name:'Проверить влияние правки'}).click();
  await expect(dialog.getByRole('status')).toContainText('Отношения и обстоятельства');
  const before=await(await request.get(`/api/jobs/${seeded.job}/generation/checkpoints/core_0?author=true`)).json();
  expect(JSON.stringify(before)).not.toContain('Спокойная, внимательная');
  await dialog.getByRole('button',{name:'Сохранить правку'}).click();
  await expect(dialog).not.toBeVisible();
  await page.reload();await nav(page,'Создать');
  await panel.getByLabel('Авторский просмотр:',{exact:false}).check();
  await stage.locator('summary').click();
  await stage.getByRole('button',{name:'Посмотреть результат'}).click();
  await expect(dialog.getByLabel('Описание черты')).toHaveValue('Спокойная, внимательная и настойчивая');
  const after=await(await request.get(`/api/jobs/${seeded.job}/generation/checkpoints/core_0?author=true`)).json();
  expect(after.artifact_version).not.toBe(before.artifact_version);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
});
