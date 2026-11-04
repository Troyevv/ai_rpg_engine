import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {defaults} from '../src/types';
import {nav} from './navigation';
import {authorView,workshopNav} from './workshop-navigation';

test('V1 turn survives manual edit, AI package, portrait replacement and V2 launch',async({page,request},info)=>{
 test.setTimeout(90000);
 const source=JSON.parse(readFileSync(new URL('../../tests/fixtures/initial_world/workshop188.json',import.meta.url),'utf8'));
 const w=await(await request.post('/test/editor173',{data:{fail:false}})).json();const url=`/api/workspaces/${w.id}/draft`;
 expect((await request.post(url+'/import',{data:{revision:0,format:'json',text:JSON.stringify(source)}})).ok()).toBeTruthy();
 await request.post('/test/editor173/release');
 await page.addInitScript(wid=>localStorage.setItem('draftWorkspace',wid),w.id);await page.goto('/');const profile=await page.evaluate(()=>localStorage.getItem('profile'));expect((await request.put(`/api/settings/${profile}`,{data:{...defaults,summary:{...defaults.summary,model:'handoff-test',context_length:131072,max_tokens:24000},game:{...defaults.game,model:'handoff-test',context_length:131072}}})).ok()).toBeTruthy();await page.reload();await nav(page,'Создать');await authorView(page);
 const openMaxim=async()=>{await workshopNav(page,'Персонажи');await page.getByRole('button',{name:'Досье Максим Ковалёв',exact:true}).click()};
 const portrait=async(color:string)=>{
  await page.getByRole('button',{name:'Редактировать портрет',exact:true}).click();
  const png=await page.evaluate(color=>{const c=document.createElement('canvas');c.width=320;c.height=480;const ctx=c.getContext('2d')!;ctx.fillStyle=color;ctx.fillRect(0,0,320,480);return c.toDataURL('image/png').split(',')[1]},color);
  await page.getByLabel('Файл портрета').setInputFiles({name:'portrait.png',mimeType:'image/png',buffer:Buffer.from(png,'base64')});await page.getByRole('button',{name:'Сохранить',exact:true}).click();await expect(page.getByRole('heading',{name:'Портрет персонажа',exact:true})).toHaveCount(0);
 };
 await openMaxim();await portrait('#41665a');await page.getByRole('button',{name:'Готово',exact:true}).click();
 await page.locator('.ww-topbar .ww-primary').click();await page.getByRole('button',{name:'Подтвердить и открыть игру',exact:true}).click();
 await page.getByRole('button',{name:'Начать игру',exact:true}).click();await expect(page.locator('.choices button')).toHaveCount(1);await page.locator('.choices button').first().click();await expect(page.locator('.turn')).toHaveCount(2);await expect(page.locator('.choices button')).toHaveCount(1);
 const v1=(await(await request.get(url+'?author=true')).json()).games[0];
 const canonical=async(sid:number)=>({...((await(await request.get(`/api/saves/${sid}/author-state`)).json()).snapshot),history:(await(await request.post(`/test/creative172/saves/${sid}/canonical`)).json()).events});
 const old=await canonical(v1.save),oldPortrait=old.world_state.characters.maxim.portraits.at(-1);
 const oldImage=await(await request.get(`/api/saves/${v1.save}/characters/maxim/portraits/assets/${oldPortrait.asset_id}`)).body();
 await nav(page,'Создать');await authorView(page);await openMaxim();
 await page.getByRole('button',{name:'Изменить fields.Внешность',exact:true}).click();await page.locator('.ww-field-dialog').getByLabel('Внешность',{exact:true}).fill('Высокий мужчина со светлыми волосами, серыми глазами, в тёмной рубашке и джинсах.');await page.getByRole('button',{name:'Сохранить поле',exact:true}).click();await expect(page.locator('.ww-field-dialog')).toHaveCount(0);
 await portrait('#c8b890');await page.getByRole('button',{name:'Готово',exact:true}).click();await workshopNav(page,'Изменить с ИИ');
 if(info.project.name==='mobile')await page.setViewportSize({width:360,height:740});
 await page.getByLabel('Что изменить в мире?').fill('WORKSHOP188 пакет');await page.getByRole('button',{name:'Предложить изменения',exact:true}).click();await expect(page.getByRole('heading',{name:'Ожидает решения',exact:true})).toBeVisible();
 await expect(page.locator('.ww-ai-compose')).toContainText('Изменения войдут в новое прохождение');
 await page.locator('.ai-diff-entity > summary').click();expect(await page.locator('.ai-diff-label').first().evaluate(e=>getComputedStyle(e).display)).toBe('block');expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:test.info().outputPath(`post-start-preview-${info.project.name}.png`),scale:'css'});
 await page.getByRole('button',{name:'Применить пакет…',exact:true}).click();await page.getByRole('button',{name:'Подтвердить изменения',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);await expect(page.locator('.ai-preview')).toContainText('Изменения сохранены');
 expect(await canonical(v1.save)).toEqual(old);
 const draft=await(await request.get(url+'?author=true')).json();expect(draft.state.campaign.description).toBe('Новая редакция мира для следующего прохождения.');
 await page.getByRole('button',{name:'Начать игру из этой версии',exact:true}).click();await expect(page.getByRole('button',{name:'Продолжить существующую игру',exact:true})).toBeVisible();await page.getByRole('button',{name:'Подтвердить и открыть игру',exact:true}).click();await expect(page.locator('.world-workshop')).toHaveCount(0);
 const v2=(await(await request.get(url+'?author=true')).json()).games[0];expect(v2.save).not.toBe(v1.save);
 const next=await canonical(v2.save);expect(next.character_cards.find((c:any)=>c.id==='maxim').fields.Внешность).toContain('светлыми волосами');expect(next.world_state.characters.maxim.portraits.at(-1).asset_id).not.toBe(oldPortrait.asset_id);
 expect(await canonical(v1.save)).toEqual(old);expect(await(await request.get(`/api/saves/${v1.save}/characters/maxim/portraits/assets/${oldPortrait.asset_id}`)).body()).toEqual(oldImage);
 expect((await(await request.post(url+'/confirm',{data:{revision:draft.revision,version_id:draft.version_id,accept_warnings:true}})).json()).save).toBe(v2.save);
 await nav(page,'Создать');await page.locator('.ww-topbar .ww-primary').click();await page.getByRole('button',{name:'Продолжить существующую игру',exact:true}).click();await expect(page.locator('.world-workshop')).toHaveCount(0);
 // Reopen the old save through the same app selection persisted by the game.
 await page.evaluate(v1=>localStorage.setItem('selection',JSON.stringify({world:v1.world,save:v1.save})),v1);await page.reload();await expect(page.locator('.turn')).toHaveCount(2);expect(await canonical(v1.save)).toEqual(old);
});
