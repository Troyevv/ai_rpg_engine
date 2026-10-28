import {test,expect,type Page} from '@playwright/test';
import {copyFile,mkdir} from 'node:fs/promises';
import type {Job,Save,Turn} from '../src/types';
test.use({video:'on'});
const prose=Array.from({length:30},(_,i)=>`Реплика ${i+1}. В трубке слышен спокойный голос. Собеседница делает паузу и продолжает длинный рассказ о планах на ближайшую неделю.`).join('\n\n');
async function frames(page:Page,n=20){await page.evaluate(n=>new Promise<void>(resolve=>{let i=0;const tick=()=>++i>=n?resolve():requestAnimationFrame(tick);requestAnimationFrame(tick)}),n)}
for(const reduced of [false,true])test(`122 call bursty SSE and independent anchors ${reduced?'reduced':'motion'}`,async({page,request},info)=>{
 test.setTimeout(120000);await page.emulateMedia({reducedMotion:reduced?'reduce':'no-preference'});
 if(info.project.name==='mobile')await page.setViewportSize({width:reduced?360:393,height:800});
 const selected=await(await request.post('/test/phone-seed?incoming=false&decision=answer')).json();
 await request.put(`/api/worlds/${selected.world}/presentation`,{data:{theme_id:reduced?'parchment':'graphite'}});
 await page.addInitScript(s=>{
  localStorage.setItem('selection',JSON.stringify(s));const Real=window.EventSource;
  (window as any).EventSource=class extends EventTarget {onopen:any;onerror:any;constructor(url:string){super();if(!url.includes('phone122-stream'))return new Real(url) as any;(window as any).callStream=this;queueMicrotask(()=>this.onopen?.(new Event('open')))}close(){}};
 },selected);
 await page.goto('/');await page.getByRole('button',{name:/^Телефон/}).click();
 const phone=page.getByRole('region',{name:'Телефон персонажа'});
 await phone.getByRole('button',{name:'Вера работа',exact:true}).click();await phone.getByRole('button',{name:'Позвонить',exact:true}).click();
 const call=page.getByRole('dialog',{name:'Сцена звонка'});await expect(call).toBeVisible();
 let save:Save=await(await request.get(`/api/saves/${selected.save}`)).json();
 const callId=save.state.phone!.events.find(e=>e.status==='answered')!.id;
 const route={surface:'call' as const,actor_id:save.state.controlled_actor_id,call_id:callId};
 const main:Turn[]=Array.from({length:16},(_,i)=>({...save.turns[0],id:800+i,node_id:`archive${i}`,active_variant_id:`archive${i}`,sequence:i,user_text:'',assistant_text:prose,variants:[{id:`archive${i}`,ordinal:1,job_id:`archive${i}`,can_regenerate:true}]}));
 save={...save,turns:main,physical_choice_source:{turn_id:main.at(-1)!.id,variant_id:main.at(-1)!.active_variant_id},job:null};
 let job:Job={id:'phone122-stream',kind:'turn',status:'generating',narrative:'',error:'',revision:save.revision,presentation:route,user_text:'Расскажи подробнее.'};
 await page.route(`**/api/saves/${selected.save}`,r=>r.fulfill({json:save}));
 await page.route(`**/api/saves/${selected.save}/turns`,r=>r.fulfill({json:job}));
 await page.reload();await expect(call).toBeVisible();await call.getByLabel('Свернуть звонок').click();
 const choices=page.locator('.choices button strong');const choiceText=await choices.allTextContents();expect(choiceText.length).toBeGreaterThan(0);
 const story=page.locator('.story-scroll');await story.evaluate(el=>el.scrollTop=el.scrollHeight/2);await frames(page);
 const mainTop=await story.evaluate(el=>el.scrollTop);
 await page.getByLabel('Своё действие или реплика').fill('Сохранить основной черновик');
 await page.getByRole('button',{name:/Вернуться к звонку/}).click();
 let markdown=0;page.on('request',r=>{if(r.url().endsWith('/markdown'))markdown++});
 await call.getByLabel('Реплика в звонке').fill(job.user_text!);await call.getByLabel('Сказать собеседнику').click();
 await expect.poll(()=>page.evaluate(()=>!!(window as any).callStream)).toBe(true);
 const emit=async(patch:Partial<Job>)=>{job={...job,...patch};await page.evaluate(j=>(window as any).callStream.dispatchEvent(new MessageEvent('snapshot',{data:JSON.stringify(j)})),job)};
 await expect(call.locator('.call-activity')).toHaveAttribute('data-state','callWaiting');
 await expect(call.locator('.call-activity [role=status]')).toHaveAttribute('aria-live','polite');
 if(reduced)expect(await call.locator('.call-activity-dots i').first().evaluate(el=>getComputedStyle(el).animationName)).toBe('none');
 await expect(call.getByRole('button',{name:'Остановить ответ',exact:true})).toBeEnabled();
 const evidenceActivity=process.env.PHONE133_FOLLOWUP_EVIDENCE;
 if(evidenceActivity){await mkdir(evidenceActivity,{recursive:true});await page.screenshot({path:`${evidenceActivity}/waiting-${info.project.name}-${reduced?'parchment':'graphite'}.png`})}
 await emit({narrative:prose.slice(0,2500)});
 await expect(call.locator('.call-activity')).toHaveAttribute('data-state','callStreaming');await frames(page,100);
 const scroll=page.locator('.call-scene-scroll');await scroll.evaluate(el=>el.scrollTop=100);await frames(page);
 const callTop=await scroll.evaluate(el=>el.scrollTop);expect(callTop).toBeGreaterThan(0);
 for(const length of [2510,3200,3300,prose.length]){await emit({narrative:prose.slice(0,length)});await frames(page,25)}
 await emit({status:'extracting',narrative_complete:true});
 await expect(call.locator('.call-activity')).toHaveAttribute('data-state','callApplying');await frames(page,100);
 await expect(choices).toHaveText(choiceText);
 await call.getByLabel('Реплика в звонке').fill('Сохранить черновик звонка');
 await page.evaluate(()=>(window as any).callText=document.querySelector('.call-scene .narrative-text'));
 const committed:Turn={...main[0],id:900,sequence:17,node_id:'call-turn',active_variant_id:'call-variant',presentation:route,user_text:job.user_text!,assistant_text:prose,variants:[{id:'call-variant',ordinal:1,job_id:job.id,can_regenerate:true}]};
 save={...save,revision:save.revision+1,turns:[...main,committed],job:{...job,status:'saved'}};
 await emit({status:'saved'});
 await expect(call.locator('.call-activity')).toHaveAttribute('data-state','connected');
 await expect(call.getByRole('button',{name:'Остановить ответ',exact:true})).toHaveCount(0);await expect(call.locator('.turn')).toHaveCount(1);await frames(page,30);
 await expect(choices).toHaveText(choiceText);
 expect(await page.evaluate(()=>(window as any).callText===document.querySelector('.call-scene .narrative-text'))).toBe(true);
 expect(Math.abs(await scroll.evaluate(el=>el.scrollTop)-callTop)).toBeLessThan(2);
 expect(Math.abs(await story.evaluate(el=>el.scrollTop)-mainTop)).toBeLessThan(2);
 expect(markdown).toBeLessThanOrEqual(2);
 await call.getByLabel('Свернуть звонок').click();await page.getByRole('button',{name:/Вернуться к звонку/}).click();
 expect(Math.abs(await scroll.evaluate(el=>el.scrollTop)-callTop)).toBeLessThan(2);
 await expect(call.getByLabel('Реплика в звонке')).toHaveValue('Сохранить черновик звонка');
 await page.keyboard.press('Escape');await expect(call).toBeHidden();
 await page.getByRole('button',{name:/Вернуться к звонку/}).click();await page.goBack();await expect(call).toBeHidden();
 await page.getByRole('button',{name:/Вернуться к звонку/}).click();
 if(info.project.name==='mobile'){
  await page.setViewportSize({width:393,height:480});await call.getByLabel('Реплика в звонке').focus();await frames(page);
  expect((await call.getByRole('button',{name:'Завершить звонок',exact:true}).boundingBox())!.y).toBeLessThan(480);
  await page.setViewportSize({width:393,height:800});
 }
 await page.route(`**/api/saves/${selected.save}/phone`,r=>{save={...save,revision:save.revision+1,state:{...save.state,phone:{...save.state.phone!,events:save.state.phone!.events.map(e=>e.id===callId?{...e,status:'ended'}:e)}}};return r.fulfill({json:save})});
 await call.getByRole('button',{name:'Завершить звонок',exact:true}).click();await expect(call).toHaveCount(0);
 await expect(page.getByLabel('Своё действие или реплика')).toHaveValue('Сохранить основной черновик');
 expect(Math.abs(await story.evaluate(el=>el.scrollTop)-mainTop)).toBeLessThan(2);
 await expect(story.locator('.turn')).toHaveCount(main.length);
 await expect(choices).toHaveText(choiceText);
 const evidence=process.env.PHONE133_FOLLOWUP_EVIDENCE||process.env.PHONE122_EVIDENCE;
 if(evidence){await mkdir(evidence,{recursive:true});await page.close();await copyFile(await page.video()!.path(),`${evidence}/anchors-${info.project.name}-${reduced?'reduced':'motion'}.webm`)}
});

