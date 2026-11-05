import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {nav} from './navigation';
import {authorView,workshopNav} from './workshop-navigation';

test('W21 W22 empty motives retain distinct editors; searchable people retain tab and focus',async({page,request},info)=>{
 const world=JSON.parse(readFileSync(new URL('../../tests/fixtures/initial_world/workshop188.json',import.meta.url),'utf8'));
 const first=world.characters[0],second=world.characters[1];
 first.fields['Намерения']='';world.world.characters[first.id].intentions=[];
 second.name='Соня Александровна Соколова';
 const w=await(await request.post('/api/workspaces',{data:{name:'Мотивы и переходы'}})).json(),url=`/api/workspaces/${w.id}/draft`;
 expect((await request.post(url+'/import',{data:{revision:0,format:'json',text:JSON.stringify(world)}})).ok()).toBe(true);
 const before=await(await request.get(url+'?author=true')).json();
 await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),w.id);
 await page.goto('/');await nav(page,'Создать');await authorView(page);await workshopNav(page,'Персонажи');
 for(const width of info.project.name==='mobile'?[360,390,430]:[1440]){
  await page.setViewportSize({width,height:width===360?800:width===390?844:width===430?932:1000});
  await page.locator('.ww-character-card').first().click();
  const dossier=page.locator('.ww-dossier-dialog');await dossier.getByRole('tab',{name:'Цели',exact:true}).click();
  const empty=dossier.locator('.ww-empty-motives');
  await expect(empty.locator('summary')).toBeVisible();
  await expect(empty.getByRole('button',{name:'Изменить fields.Намерения',exact:true})).not.toBeVisible();
  await empty.locator('summary').click();
  await empty.getByRole('button',{name:'Изменить fields.Намерения',exact:true}).click();
  await expect(page.locator('.ww-field-dialog').getByLabel('Намерения',{exact:true})).toHaveValue('');
  await page.locator('.ww-field-dialog').getByRole('button',{name:'Закрыть',exact:true}).click();
  await expect(empty.getByRole('button',{name:'Изменить Намерения',exact:true})).toBeVisible();
  await dossier.getByLabel('Найти персонажа в досье').fill('Александровна');
  await dossier.getByLabel('Переключить досье').selectOption(second.id);
  await expect(dossier.locator('.ww-dossier-identity h2')).toHaveText(second.name);
  await expect(dossier.getByRole('tab',{name:'Цели',exact:true})).toHaveAttribute('aria-selected','true');
  await dossier.getByLabel('Найти персонажа в досье').fill('');
  await dossier.getByRole('button',{name:`Досье ${first.name}`,exact:true}).click();
  await expect(dossier.locator('.ww-dossier-identity h2')).toHaveText(first.name);
  await page.keyboard.press('Escape');await expect(page.locator('.ww-character-card').first()).toBeFocused();
 }
 const after=await(await request.get(url+'?author=true')).json();expect(after.state).toEqual(before.state);expect(after.revision).toBe(before.revision);
});
