import {test,expect} from '@playwright/test';
import {defaults} from '../src/types';

test.afterEach(async({request})=>{await request.post('/test/scene255-reset')});

for (const width of [360,393,1280]) {
  test(`current contract: agency correction and editable suggestions at ${width}px`,async({page,request},info)=>{
    test.skip((width===1280)!==(info.project.name==='desktop'));
    await page.setViewportSize({width,height:width===1280?900:612});
    const selection=await (await request.post('/test/scene263-seed')).json();
    const path=`/api/saves/${selection.save}`, profile=`scene263-${selection.save}`;
    await request.put(`/api/settings/${profile}`,{data:{...defaults,game:{...defaults.game,model:'scene263-test',context_length:65536}}});
    await page.addInitScript(({selection,profile})=>{
      localStorage.setItem('selection',JSON.stringify(selection));
      localStorage.setItem('profile',profile);
    },{selection,profile});
    await page.goto('/');
    const view=async()=>(await request.get(path)).json();
    const before=await view();
    const input=page.getByLabel('Своё действие или реплика');
    const send=page.getByRole('button',{name:'Отправить действие',exact:true});
    await input.fill('Рассматриваю фотографию.');
    await send.click();
    await input.fill('Спрошу о погоде.');
    const correction=page.getByRole('button',{name:'Исправить противоречие в сцене'});
    await expect(correction).toBeEnabled();
    expect((await view()).revision).toBe(before.revision);
    await expect(send).toBeDisabled();
    await expect(page.getByText('Чужой секрет')).toHaveCount(0);
    await page.reload();
    await expect(input).toHaveValue('Спрошу о погоде.');
    await correction.click();
    await expect.poll(async()=>(await view()).revision).toBe(before.revision+1);
    const choice=page.locator('.choices button').filter({hasText:'Налить воды'});
    await expect(choice).toBeEnabled();
    await expect(page.locator('.turn').last().locator('strong').filter({hasText:'В альбоме'})).toBeVisible();
    await expect(page.locator('.turn').last().locator('hr')).toHaveCount(1);
    await expect(page.getByText('Чужой секрет')).toHaveCount(0);
    await choice.click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(input).toHaveValue('Спрошу о погоде.');
    await choice.click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.goBack();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await choice.click();
    await page.getByRole('button',{name:'Добавить к черновику'}).click();
    await expect(input).toHaveValue('Спрошу о погоде.\nНалить воды');
    await expect(input).toBeFocused();
    await choice.click();
    await page.getByRole('button',{name:'Заменить черновик'}).click();
    await expect(input).toHaveValue('Налить воды');
    if(width<400) await page.setViewportSize({width,height:430});
    await expect(input).toBeInViewport();
    await page.reload();
    await expect(input).toHaveValue('Налить воды');
    expect((await view()).revision).toBe(before.revision+1);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  });
}
