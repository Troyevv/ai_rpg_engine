import {test,expect} from '@playwright/test';
import {mkdir} from 'node:fs/promises';
const evidence='../docs/manual_qa/narrative_v4/issue87';
const phase=process.env.READING_BASELINE==='1'?'before':'after';
for(const width of [360,393,768,1440]) for(const skin of ['graphite','parchment']) test(`87 reading ${width} ${skin}`,async({page,request},info)=>{
 test.skip(info.project.name!=='desktop');test.setTimeout(120000);
 await mkdir(evidence,{recursive:true});await page.setViewportSize({width,height:900});
 await page.emulateMedia({reducedMotion:'reduce'});
 const s=await(await request.post('/test/phone-seed?unread=true&incoming=false')).json();
 await request.put(`/api/worlds/${s.world}/presentation`,{data:{theme_id:skin}});
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);
 await page.goto('/');await expect(page.locator('.turn')).toHaveCount(1);
 await expect(page.locator('.choices button').first()).toBeEnabled();
 const input=page.getByLabel('Своё действие или реплика');
 await input.fill('Я задерживаюсь у окна, разглядывая вечерний город.');
 await page.locator('.story-scroll').evaluate(e=>e.scrollTop=0);
 await page.screenshot({path:`${evidence}/${phase}-${width}-${skin}-reading.png`,animations:'disabled'});
 await page.locator('.story-scroll').evaluate(e=>e.scrollTop=e.scrollHeight);
 await expect.poll(()=>page.locator('.story-scroll').evaluate(e=>e.scrollHeight-e.clientHeight-e.scrollTop)).toBeLessThan(2);
 if(phase==='after'){const story=await page.locator('.story-scroll').boundingBox();const phone=await page.locator('.phone-peek').boundingBox();expect(story!.y+story!.height).toBeLessThanOrEqual(phone!.y+1)}
 await page.screenshot({path:`${evidence}/${phase}-${width}-${skin}-choices.png`,animations:'disabled'});
 await page.getByRole('button',{name:/^Телефон/}).click();
 await expect(page.getByRole('region',{name:'Телефон персонажа'})).toBeVisible();
 await page.screenshot({path:`${evidence}/${phase}-${width}-${skin}-phone.png`,animations:'disabled'});
 await page.getByRole('button',{name:'Свернуть телефон'}).click();
 await expect(input).toHaveValue('Я задерживаюсь у окна, разглядывая вечерний город.');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
 if(width<768){
 await input.focus();await page.evaluate(()=>{Object.defineProperty(visualViewport,'height',{configurable:true,value:440});visualViewport!.dispatchEvent(new Event('resize'))});
 await expect(page.locator('html')).toHaveClass(/keyboard-open/);
 await page.screenshot({path:`${evidence}/${phase}-${width}-${skin}-keyboard.png`,animations:'disabled'});
 expect((await input.boundingBox())!.y+(await input.boundingBox())!.height).toBeLessThan(441);
 }
});

test('87 real failed Extraction has no phantom incoming event; Retry commits once',async({page,request},info)=>{
 const s=await(await request.post('/test/narrative-phone138-seed')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);await page.goto('/');
 await page.getByRole('button',{name:'Начать игру',exact:true}).click();
 await expect(page.locator('.choices button').first()).toBeEnabled();
 const view=async()=>await(await request.get(`/api/saves/${s.save}`)).json();
 const before=await view();
 await request.post('/test/reading87-extraction-failure');
 await page.getByLabel('Своё действие или реплика').fill('Посмотреть на дождь.');
 await page.getByRole('button',{name:'Отправить действие',exact:true}).click();
 await expect(page.getByRole('button',{name:'Повторить обработку состояния',exact:true})).toBeVisible();
 const failed=await view();expect(failed.state.phone.events).toEqual(before.state.phone.events);expect(failed.revision).toBe(before.revision);
 await expect(page.locator('.phone-device')).not.toHaveClass(/is-ringing/);
 await expect(page.locator('.phone-led')).toHaveCount(0);
 await page.screenshot({path:`${evidence}/after-${info.project.name}-extraction-error.png`});
 await page.getByRole('button',{name:'Повторить обработку состояния',exact:true}).click();
 await expect.poll(async()=>(await view()).job.status).toBe('saved');
 const after=await view();expect(after.state.phone.events).toHaveLength(1);expect(after.state.phone.events[0].unread).toBe(true);
 await page.reload();await expect(page.locator('.choices button').first()).toBeEnabled();
 expect((await view()).state.phone.events).toHaveLength(1);
});