test('133 call stop restores unsaved speech without hanging up',async({page,request})=>{
 const s=await(await request.post('/test/phone-seed?incoming=false&decision=answer')).json();
 await page.addInitScript(s=>{localStorage.setItem('selection',JSON.stringify(s));const Real=window.EventSource;
  (window as any).EventSource=class extends EventTarget{onopen:any;onerror:any;constructor(url:string){super();if(!url.includes('phone133-stop'))return new Real(url) as any;queueMicrotask(()=>this.onopen?.(new Event('open')))}close(){}};
 },s);
 await page.goto('/');await page.getByRole('button',{name:/^Телефон/}).click();
 const phone=page.getByRole('region',{name:'Телефон персонажа'});
 await phone.getByRole('button',{name:'Вера работа',exact:true}).click();await phone.getByRole('button',{name:'Позвонить',exact:true}).click();
 const call=page.getByRole('dialog',{name:'Сцена звонка'});await expect(call).toBeVisible();
 let save:Save=await(await request.get(`/api/saves/${s.save}`)).json();
 const callId=save.state.phone!.events.find(e=>e.status==='answered')!.id;
 let job:Job={id:'phone133-stop',kind:'turn',status:'generating',narrative:'',error:'',revision:save.revision,presentation:{surface:'call',call_id:callId},user_text:'Алло, ты здесь?'};
 await page.route(`**/api/saves/${s.save}`,r=>r.fulfill({json:save}));
 await page.route(`**/api/saves/${s.save}/turns`,r=>r.fulfill({json:job}));
 let stops=0;await page.route('**/api/jobs/phone133-stop/stop',r=>{stops++;job={...job,status:'stopped',live:false};save={...save,job};return r.fulfill({json:job})});
 await call.getByLabel('Реплика в звонке').fill(job.user_text!);await call.getByLabel('Сказать собеседнику').click();
 await expect(call.locator('.call-activity')).toHaveAttribute('data-state','callWaiting');
 await call.getByRole('button',{name:'Остановить ответ',exact:true}).click();
 await expect(call.locator('.call-activity')).toHaveAttribute('data-state','callStopped');
 await call.getByRole('button',{name:'Вернуть реплику в поле ввода',exact:true}).click();
 await expect(call.getByLabel('Реплика в звонке')).toHaveValue(job.user_text!);
 await expect(call.getByRole('button',{name:'Завершить звонок',exact:true})).toBeEnabled();
 expect(stops).toBe(1);expect(save.state.phone!.events.find(e=>e.id===callId)!.status).toBe('answered');
});
