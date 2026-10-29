import {test,expect} from '@playwright/test';
import {writeFile,mkdir} from 'node:fs/promises';
import {nav} from './navigation';
const out='../docs/manual_qa/narrative_v4/issue87';
const longText=Array.from({length:10},(_,i)=>`Абзац ${i+1}. За окном загорались первые огни. Сумерки медленно заполняли комнату; собеседник отложил раскрытую книгу и повернулся к двери. Никто не торопился нарушать тишину.\n\n— Я вернусь к этому разговору завтра, — сказал он. — Сейчас важнее понять, что произошло.`).join('\n\n');

test('87 1000-turn reading, panels, draft selection, resize and performance',async({page,request},info)=>{
 test.setTimeout(180000);await mkdir(out,{recursive:true});
 const s=await(await request.post('/test/phone-seed?incoming=false')).json();
 const base=await(await request.get(`/api/saves/${s.save}`)).json();
 // A presentation load fixture only. Canonical end-to-end scenarios live in
 // reading87 / narrative-phone138 and exercise real API, jobs and SQLite.
 const first=base.turns[0];const turns=Array.from({length:1000},(_,i)=>({...first,id:10000+i,node_id:`load-${i}`,sequence:i+1,user_text:i?'Продолжаю разговор.':'',assistant_text:longText,active_variant_id:`variant-${i}`,variants:[{id:`variant-${i}`,ordinal:1,job_id:`load-job-${i}`,can_regenerate:true}]}));
 const state={...base,turns,job:null,physical_choice_source:{turn_id:turns.at(-1).id,variant_id:turns.at(-1).active_variant_id}};
 await page.route(`**/api/saves/${s.save}`,r=>r.fulfill({json:state}));
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);
 const start=Date.now();await page.goto('/');await expect(page.locator('.story .turn')).toHaveCount(1000);
 const ready=Date.now()-start;
 await page.waitForLoadState('networkidle');
 const input=page.getByLabel('Своё действие или реплика'),story=page.locator('.story-scroll');
 await input.fill('Черновик длинной истории — сохранить выделение.');
 await input.evaluate((e:HTMLTextAreaElement)=>e.setSelectionRange(9,24));
 await story.evaluate(e=>e.scrollTop=e.scrollHeight/2);await page.waitForLoadState('networkidle');
 await expect(page.getByRole('button',{name:'К последней сцене'})).toBeVisible();
 const top=await story.evaluate(e=>e.scrollTop);
 await page.evaluate(()=>{(window as any).readingNode=document.querySelector('.story-scroll')});
 for(const panel of ['phone','calendar','inspector']){
  if(panel==='phone'){await page.getByRole('button',{name:/^Телефон/}).click();await page.keyboard.press('Escape')}
  else {await nav(page,panel==='calendar'?'Календарь':'Мир');const surface=page.locator(panel==='calendar'?'.save-workspace':'.inspector-workspace');await expect(surface).toBeVisible();await page.keyboard.press('Escape');await expect(surface).toBeHidden()}
  await expect(input).toHaveValue('Черновик длинной истории — сохранить выделение.');
  expect(await input.evaluate((e:HTMLTextAreaElement)=>[e.selectionStart,e.selectionEnd])).toEqual([9,24]);
  expect(Math.abs(await story.evaluate(e=>e.scrollTop)-top)).toBeLessThan(3);
  expect(await page.evaluate(()=>(window as any).readingNode===document.querySelector('.story-scroll'))).toBe(true);
 }
 const metrics=await page.evaluate(async()=>{
  const el=document.querySelector('.story-scroll')!;const durations:number[]=[];
  const heapStart=(performance as any).memory?.usedJSHeapSize;
  let last=performance.now();
  for(let i=0;i<60;i++){el.scrollTop+=30;await new Promise(requestAnimationFrame);const now=performance.now();durations.push(now-last);last=now}
  return {frameMedian:durations.sort((a,b)=>a-b)[30],frameP95:durations[57],heapStart,heapEnd:(performance as any).memory?.usedJSHeapSize,domNodes:document.querySelectorAll('*').length};
 });
 await page.screenshot({path:`${out}/after-${info.project.name}-1000-history.png`});
 await writeFile(`${out}/performance-${info.project.name}.json`,JSON.stringify({readyMs:ready,...metrics},null,2));
 expect(metrics.frameP95).toBeLessThan(150);
 await page.getByRole('button',{name:'К последней сцене'}).click();
 await expect.poll(()=>story.evaluate(e=>e.scrollHeight-e.clientHeight-e.scrollTop)).toBeLessThan(3);
 await page.setViewportSize({width:info.project.name==='mobile'?800:393,height:800});
 await expect(input).toHaveValue('Черновик длинной истории — сохранить выделение.');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
});

