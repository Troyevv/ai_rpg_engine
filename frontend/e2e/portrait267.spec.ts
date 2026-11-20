import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {nav} from './navigation';
import {chooseOption} from './choice-navigation';
import {authorView,workshopNav} from './workshop-navigation';

test('portrait catalogue, local edits and quoted batch commissions',async({page,request},info)=>{
 test.setTimeout(180000);
 const mobile=info.project.name==='mobile';
 await page.setViewportSize({width:mobile?360:1280,height:mobile?680:850});
 const state=JSON.parse(readFileSync(new URL('../../tests/fixtures/initial_world/runtime_presentation.json',import.meta.url),'utf8'));
 const hair=['bun','undercut','braid','pixie','ponytail','curly','bald','parted'];
 const cuts=['blouse','hoodie','cloak','coveralls','vest','smock','sweater','jacket'];
 state.characters.forEach((card:{id:string;portrait_traits?:unknown},i:number)=>{
   state.world.characters[card.id].developmental_stage=i===2?'child':'adult';
   card.portrait_traits={hair:hair[i],clothing:cuts[i]};
 });
 const w=await(await request.post('/api/workspaces',{data:{name:'Портретная мастерская'}})).json();
 const url='/api/workspaces/'+w.id+'/draft';
 expect((await request.post(url+'/import',{data:{revision:0,format:'json',text:JSON.stringify(state)}})).ok()).toBe(true);
 await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),w.id);
 await page.goto('/');await nav(page,'Создать');await authorView(page);await workshopNav(page,'Персонажи');
 const button=(name:string)=>page.getByRole('button',{name,exact:true});
 const tile=button('Досье Анна');
 if(mobile)await button('Разделы мастерской').click();
 await page.locator(mobile?'.ww-menu-dialog':'.ww-sidebar').getByRole('button',{name:'Оформление',exact:true}).click();
 await chooseOption(page.getByRole('combobox',{name:'Тема мира',exact:true}),mobile?'parchment':'graphite');
 await page.keyboard.press('Escape');await expect(page.getByRole('dialog',{name:'Оформление мастерской'})).toHaveCount(0);
 if(mobile){await page.keyboard.press('Escape');await expect(page.locator('.ww-menu-dialog')).toHaveCount(0)}
 await tile.scrollIntoViewIfNeeded();
 await page.locator('.ww-characters-grid').screenshot({path:info.outputPath('cards.png'),scale:'css'});
 if(!mobile){
   const first=await tile.boundingBox(),last=await page.locator('.ww-character-card').nth(3).boundingBox();
   if(!first||!last)throw new Error('Карточки недоступны');
   await page.screenshot({path:info.outputPath('card-row.jpg'),type:'jpeg',quality:86,scale:'css',
    clip:{x:first.x,y:first.y,width:last.x+last.width-first.x,height:first.height}});
 }
 await tile.click();
 const open=async()=>{await button('Редактировать портрет').click();await button('Настроить иллюстрацию').click()};
 await open();
 const desired=button('Коса');
 await desired.click();await expect(desired).toHaveAttribute('aria-pressed','true');
 await button('Одежда').click();await button('Плащ').click();
 await page.locator('.studio-open').screenshot({path:info.outputPath('studio.png'),scale:'css'});
 const preview=page.locator('.portrait-comparison figure').last().locator('img');
 const expected=await preview.getAttribute('src');
 if(mobile)await page.setViewportSize({width:393,height:500});
 const inViewport=async()=>{const box=await button('Сохранить иллюстрацию').boundingBox();expect(box!.y+box!.height).toBeLessThanOrEqual(page.viewportSize()!.height);expect(await page.locator('.studio-open').evaluate(e=>e.scrollWidth<=e.clientWidth+1)).toBe(true)};
 await inViewport();
 if(mobile)await page.locator('.studio-open').screenshot({path:info.outputPath('studio-393.png'),scale:'css'});
 await page.route('**/portraits/procedural',r=>r.fulfill({status:409,json:{detail:'Проверка ошибки сохранения'}}),{times:1});
 await button('Сохранить иллюстрацию').click();await expect(page.getByRole('alert')).toContainText('Проверка ошибки');
 await expect(preview).toHaveAttribute('src',expected!);
 await button('Сбросить несохранённые изменения').click();await expect(button('Сохранить иллюстрацию')).toBeDisabled();
 await button('Отмена').click();await button('Настроить иллюстрацию').click();
 await button('Создать по описанию').click();await button('Рассчитать расход').click();await expect(button('Подтвердить запрос')).toBeVisible();
 await button('Подтвердить запрос').click();await button('В предпросмотр').click();
 await expect(page.locator('.portrait-comparison')).toContainText('Предложение модели');
 const generated=await preview.getAttribute('src');await button('Сохранить иллюстрацию').click();await expect(page.locator('.portrait-dialog')).toHaveCount(0);
 await open();await expect(preview).toHaveAttribute('src',generated!);await page.keyboard.press('Escape');
 await button('Готово').click();await button('Портреты').click();
 await page.getByRole('checkbox',{name:'Анна',exact:true}).check();await page.getByRole('checkbox',{name:'Борис',exact:true}).check();
 await button('Рассчитать расход').click();await expect(page.locator('.portrait-commission')).toContainText('Запросов: 1');
 await button('Подтвердить запрос').click();await expect(page.locator('.commission-result')).toHaveCount(2);
 await page.locator('.commission-result').last().getByRole('checkbox').check();await button('Применить выбранные · 1').click();
 await expect(page.locator('.portrait-commission')).toHaveCount(0);
 const saved=await(await request.get(url+'?author=true')).json();
 expect(saved.portraits.character_2.procedural_portrait.garment).toBe('blouse');
});

