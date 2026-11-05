import {expect,type Page} from '@playwright/test';
export async function ideaGroup(page:Page,title:string){
 const dialog=page.getByRole('dialog');if(await dialog.isVisible())await dialog.getByRole('button',{name:'Готово',exact:true}).click();
 await page.locator('.atelier-param').filter({hasText:title}).click();
}
export async function closeIdeaGroup(page:Page){const dialog=page.locator('.atelier-dialog');if(await dialog.isVisible())await dialog.getByRole('button',{name:'Готово',exact:true}).click()}
export async function generateIdea(page:Page){
 await closeIdeaGroup(page);
 await page.getByRole('button',{name:'Проверить замысел',exact:true}).click();
 await expect(page.getByRole('region',{name:'Сводка замысла'})).toBeVisible();
 await page.getByRole('button',{name:'Создать мир',exact:true}).click();
}
