import {test,expect,type Page,type APIRequestContext} from '@playwright/test';
import {nav,actor,pickCharacter} from './navigation';
const evidence=process.env.PORTRAIT_EVIDENCE||'../docs/manual_qa/narrative_v4/pr121-polish-evidence';
const phase=process.env.PR121_BEFORE?'before':'after';
test.use({video:'on'});
async function seed(page:Page,request:APIRequestContext,hidden=false){
 const r=await request.post(`/test/phone-seed?incoming=false&polish=true&hidden=${hidden}`);expect(r.ok(),await r.text()).toBeTruthy();const s=await r.json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);return s;
}
async function dossier(page:Page){await nav(page,'Мир');await nav(page,'Персонажи');return page.locator('.inspector-workspace')}
async function upload(page:Page,request:APIRequestContext,s:any){
 for(const [i,cid] of ['qa_kirill','qa_vera','qa_timur'].entries()){
  const data=await page.evaluate(i=>{const c=document.createElement('canvas');c.width=300;c.height=400;const x=c.getContext('2d')!;x.fillStyle=['#3478aa','#b64e76','#548756'][i];x.fillRect(0,0,300,400);x.fillStyle='#f8e0c5';x.beginPath();x.arc(150,140,70,0,Math.PI*2);x.fill();x.fillStyle='#233042';x.fillRect(60,220,180,180);x.fillStyle='white';x.font='48px sans-serif';x.fillText(['К','В','Т'][i],132,315);return c.toDataURL('image/png').split(',')[1]},i);
  const save=await(await request.get(`/api/saves/${s.save}`)).json();
  const r=await request.post(`/api/saves/${s.save}/characters/${cid}/portraits?revision=${save.revision}`,{data:Buffer.from(data,'base64'),headers:{'Content-Type':'image/png'}});expect(r.ok(),await r.text()).toBeTruthy();
 }
}
for(const width of [360,393,768,1440])test(`polish visual matrix ${width}`,async({page,request},info)=>{
 test.skip(info.project.name!=='desktop');test.setTimeout(180000);await page.setViewportSize({width,height:1000});
 const s=await seed(page,request);
 for(const skin of ['graphite','parchment']){
  await request.put(`/api/worlds/${s.world}/presentation`,{data:{theme_id:skin}});await page.goto('/');const d=await dossier(page);
  await page.emulateMedia({reducedMotion:'reduce'});
  if(width>=768&&await d.getByRole('button',{name:'Компактная панель'}).count())await d.getByRole('button',{name:'Компактная панель'}).click();
  if(phase==='after')await expect(d.locator('.portrait-control>.character-avatar')).toHaveCSS('width',width<768?'104px':'120px');
  await page.screenshot({path:`${evidence}/${phase}-${width}-${skin}-compact.png`});
  if(width>=768&&await d.getByRole('button',{name:'Расширить панель',exact:true}).isVisible())await d.getByRole('button',{name:'Расширить панель',exact:true}).click();
  if(phase==='after'){
   await expect(d.locator('.portrait-control>.character-avatar')).toHaveCSS('width',width<768?'104px':'144px');
   const pencil=d.locator('.portrait-pencil');await expect(pencil).toHaveCSS('width','44px');await expect(pencil.locator('svg')).toHaveAttribute('width','16');
   expect(await d.locator('.dossier-tabs svg').evaluateAll(els=>new Set(els.map(e=>getComputedStyle(e).color)).size)).toBe(5);
   expect(await d.evaluate(e=>e.scrollWidth<=e.clientWidth+1)).toBe(true);
   const columns=d.locator('.dossier-column');for(const col of await columns.all()){
    const boxes=await col.locator(':scope > section').evaluateAll(es=>es.map(e=>e.getBoundingClientRect().toJSON()));
    for(let i=1;i<boxes.length;i++)expect(boxes[i].top-boxes[i-1].bottom).toBeCloseTo(12,0);
   }
  }
  await page.screenshot({path:`${evidence}/${phase}-${width}-${skin}-overview.png`});
  await pickCharacter(page,'qa_vera');
  await page.screenshot({path:`${evidence}/${phase}-${width}-${skin}-female.png`});
  await page.keyboard.press('Escape');
 }
 await upload(page,request,s);
 for(const skin of ['graphite','parchment']){
 await request.put(`/api/worlds/${s.world}/presentation`,{data:{theme_id:skin}});await page.reload();const d=await dossier(page);await pickCharacter(page,'qa_kirill');await d.getByRole('tab',{name:'Обзор',exact:true}).click();
 await expect.poll(()=>d.locator('.portrait-control img').evaluate((e:HTMLImageElement)=>e.complete&&e.naturalWidth>0)).toBe(true);
 await page.screenshot({path:`${evidence}/${phase}-${width}-${skin}-uploaded.png`});await page.keyboard.press('Escape');
 await page.getByRole('button',{name:/^Телефон/}).click();const phone=page.getByRole('region',{name:'Телефон персонажа'});
 await phone.getByRole('button',{name:'Переписки',exact:true}).click();await phone.getByRole('button').filter({hasText:'Вера Ларина'}).click();
 await expect(phone.locator('.phone-message')).toHaveCount(2);
 if(phase==='after'){
  await expect(phone.locator('.phone-message.outgoing img')).toHaveAttribute('src',new RegExp(`/qa_kirill/`));
  await expect(phone.locator('.phone-message:not(.outgoing) img')).toHaveAttribute('src',new RegExp(`/qa_vera/`));
 }
 await expect(phone).not.toContainText('Непрочитанное сообщение');
 await phone.locator('.phone-messages').evaluate(e=>e.scrollTop=0);
 await expect.poll(()=>phone.locator('.phone-message img').evaluateAll(es=>es.every(e=>(e as HTMLImageElement).complete&&(e as HTMLImageElement).naturalWidth>0))).toBe(true);
 await page.screenshot({path:`${evidence}/${phase}-${width}-${skin}-phone-direct.png`});
 await phone.getByRole('button',{name:'К перепискам',exact:true}).click();await phone.getByRole('button').filter({hasText:'Общая переписка'}).click();
 await expect(phone.locator('.phone-message')).toHaveCount(3);
 if(phase==='after')for(const [i,cid] of ['qa_kirill','qa_vera','qa_timur'].entries())await expect(phone.locator('.phone-message').nth(i).locator('img')).toHaveAttribute('src',new RegExp(`/${cid}/`));
 await phone.locator('.phone-messages').evaluate(e=>e.scrollTop=0);
 await expect.poll(()=>phone.locator('.phone-message img').evaluateAll(es=>es.every(e=>(e as HTMLImageElement).complete&&(e as HTMLImageElement).naturalWidth>0))).toBe(true);
 await page.screenshot({path:`${evidence}/${phase}-${width}-${skin}-phone-group.png`});
 if(phase==='after'&&[393,1440].includes(width))for(let i=0;i<3;i++){await phone.locator('.phone-message').nth(i).evaluate(el=>el.scrollIntoView({block:'start'}));await page.screenshot({path:`${evidence}/${phase}-${width}-${skin}-group-author-${i}.png`})}
 await page.keyboard.press('Escape');
 }
});

