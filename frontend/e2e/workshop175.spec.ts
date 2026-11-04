import {test,expect} from '@playwright/test';
import {nav} from './navigation';
import {workshopNav,authorView} from './workshop-navigation';

test('workshop: 240 characters, long text, dossier, portraits and scoped search',async({page,request},info)=>{
 const seed=await(await request.post('/test/seed')).json();const world=await(await request.get(`/api/worlds/${seed.world}`)).json();
 const workspace=await(await request.post('/api/workspaces',{data:{name:'Большой мир'}})).json();const url=`/api/workspaces/${workspace.id}/draft`;
 expect((await request.post(url+'/import',{data:{revision:0,text:world.source_md}})).ok()).toBeTruthy();
 let draft=await(await request.get(url+'?author=true')).json();const state=draft.state;
 state.campaign.title='Истории у моря';state.campaign.description='Портовый город, старые друзья и новая жизнь. '+ 'За окнами шумит дождь. '.repeat(100);
 const sample=state.characters[0],actor=state.world.characters[sample.id];
 for(let i=state.characters.length;i<240;i++){const id=`crowd_${i}`;state.characters.push({...sample,id,name:`Житель ${i}`,is_player:false});state.world.characters[id]={...actor,id,developmental_stage:'adult'}}
 for(const actor of Object.values(state.world.characters) as {developmental_stage:string}[])actor.developmental_stage='adult';
 expect((await request.post(url+'/import',{data:{revision:draft.revision,format:'json',text:JSON.stringify(state)}})).ok()).toBeTruthy();
 await page.goto('/');await page.evaluate(wid=>localStorage.setItem('draftWorkspace',wid),workspace.id);await page.reload();await nav(page,'Создать');
 await expect(page.locator('.ww-hero h1')).toHaveText('Истории у моря');await authorView(page);await page.evaluate(()=>document.fonts.ready);await page.screenshot({path:`/tmp/workshop175-overview-${info.project.name}.png`});
 await workshopNav(page,'Персонажи');await expect(page.locator('.ww-character-card')).toHaveCount(12);
 await page.screenshot({path:`/tmp/workshop175-${info.project.name}.png`});
 for(const skin of ['parchment','cyberpunk','medieval','noir','graphite']){
  if((page.viewportSize()?.width||1440)<=760)await page.getByRole('button',{name:'Разделы мастерской',exact:true}).click();
  await page.getByRole('button',{name:'Оформление',exact:true}).click();
  await page.getByRole('combobox',{name:'Тема мира',exact:true}).selectOption(skin);await expect(page.locator('html')).toHaveAttribute('data-theme',skin);
  await page.getByRole('dialog').last().getByRole('button',{name:'Закрыть',exact:true}).click();
  if((page.viewportSize()?.width||1440)<=760)await page.getByRole('dialog').getByRole('button',{name:'Закрыть',exact:true}).click();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(await page.evaluate(()=>innerWidth));
 }
 await page.getByLabel('Поиск персонажей').fill('Житель 239');await expect(page.locator('.ww-character-card')).toHaveCount(1);
 await page.locator('.ww-character-card').click();await expect(page.getByRole('dialog',{name:'Досье персонажа'})).toBeVisible();
 await expect(page.locator('.ww-dossier-aside>.portrait-control .procedural-portrait')).toHaveCount(1);
 await page.screenshot({path:`/tmp/workshop175-dossier-clean-${info.project.name}.png`});
 await page.getByRole('button',{name:'Изменить fields.Внешность',exact:true}).click();
 await page.getByRole('dialog').last().getByLabel('Внешность',{exact:true}).fill('Длинное описание. '.repeat(1000));
 await page.locator('.ww-field-dialog').getByRole('button',{name:'Закрыть',exact:true}).click();
 await page.getByRole('button',{name:'Изменить fields.Внешность',exact:true}).click();
 await expect(page.locator('.ww-field-dialog').getByLabel('Внешность',{exact:true})).toHaveValue('Длинное описание. '.repeat(1000));
 await page.getByRole('button',{name:'Сохранить поле',exact:true}).click();
 await expect.poll(async()=>(await(await request.get(url+'?author=true')).json()).state.characters.find((c:{id:string})=>c.id==='crowd_239').fields.Внешность).toBe('Длинное описание. '.repeat(1000));
 await expect(page.getByRole('button',{name:'Изменить fields.Внешность',exact:true})).toBeEnabled();
 await expect(page.locator('.ww-dossier-fields')).toContainText('Длинное описание.');
 await page.screenshot({path:`/tmp/workshop175-dossier-${info.project.name}.png`});
 await page.getByRole('button',{name:'Готово',exact:true}).click();
 await expect(page.getByLabel('Поиск персонажей')).toHaveValue('Житель 239');
 await workshopNav(page,'Обзор мира');await workshopNav(page,'Персонажи');await expect(page.getByLabel('Поиск персонажей')).toHaveValue('Житель 239');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(await page.evaluate(()=>innerWidth));
});

