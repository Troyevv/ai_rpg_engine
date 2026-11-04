import {test,expect,type Page,type APIRequestContext} from '@playwright/test';
import {nav,pickCharacter} from './navigation';
const area=(page:Page)=>page.locator('.inspector-workspace');
async function setup(page:Page,request:APIRequestContext,theme='graphite'){
 const s=await(await request.post('/test/story168-seed')).json();
 await request.put(`/api/worlds/${s.world}/presentation`,{data:{theme_id:theme}});
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify({world:s.world,save:s.save})),s);
 await page.goto('/');await expect(page.getByLabel('Своё действие или реплика')).toBeVisible();return s;
}
async function dossier(page:Page){await nav(page,'Персонажи');await pickCharacter(page,'qa_vera');await area(page).getByRole('tab',{name:'Тайны',exact:true}).click()}
const bitmap=async(page:Page,index=0)=>page.locator('.secret-entry.is-hidden canvas').nth(index).evaluate((c:HTMLCanvasElement)=>c.toDataURL());
for(const theme of ['graphite','parchment']){
 test(`moving fog, in-place reveal, branch history and navigation: ${theme}`,async({page,request},info)=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  const s=await setup(page,request,theme);
  await dossier(page);
  await expect(area(page).getByText('Скрытых тайн: 9')).toBeVisible();
  await expect(page.locator('.secret-entry.is-hidden')).toHaveCount(9);
  await expect(page.locator('.secret-entry.is-known canvas')).toHaveCount(0);
  expect(await page.content()).not.toContain('NEVER-EXPOSE');
  // Category headers and known records precede the hidden group. Offscreen fog
  // intentionally sleeps, so bring the measured surface into the viewport.
  await page.locator('.secret-entry.is-hidden').first().scrollIntoViewIfNeeded();
  const before=await bitmap(page);await expect.poll(()=>bitmap(page)).not.toBe(before);
  const frameStats=await page.evaluate(()=>new Promise<{p95:number;max:number}>(resolve=>{
   const samples:number[]=[];let previous=performance.now();
   const frame=(now:number)=>{samples.push(now-previous);previous=now;if(samples.length<48)requestAnimationFrame(frame);else{samples.sort((a,b)=>a-b);resolve({p95:samples[45],max:samples.at(-1)!})}};requestAnimationFrame(frame);
  }));
  console.log('fog frame timing',info.project.name,theme,frameStats);
  // Multiple layers live before any input; offscreen rows do no continuous work.
  await expect(page.locator('.secret-entry.is-hidden[data-fog-active="false"]').last()).toBeAttached();
  const firstSizes=await page.locator('.secret-entry.is-hidden').evaluateAll(rows=>rows.map(r=>[r.clientWidth,r.clientHeight]));
  expect(new Set(firstSizes.map(r=>r.join(':'))).size).toBe(1);
  if(process.env.STORY168_VISUAL)await page.screenshot({path:`/tmp/story168-${theme}-${info.project.name}-fog.png`});
  await page.goBack();await expect(page.getByLabel('Своё действие или реплика')).toBeVisible();
  await request.post(`/test/story168-prepare/${s.save}?delayed=true`);
  await page.getByLabel('Своё действие или реплика').fill('Расскажи о рукописи.');
  await page.getByRole('button',{name:'Отправить действие',exact:true}).click();
  await dossier(page);
  await expect(page.locator('.secret-entry.is-revealing')).toHaveCount(0);
  await request.post('/test/story168-release');
  await expect(page.locator('.secret-entry.is-revealing')).toHaveCount(1);
  await page.locator('.secret-entry.is-revealing').scrollIntoViewIfNeeded();
  const revealing=page.locator('.secret-entry.is-revealing canvas');
  const start=await revealing.evaluate((c:HTMLCanvasElement)=>c.toDataURL());
  await expect.poll(()=>revealing.evaluate((c:HTMLCanvasElement)=>c.toDataURL())).not.toBe(start);
  if(process.env.STORY168_VISUAL)await page.screenshot({path:`/tmp/story168-${theme}-${info.project.name}-reveal.png`});
  await expect(page.locator('.secret-entry.is-revealing')).toHaveCount(0);
  await expect(page.locator('.secret-entry.is-hidden')).toHaveCount(8);
  await expect(area(page).getByText('Скрытых тайн: 8')).toBeVisible();
  await page.locator('.secret-entry.is-hidden').first().scrollIntoViewIfNeeded();
  const moving=await bitmap(page);await expect.poll(()=>bitmap(page)).not.toBe(moving);
  await expect(area(page)).toContainText('Вера тайно написала роман.');
  const response=await(await request.get(`/api/saves/${s.save}`)).json();
  expect(response.state.notification_history.map((n:any)=>n.kind)).toEqual(['secret_revealed','secret_new','thread_new']);
  expect(JSON.stringify(response)).not.toContain('NEVER-EXPOSE');
  await page.goBack();
  const draft=page.getByLabel('Своё действие или реплика');await draft.fill('Несохранённый черновик');
  await page.getByRole('button',{name:'История уведомлений, 3',exact:true}).click();
  await expect(page.locator('.story-journal-list li')).toHaveCount(3);
  await page.locator('.story-journal-list button').filter({hasText:'Вера тайно написала роман.'}).click();
  await expect(area(page).getByRole('tab',{name:'Тайны',exact:true})).toHaveAttribute('aria-selected','true');
  await expect(page.locator('.secret-entry.is-revealing')).toHaveCount(0);
  await page.goBack();await expect(draft).toHaveValue('Несохранённый черновик');
  await expect(page.locator('.choices').or(page.locator('.narrative-choices'))).toBeVisible();
  await page.getByRole('button',{name:'История уведомлений, 3',exact:true}).click();
  await page.locator('.story-journal-list button').filter({hasText:'Найти подлинную рукопись'}).click();
  await expect(page.locator('[data-thread-id="thread168"]')).toBeVisible();
  await page.goBack();await page.getByRole('button',{name:'История уведомлений, 3',exact:true}).click();
  await page.locator('.story-journal-list button').filter({hasText:'Подмена рукописи связана'}).click();
  await expect(page.locator('.story-secrets .secret-entry.is-known').filter({hasText:'Подмена рукописи связана'})).toBeVisible();
  await expect(page.locator('.secret-entry.is-revealing')).toHaveCount(0);
  await page.reload();await dossier(page);
  await expect(page.locator('.secret-entry.is-revealing')).toHaveCount(0);
  await expect(page.locator('.story-toast')).toHaveCount(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  if(process.env.STORY168_VISUAL)await page.screenshot({path:`/tmp/story168-${theme}-${info.project.name}-known.png`});
  expect(errors).toEqual([]);
 });
}
test('reduced motion, separately committed reading, reload and phone',async({page,request})=>{
 await page.emulateMedia({reducedMotion:'reduce'});
 const s=await setup(page,request,'cyberpunk');await dossier(page);
 const first=await bitmap(page);await page.waitForTimeout(200);expect(await bitmap(page)).toBe(first);
 await expect(page.locator('[data-fog-active="true"]')).toHaveCount(0);
 const before=await(await request.get(`/api/saves/${s.save}`)).json();
 const read=await request.post(`/api/saves/${s.save}/phone`,{data:{revision:before.revision,command:{action:'read',event_id:s.event,operation_id:'story168-read'}}});
 expect(read.ok()).toBe(true);const after=await read.json();expect(after.state.notification_history).toHaveLength(1);
 await page.reload();await page.getByRole('button',{name:'История уведомлений, 1',exact:true}).click();
 await page.locator('.story-journal-list button').click();
 await expect(page.locator('.secret-entry.is-revealing')).toHaveCount(0);
 await expect(area(page)).toContainText('Вера тайно написала роман.');
 await page.goBack();await page.locator('.phone-peek').click();
 await expect(page.locator('.phone-device')).toHaveClass(/is-open/);
 await expect(page.locator('.story-toast')).toHaveCount(0);
 await expect(page.locator('.phone-screen')).toBeVisible();
});

