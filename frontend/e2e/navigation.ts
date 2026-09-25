import {expect,type Page} from '@playwright/test';
export async function nav(page:Page,name:string){
 const button=page.getByRole('button',{name,exact:true}).last();
 if((page.viewportSize()?.width||1440)<768){await expect(page.getByRole('dialog')).toHaveCount(0);await page.getByRole('button',{name:'Меню игры'}).click()}
 await page.getByRole('button',{name,exact:true}).last().click();
}
export async function actor(page:Page,id:string,name:string){
 if(await page.getByLabel('Управляемый персонаж').isVisible())await page.getByLabel('Управляемый персонаж').selectOption(id);
 else {await page.locator('.mobile-pov button').first().click();await page.getByRole('dialog').getByRole('button',{name,exact:true}).click()}
}
export async function diagnostics(page:Page){
 if(await page.locator('.mobile-story-tools').isVisible() && await page.locator('.mobile-story-tools').getAttribute('open')===null)await page.locator('.mobile-story-tools summary').click();
 await page.getByRole('button',{name:'Диагностика',exact:true}).click();
}
