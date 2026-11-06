import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {nav,pickCharacter} from './navigation';
import {authorView,confirmWorkshopStart,workshopNav} from './workshop-navigation';
import {themes} from '../src/lib/skins';

test('legacy illustration upgrades in preview and retains its full beard in every skin and Runtime',async({page,request},info)=>{
 test.setTimeout(180000);
 const state=JSON.parse(readFileSync(new URL('../../tests/fixtures/initial_world/runtime_presentation.json',import.meta.url),'utf8'));
 const card=state.characters[0],cid=card.id,actor=state.world.characters[cid];
 Object.assign(actor,{biological_sex:'male',birth_date:'1985-01-01',developmental_stage:'adult'});
 delete actor.procedural_portrait;
 const workspace=await(await request.post('/api/workspaces',{data:{name:'Ателье портретов'}})).json();
 const url=`/api/workspaces/${workspace.id}/draft`;
 expect((await request.post(url+'/import',{data:{revision:0,format:'json',text:JSON.stringify(state)}})).ok()).toBeTruthy();
 await page.addInitScript(wid=>localStorage.setItem('draftWorkspace',wid),workspace.id);
 await page.goto('/');await nav(page,'Создать');await authorView(page);await workshopNav(page,'Персонажи');
 const tile=page.getByRole('button',{name:'Досье '+card.name,exact:true});
 await tile.click();
 const editor=async()=>{await page.getByRole('button',{name:'Редактировать портрет',exact:true}).click();await page.getByRole('button',{name:'Настроить иллюстрацию',exact:true}).click()};
 await editor();
 const frame=page.getByLabel('Основа тела'),beard=page.getByLabel('Растительность на лице');
 await expect(frame).toHaveValue('');
 const preview=page.locator('.portrait-comparison figure').last().locator('img');
 const pixels=async()=>preview.evaluate(async(element:HTMLImageElement)=>{
  await element.decode();
  const c=document.createElement('canvas');c.width=160;c.height=200;
  c.getContext('2d')!.drawImage(element,0,0,c.width,c.height);return c.toDataURL();
 });
 const bodies=new Set<string>();
 for(const id of ['female','neutral','male']){await frame.selectOption(id);bodies.add(await pixels())}
 expect(bodies.size).toBe(3);
 const faces=new Set<string>();
 for(const id of ['clean_shaven','stubble','mustache','short_beard','full_beard']){await beard.selectOption(id);faces.add(await pixels())}
 expect(faces.size).toBe(5);
 await page.getByLabel('Визуальный возраст',{exact:true}).selectOption('child');await expect(beard).toHaveCount(0);
 await page.getByLabel('Визуальный возраст',{exact:true}).selectOption('elderly');await expect(beard).toHaveValue('clean_shaven');
 await beard.selectOption('full_beard');await page.getByLabel('Цвет волос',{exact:true}).selectOption('5');
 const saved=await preview.getAttribute('src');
 await page.getByRole('button',{name:'Сохранить иллюстрацию',exact:true}).click();await expect(page.locator('.portrait-dialog')).toHaveCount(0);
 await editor();await expect(frame).toHaveValue('male');await expect(beard).toHaveValue('full_beard');
 await page.keyboard.press('Escape');await expect(page.locator('.portrait-dialog')).toHaveCount(0);
 await page.getByRole('button',{name:'Готово',exact:true}).click();
 const mobile=info.project.name==='mobile';
 for(const theme of themes){
  if(mobile)await page.getByRole('button',{name:'Разделы мастерской',exact:true}).click();
  await page.locator(mobile?'.ww-menu-dialog':'.ww-sidebar').getByRole('button',{name:'Оформление',exact:true}).click();
  await page.getByRole('combobox',{name:'Тема мира',exact:true}).selectOption(theme.id);
  await expect(page.locator('html')).toHaveAttribute('data-theme',theme.id);
  await page.keyboard.press('Escape');await expect(page.getByRole('dialog',{name:'Оформление мастерской'})).toHaveCount(0);
  if(mobile){await page.keyboard.press('Escape');await expect(page.locator('.ww-menu-dialog')).toHaveCount(0)}
  const art=tile.locator('.ww-card-art');await expect(art.locator('img')).toHaveAttribute('src',saved!);
  const box=await art.boundingBox();expect(box!.width/box!.height).toBeCloseTo(.8,2);
 }
 await page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true}).click();await confirmWorkshopStart(page);
 await page.getByRole('button',{name:'Начать игру',exact:true}).click();await expect(page.locator('.choices button')).toHaveCount(6);
 await nav(page,'Персонажи');await pickCharacter(page,cid);
 const avatar=page.locator('.character-profile .portrait-control .character-avatar');
 await expect(avatar.locator('img')).toHaveAttribute('src',saved!);
 expect(await avatar.evaluate(el=>getComputedStyle(el).borderRadius)).toBe('50%');
});
