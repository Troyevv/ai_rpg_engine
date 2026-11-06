import {test,expect} from '@playwright/test';

test.afterEach(async({request})=>{
  expect((await request.post('/test/letter130-reset')).ok()).toBeTruthy();
});

test('130 reader sees authored letter but character reads canonical text only after delivery', async({page,request})=>{
  const secret='SEALED-130: Встреча у башни, пароль — янтарь.';
  const seed=await(await request.post('/test/letter130-seed')).json();
  await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),seed);
  const received:string[]=[];
  page.on('console',m=>received.push(m.text()));
  page.on('response',async r=>{
    if(r.url().includes('/api/')){try{received.push(await r.text());}catch{}}
  });
  const view=async()=>await(await request.get(`/api/saves/${seed.save}`)).json();
  await page.goto('/');
  await page.getByRole('button',{name:'Начать игру',exact:true}).click();
  await expect.poll(async()=>(await view()).job?.status).toBe('saved');
  await request.post('/test/letter130-arm');
  await page.getByLabel('Своё действие или реплика').fill('Жду.');
  const initial=(await view()).revision;
  await page.getByRole('button',{name:'Отправить действие',exact:true}).click();
  await expect.poll(async()=>{const v=await view();return v.job?.status==='generating' && v.job?.narrative?.includes('Гонец');}).toBeTruthy();
  await expect.poll(async()=>{const v=await view();return v.job?.status==='generating' && (await page.locator('body').innerText()).includes('SEALED-130');}).toBeTruthy();
  await expect(page.locator('.narrative-letter').filter({hasText:'SEALED-130'})).toBeVisible();
  await expect(page.locator('.narrative-text').last()).not.toContainText('```letter');
  expect((await request.post('/test/letter130-release')).ok()).toBeTruthy();
  await expect.poll(async()=>(await view()).revision).toBeGreaterThan(initial);
  await expect.poll(async()=>(await view()).job.status).toBe('saved');
  await expect(page.locator('body')).toContainText(secret);
  await expect.poll(()=>received.join('\n')).toContain(secret);
  await expect(page.locator('.narrative-letter').filter({hasText:secret})).toBeVisible();
  await expect(page.locator('code.language-letter')).toHaveCount(0);
  let v=await view();
  const response=await request.post(`/api/saves/${seed.save}/turns`,{data:{kind:'turn',text:'Жду почту.',revision:v.revision,config:{model:'test-model',provider:'local',context_length:131072,max_tokens:8000,update_tokens:8000},time_skip:{duration:20,reason:'Жду почту'}}});
  expect(response.ok()).toBeTruthy();
  const jid=(await response.json()).id;
  await expect.poll(async()=>(await(await request.get(`/api/jobs/${jid}`)).json()).status).toBe('saved');
  await page.reload();
  const mail=await(await request.get(`/api/saves/${seed.save}/correspondence`)).json();
  expect(mail).toHaveLength(1);expect(mail[0].unread).toBe(true);expect(mail[0].content).toBeUndefined();
  await expect(page.locator('body')).toContainText(secret);
  await expect.poll(()=>received.join('\n')).toContain(secret);
  v=await view();
  const opened=await request.post(`/api/saves/${seed.save}/correspondence`,{data:{revision:v.revision,command:{action:'read',event_id:mail[0].id,operation_id:'browser-open-130'}}});
  expect(opened.ok()).toBeTruthy();
  expect((await(await request.get(`/api/saves/${seed.save}/correspondence`)).json())[0].content).toBe(secret);
});

test('130 long authored letter survives rendering reload and canonical reading without truncation', async({page,request})=>{
  const seed=await(await request.post('/test/letter130-seed')).json();
  await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),seed);
  const view=async()=>await(await request.get(`/api/saves/${seed.save}`)).json();
  await page.goto('/');
  await page.getByRole('button',{name:'Начать игру',exact:true}).click();
  await expect.poll(async()=>(await view()).job?.status).toBe('saved');
  const {content}=await(await request.post('/test/letter130-arm?size=35000')).json();
  await request.post('/test/letter130-release');
  const config={model:'handoff-test',provider:'local',context_length:131072,max_tokens:8000,update_tokens:8000};
  const start=await request.post(`/api/saves/${seed.save}/turns`,{data:{kind:'turn',text:'Жду.',revision:(await view()).revision,config}});
  expect(start.ok()).toBeTruthy();const jid=(await start.json()).id;
  await expect.poll(async()=>(await(await request.get(`/api/jobs/${jid}`)).json()).status).toBe('saved');
  await page.reload();
  const letter=page.locator('.narrative-letter');
  await expect(letter).toBeVisible();
  const displayed=content.replace(/\r\n/g,'\n')+'\n';
  await expect.poll(()=>letter.textContent()).toBe(displayed);
  await expect(page.locator('code.language-letter')).toHaveCount(0);
  const skip=await request.post(`/api/saves/${seed.save}/turns`,{data:{kind:'turn',text:'Жду почту.',revision:(await view()).revision,config,time_skip:{duration:20,reason:'Жду почту'}}});
  expect(skip.ok()).toBeTruthy();const skipId=(await skip.json()).id;
  await expect.poll(async()=>(await(await request.get(`/api/jobs/${skipId}`)).json()).status).toBe('saved');
  const mail=await(await request.get(`/api/saves/${seed.save}/correspondence`)).json();
  expect(mail[0].content).toBeUndefined();
  const revision=(await view()).revision;
  for(let i=0;i<2;i++) {
    const opened=await request.post(`/api/saves/${seed.save}/correspondence`,{data:{revision,command:{action:'read',event_id:mail[0].id,operation_id:'open-long-browser130'}}});
    expect(opened.ok()).toBeTruthy();
    expect((await(await request.get(`/api/saves/${seed.save}/correspondence`)).json())[0].content).toBe(content);
  }
  await page.reload();
  await expect.poll(()=>page.locator('.narrative-letter').textContent()).toBe(displayed);
});
