import {chooseOption} from './choice-navigation';
import {test, expect, type Page} from '@playwright/test';

async function geometry(page: Page) {
  const management = await page.getByRole('button', {name: 'Управление игрой', exact: true}).boundingBox();
  const journal = await page.getByRole('button', {name: /^История уведомлений, /}).boundingBox();
  expect(management).not.toBeNull();
  expect(journal).not.toBeNull();
  const toolbar=page.getByRole('group',{name:'Действия истории'});
  const box=(await toolbar.boundingBox())!;
  const header=(await page.locator('.topbar').boundingBox())!;
  expect(Math.abs(box.y-header.y-header.height)).toBeLessThanOrEqual(1);
  expect(management!.y).toBeGreaterThanOrEqual(box.y);
  expect(management!.y+management!.height).toBeLessThanOrEqual(box.y+box.height+1);
  await expect(page.locator('.nr-context .story-journal-trigger')).toHaveCount(1);
  expect(await toolbar.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  return box;
}

for (const theme of ['graphite', 'parchment']) {
  for (const size of [0, 1]) {
    test(`compact narrative controls and preserved dialogs/notifications: ${theme}, size ${size}`, async ({page, request}, info) => {
      const mobile = info.project.name === 'mobile';
      const viewport = mobile
        ? [{width: 360, height: 800}, {width: 393, height: 852}][size]
        : [{width: 1440, height: 900}, {width: 1920, height: 1080}][size];
      await page.setViewportSize(viewport);
      const seed = async () => {
        const response = await request.post('/test/story168-seed');
        expect(response.ok()).toBe(true);
        const s = await response.json();
        expect((await request.put(`/api/worlds/${s.world}/presentation`, {data: {theme_id: theme}})).ok()).toBe(true);
        return s;
      };
      const s = await seed(), other = await seed();
      await page.addInitScript(s => {
        if (!localStorage.getItem('selection')) localStorage.setItem('selection', JSON.stringify({world: s.world, save: s.save}));
      }, s);
      await page.goto('/');
      const management = page.getByRole('button', {name: 'Управление игрой', exact: true});
      const journal = page.getByRole('button', {name: /^История уведомлений, /});
      await expect(journal).toHaveAccessibleName('История уведомлений, 0');
      const initial = await geometry(page);

      await management.focus();
      await management.press('Enter');
      await expect(page.getByRole('dialog').getByRole('heading', {name: 'Управление игрой', exact: true})).toBeVisible();
      await expect(page.locator('.narrative-toolbar [role="dialog"]')).toHaveCount(0);
      await page.keyboard.press('Escape');
      await expect(page.getByRole('dialog')).toHaveCount(0);
      await expect(management).toBeFocused();
      await journal.focus();
      await expect(journal).toBeFocused();
      await journal.press('Enter');
      await expect(page.getByRole('dialog').getByRole('heading', {name: 'События истории', exact: true})).toBeVisible();
      await expect(page.locator('.story-journal-empty')).toContainText('История открытий ещё не началась');
      await page.keyboard.press('Escape');
      await expect(page.getByRole('dialog')).toHaveCount(0);
      expect(await geometry(page)).toEqual(initial);

      // A committed Narrative turn exercises the real notification lifecycle.
      expect((await request.post(`/test/story168-prepare/${s.save}`)).ok()).toBe(true);
      await page.getByLabel('Своё действие или реплика').fill('Расскажи о рукописи.');
      await page.getByRole('button', {name: 'Отправить действие', exact: true}).click();
      const toast = page.locator('.story-toast');
      await expect(toast).toBeVisible();
      await expect(journal).toHaveAccessibleName('История уведомлений, 3');
      expect(await geometry(page)).toEqual(initial);
      expect(await toast.evaluate(el => getComputedStyle(el).position)).toBe('fixed');
      const toastBox = (await toast.boundingBox())!;
      expect(toastBox.x).toBeGreaterThanOrEqual(0);
      expect(toastBox.x + toastBox.width).toBeLessThanOrEqual(viewport.width);
      const after = await (await request.get(`/api/saves/${s.save}`)).json();
      for (const event of after.state.notification_history) {
        await expect(toast).toHaveAttribute('data-notice-id', event.id);
        await toast.getByRole('button', {name: 'Скрыть уведомление', exact: true}).click();
      }
      await expect(toast).toHaveCount(0);
      await journal.click();
      await expect(page.locator('.story-journal-list li')).toHaveCount(3);
      await page.getByRole('dialog').getByRole('button', {name: 'Закрыть', exact: true}).click();
      await expect(page.getByRole('dialog')).toHaveCount(0);
      await page.reload();
      await expect(journal).toHaveAccessibleName('История уведомлений, 3');
      await expect(toast).toHaveCount(0);
      expect(await geometry(page)).toEqual(initial);

      // Switch through the actual library, without remounting the browser.
      for (const target of [other, s]) {
        await page.locator('.breadcrumb').click();
        if(mobile)await chooseOption(page.getByLabel('Выбрать мир',{exact:true}), String(target.world));
        else await page.locator(`[data-world-id="${target.world}"] .world-card`).click();
        const saves = await (await request.get(`/api/worlds/${target.world}/saves`)).json();
        const choices = page.locator('.save-list button').filter({hasText: 'Продолжить →'});
        await expect(choices).toHaveCount(saves.length);
        const index = saves.findIndex((save: {id: number}) => save.id === target.save);
        expect(index).toBeGreaterThanOrEqual(0);
        const loaded = page.waitForResponse(r => r.url().endsWith(`/api/saves/${target.save}`) && r.request().method() === 'GET');
        await choices.nth(index).click();
        expect((await loaded).ok()).toBe(true);
        await expect(page.getByRole('dialog')).toHaveCount(0);
        await expect(journal).toHaveAccessibleName(`История уведомлений, ${target === s ? 3 : 0}`);
        await expect(toast).toHaveCount(0);
        expect(await geometry(page)).toEqual(initial);
      }
      if (process.env.TOOLBAR_SCREENSHOTS && size === 0) {
        await page.screenshot({path: `${process.env.TOOLBAR_SCREENSHOTS}/toolbar-${theme}-${info.project.name}.png`});
      }
    });
  }
}

test('Narrative header keeps world selection and Chat reachable with long names',async({page,request},info)=>{
  test.setTimeout(120000);
  const seed=await(await request.post('/test/story168-seed')).json();
  await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),seed);
  const titles=['Наследие Волковых','Наследие Волковых — семейная сага о городе, старом доме и тайнах нескольких поколений','НаследиеВолковых'.repeat(30)];
  let title=titles[0];
  await page.route(`**/api/worlds/${seed.world}`,async route=>{const response=await route.fetch();const body=await response.json();body.name=title;await route.fulfill({response,json:body})});
  for(const width of info.project.name==='mobile'?[320,360,393,430]:[768,900,1024,1440,1920]){
    await page.setViewportSize({width,height:width<768?780:900});
    for(title of titles){
      await page.goto('/');const header=page.locator('.topbar'),world=header.locator('.breadcrumb');await expect(world).toContainText(title);await expect(world).toHaveAttribute('title',title);
      await expect(header.locator(':scope > div')).toHaveCount(2);await expect(page.locator('.chat-copy-entry')).toHaveCount(0);
      if(width>=768)await expect(header.getByRole('button',{name:'О мире',exact:true})).toBeVisible();
      const h=(await header.boundingBox())!,t=(await world.boundingBox())!;
      expect(t.x).toBeGreaterThanOrEqual(h.x);
      const groups=await header.locator(':scope > div').evaluateAll(nodes=>nodes.map(el=>el.getBoundingClientRect().toJSON()));
      expect(groups[0].right).toBeLessThanOrEqual(groups[1].left);
      for(const button of await header.locator('button').all()){
        const b=(await button.boundingBox())!;expect(b.x).toBeGreaterThanOrEqual(h.x);expect(b.x+b.width).toBeLessThanOrEqual(h.x+h.width);
        expect(Math.abs(b.y+b.height/2-(t.y+t.height/2))).toBeLessThanOrEqual(1);
        if(width<768)expect(b.height).toBeGreaterThanOrEqual(44);
      }
      const left=(await header.getByRole('button',{name:'RP-чат',exact:true}).boundingBox())!;
      expect(t.x+t.width).toBeLessThanOrEqual(left.x);const action=(await header.locator('.topbar-actions button').first().boundingBox())!;expect(t.x+t.width).toBeLessThanOrEqual(action.x);
      expect(await header.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    }
  }
  if(info.project.name==='desktop'){
    await expect(page.locator('.topbar').getByRole('button',{name:'О мире',exact:true})).toBeVisible();
    await page.getByRole('button',{name:'Режим чтения',exact:true}).click();await expect(page.locator('.nav-rail')).toBeHidden();
    const h=(await page.locator('.topbar').boundingBox())!,t=(await page.locator('.breadcrumb').boundingBox())!;
    expect(t.x).toBeGreaterThanOrEqual(h.x);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.getByRole('button',{name:'Выйти из чтения',exact:true}).click();
  }
  await page.locator('.breadcrumb').click();await expect(page.getByRole('dialog')).toBeVisible();await page.getByRole('dialog').getByRole('button',{name:'Закрыть',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('button',{name:'RP-чат',exact:true}).click();await expect(page.getByRole('button',{name:'Новая RP-кампания',exact:true})).toBeVisible();await page.getByRole('dialog').getByRole('button',{name:'Закрыть',exact:true}).click();await page.getByRole('button',{name:'Вернуться в Narrative',exact:true}).click();await expect(page.locator('.breadcrumb')).toContainText(title);
});
