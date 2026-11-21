import {test,expect} from '@playwright/test';
import {scrollByTouch} from './touch';

test('choice proposals survive reload without committing action; free input remains available',async({page,request})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const response=await request.post('/test/choices-seed');expect(response.ok()).toBeTruthy();
 const selection=await response.json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selection);
 const saved=async()=> (await request.get(`/api/saves/${selection.save}`)).json();
 const before=await saved();
 await page.goto('/');
 await expect(page.locator('.choices button')).toHaveCount(6);
 await expect(page.locator('.choices')).toContainText('Предложить смелую версию');
 await expect(page.getByLabel('Своё действие или реплика')).toBeEnabled();
 await page.reload();
 await expect(page.locator('.choices button')).toHaveCount(6);
 expect((await saved()).state).toEqual(before.state);
 // Typed input is outside the suggestions and deliberately atypical.
 const input='Вопреки привычке, не проверяю детали, а предлагаю рискнуть.';
 await page.getByLabel('Своё действие или реплика').fill(input);
 await page.getByRole('button',{name:'Отправить действие',exact:true}).click();
 await expect(page.locator('.turn')).toHaveCount(4);
 await expect(page.locator('.turn').last().getByTestId('player-action')).toContainText(input);
 await expect(page.locator('.choices button')).toHaveCount(6);
 await page.reload();
 await expect(page.locator('.choices button')).toHaveCount(6);
 await page.locator('.choices button').first().click();
  await page.getByRole('button',{name:'Отправить действие',exact:true}).click();
 await expect(page.locator('.turn')).toHaveCount(5);
 await expect(page.locator('.turn').last().getByTestId('player-action')).toContainText('Действие 0');
 const after=await saved();
 for(const key of ['goals','intentions','obligations','emotion','personality']){
  expect(after.state.world.characters.qa_kirill[key]).toEqual(before.state.world.characters.qa_kirill[key]);
 }
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
 expect(errors).toEqual([]);
});

test('touch scrolls through ten proposals and back to the story without selecting one', async ({page, request}, info) => {
 test.skip(info.project.name !== 'mobile');
 await page.setViewportSize({width:393,height:720});
 const selection=await (await request.post('/test/choices-seed')).json();
 const path='/api/saves/'+selection.save;
 const save=await (await request.get(path)).json();
 const turn=save.turns.find((t:{id:number})=>t.id===save.physical_choice_source.turn_id);
 turn.choices=Array.from({length:10}, (_,i)=>({
   action:'Рассмотреть страницу '+(i+1),
   speech:'Помнишь эту фотографию у окна? Я думал, она осталась у тебя.'
 }));
 await page.route('**'+path,r=>r.fulfill({json:save}));
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selection);
 await page.goto('/');
 const cards=page.locator('.choices button'), story=page.locator('.story-scroll');
 const panel=page.locator('.story .action-panel').first(), toggle=panel.locator('.action-panel-toggle');
 const draft=page.getByLabel('Своё действие или реплика');
 await expect(cards).toHaveCount(10);
 await cards.first().evaluate(el=>el.scrollIntoView({block:'start'}));
 const finger=await page.context().newCDPSession(page);
 // Begin inside an actual visible card. No scrollIntoView, wheel injection or
 // programmatic scrolling between swipes.
 async function dragCard(distance:number) {
   const point=await cards.evaluateAll(nodes=>{
     const v=document.querySelector('.story-scroll')!.getBoundingClientRect();
     const b=nodes[0].parentElement!.getBoundingClientRect();
     const y=(Math.max(b.top,v.top)+Math.min(b.bottom,v.bottom))/2;
     const x=b.left+b.width/2;
     if(!document.elementFromPoint(x,y)?.closest('.choices button')) {
       const card=nodes.find(n=>{const r=n.getBoundingClientRect();return r.top>=v.top&&r.bottom<=v.bottom});
       if(!card)throw Error('No visible proposal');
       const r=card.getBoundingClientRect();return {x,y:r.top+r.height/2};
     }
     return {x,y};
   });
   await finger.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[point]});
   for(let i=1;i<=8;i++)await finger.send('Input.dispatchTouchEvent',{
     type:'touchMove',touchPoints:[{x:point.x,y:point.y+distance*i/8}]
   });
   await finger.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
 }
 try {
   await expect(cards.first()).toBeInViewport();
   const start=await story.evaluate(el=>el.scrollTop);
   for(let i=0;i<6;i++){
     await dragCard(-110);
     if(await cards.last().evaluate(n=>n.getBoundingClientRect().bottom<=document.querySelector('.story-scroll')!.getBoundingClientRect().bottom))break;
   }
   await expect(cards.last()).toBeInViewport({ratio:.9});
   await expect.poll(()=>story.evaluate(el=>el.scrollTop)).toBeGreaterThan(start+40);
   await expect(panel).toHaveAttribute('data-stop','2');
   await expect(draft).toHaveValue('');
   const bottom=await story.evaluate(el=>el.scrollTop);
   await dragCard(145);
   await expect.poll(()=>story.evaluate(el=>el.scrollTop)).toBeLessThan(bottom-35);
   await toggle.scrollIntoViewIfNeeded();
   await toggle.tap();
   await expect(panel).toHaveAttribute('data-stop','0');
   await expect(toggle).toHaveAttribute('aria-expanded','false');
   await toggle.tap();
   await expect(panel).toHaveAttribute('data-stop','1');
   const body=panel.locator('.action-panel-body');
   const box=await body.boundingBox();
   if(!box)throw Error('Compact list is hidden');
   await scrollByTouch(page,body,-Math.min(85,box.height*.6),{from:.4});
   await expect.poll(()=>body.evaluate(el=>el.scrollTop)).toBeGreaterThan(0);
   await expect(panel).toHaveAttribute('data-stop','1');
   // On Android, a tap during native momentum first brakes the list.
   await body.evaluate(el=>new Promise<void>(resolve=>{
     let previous=-1, stable=0;
     function frame(){
       const top=el.scrollTop;
       stable=top===previous?stable+1:0;
       previous=top;
       if(stable>=5)resolve();else requestAnimationFrame(frame);
     }
     requestAnimationFrame(frame);
   }));
   await toggle.tap();
   await expect(panel).toHaveAttribute('data-stop','2');
   await expect(draft).toBeInViewport();
   await cards.last().tap();
   await expect(draft).toHaveValue('Рассмотреть страницу 10: «Помнишь эту фотографию у окна? Я думал, она осталась у тебя.»');
   await draft.fill('Подойти к окну.');
   await expect(draft).toHaveValue('Подойти к окну.');
   expect((await (await request.get(path)).json()).revision).toBe(save.revision);
 } finally {await finger.detach()}
});