test('portrait viewer, editor, error recovery, semantic tabs and resize drafts',async({page,request},info)=>{
 test.skip(phase==='before');test.setTimeout(120000);const s=await seed(page,request);await page.goto('/');await upload(page,request,s);await page.reload();
 const d=await dossier(page);const main=d.locator('.portrait-control>.character-avatar');
 await main.click();await expect(page.getByRole('heading',{name:'Портрет в полном размере'})).toBeVisible();await page.keyboard.press('Escape');
 await d.getByRole('button',{name:'Редактировать портрет',exact:true}).click();const editor=page.getByRole('dialog').filter({has:page.getByRole('heading',{name:'Портрет персонажа',exact:true})});
 await expect(editor).toBeVisible();await expect(page.getByRole('heading',{name:'Портрет в полном размере'})).toHaveCount(0);
 const crop=editor.getByLabel('Масштаб кадрирования',{exact:true});await crop.fill('1.6');await editor.getByRole('button',{name:'Сохранить',exact:true}).click();await expect(editor).toBeHidden();
 await expect(main.locator('img')).toHaveCSS('width',/px/);const state=await(await request.get(`/api/saves/${s.save}`)).json();expect(state.state.characters.find((c:any)=>c.id==='qa_kirill').portrait.crop.zoom).toBe(1.6);
 const colors=await d.locator('.dossier-tabs svg').evaluateAll(es=>es.map(e=>getComputedStyle(e).color));
 for(const [i,tab] of (await d.getByRole('tab').all()).entries()){
  await tab.click();await tab.hover();await tab.focus();expect(await tab.locator('svg').evaluate(e=>getComputedStyle(e).color)).toBe(colors[i]);
 }
 await d.getByRole('tab',{name:'Обзор',exact:true}).click();
 const bio=d.locator('.dossier-card').filter({has:page.getByRole('heading',{name:'Биография',exact:true})});await bio.locator('summary').click();await expect(bio).toContainText('историю своей семьи');
 await page.screenshot({path:`${evidence}/after-${info.project.name}-biography.png`});
 await d.getByRole('tab',{name:'Личность',exact:true}).click();
 await d.getByRole('button',{name:'+ Добавить цель',exact:true}).click();
 const input=page.getByLabel('Текст цели или намерения');await input.fill('Длинный черновик цели — сохранить после изменения ширины.');await page.setViewportSize({width:393,height:900});await expect(input).toHaveValue('Длинный черновик цели — сохранить после изменения ширины.');await expect(input).toBeFocused();await page.keyboard.press('Escape');
 await page.keyboard.press('Escape');
 // A failed image URL must not poison a different character or a subsequent upload.
 await page.route('**/qa_kirill/portraits/assets/*',r=>r.fulfill({status:404,body:''}));await page.reload();const again=await dossier(page);await again.getByRole('tab',{name:'Обзор',exact:true}).click();await expect(again.locator('.portrait-control .avatar-fallback')).toBeVisible();
 await pickCharacter(page,'qa_vera');await expect(again.locator('.portrait-control img')).toBeVisible();
 await page.unroute('**/qa_kirill/portraits/assets/*');await pickCharacter(page,'qa_kirill');await expect(again.locator('.portrait-control img')).toBeVisible();
 await page.evaluate(()=>document.documentElement.style.fontSize='24px');expect(await again.evaluate(e=>e.scrollWidth<=e.clientWidth+1)).toBe(true);
 await page.screenshot({path:`${evidence}/after-${info.project.name}-large-text.png`});
 await page.keyboard.press('Escape');await page.getByRole('button',{name:/^Телефон/}).click();const phone=page.getByRole('region',{name:'Телефон персонажа'});await phone.getByRole('button',{name:'Переписки',exact:true}).click();await phone.locator('button.phone-row').filter({hasText:'Вера Ларина'}).click();await expect(phone.locator('.phone-message.outgoing img')).toHaveAttribute('src',/qa_kirill/);
});

