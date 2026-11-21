import {expect, test} from '@playwright/test';

test('container resize preserves the physical draft, phone geometry and modal focus',async({page,request},info)=>{
  test.skip(info.project.name!=='desktop','Resizes the app independently of the browser viewport');
  const seed=await(await request.post('/test/phone-seed?incoming=false')).json();
  await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),seed);
  await page.setViewportSize({width:1440,height:900});
  await page.goto('/');
  const root=page.locator('#root'), input=page.getByLabel('Своё действие или реплика');
  const draft=Array(12).fill('Многострочное действие игрока').join('\n');
  await input.fill(draft);
  for (const width of [1080,681,680,390,320,768]) {
    await root.evaluate((el,w)=>el.style.width=w+'px',width);
    const mobile=width<=680;
    await expect(page.locator('[data-mobile-menu-trigger]')).toHaveCount(mobile?1:0);
    const header=await page.locator('.nr-topbar').boundingBox();
    expect(header!.y).toBe(0);
    await page.getByRole('button',{name:/^Телефон/}).click();
    const device=page.locator('.phone-device.is-open');
    await expect.poll(async()=>Math.round((await device.boundingBox())!.width)).toBe(mobile?width:350);
    await expect.poll(async()=>Math.round((await device.boundingBox())!.y)).toBe(mobile?0:200);
    await expect(page.locator('.narrative-shell')).toHaveAttribute('inert','');
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button',{name:/^Телефон/})).toBeFocused();
    await expect(input).toHaveValue(draft);
    await page.getByRole('button',{name:'Управление игрой',exact:true}).click();
    const panel=root.getByRole('dialog',{name:'Управление игрой'});
    await expect(panel.getByRole('tab')).toHaveCount(4);
    if(mobile)await expect.poll(async()=>Math.round((await panel.boundingBox())!.width)).toBe(width);
    expect(await panel.evaluate(e=>e.scrollWidth<=e.clientWidth+1)).toBe(true);
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button',{name:'Управление игрой',exact:true})).toBeFocused();
  }
});

test('saved directory entry survives reload without granting an NPC identity',async({page,request})=>{
  const seed=await(await request.post('/test/phone-seed?incoming=false')).json();
  await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),seed);
  await page.goto('/');
  const openDirectory=async()=>{
    await page.getByRole('button',{name:/^Телефон/}).click();
    await page.getByRole('button',{name:'Контакты',exact:true}).click();
  };
  await openDirectory();
  await page.getByRole('button',{name:'Добавить контакт',exact:true}).click();
  await page.getByLabel('Сохранённое имя').fill('Справочная');
  await page.getByLabel('Адрес или номер').fill('555-0103');
  await page.getByRole('button',{name:'Сохранить контакт',exact:true}).click();
  await expect(page.getByRole('button',{name:'Справочная',exact:true})).toBeVisible();
  await page.reload();
  await openDirectory();
  await page.getByRole('button',{name:'Справочная',exact:true}).click();
  await expect(page.locator('.phone-contact-detail')).toContainText('555-0103');
});
