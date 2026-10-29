import {test,expect,type Page} from '@playwright/test';
import {mkdir,writeFile,copyFile} from 'node:fs/promises';
import {nav} from './navigation';
import type {Job,Save,Turn} from '../src/types';
const baseline=process.env.STREAM_BASELINE==='1';
const evidence=process.env.STREAM_EVIDENCE||'../docs/manual_qa/narrative_v4/issue72-evidence';
const capture=process.env.UI_EVIDENCE==='1';
test.use({video:capture?'on':'off'});
const narrative=Array.from({length:18},(_,i)=>`Абзац ${i+1}. Персонаж 1 открывает книгу. Вечерний свет падает на стол, и разговор продолжается спокойно, без спешки. 🕯️`).join('\n\n')+'\n\n**Тихий вечер** продолжается. [Книга](https://example.com) остаётся открытой.\n\n- Чашка на столе\n- Свет у окна';
async function frames(page:Page,n=20){await page.evaluate(n=>new Promise<void>(resolve=>{let count=0;const tick=()=>++count>=n?resolve():requestAnimationFrame(tick);requestAnimationFrame(tick)}),n)}
for(const reduced of [false,true])test(`controlled streaming, commit, scroll and journal ${reduced?'reduced':'motion'}`,async({page,request},info)=>{
 test.setTimeout(120000);if(capture)await mkdir(evidence,{recursive:true});
 await page.emulateMedia({reducedMotion:reduced?'reduce':'no-preference'});
 const s=await(await request.post(reduced?'/test/phone-seed?unread=true':'/test/seed')).json();
 let save:Save=await(await request.get(`/api/saves/${s.save}`)).json();
 const turns:Turn[]=Array.from({length:60},(_,i)=>({id:1000+i,node_id:`n${i}`,active_variant_id:`v${i}`,sequence:i+1,user_text:'',assistant_text:`Архивная сцена ${i+1}.\n\n`+narrative,choices:[{action:'Продолжить',speech:''}],kind:'turn',memory_archived:false,variants:[{id:`v${i}`,ordinal:1,job_id:`old${i}`,can_regenerate:true}]}));
 // This fixture replaces the complete API History, including its read projection.
 save={...save,turns,physical_choice_source:{turn_id:turns.at(-1)!.id,variant_id:turns.at(-1)!.active_variant_id}};let job:Job={id:'stream72',status:'generating',narrative:'',error:'',kind:'turn',revision:save.revision,user_text:'Открываю книгу.'};
 await page.route(`**/api/saves/${s.save}`,route=>route.fulfill({json:save}));
 await page.route(`**/api/saves/${s.save}/turns`,route=>route.fulfill({json:job}));
 await page.addInitScript(s=>{
 localStorage.setItem('selection',JSON.stringify(s));
 const Real=window.EventSource;
 (window as any).EventSource=class extends EventTarget {onopen:any;onerror:any; constructor(url:string){super();if(!url.includes('stream72'))return new Real(url) as any;(window as any).testStream=this;queueMicrotask(()=>this.onopen?.(new Event('open')))}close(){}};
 },s);
 let markdown=0;page.on('request',r=>{if(r.url().endsWith('/markdown'))markdown++});
 await page.goto('/');await expect(page.locator('.turn')).toHaveCount(60);await frames(page,60);
 const beforeRequests=markdown;
 const cdp=await page.context().newCDPSession(page);await cdp.send('Emulation.setCPUThrottlingRate',{rate:4});
 await page.getByLabel('Своё действие или реплика').fill(job.user_text!);await page.getByRole('button',{name:'Отправить действие',exact:true}).click();
 await expect.poll(()=>page.evaluate(()=>!!(window as any).testStream)).toBe(true);
 if(!baseline){await expect(page.locator('.choices button')).toHaveCount(1);await expect(page.locator('.choices button')).toBeDisabled()}
 const emit=async(patch:Partial<Job>)=>{job={...job,...patch};await page.evaluate(j=>(window as any).testStream.dispatchEvent(new MessageEvent('snapshot',{data:JSON.stringify(j)})),job)};
 await page.evaluate(()=>{
 const w=window as any;w.samples=[];w.oldNode=document.querySelector('.turn .prose');w.oldMutations=0;
 new MutationObserver(rs=>w.oldMutations+=rs.length).observe(w.oldNode,{subtree:true,childList:true,characterData:true});
 w.longTasks=[];new PerformanceObserver(list=>w.longTasks.push(...list.getEntries().map(e=>e.duration))).observe({entryTypes:['longtask']});
 w.inputLatencies=[];document.addEventListener('input',()=>{const start=performance.now();requestAnimationFrame(()=>w.inputLatencies.push(performance.now()-start))});
 w.sampling=true;const tick=()=>{const e=document.querySelector('.story-scroll')!;const prose=document.querySelector('[data-stream-id] .narrative-text')||document.querySelector('.job details > .prose');w.samples.push({at:performance.now(),heap:(performance as any).memory?.usedJSHeapSize,top:e.scrollTop,gap:e.scrollHeight-e.clientHeight-e.scrollTop,length:prose?.textContent?.length||0});if(w.sampling)requestAnimationFrame(tick)};requestAnimationFrame(tick);
 });
 for(const length of [35,90,700,710,narrative.length]){
  await emit({narrative:narrative.slice(0,length)});
  if(length===90)await page.getByLabel('Своё действие или реплика').fill('Черновик во время генерации');
  await frames(page,25);
  if(!baseline)await expect.poll(()=>page.locator('.story-scroll').evaluate(el=>el.scrollHeight-el.clientHeight-el.scrollTop)).toBeLessThan(2);
 }
 await emit({status:'extracting',narrative_complete:true});await frames(page,100);
 await page.evaluate(()=>(window as any).testStream.onerror?.(new Event('error')));
 await expect(page.getByText('Восстанавливаем соединение…',{exact:true})).toBeVisible();
 await page.evaluate(()=>(window as any).testStream.onopen?.(new Event('open')));
 await emit({status:'error',error:'Временная ошибка обработки'});
 await expect(page.getByRole('button',{name:'Повторить обработку состояния',exact:true})).toBeVisible();
 await page.route('**/api/jobs/stream72/retry',route=>{job={...job,status:'extracting',error:'',attempt_epoch:1};return route.fulfill({json:job})});
 await page.getByRole('button',{name:'Повторить обработку состояния',exact:true}).click();
 await expect(page.getByText('Обновляет состояние мира',{exact:true})).toBeVisible();
 if(reduced){
  await page.getByRole('button',{name:/^Телефон/}).click();
  await expect(page.getByRole('region',{name:'Телефон персонажа'})).toBeVisible();
  await page.getByRole('button',{name:'Свернуть телефон'}).click();
 }
 const scroller=page.locator('.story-scroll');await scroller.evaluate(el=>el.scrollTop=el.scrollHeight/2);await frames(page);
 const up=await scroller.evaluate(el=>el.scrollTop);
 await emit({status:'validating'});await frames(page);
 await page.evaluate(()=>{(window as any).streamNode=document.querySelector('[data-stream-id] .narrative-text')||document.querySelector('.job details > .prose')});
 const streamedRequests=markdown-beforeRequests;
 const turn={...turns[0],id:2000,node_id:'new',active_variant_id:'committed',sequence:61,user_text:job.user_text!,assistant_text:narrative,choices:[{action:'Закрыть книгу',speech:''}],variants:[{id:'committed',ordinal:1,job_id:job.id,can_regenerate:true}]};
 save={...save,revision:save.revision+1,turns:[...turns,turn],physical_choice_source:{turn_id:turn.id,variant_id:turn.active_variant_id},job:{...job,status:'saved'}};
 await emit({status:'saved'});await expect(page.locator('.turn')).toHaveCount(61);await expect(page.locator('.choices button')).toHaveCount(1);await frames(page,30);
 await expect(page.locator('.choices button')).toContainText('Закрыть книгу');
 const upAfter=await scroller.evaluate(el=>el.scrollTop);
 const stable=await page.evaluate(()=>{const w=window as any;return w.streamNode?.isConnected && document.querySelector('.turn:last-of-type .narrative-text')===w.streamNode});
 if(!baseline){expect(stable).toBe(true);expect(Math.abs(upAfter-up)).toBeLessThan(2);expect(streamedRequests).toBeLessThanOrEqual(2);expect(await page.evaluate(()=>(window as any).oldMutations)).toBe(0)}
 await page.getByRole('button',{name:'К последней сцене'}).click();await frames(page,30);
 if(!baseline)expect(await scroller.evaluate(el=>el.scrollHeight-el.clientHeight-el.scrollTop)).toBeLessThan(2);
 await expect(page.locator('.turn').last()).toContainText('Абзац 18.');
 await page.getByLabel('Своё действие или реплика').fill('Черновик не потерять');
 if(info.project.name==='mobile'){await page.setViewportSize({width:393,height:480});await page.getByLabel('Своё действие или реплика').focus();await frames(page,30);await page.setViewportSize({width:393,height:852})}
 await nav(page,'Мир');await page.keyboard.press('Escape');await expect(page.getByLabel('Своё действие или реплика')).toHaveValue('Черновик не потерять');
 const metrics=await page.evaluate(()=>{const w=window as any;w.sampling=false;return {samples:w.samples,longTasks:w.longTasks,inputLatencies:w.inputLatencies,oldMutations:w.oldMutations,heap:(performance as any).memory?.usedJSHeapSize}});
 const name=`${baseline?'before':'after'}-${info.project.name}-${reduced?'reduced':'motion'}`;
 if(capture)await writeFile(`${evidence}/${name}.json`,JSON.stringify({...metrics,markdown:streamedRequests,stable,up,upAfter,viewport:page.viewportSize(),cpuThrottle:4},null,2));
 if(capture)await page.screenshot({path:`${evidence}/${name}.png`});await page.close();if(capture)await copyFile((await page.video()!.path()),`${evidence}/${name}.webm`);
});

