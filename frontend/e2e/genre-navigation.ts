import {expect,type Locator,type Page} from '@playwright/test';
/** Exercise the public search and cards, not hidden compatibility form controls. */
export async function chooseGenre(scope:Page|Locator,name:string,role:'primary'|'secondary'='primary'){
 const control=scope.locator('.genre-target button').nth(role==='primary'?0:1);
 await control.click();
 const search=scope.getByLabel('Найти жанр',{exact:true});await search.fill(name);
 const card=scope.getByRole('button',{name:`${role==='primary'?'Основной':'Дополнительный'} жанр: ${name}`,exact:true});
 await expect(card).toHaveAttribute('aria-disabled','false');await card.click();
 await scope.getByRole('button',{name:'Очистить поиск',exact:true}).click();
}
