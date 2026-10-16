import {test,expect} from '@playwright/test';

test('phone controls, freeform text, reload and physical scene',async({page,request})=>{
 const seed=await request.post('/test/phone-seed');expect(seed.ok()).toBeTruthy();
 const selected=await seed.json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selected);
 const before=await (await request.get(`/api/saves/${selected.save}`)).json();
 await page.goto('/');
 await expect(page.getByRole('button',{name:'Посмотреть в окно',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Открыть звонок',exact:true}).click();
 const dialog=page.getByRole('dialog');
 await expect(dialog.getByText('Входящий',{exact:false})).toBeVisible();
 await dialog.getByRole('button',{name:'Ответить',exact:true}).click();
 await expect(dialog.getByRole('button',{name:'Завершить звонок',exact:true})).toBeVisible();
 await page.reload();
 await page.getByRole('button',{name:'Открыть звонок',exact:true}).click();
 await dialog.getByRole('button',{name:'Завершить звонок',exact:true}).click();
 await expect(dialog.getByRole('button',{name:'Завершить звонок',exact:true})).toHaveCount(0);
 const after=await (await request.get(`/api/saves/${selected.save}`)).json();
 expect(after.state.scene).toEqual(before.state.scene);
 await dialog.getByRole('button',{name:'Написать',exact:true}).first().click();
 await dialog.getByLabel('Сообщение в телефоне').fill('Привет! Это мой точный текст.');
 await dialog.getByRole('button',{name:'Отправить сообщение',exact:true}).click();
 await expect(dialog.getByText('Привет! Это мой точный текст.',{exact:true})).toBeVisible();
 await expect(dialog.locator('.choice')).toHaveCount(0);
 await page.reload();
 await page.getByRole('button',{name:'Телефон',exact:true}).click();
 await dialog.getByRole('button',{name:'Переписки',exact:true}).click();
 await dialog.getByRole('button').filter({hasText:'Вера работа'}).click();
 await expect(dialog.getByText('Привет! Это мой точный текст.',{exact:true})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
});

test('decline and configured in-game emergency log',async({page,request})=>{
 const selected=await (await request.post('/test/phone-seed')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selected);
 await page.goto('/');await page.getByRole('button',{name:'Открыть звонок',exact:true}).click();
 const dialog=page.getByRole('dialog');await dialog.getByRole('button',{name:'Отклонить',exact:true}).click();
 await dialog.getByRole('button',{name:'Звонки',exact:true}).click();
 await expect(dialog.getByText(/Входящий · Отклонён/)).toBeVisible();
 await dialog.getByRole('button',{name:'Позвонить: Скорая помощь',exact:true}).click();
 await expect(dialog.getByRole('button',{name:'Завершить звонок',exact:true})).toBeVisible();
 await expect(dialog.locator('a[href^="tel:"]')).toHaveCount(0);
});