test('real Start Game → ordinary turn → persisted reload → next ordinary turn',async({page,request},info)=>{
 const s=await(await request.post('/test/seed')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);await page.goto('/');
 await page.getByRole('button',{name:'Начать игру',exact:true}).click();await expect(page.locator('.choices button')).toHaveCount(6);
 await page.locator('.choices button').first().click();await expect(page.locator('.turn')).toHaveCount(2);await expect(page.locator('.choices button')).toHaveCount(6);
 const stored=await(await request.get(`/api/saves/${s.save}`)).json();expect(stored.turns).toHaveLength(2);
 await page.getByLabel('Своё действие или реплика').fill('Черновик следующего хода');await page.reload();await expect(page.locator('.turn')).toHaveCount(2);await expect(page.getByLabel('Своё действие или реплика')).toHaveValue('Черновик следующего хода');
 await page.getByRole('button',{name:'Отправить действие',exact:true}).click();await expect(page.locator('.turn')).toHaveCount(3);await expect(page.locator('.choices button')).toHaveCount(6);
 const after=await(await request.get(`/api/saves/${s.save}`)).json();expect(after.revision).toBeGreaterThan(stored.revision);
 if(capture)await mkdir(evidence,{recursive:true});await page.close();if(capture)await copyFile(await page.video()!.path(),`${evidence}/smoke-${info.project.name}.webm`);
});

