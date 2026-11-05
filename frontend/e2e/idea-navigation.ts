import {expect,type Page} from '@playwright/test';
export async function ideaGroup(page:Page,title:string){
 await closeIdeaGroup(page);
 await page.locator('.atelier-param').filter({hasText:title}).click();
}
export async function closeIdeaGroup(page:Page){
 const dialog=page.locator('.atelier-dialog[data-state="open"]');
 if(await dialog.isVisible())await dialog.getByRole('button',{name:'Готово',exact:true}).click();
 await expect(page.locator('.atelier-dialog')).toHaveCount(0);
}
export async function generateIdea(page:Page){
 await closeIdeaGroup(page);
 await page.getByRole('button',{name:'Проверить замысел',exact:true}).click();
 await expect(page.getByRole('region',{name:'Сводка замысла'})).toBeVisible();
 await page.getByRole('button',{name:'Создать мир',exact:true}).click();
}

export async function creationMethod(page:Page,name:string){
 await expect(page.locator('.atelier-method, .workshop-paths')).toBeVisible();
 const menu=page.locator('.atelier-method');
 if(await menu.isVisible())await menu.click();
 await page.getByRole('button',{name,exact:true}).click();
}