test('phone reading queues a disclosure until the phone closes; first dossier view reveals it once',async({page,request},info)=>{
 const s=await setup(page,request);
 const draft=page.getByLabel('Своё действие или реплика');await draft.fill('Черновик до чтения');
 await page.locator('.phone-peek').click();
 const phone=page.getByRole('region',{name:'Телефон персонажа'});
 const committed=page.waitForResponse(r=>r.url().endsWith(`/saves/${s.save}/phone`)&&r.request().method()==='POST');
 await phone.locator('.phone-notifications button').first().click();
 expect((await committed).ok()).toBe(true);
 await expect(phone).toContainText('Я написала роман.');
 await expect(page.locator('.story-toast')).toHaveCount(0);
 await phone.getByRole('button',{name:'Свернуть телефон',exact:true}).click();
 await expect(page.locator('.story-toast')).toContainText('Раскрыта тайна');
 if(process.env.STORY168_VISUAL)await page.screenshot({animations:'disabled',path:`/tmp/story168-${info.project.name}-toast.png`});
 await page.locator('.story-toast-body button').click();
 await expect(page.locator('.secret-entry.is-revealing')).toHaveCount(1);
 await expect(page.locator('.secret-entry.is-revealing')).toHaveCount(0);
 await expect(area(page)).toContainText('Вера тайно написала роман.');
 await page.goBack();await expect(draft).toHaveValue('Черновик до чтения');
 await expect(page.locator('.choices button')).toHaveCount(6);
 await page.reload();await dossier(page);await expect(page.locator('.secret-entry.is-revealing')).toHaveCount(0);
});