test('proposal types, confirmation, exact editable speech and a single pending submission', async ({page, request}, info) => {
  const selection = await (await request.post('/test/choices-seed')).json();
  const path = '/api/saves/' + selection.save;
  const save = await (await request.get(path)).json();
  const turn = save.turns.find((row:{id:number}) => row.id === save.physical_choice_source.turn_id);
  const action = 'Позвать Соню';
  const speech = 'Сонь…  Слышишь?\nЯ здесь.';
  const exact = action + ': «' + speech + '»';
  turn.choices = [{action, speech}, {action:'Подвинуть чашку.', speech:''}, ...turn.choices];
  await page.route('**' + path, route => route.fulfill({json:save}));
  await page.addInitScript(s => localStorage.setItem('selection',JSON.stringify(s)),selection);
  if (info.project.name === 'mobile') await page.setViewportSize({width:320,height:690});
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.goto('/');
  const cards = page.locator('.choices button'), spoken = cards.first(), silent = cards.nth(1);
  const draft = page.getByLabel('Своё действие или реплика');
  await expect(spoken.locator('strong')).toHaveText(action);
  expect(await spoken.locator('.choice-speech').textContent()).toBe('«' + speech + '»');
  await expect(silent.locator('.choice-speech')).toHaveCount(0);
  expect((await silent.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await spoken.focus();
  await page.keyboard.press('Enter');
  await expect(spoken).toHaveAttribute('aria-pressed','true');
  await expect(draft).toHaveValue(exact);
  await silent.click();
  await page.getByRole('button',{name:'Отмена',exact:true}).click();
  await expect(silent).toHaveAttribute('aria-pressed','false');
  await expect(spoken).toHaveAttribute('aria-pressed','true');
  await draft.fill('Своими словами.');
  await expect(spoken).toHaveAttribute('aria-pressed','false');
  await spoken.click();
  await page.getByRole('button',{name:'Заменить черновик'}).click();
  const requests:string[] = [];
  let release!: () => void;
  const responseGate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**' + path + '/turns', async route => {
    requests.push(route.request().postDataJSON().text);
    await responseGate;
    await route.fulfill({status:503,json:{detail:'Контрольная пауза связи'}});
  });
  try {
    await draft.press('Control+Enter');
    await expect(spoken).toHaveAttribute('aria-busy','true');
    await expect(silent).toBeDisabled();
    await draft.press('Control+Enter');
    await expect(page.getByLabel('Отправить действие')).toBeDisabled();
    expect(requests).toEqual([exact]);
  } finally { release(); }
  await expect(spoken).toBeEnabled();
  await expect(spoken).not.toHaveAttribute('aria-busy','true');
  await expect(draft).toHaveValue(exact);
  await expect(spoken).toHaveAttribute('aria-pressed','true');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
});