test('same v3 illustration stays legible in phone contacts and family nodes',async({page,request},info)=>{
 const mobile=info.project.name==='mobile';
 await page.setViewportSize({width:mobile?393:1280,height:820});
 for(const surface of ['phone','family']){
  const fixture=surface==='phone'?'/test/phone-seed?incoming=false&polish=true':'/test/ui-completion-seed?checkpoint=ui-family';
  const selected=await(await request.post(fixture)).json();
  const path='/api/saves/'+selected.save+'/characters/qa_timur/portraits';
  const listing=await(await request.get(path)).json();
  const descriptor={...listing.descriptor,version:3,base_version:2,form:'human',body_frame:'male',
   facial_hair:'clean_shaven',hairstyle:'bun',garment:'cloak',visage:'angular',visual_age_mode:'manual',visual_age:'young_adult'};
  const result=await request.put(path+'/procedural',{data:{descriptor,revision:listing.revision,mode:'procedural'}});
  expect(result.ok(),await result.text()).toBeTruthy();
  await page.goto('/');await page.evaluate(selection=>localStorage.setItem('selection',JSON.stringify(selection)),selected);
  await page.reload();
  if(surface==='phone'){
   await page.getByRole('button',{name:/^Телефон/}).click();
   await page.getByRole('region',{name:'Телефон персонажа'}).getByRole('button',{name:'Контакты',exact:true}).click();
  }else{
   await nav(page,'Родословная');
   await chooseOption(page.getByLabel('Семья персонажа'),'qa_timur');
  }
  const row=page.locator(surface==='phone'?'.phone-recipient':'.family-root').filter({hasText:'Тимур'}).first();
  const avatar=row.locator('.character-avatar').first();
  await expect(avatar.locator('img')).toHaveAttribute('src',/^data:image\/svg/);
  await expect(avatar).toHaveCSS('border-radius','50%');
  await row.scrollIntoViewIfNeeded();
  await row.screenshot({path:info.outputPath(surface+'-round.png'),scale:'css'});
 }
});