test('leave for authoring and return during generation without losing the stream or draft',async({page,request},info)=>{
 test.skip(baseline,'Baseline unmounts Game; this is an added regression assertion.');
 const s=await(await request.post('/test/seed')).json();
 const saved=await(await request.get(`/api/saves/${s.save}`)).json();
 const job:Job={id:'navigation72',status:'generating',narrative:'',error:'',kind:'start',revision:saved.revision};
 await page.route(`**/api/saves/${s.save}/turns`,route=>route.fulfill({json:job}));
 await page.addInitScript(s=>{
  localStorage.setItem('selection',JSON.stringify(s));const Real=window.EventSource;
  (window as any).EventSource=class extends EventTarget {onopen:any;onerror:any;closed=false;constructor(url:string){super();if(!url.includes('navigation72'))return new Real(url) as any;(window as any).navStream=this;queueMicrotask(()=>this.onopen?.(new Event('open')))}close(){this.closed=true}};
 },s);
 await page.goto('/');await page.getByRole('button',{name:'Начать игру',exact:true}).click();
 await expect.poll(()=>page.evaluate(()=>!!(window as any).navStream)).toBe(true);
 const emit=async(patch:Partial<Job>)=>{Object.assign(job,patch);await page.evaluate(j=>(window as any).navStream.dispatchEvent(new MessageEvent('snapshot',{data:JSON.stringify(j)})),job)};
 await emit({narrative:narrative.slice(0,700)});await frames(page,30);
 await page.getByLabel('Своё действие или реплика').fill('Черновик при переходе');
 await page.evaluate(()=>{(window as any).navNode=document.querySelector('.narrative-text')});
 await nav(page,'Создать');await expect(page.locator('.game')).toBeHidden();
 await emit({narrative,status:'extracting',narrative_complete:true});await frames(page,90);
 await nav(page,'Игра');await expect(page.locator('.game')).toBeVisible();
 expect(await page.evaluate(()=>!(window as any).navStream.closed&&(window as any).navNode===document.querySelector('.narrative-text'))).toBe(true);
 await expect(page.getByLabel('Своё действие или реплика')).toHaveValue('Черновик при переходе');
 await expect(page.getByText('Обновляет состояние мира',{exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Отправить действие',exact:true})).toBeDisabled();
 await expect(page.locator('.narrative-text')).toContainText('Абзац 18.');
 if(capture)await mkdir(evidence,{recursive:true});await page.close();if(capture)await copyFile(await page.video()!.path(),`${evidence}/navigation-${info.project.name}.webm`);
});
