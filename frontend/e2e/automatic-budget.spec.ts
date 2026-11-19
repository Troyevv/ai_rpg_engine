import {test, expect} from '@playwright/test';
import {gameAction, nav} from './navigation';

for (const [width, skin] of [[360,'graphite'], [393,'parchment'], [1280,'cyberpunk'], [1920,'parchment']] as const) {
  test(`budget and narrative detail in a dialog · ${width} · ${skin}`, async ({page,request}, info) => {
    test.skip((info.project.name === 'mobile') !== (width < 700));
    await page.setViewportSize({width,height:width < 700 ? 820 : 970});
    await page.emulateMedia({reducedMotion:'reduce'});
    const selection=await (await request.post('/test/protagonist-seed')).json();
    await request.put(`/api/worlds/${selection.world}/presentation`,{data:{theme_id:skin}});
    await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selection);
    await page.goto('/');
    await nav(page,'Настройки');
    const auto=page.getByLabel('Автоматические лимиты game');
    await expect(auto).toBeChecked();
    const budget=auto.locator('xpath=ancestor::section[1]');
    await budget.getByText('Расширенные настройки').click();
    await auto.uncheck();
    await page.getByLabel('Контекст game',{exact:true}).fill('16384');
    if (width < 700) {
      // interactive-widget=resizes-content gives Android keyboards this layout.
      const numeric = page.getByLabel('Контекст game',{exact:true});
      await numeric.focus();
      await page.setViewportSize({width,height:460});
      await numeric.scrollIntoViewIfNeeded();
      const field = await numeric.boundingBox();
      expect(field!.y + field!.height).toBeLessThanOrEqual(460);
      expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      await page.setViewportSize({width,height:820});
    }
    await auto.check();
    const names=Array.from({length:42},(_,i)=>`Локальная модель ${i} с длинным описанием для проверки переноса и выбора в списке`);
    await page.route('**/api/models/list',route=>route.fulfill({json:{models:names,loaded:[]}}));
    await page.getByRole('button',{name:'Обновить список моделей'}).last().click();
    const model=page.getByRole('combobox',{name:'Модель game',exact:true});
    await model.click();
    await page.keyboard.press('End');
    await expect(model.locator('option').last()).toBeFocused();
    const rect=await model.locator('option').last().boundingBox();
    expect(rect).not.toBeNull();
    expect(rect!.x+rect!.width).toBeLessThanOrEqual(width);
    await page.screenshot({path:info.outputPath('long-list.png'),scale:'css',animations:'disabled'});
    await page.keyboard.press('Enter');
    await expect(model).toHaveValue(names.at(-1)!);
    await expect(page.getByLabel('Контекст game',{exact:true})).toBeDisabled();
    await page.getByRole('button',{name:'Сохранить настройки',exact:true}).click();
    await gameAction(page,'Политика истории');
    const detail=page.getByLabel('Подробность повествования',{exact:true});
    await expect(detail).toHaveValue('balanced');
    await detail.click();
    await expect(detail.locator('option:checked')).toBeFocused();
    await page.screenshot({path:info.outputPath('detail-picker.png'),scale:'css',animations:'disabled'});
    await page.keyboard.press('Escape');
    await expect(detail).toBeFocused();
    await detail.selectOption('extended');
    await page.getByRole('button',{name:'Сохранить настройки истории'}).click();
    await page.reload();
    await gameAction(page,'Политика истории');
    await expect(detail).toHaveValue('extended');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  });
}

test('older picker engine restores focus inside the parent dialog after selection and dismissal', async ({page,request})=>{
  await page.addInitScript(()=>{
    const supports=CSS.supports.bind(CSS);
    CSS.supports=(property:string,value?:string)=>property==='appearance'&&value==='base-select' ? false :
      value===undefined ? supports(property) : supports(property,value);
  });
  const selection=await (await request.post('/test/protagonist-seed')).json();
  await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selection);
  await page.goto('/');
  await gameAction(page,'Политика истории');
  const field=page.getByRole('combobox',{name:'Подробность повествования'});
  await field.click();
  await page.getByRole('option',{name:'Подробно',exact:true}).click();
  await expect(field).toHaveText('Подробно');
  await expect(field).toBeFocused();
  await field.press('ArrowDown');
  await expect(page.getByRole('listbox')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('listbox')).toHaveCount(0);
  await expect(field).toBeFocused();
  await field.click();
  await page.mouse.click(2,2);
  await expect(page.getByRole('listbox')).toHaveCount(0);
  await expect(field).toBeVisible();
});
