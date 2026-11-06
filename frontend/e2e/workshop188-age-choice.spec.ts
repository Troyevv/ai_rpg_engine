import {confirmWorkshopStart} from './workshop-navigation';
import {test,expect,type Locator,type Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {nav,pickCharacter} from './navigation';
import {workshopNav,authorView} from './workshop-navigation';

// Pixel oracle from the actual SVG, rendered at the screenshot resolution. This
// catches cover cropping / letterboxing without platform-specific font baselines.
async function fullArt(page:Page,card:Locator){
 const art=card.locator('.ww-card-art'),avatar=art.locator('.character-avatar');
 const geometry=await card.evaluate(el=>{
  const art=el.querySelector('.ww-card-art')!,avatar=art.querySelector('.character-avatar')!;
  const box=(e:Element)=>{const b=e.getBoundingClientRect();return {x:b.x,y:b.y,width:b.width,height:b.height}};
  return {card:box(el),art:box(art),avatar:box(avatar),border:parseFloat(getComputedStyle(el).borderTopWidth),display:getComputedStyle(el).display,fit:getComputedStyle(avatar.querySelector('img')||avatar).objectFit};
 });
 expect(Math.abs(geometry.art.y-geometry.card.y-geometry.border)).toBeLessThan(1);
 expect(geometry.avatar.width).toBeCloseTo(geometry.art.width,0);
 expect(geometry.avatar.height).toBeCloseTo(geometry.art.height,0);
 expect(geometry.avatar.y).toBeCloseTo(geometry.art.y,0);
 expect(geometry.art.width/geometry.art.height).toBeCloseTo(.8,2);
 if(await avatar.locator('img.procedural-portrait').count()){
  const img=avatar.locator('img');await img.evaluate(async e=>{await (e as HTMLImageElement).decode()});
  const src=(await img.getAttribute('src'))!;
  const png=(await art.screenshot({animations:'disabled'})).toString('base64');
  const fraction=await page.evaluate(async({src,png})=>{
   const load=(s:string)=>new Promise<HTMLImageElement>((resolve,reject)=>{const i=new Image();i.onload=()=>resolve(i);i.onerror=reject;i.src=s});
   const actual=await load('data:image/png;base64,'+png),original=await load(src);
   const pixels=(image:HTMLImageElement)=>{const c=document.createElement('canvas');c.width=actual.width;c.height=actual.height;const ctx=c.getContext('2d')!;ctx.drawImage(image,0,0,c.width,c.height);return ctx.getImageData(0,0,c.width,c.height).data};
   const a=pixels(actual),b=pixels(original);let changed=0,total=0;
   // Exclude the role badge and rounded outer card corners, retain the entire head.
   for(let y=6;y<actual.height*.74;y++)for(let x=6;x<actual.width-6;x++){
    const i=(Math.floor(y)*actual.width+x)*4;total++;
    if(Math.max(...[0,1,2].map(k=>Math.abs(a[i+k]-b[i+k])))>35)changed++;
   }
   return changed/total;
  },{src,png});
  expect(fraction,'Visible upper artwork must match the full uncropped SVG').toBeLessThan(.04);
 }
 return geometry;
}

test('manual visual age: Anna, persistence, full artwork and Runtime handoff',async({page,request},info)=>{
 test.setTimeout(120000);
 const state=JSON.parse(readFileSync(new URL('../../tests/fixtures/initial_world/runtime_presentation.json',import.meta.url),'utf8'));
 const cid=state.characters[0].id;state.characters[0].name='Анна Соколова';state.characters[0].fields['Возраст']='24 года';
 state.world.characters[cid].birth_date='2002-01-01';state.world.characters[cid].developmental_stage='adult';delete state.world.characters[cid].procedural_portrait;
 // Mixed copy heights reproduce the old browser button vertical centering gap.
 state.characters[1].fields['Роль']='Очень длинная роль в истории, которая занимает несколько строк и увеличивает высоту соседней карточки.';
 const w=await(await request.post('/api/workspaces',{data:{name:'Визуальный возраст Анны'}})).json();const url=`/api/workspaces/${w.id}/draft`;
 expect((await request.post(url+'/import',{data:{revision:0,format:'json',text:JSON.stringify(state)}})).ok()).toBeTruthy();
 await page.addInitScript(wid=>localStorage.setItem('draftWorkspace',wid),w.id);await page.goto('/');await nav(page,'Создать');await authorView(page);await workshopNav(page,'Персонажи');
 await expect(page.locator('.ww-menu-dialog')).toHaveCount(0);
 const card=page.getByRole('button',{name:'Досье Анна Соколова',exact:true});
 const geometry=[];
 for(const skin of ['graphite','parchment','cyberpunk']){
  await page.evaluate(skin=>document.documentElement.setAttribute('data-theme',skin),skin);
  geometry.push({skin,...await fullArt(page,card)});
 }
 await page.evaluate(()=>document.documentElement.setAttribute('data-theme','graphite'));
 await page.screenshot({path:info.outputPath(`anna-cards-${info.project.name}.png`),animations:'disabled',fullPage:true});
 await page.getByRole('button',{name:'Список',exact:true}).click();await fullArt(page,card);
 await card.click();await page.getByRole('button',{name:'Редактировать портрет',exact:true}).click();
 await page.getByRole('button',{name:'Настроить иллюстрацию',exact:true}).click();
 const selector=page.getByLabel('Визуальный возраст',{exact:true});await expect(selector).toHaveValue('auto');
 await expect(page.locator('.portrait-age-reference')).toContainText('24 года · Молодой взрослый');
 const previews=new Map<string,string>();
 for(const age of ['infant','child','adolescent','young_adult','mature_adult','elderly']){
  await selector.selectOption(age);
  const preview=page.locator('.portrait-comparison figure').last();
  const src=(await preview.locator('img').getAttribute('src'))!;previews.set(age,src);
  await preview.locator('img').evaluate(async e=>{await (e as HTMLImageElement).decode()});
  await preview.screenshot({path:info.outputPath(`age-${age}-${info.project.name}.png`),animations:'disabled'});
 }
 expect(new Set(previews.values()).size).toBe(6);
 await page.locator('.portrait-age-reference').scrollIntoViewIfNeeded();
 await page.locator('.portrait-dialog').screenshot({path:info.outputPath(`anna-age-editor-${info.project.name}.png`),animations:'disabled'});
 await page.getByLabel('Предпочтение',{exact:true}).selectOption('procedural');
 await page.getByRole('button',{name:'Сохранить иллюстрацию',exact:true}).click();
 await expect(page.locator('.portrait-dialog')).toHaveCount(0);
 const elderly=previews.get('elderly')!;
 await expect(page.locator('.ww-dossier-aside>.portrait-control .procedural-portrait')).toHaveAttribute('src',elderly);
 await page.reload();await nav(page,'Создать');await authorView(page);await workshopNav(page,'Персонажи');await card.click();
 await page.getByRole('button',{name:'Редактировать портрет',exact:true}).click();await page.getByRole('button',{name:'Настроить иллюстрацию',exact:true}).click();
 await expect(selector).toHaveValue('elderly');
 await page.getByRole('button',{name:'Вернуть возраст по персонажу',exact:true}).click();await expect(selector).toHaveValue('auto');
 await expect(page.locator('.portrait-comparison figure').last().locator('img')).toHaveAttribute('src',previews.get('young_adult')!);
 await page.getByRole('button',{name:'Сохранить иллюстрацию',exact:true}).click();await expect(page.locator('.portrait-dialog')).toHaveCount(0);
 const persisted=await(await request.get(url+`/characters/${cid}/portraits?author=true`)).json();
 expect(persisted.descriptor.visual_age_mode).toBe('auto');expect(persisted.descriptor.visual_age).toBe('young_adult');
 // Persist a manual minor category on an adult, then start the real Runtime.
 await page.getByRole('button',{name:'Редактировать портрет',exact:true}).click();await page.getByRole('button',{name:'Настроить иллюстрацию',exact:true}).click();
 await selector.selectOption('infant');await page.getByRole('button',{name:'Сохранить иллюстрацию',exact:true}).click();await expect(page.locator('.portrait-dialog')).toHaveCount(0);
 await page.getByRole('button',{name:'Готово',exact:true}).click();
 await page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true}).click();await confirmWorkshopStart(page);
 await page.getByRole('button',{name:'Начать игру',exact:true}).click();await expect(page.locator('.choices button')).toHaveCount(6);
 await nav(page,'Персонажи');await pickCharacter(page,cid);
 await expect(page.locator('.character-profile .portrait-control .procedural-portrait')).toHaveAttribute('src',previews.get('infant')!);
 await page.reload();await nav(page,'Персонажи');await pickCharacter(page,cid);
 await expect(page.locator('.character-profile .portrait-control .procedural-portrait')).toHaveAttribute('src',previews.get('infant')!);
 await info.attach('computed-geometry',{body:JSON.stringify(geometry,null,2),contentType:'application/json'});
});