test('workshop portrait illustration and uploaded original survive Start Game',async({page,request})=>{
 const {readFileSync}=await import('node:fs');
 const {pickCharacter}=await import('./navigation');
 const state=JSON.parse(readFileSync(new URL('../../tests/fixtures/initial_world/runtime_presentation.json',import.meta.url),'utf8'));
 const workspace=await(await request.post('/api/workspaces',{data:{name:'Портреты в истории'}})).json();const url=`/api/workspaces/${workspace.id}/draft`;
 expect((await request.post(url+'/import',{data:{revision:0,format:'json',text:JSON.stringify(state)}})).ok()).toBeTruthy();
 await page.goto('/');await page.evaluate(wid=>localStorage.setItem('draftWorkspace',wid),workspace.id);await page.reload();await nav(page,'Создать');await authorView(page);await workshopNav(page,'Персонажи');
 await page.locator('.ww-character-card').first().click();await page.getByRole('button',{name:'Редактировать портрет',exact:true}).click();
 await page.getByText('Настроить иллюстрацию',{exact:true}).click();
 await page.getByLabel('Вид изображения',{exact:true}).selectOption('human');await page.getByLabel('Волосы',{exact:true}).selectOption('3');
 await page.getByLabel('Предпочтение',{exact:true}).selectOption('procedural');
 let release!:()=>void,received!:()=>void;const gate=new Promise<void>(r=>release=r),refreshStarted=new Promise<void>(r=>received=r);
 await page.route(`**/api/workspaces/${workspace.id}/draft?author=true`,async route=>{const response=await route.fetch();received();await gate;await route.fulfill({response})},{times:1});
 await page.getByRole('button',{name:'Сохранить иллюстрацию',exact:true}).click();await refreshStarted;
 await expect(page.getByRole('heading',{name:'Портрет персонажа',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Сохранить иллюстрацию',exact:true})).toBeDisabled();release();
 await expect(page.getByRole('heading',{name:'Портрет персонажа',exact:true})).toHaveCount(0);
 const svg=await page.locator('.ww-dossier-aside>.portrait-control .procedural-portrait').getAttribute('src');expect(svg).toMatch(/^data:image\/svg/);
 const second=state.characters[1].id;await page.getByLabel('Переключить досье').selectOption(second);await page.getByRole('button',{name:'Редактировать портрет',exact:true}).click();
 const png=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=320;c.height=480;const ctx=c.getContext('2d')!;ctx.fillStyle='#41665a';ctx.fillRect(0,0,320,480);ctx.fillStyle='#c8b890';ctx.fillRect(80,60,160,200);return c.toDataURL('image/png').split(',')[1]});
 await page.getByLabel('Файл портрета').setInputFiles({name:'portrait.png',mimeType:'image/png',buffer:Buffer.from(png,'base64')});
 await page.getByLabel('Масштаб кадрирования').fill('1.5');await page.getByRole('button',{name:'Сохранить',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Портрет персонажа',exact:true})).toHaveCount(0);
 await expect(page.locator('.ww-dossier-aside>.portrait-control img')).toHaveAttribute('src',/\/assets\//);
 await page.getByRole('button',{name:'Готово',exact:true}).click();
 await page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true}).click();await page.getByRole('button',{name:'Подтвердить и открыть игру',exact:true}).click();
 await page.getByRole('button',{name:'Начать игру',exact:true}).click();await expect(page.locator('.choices button')).toHaveCount(6);
 await nav(page,'Персонажи');await pickCharacter(page,state.characters[0].id);
 await expect(page.locator('.character-profile .portrait-control .procedural-portrait')).toHaveAttribute('src',svg!);
 await pickCharacter(page,second);await expect(page.locator('.character-profile .portrait-control img')).toHaveAttribute('src',/\/api\/saves\/.*\/assets\//);
 await page.reload();await nav(page,'Персонажи');await pickCharacter(page,second);await expect(page.locator('.character-profile .portrait-control img')).toBeVisible();
 await nav(page,'Игра');
 await expect(page.getByRole('dialog')).toHaveCount(0);
 await expect(page.locator('.game-preserved')).not.toHaveAttribute('inert','');
 for(const [index,action] of ['Осматриваюсь.','Продолжаю разговор.'].entries()){
  await page.getByLabel('Своё действие или реплика').fill(action);
  await page.getByRole('button',{name:'Отправить действие',exact:true}).click();
  await expect(page.locator('.turn')).toHaveCount(index+2);
  await expect(page.locator('.choices button')).toHaveCount(6);
  await page.reload();await expect(page.locator('.turn')).toHaveCount(index+2);
 }
 await nav(page,'Персонажи');await pickCharacter(page,state.characters[0].id);
 await expect(page.locator('.character-profile .portrait-control .procedural-portrait')).toHaveAttribute('src',svg!);
 await pickCharacter(page,second);await expect(page.locator('.character-profile .portrait-control img')).toHaveAttribute('src',/\/api\/saves\/.*\/assets\//);
});

test('workshop accessibility: keyboard, narrow height, all skin presets and scaled text',async({page,request},info)=>{
 test.setTimeout(90000);
 const {readFileSync}=await import('node:fs');const {themes}=await import('../src/lib/skins');
 const state=JSON.parse(readFileSync(new URL('../../tests/fixtures/initial_world/runtime_presentation.json',import.meta.url),'utf8'));
 const workspace=await(await request.post('/api/workspaces',{data:{name:'Доступность мастерской'}})).json();
 expect((await request.post(`/api/workspaces/${workspace.id}/draft/import`,{data:{revision:0,format:'json',text:JSON.stringify(state)}})).ok()).toBeTruthy();
 await page.addInitScript(wid=>localStorage.setItem('draftWorkspace',wid),workspace.id);await page.goto('/');await nav(page,'Создать');await authorView(page);
 await page.emulateMedia({reducedMotion:'reduce'});
 if(info.project.name==='mobile')await page.getByRole('button',{name:'Разделы мастерской',exact:true}).click();
 await page.getByRole('button',{name:'Оформление',exact:true}).click();
 for(const skin of themes){await page.getByRole('combobox',{name:'Тема мира',exact:true}).selectOption(skin.id);await expect(page.locator('html')).toHaveAttribute('data-theme',skin.id)}
 await page.getByRole('combobox',{name:'Тема мира',exact:true}).selectOption('graphite');
 await page.keyboard.press('Escape');if(info.project.name==='mobile')await page.keyboard.press('Escape');
 await workshopNav(page,'Персонажи');
 const card=page.locator('.ww-character-card').first();await card.focus();await page.keyboard.press('Enter');await expect(page.getByRole('dialog',{name:'Досье персонажа'})).toBeVisible();
 await page.keyboard.press('Escape');await expect(card).toBeFocused();
 const widths=info.project.name==='desktop'?[768,1280,1440,1920]:[360,390,430];
 for(const width of widths){await page.setViewportSize({width,height:600});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await card.click();await expect(page.getByRole('button',{name:'Готово',exact:true})).toBeInViewport();await page.keyboard.press('Escape')}
 // Scale text independently of viewport geometry (a reproducible 200% text-zoom stress case).
 await page.evaluate(()=>{const nodes=[...document.querySelectorAll<HTMLElement>('.ww-shell *')].filter(e=>!['SVG','PATH'].includes(e.tagName));const sizes=nodes.map(e=>parseFloat(getComputedStyle(e).fontSize));nodes.forEach((e,i)=>e.style.fontSize=sizes[i]*2+'px')});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:`/tmp/workshop175-text200-${info.project.name}.png`});
});