for(const count of [0,1,9]) test(`87 ${count} choices, long speech, exact dispatch and eligibility`,async({page,request},info)=>{
 const s=await(await request.post('/test/phone-seed?incoming=false')).json();
 const saved=await(await request.get(`/api/saves/${s.save}`)).json();
 const choices=Array.from({length:count},(_,i)=>({action:i?'Посмотреть на собеседника':'Открыть книгу',speech:i?'Да, давай вернёмся к этому разговору завтра. '.repeat(8):''}));
 saved.turns[0].choices=choices;saved.turns[0].assistant_text=longText;
 await page.route(`**/api/saves/${s.save}`,r=>r.fulfill({json:saved}));
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);await page.goto('/');
 await expect(page.locator('.choices button')).toHaveCount(count);
 const input=page.getByLabel('Своё действие или реплика');
 await input.fill('Первая строка\nВторая строка\nТретья строка\nЧетвёртая строка');
 expect((await input.boundingBox())!.height).toBeGreaterThan(80);
 await input.fill('Черновик');expect((await input.boundingBox())!.height).toBeLessThan(60);
 if(count){
  const button=page.locator('.choices button').last();await button.scrollIntoViewIfNeeded();
  expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await page.screenshot({path:`${out}/after-${info.project.name}-${count}-choices.png`});
  const command=page.waitForRequest(r=>r.url().endsWith(`/saves/${s.save}/turns`)&&r.method()==='POST');
  await page.route(`**/api/saves/${s.save}/turns`,r=>r.fulfill({status:409,json:{detail:'Presentation test: no mutation'}}));
  await button.click();const body=(await command).postDataJSON();const c=choices.at(-1)!;
  expect(body.text).toBe(c.action+(c.speech?`: «${c.speech}»`:''));
 }
 saved.state.actor_capabilities={...saved.state.actor_capabilities,can_act:false};await page.reload();
 await expect(input).toBeDisabled();await expect(page.getByRole('button',{name:'Отправить действие',exact:true})).toBeDisabled();
 let submissions=0;page.on('request',r=>{if(r.url().endsWith('/turns')&&r.method()==='POST')submissions++});
 await input.dispatchEvent('keydown',{key:'Enter',ctrlKey:true});
 await page.locator('.composer-inner').dispatchEvent('submit');
 expect(submissions).toBe(0);
});

test('87 authorized character link returns to the same reading anchor and draft',async({page,request})=>{
 const s=await(await request.post('/test/seed')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);await page.goto('/');
 await page.getByRole('button',{name:'Начать игру',exact:true}).click();
 await expect(page.locator('.choices button')).toHaveCount(6);
 const input=page.getByLabel('Своё действие или реплика');await input.fill('Неотправленная реплика');
 const link=page.locator('.narrative-text [data-character-id]').first();await link.scrollIntoViewIfNeeded();
 const before=await page.locator('.story-scroll').evaluate(e=>e.scrollTop);
 await link.click();await expect(page.locator('.inspector-workspace')).toBeVisible();
 await page.keyboard.press('Escape');await expect(page.locator('.inspector-workspace')).toBeHidden();
 await expect(input).toHaveValue('Неотправленная реплика');
 expect(Math.abs(await page.locator('.story-scroll').evaluate(e=>e.scrollTop)-before)).toBeLessThan(3);
 await expect(link).toBeFocused();
});
