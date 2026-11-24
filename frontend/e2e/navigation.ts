import {chooseOption} from './choice-navigation';
import {expect,type Locator,type Page} from '@playwright/test';
export async function nav(page:Page,name:string){
 if(await page.locator('.ww-shell').isVisible()){
  if(name==='Создать')return;
  if(name==='Настройки'||name==='Игра'){
   if((page.viewportSize()?.width||1440)<=760)await page.getByRole('button',{name:'Разделы мастерской',exact:true}).click();
   await page.getByRole('button',{name:name==='Настройки'?'Модели и настройки':'Вернуться к игре',exact:true}).click();return;
  }
 }

 const mobile=await page.locator('#root').evaluate(root=>root.clientWidth<=680);
 const reading=name==='Режим чтения'||name==='Выйти из чтения';
 if(mobile){
  await expect(page.getByRole('dialog')).toHaveCount(0);
  if(reading){
   await page.getByLabel('Ещё действия').click();
   await page.getByRole('dialog').getByRole('button',{name,exact:true}).click();
   return;
  }
  await page.getByRole('button',{name:'Меню игры',exact:true}).click();
  const menu=page.getByRole('dialog',{name:'Меню игры'});
  if(name==='Игра'){await menu.locator('.mobile-menu-resume').click();return}
  await menu.getByRole('button',{name:name==='Создать'?'Создать мир':name,exact:true}).click();
  return;
 }
 if(reading){await page.getByRole('button',{name,exact:true}).click();return}
 await page.getByRole('navigation',{name:'Главная навигация'}).getByRole('button',{name,exact:true}).click();
}
export async function actor(page:Page,id:string,name:string){
 const field=page.getByLabel('Управляемый персонаж',{exact:true});
 const committed=page.waitForResponse(r=>r.url().endsWith('/protagonist')&&r.request().method()==='POST');
 await chooseOption(field,id);
 const response=await committed;
 expect(response.ok(),await response.text()).toBe(true);
 expect((await response.json()).state.controlled_actor_id).toBe(id);
 await expect(field).toHaveJSProperty('value',id);
 await expect(field).toContainText(name.replace(' (ГГ)',''));
 await expect(field).toBeEnabled();
}
export async function camera(page:Page){
 if(await page.getByLabel('Ещё действия').isVisible())await page.getByLabel('Ещё действия').click();
 await page.getByRole('button',{name:'Камера · Журнал',exact:true}).click();
}
export async function diagnostics(page:Page){
 if(await page.getByLabel('Ещё действия').isVisible())await page.getByLabel('Ещё действия').click();
 await page.getByRole('button',{name:'Диагностика',exact:true}).click();
}
export async function gameAction(page:Page,name:string){
 const menu=page.getByRole('dialog').filter({has:page.getByRole('heading',{name:'Управление игрой',exact:true})});
 if(!await menu.isVisible())await page.locator('.current-game-entry button').click();
 const section=name==='Политика истории'?'Настройки':name==='Сменить главного героя'?'Персонажи':'Время';
 await menu.getByRole('tablist',{name:'Разделы текущей игры'}).getByRole('tab',{name:section,exact:true}).click();
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

export async function openDeviceApp(phone:Locator, name:string){
 const home=phone.getByRole('button',{name:'Домой',exact:true});
 if(await home.isVisible())await home.click();
 await phone.getByRole('navigation',{name:'Приложения'}).getByRole('button',{name,exact:true}).click();
}
