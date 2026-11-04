import {expect,type Page} from '@playwright/test';
export async function workshopNav(page:Page,name:string){
 const direct=page.locator('.ww-sidebar').getByRole('button').filter({hasText:name});
 if((page.viewportSize()?.width||1440)>760)await direct.click();
 else {await page.getByRole('button',{name:'Разделы мастерской',exact:true}).click();await page.getByRole('dialog').getByRole('button').filter({hasText:name}).click()}
}
export async function authorView(page:Page){
 await page.getByRole('button',{name:'Автор мира',exact:true}).click();
 const confirm=page.getByRole('button',{name:'Показать всё',exact:true});if(await confirm.isVisible())await confirm.click();
 await expect(page.getByRole('button',{name:'Автор мира',exact:true})).toHaveAttribute('aria-pressed','true');
}
export async function draftsMenu(page:Page){
 if((page.viewportSize()?.width||1440)>760)await page.locator('.ww-sidebar .ww-world-switch').click();
 else {await page.getByRole('button',{name:'Разделы мастерской',exact:true}).click();await page.locator('.ww-menu-dialog .ww-world-switch').click()}
}