test('neutral cards use the same gap-free frame in grid and list',async({page,request},info)=>{
 const state=JSON.parse(readFileSync(new URL('../../tests/fixtures/initial_world/runtime_presentation.json',import.meta.url),'utf8'));
 const cid=state.characters[0].id;state.characters[0].name='Анна Соколова';
 state.characters[1].fields['Роль']='Длинная роль соседнего персонажа с дополнительными строками текста для проверки вертикального выравнивания.';
 const w=await(await request.post('/api/workspaces',{data:{name:'Нейтральный портрет'}})).json();const url=`/api/workspaces/${w.id}/draft`;
 expect((await request.post(url+'/import',{data:{revision:0,format:'json',text:JSON.stringify(state)}})).ok()).toBeTruthy();
 const draft=await(await request.get(url+'?author=true')).json();
 expect((await request.put(url+`/characters/${cid}/portraits/procedural`,{data:{revision:draft.revision,mode:'procedural',descriptor:{...draft.portraits[cid].procedural_portrait,form:'neutral'}}})).ok()).toBeTruthy();
 await page.addInitScript(wid=>localStorage.setItem('draftWorkspace',wid),w.id);await page.goto('/');await nav(page,'Создать');await authorView(page);await workshopNav(page,'Персонажи');
 await expect(page.locator('.ww-menu-dialog')).toHaveCount(0);
 const card=page.getByRole('button',{name:'Досье Анна Соколова',exact:true});
 await expect(card.locator('.portrait-initials')).toHaveText('АС');await fullArt(page,card);
 await card.screenshot({path:info.outputPath(`anna-neutral-${info.project.name}.png`),animations:'disabled'});
 await page.getByRole('button',{name:'Список',exact:true}).click();await fullArt(page,card);
});
