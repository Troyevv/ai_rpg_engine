import {expect,type Page} from '@playwright/test';
export async function nav(page:Page,name:string){
 const button=page.getByRole('button',{name,exact:true}).last();
 if((page.viewportSize()?.width||1440)<768){await expect(page.getByRole('dialog')).toHaveCount(0);await page.getByRole('button',{name:'Меню игры'}).click()}
 await page.getByRole('button',{name,exact:true}).last().click();
}
export async function actor(page:Page,id:string,name:string){
 const committed=page.waitForResponse(r=>r.url().endsWith('/protagonist')&&r.request().method()==='POST');
 if(await page.getByLabel('Управляемый персонаж').isVisible())await page.getByLabel('Управляемый персонаж').selectOption(id);
 else {await page.locator('.mobile-pov button').first().click();await page.getByRole('dialog').getByRole('button',{name,exact:true}).click()}
 const response=await committed;
 expect(response.ok(),await response.text()).toBe(true);
 const after=await response.json();
 expect(after.state.controlled_actor_id).toBe(id);
 if(await page.getByLabel('Управляемый персонаж').isVisible())await expect(page.getByLabel('Управляемый персонаж')).toHaveValue(id);
 else await expect(page.locator('.mobile-pov button').first()).toHaveText(after.state.characters.find((c:{id:string})=>c.id===id).name.replace(' (ГГ)','')+' ▾');
 await expect(page.getByLabel('Управляемый персонаж').or(page.locator('.mobile-pov button').first())).toBeEnabled();
}
export async function diagnostics(page:Page){
 if(await page.locator('.mobile-story-tools').isVisible() && await page.locator('.mobile-story-tools').getAttribute('open')===null)await page.locator('.mobile-story-tools summary').click();
 await page.getByRole('button',{name:'Диагностика',exact:true}).click();
}
export async function gameAction(page:Page,name:string){
 const menu=page.getByRole('dialog').filter({has:page.getByRole('heading',{name:'Текущая игра',exact:true})});
 if(!await menu.isVisible())await page.locator('.current-game-entry button').click();
 const section=name==='Политика истории'?'Настройки':name==='Сменить главного героя'?'Персонажи':'Время';
 await menu.getByRole('navigation',{name:'Разделы текущей игры'}).getByRole('button',{name:section,exact:true}).click();
 await menu.getByRole('button',{name,exact:true}).click();
}

export async function pickCharacter(page:Page,id:string){
 await page.getByRole('combobox',{name:'Персонаж',exact:true}).click();
 await page.getByLabel('Найти персонажа').fill('');
 await page.locator(`[role="option"][data-character-id="${id}"]`).click();
}
export async function searchCharacter(page:Page,query:string){
 await page.getByRole('combobox',{name:'Персонаж',exact:true}).click();
 await page.getByLabel('Найти персонажа').fill(query);
 await page.getByLabel('Найти персонажа').press('Enter');
}