test('temporary phone owner and real outgoing API use its portrait',async({page,request},info)=>{
 test.skip(phase==='before');const s=await seed(page,request);await page.goto('/');await upload(page,request,s);
 let save=await(await request.get(`/api/saves/${s.save}`)).json();
 const switched=await request.post(`/api/saves/${s.save}/protagonist`,{data:{revision:save.revision,operation_id:'polish-temporary',operation:'temporary',actor_id:'qa_vera'}});expect(switched.ok(),await switched.text()).toBeTruthy();save=await switched.json();
 const sent=await request.post(`/api/saves/${s.save}/phone`,{data:{revision:save.revision,command:{action:'send',operation_id:'polish-owner-send',contact_id:'phone-qa_vera-qa-kirill',content:'Я временный владелец телефона.'}}});expect(sent.ok(),await sent.text()).toBeTruthy();
 const data=await sent.json();const row=data.state.phone.events.at(-1);expect(row.sender.id).toBe('qa_vera');expect(row.subject.id).toBe('qa_kirill');
 // Commit read on the real server, but hold its response and the subsequent
 // projection independently. This reproduces the CI 409 without timing sleeps.
 let releaseRead!:()=>void, readArrived!:()=>void, releaseView!:()=>void, viewArrived!:()=>void;
 const readGate=new Promise<void>(r=>releaseRead=r), readReady=new Promise<void>(r=>readArrived=r);
 const viewGate=new Promise<void>(r=>releaseView=r), viewReady=new Promise<void>(r=>viewArrived=r);
 let readRevision=Infinity;
 await page.route(`**/api/saves/${s.save}/phone`,async route=>{
  if(route.request().postDataJSON()?.command?.action!=='read'){await route.continue();return;}
  const response=await route.fetch();expect(response.ok()).toBeTruthy();readRevision=(await response.json()).revision;readArrived();await readGate;await route.fulfill({response});
 });
 await page.route(`**/api/saves/${s.save}`,async route=>{
  const response=await route.fetch();const value=await response.json();
  if(value.revision>=readRevision){viewArrived();await viewGate;}
  await route.fulfill({response});
 });
 await page.reload();await page.getByRole('button',{name:/^Телефон/}).click();const phone=page.getByRole('region',{name:'Телефон персонажа'});await phone.getByRole('button',{name:'Переписки',exact:true}).click();await phone.locator('button.phone-row').filter({hasText:'Кирилл Ларин'}).click();
 const message=phone.locator('.phone-message').filter({hasText:'Я временный владелец телефона.'});await expect(message).toContainText('Ты');await expect(message.locator('img')).toHaveAttribute('src',/\/qa_vera\//);
 await expect.poll(()=>message.locator('img').evaluate((e:HTMLImageElement)=>e.complete&&e.naturalWidth>0)).toBe(true);
 await page.screenshot({path:`${evidence}/after-${info.project.name}-temporary-owner.png`});
 await readReady;
 try {
  await page.keyboard.press('Escape');
  const control=info.project.name==='mobile'?page.locator('.mobile-pov button').first():page.getByLabel('Управляемый персонаж',{exact:true});
  await expect(control).toBeDisabled();
  await expect(page.getByRole('button',{name:'Мир без ГГ',exact:true})).toBeDisabled();
  releaseRead();await viewReady;
  await expect(control).toBeDisabled();
  await expect(page.getByRole('button',{name:'Мир без ГГ',exact:true})).toBeDisabled();
 } finally {releaseRead();releaseView();}
 await page.unrouteAll({behavior:'wait'});
 await expect(page.getByRole('button',{name:'Мир без ГГ',exact:true})).toBeEnabled();
 for(const [id,name] of [['qa_timur','Тимур Серов'],['qa_kirill','Кирилл Ларин (ГГ)']]) await actor(page,id,name);
 await page.getByRole('button',{name:/^Телефон/}).click();await phone.getByRole('button',{name:'Переписки',exact:true}).click();await phone.locator('button.phone-row').filter({hasText:'Вера Ларина'}).click();await expect(phone.locator('.phone-message.outgoing img').first()).toHaveAttribute('src',/qa_kirill/);
});

test('fallback geometry, neutral identity and long text at each size',async({page,request},info)=>{
 test.skip(phase==='before');test.setTimeout(90000);await seed(page,request);await page.goto('/');const d=await dossier(page);
 for(const [cid,sex] of [['qa_kirill','male'],['qa_vera','female'],['qa_oleg','neutral']]){
  await pickCharacter(page,cid);
  const avatar=d.locator('.portrait-control>.character-avatar');await expect(avatar).toHaveClass(new RegExp('avatar-'+sex));await expect(avatar.locator('svg')).toHaveAttribute('data-silhouette',sex);
  for(const size of [36,40,48,104,120,144]){
   // Exercise the actual shared component's responsive typography, not an SVG mock.
   await avatar.evaluate((el,n)=>el.style.setProperty('--avatar-size',`${n}px`),size);
   await expect(avatar).toHaveCSS('width',`${size}px`);await expect(avatar).toHaveCSS('height',`${size}px`);
   const bounds=await avatar.evaluate(el=>{const a=el.getBoundingClientRect(),b=el.querySelector('.portrait-initials')!.getBoundingClientRect();return {inside:b.left>=a.left&&b.right<=a.right&&b.top>=a.top&&b.bottom<=a.bottom,font:parseFloat(getComputedStyle(el.querySelector('.portrait-initials')!).fontSize)}});expect(bounds.inside).toBe(true);expect(bounds.font).toBeGreaterThanOrEqual(9);
   await avatar.screenshot({path:`${evidence}/fallback-${info.project.name}-${sex}-${size}.png`});
  }
  await avatar.evaluate(el=>el.style.setProperty('--avatar-size','var(--dossier-portrait-size,120px)'));
 }
 await page.screenshot({path:`${evidence}/after-${info.project.name}-neutral.png`});
 // Stress the text containers after rendering authorized content; no identity inference.
 await d.locator('.dossier-name h2').evaluate(el=>el.textContent='Александра Константиновна Ларина-Воскресенская');
 await d.locator('.character-lead').evaluate(el=>el.textContent='Проверяет подробное описание текущего состояния персонажа с длинными русскими словами.');
 for(const width of [360,393,768,1440]){await page.setViewportSize({width,height:900});expect(await d.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);await page.screenshot({path:`${evidence}/after-${info.project.name}-long-text-${width}.png`})}
});

test('hidden canonical sender stays anonymous despite public directory and uploaded portrait',async({page,request},info)=>{
 test.skip(phase==='before');const s=await seed(page,request,true);await page.goto('/');await upload(page,request,s);await page.reload();
 const saved=await(await request.get(`/api/saves/${s.save}`)).json();expect(saved.state.characters.some((c:any)=>c.id==='qa_timur')).toBe(true);
 const row=saved.state.phone.events.find((e:any)=>e.content===null&&e.conversation_id==='qa-group'&&e.sender.id==='');expect(row.sender).toEqual({id:'',name:'Неизвестный участник',portrait:null,silhouette:'neutral'});
 await page.getByRole('button',{name:/^Телефон/}).click();const phone=page.getByRole('region',{name:'Телефон персонажа'});await phone.getByRole('button',{name:'Переписки',exact:true}).click();await phone.locator('button.phone-row').filter({hasText:'Общая переписка'}).click();
 const message=phone.locator('.phone-message').nth(2);await expect(message).toContainText('Неизвестный участник');await expect(message.locator('img')).toHaveCount(0);await expect(message.locator('svg')).toHaveAttribute('data-silhouette','neutral');await message.scrollIntoViewIfNeeded();await page.screenshot({path:`${evidence}/after-${info.project.name}-hidden-sender.png`});
});
