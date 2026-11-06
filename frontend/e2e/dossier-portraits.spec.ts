import {test,expect} from '@playwright/test';
import {nav,pickCharacter} from './navigation';
const out='../docs/manual_qa/narrative_v4/issue83-evidence';
test('portrait original and edit surfaces retain circular crop in both skins',async({page,request},info)=>{
 const s=await(await request.post('/test/appearance-seed')).json();await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);
 if(info.project.name==='mobile')await page.setViewportSize({width:360,height:800});
 for(const skin of ['graphite','parchment']){
 await request.put(`/api/worlds/${s.world}/presentation`,{data:{theme_id:skin}});await page.goto('/');await nav(page,'Мир');await nav(page,'Персонажи');await pickCharacter(page,'qa_vera');
 await page.getByRole('button',{name:'Редактировать портрет',exact:true}).click();await expect(page.getByLabel('Файл портрета')).toBeVisible();
 if(skin==='graphite'){
 const png=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=256;c.height=384;const ctx=c.getContext('2d')!;ctx.fillStyle='#75848f';ctx.fillRect(0,0,256,384);ctx.fillStyle='#d2c3a5';ctx.fillRect(80,80,96,150);return c.toDataURL().split(',')[1]});
 await page.getByLabel('Файл портрета').setInputFiles({name:'qa-shared-portrait.png',mimeType:'image/png',buffer:Buffer.from(png,'base64')});
 }
 await page.screenshot({path:`${out}/portrait-editor-${info.project.name}-${skin}.png`,animations:'disabled'});
 await page.getByRole('button',{name:skin==='graphite'?'Сохранить':'Отмена',exact:true}).click();
 const avatar=page.locator('.character-profile .portrait-control .character-avatar');await expect(avatar.locator('img')).toBeVisible();expect(await avatar.evaluate(e=>getComputedStyle(e).borderRadius)).toBe('50%');
 await page.screenshot({path:`${out}/portrait-card-${info.project.name}-${skin}.png`,animations:'disabled'});
 await avatar.click();await expect(page.getByRole('heading',{name:'Портрет в полном размере'})).toBeVisible();await page.screenshot({path:`${out}/portrait-viewer-${info.project.name}-${skin}.png`,animations:'disabled'});
 }
});
