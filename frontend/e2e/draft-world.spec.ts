import {test,expect} from '@playwright/test';
import {nav} from './navigation';
for(const width of [360,390,412,430,1280,1440,1920]){
 test(`world draft creation and editor ${width}`,async({page,request})=>{
  await page.setViewportSize({width,height:900});
  const workspace=await (await request.post('/api/workspaces',{data:{name:`Черновик ${width}`}})).json();
  await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),workspace.id);
  await page.goto('/');await nav(page,'Создать');
  await page.getByLabel('Описание мира или текст импорта').fill('Драмеди. Восемь соседей собрались на кухне; один скрывает встречу у маяка. Сохрани направленные отношения.');
  await page.getByRole('button',{name:'Развить идею и создать мир',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Посмотри, что получилось'})).toBeVisible();
  await expect(page.locator('main')).not.toContainText('Тайная встреча у маяка');
  await expect(page.locator('.workshop-view')).toContainText('Игрок');
  await page.locator('.workshop-tabs').getByRole('button',{name:'Начало',exact:true}).click();
  await expect(page.locator('.workshop-content')).toContainText('Кухня');
  await page.locator('.workshop-tabs').getByRole('button',{name:'Места и факты',exact:true}).click();
  await expect(page.locator('.workshop-content')).not.toContainText('Тайная встреча у маяка');
  await page.locator('.workshop-tabs').getByRole('button',{name:'Обзор',exact:true}).click();
  await expect(page.locator('.workshop-overview-grid')).toContainText('Главный герой');
  await page.getByRole('button',{name:'Автор мира',exact:true}).click();
  await page.getByRole('button',{name:'Показать всё',exact:true}).click();
  await page.locator('.workshop-tabs').getByRole('button',{name:'Персонажи',exact:true}).click();
  const first=page.locator('.workshop-person').first();
  await first.getByRole('button',{name:'Изменить fields.Внешность',exact:true}).click();
  await page.getByRole('dialog').getByLabel('Внешность',{exact:true}).fill('Рыжие волосы, зелёный шарф.');
  await page.getByRole('button',{name:'Сохранить поле',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  const draft=await (await request.get(`/api/workspaces/${workspace.id}/draft?author=true`)).json();
  expect(draft.state.characters[0].fields.Внешность).toContain('зелёный шарф');
  const exported=await request.get(`/api/workspaces/${workspace.id}/draft/export?version_id=${draft.version_id}&format=txt`);
  expect(exported.ok()).toBeTruthy();expect(await exported.text()).toContain('зелёный шарф');
  await page.evaluate(()=>{window.scrollTo(0,0);document.querySelector('.world-workshop')?.scrollTo(0,0)});
  const geometry=await page.evaluate(()=>({left:scrollX,document:document.documentElement.scrollWidth,body:document.body.scrollWidth,viewport:innerWidth,workshop:document.querySelector('.world-workshop')?.scrollWidth,client:document.querySelector('.world-workshop')?.clientWidth}));
  expect(geometry.left,JSON.stringify(geometry)).toBe(0);
  expect(geometry.body,JSON.stringify(geometry)).toBeLessThanOrEqual(geometry.viewport);
  expect(geometry.document,JSON.stringify(geometry)).toBeLessThanOrEqual(geometry.viewport);
  expect(geometry.workshop,JSON.stringify(geometry)).toBeLessThanOrEqual(geometry.client!+1);
  await page.screenshot({path:`test-results/draft-${width}.png`,fullPage:false});
  await page.reload();await nav(page,'Создать');
  await expect(page.getByRole('heading',{name:'Посмотри, что получилось'})).toBeVisible();
  await page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true}).click();
  await page.getByRole('button',{name:'Подтвердить и открыть игру',exact:true}).click();
  await expect(page.getByRole('button',{name:'Начать игру',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Начать игру',exact:true}).click();
  await expect(page.locator('.choices button')).toHaveCount(6);
 });
}

test('new visitor can begin with an idea without making a workspace', async ({page}) => {
  await page.goto('/');
  await nav(page,'Создать');
  await expect(page.getByRole('heading',{name:'Придумай свою историю'})).toBeVisible();
  await page.getByLabel('Название черновика').fill('Вечер в клинике');
  await page.getByLabel('Описание мира или текст импорта').fill('Вечером врач заканчивает дежурство. Придумай коллег, привычки, отношения и начало истории.');
  await page.getByRole('button',{name:'Развить идею и создать мир'}).click();
  await expect(page.getByRole('heading',{name:'Посмотри, что получилось'})).toBeVisible();
  await expect(page.locator('.workshop-content')).toBeVisible();
  await expect(page.locator('main')).not.toContainText('Тайная встреча у маяка');
  await page.reload();await nav(page,'Создать');
  await expect(page.getByRole('heading',{name:'Посмотри, что получилось'})).toBeVisible();
});

test('draft trash and responsive workshop width', async ({page,request}) => {
  const kept=await (await request.post('/api/workspaces',{data:{name:'Оставить этот черновик'}})).json();
  const removed=await (await request.post('/api/workspaces',{data:{name:'Удалить этот черновик'}})).json();
  await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),removed.id);
  await page.setViewportSize({width:1920,height:900});
  await page.goto('/');await nav(page,'Создать');
  const workshop=page.locator('.world-workshop');
  const row=workshop.locator(`.workshop-draft-list [data-workspace-id="${removed.id}"]`);
  await expect.poll(()=>workshop.evaluate(node=>node.getBoundingClientRect().width)).toBeGreaterThan(1200);
  await workshop.locator('.workshop-continue > summary').click();
  await row.getByRole('button',{name:'Удалить черновик «Удалить этот черновик»'}).click();
  await expect(page.getByRole('dialog')).toContainText('Готовые игровые сохранения не затрагиваются');
  await page.getByRole('dialog').getByRole('button',{name:'Удалить',exact:true}).click();
  await expect(row).toHaveCount(0);
  expect((await (await request.get('/api/workspaces')).json()).map((item:{id:string})=>item.id)).toContain(kept.id);
  await workshop.locator('.workshop-trash > summary').click();
  await workshop.locator(`.workshop-trash [data-workspace-id="${removed.id}"]`).getByRole('button',{name:'Восстановить'}).click();
  await expect(row).toBeVisible();
  await page.setViewportSize({width:390,height:844});
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

for (const extension of ['md', 'txt', 'json']) {
 test(`world file import ${extension} opens existing editor`, async ({page,request}) => {
  const seed=await (await request.post('/test/seed')).json();
  const world=await (await request.get(`/api/worlds/${seed.world}`)).json();
  const source=await (await request.post('/api/workspaces',{data:{name:'Источник импорта'}})).json();
  const prepared=await request.post(`/api/workspaces/${source.id}/draft/import`,{data:{revision:source.revision,text:world.source_md}});
  expect(prepared.ok()).toBeTruthy();
  const draft=await (await request.get(`/api/workspaces/${source.id}/draft?author=true`)).json();
  const filename=`готовый-мир.${extension}`;
  const content=extension==='json' ? JSON.stringify(draft.state) : world.source_md;
  let importBody: Record<string,unknown> | undefined;
  let generationRequests=0;
  page.on('request', r => {
   if (r.url().endsWith('/draft/import')) importBody=r.postDataJSON();
   if (r.url().includes('/generate')) generationRequests++;
  });
  await page.goto('/'); await nav(page,'Создать');
  await page.getByRole('button',{name:'Импортировать',exact:true}).click();
  await page.getByLabel('Название черновика').fill(source.name);
  await expect(page.getByLabel('Файл мира')).toHaveAttribute('accept','.md,.txt,.json');
  await page.getByLabel('Файл мира').setInputFiles({name:filename,mimeType:extension==='json'?'application/json':'text/plain',buffer:Buffer.from(content,'utf8')});
  if (extension==='json') {
   await expect(page.getByRole('status')).toContainText(filename);
   await expect(page.getByLabel('Описание мира или текст импорта')).toHaveCount(0);
  } else await expect(page.getByLabel('Описание мира или текст импорта')).toHaveValue(content);
  await page.getByRole('button',{name:'Открыть в редакторе',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Посмотри, что получилось'})).toBeVisible();
  expect(importBody?.format).toBe(extension==='json'?'json':'text');
  expect(importBody?.text).toBe(content);
  expect(generationRequests).toBe(0);
  await page.getByRole('button',{name:'Автор мира',exact:true}).click();
  await page.getByRole('button',{name:'Показать всё',exact:true}).click();
  await page.locator('.workshop-tabs').getByRole('button',{name:'Ещё',exact:true}).click();
  const downloadPromise=page.waitForEvent('download');
  await page.getByRole('button',{name:'Экспорт JSON',exact:true}).click();
  const download=await downloadPromise;
  expect(download.suggestedFilename()).toBe('world.json');
  const stream=await download.createReadStream();
  const chunks: Buffer[]=[];
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
  const exported=JSON.parse(Buffer.concat(chunks).toString('utf8'));
  expect(exported).toEqual(draft.state);
 });
}

for (const input of ['state', 'wrapper', 'markdown', 'broken']) {
 test(`pasted world import ${input} detects format`, async ({page,request}) => {
  const seed=await (await request.post('/test/seed')).json();
  const world=await (await request.get(`/api/worlds/${seed.world}`)).json();
  const source=await (await request.post('/api/workspaces',{data:{name:'Ручной импорт'}})).json();
  const prepared=await request.post(`/api/workspaces/${source.id}/draft/import`,{data:{revision:source.revision,text:world.source_md}});
  expect(prepared.ok()).toBeTruthy();
  const draft=await (await request.get(`/api/workspaces/${source.id}/draft?author=true`)).json();
  const text=input==='markdown' ? world.source_md : input==='broken' ? '{"campaign":' :
   ` \n${JSON.stringify(input==='wrapper' ? {state:draft.state} : draft.state)}\n `;
  const bodies: Record<string,unknown>[]=[];
  let generationRequests=0;
  page.on('request', r => {
   if (r.url().endsWith('/draft/import')) bodies.push(r.postDataJSON());
   if (r.url().includes('/generate')) generationRequests++;
  });
  await page.goto('/');await nav(page,'Создать');
  await page.getByRole('button',{name:'Импортировать',exact:true}).click();
  await page.getByLabel('Название черновика').fill(source.name);
  const textarea=page.getByLabel('Описание мира или текст импорта');
  await textarea.fill(text);
  await expect(textarea).toBeVisible(); // Pasted JSON must remain editable.
  const submit=page.getByRole('button',{name:'Открыть в редакторе',exact:true});
  if (input==='broken') {
   await expect(page.getByRole('alert')).toContainText('Не удалось прочитать JSON: ошибка синтаксиса.');
   await expect(submit).toBeDisabled();
   expect(bodies).toHaveLength(0);
   // Correcting JSON recovers the canonical route without losing the textarea.
   await textarea.fill(JSON.stringify({state:draft.state}));
   await expect(page.getByRole('alert')).toHaveCount(0);
  }
  await expect(page.getByRole('status')).toContainText(input==='markdown' ? 'Распознано: текстовая выжимка' : 'Распознано: JSON World State');
  await submit.click();
  await expect(page.getByRole('heading',{name:'Посмотри, что получилось'})).toBeVisible();
  expect(bodies).toHaveLength(1);
  expect(bodies[0].format).toBe(input==='markdown' ? 'text' : 'json');
  expect(generationRequests).toBe(0);
  const wid=await page.evaluate(()=>localStorage.getItem('draftWorkspace'));
  const imported=await (await request.get(`/api/workspaces/${wid}/draft?author=true`)).json();
  expect(imported.state).toEqual(draft.state);
 });
}

for (const format of ['json','text']) {
 test(`workspace identity full lifecycle ${format} with stale storage`,async({page,request})=>{
  const seed=await (await request.post('/test/seed')).json();
  const world=await (await request.get(`/api/worlds/${seed.world}`)).json();
  const source=await (await request.post('/api/workspaces',{data:{name:'Источник identity'}})).json();
  expect((await request.post(`/api/workspaces/${source.id}/draft/import`,{data:{revision:source.revision,text:world.source_md}})).ok()).toBeTruthy();
  let canonical=await (await request.get(`/api/workspaces/${source.id}/draft?author=true`)).json();
  for (const [field,value] of [['location','Кухня'],['participants',[canonical.state.controlled_actor_id]]] as const) {
   const patched=await request.patch(`/api/workspaces/${source.id}/draft`,{data:{revision:canonical.revision,operation:'patch',kind:'scene',entity_id:canonical.state.camera.scene_id,field,value,warnings_ack:true}});
   expect(patched.ok()).toBeTruthy();canonical=await patched.json();
  }
  expect(canonical.validation.errors).toEqual([]);
  const markdown=await (await request.get(`/api/workspaces/${source.id}/draft/export?version_id=${canonical.version_id}&format=md`)).text();
  const stale='removed-workspace-identity';
  await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),stale);
  const calls:{id:string;method:string;path:string;author:string|null}[]=[];
  page.on('request',r=>{
   const u=new URL(r.url());const match=u.pathname.match(/^\/api\/workspaces\/([^/]+)\/draft(.*)$/);
   if(match)calls.push({id:match[1],method:r.method(),path:match[2],author:u.searchParams.get('author')});
  });
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');await nav(page,'Создать');
  const workshop=page.locator('.world-workshop');
  await expect(workshop).toHaveAttribute('aria-busy','false');
  await page.getByRole('button',{name:'Импортировать',exact:true}).click();
  const content=format==='json'?JSON.stringify(canonical.state):markdown;
  await page.getByLabel('Описание мира или текст импорта').fill(content);
  const createdPromise=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/workspaces'&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Открыть в редакторе',exact:true}).click();
  const created=await (await createdPromise).json();
  await expect(page.getByRole('heading',{name:'Посмотри, что получилось'})).toBeVisible();
  const invariant=async()=>{
   await expect(workshop).toHaveAttribute('data-workspace-id',created.id);
   await expect(workshop).toHaveAttribute('data-draft-workspace-id',created.id);
   await expect(workshop).toHaveAttribute('aria-busy','false');
   expect(await page.evaluate(()=>localStorage.getItem('draftWorkspace'))).toBe(created.id);
  };
  await invariant();
  await page.getByRole('button',{name:'Автор мира',exact:true}).click();
  await page.getByRole('button',{name:'Показать всё',exact:true}).click();
  await invariant();
  await page.locator('.workshop-tabs').getByRole('button',{name:'Персонажи',exact:true}).click();
  const person=page.locator('.workshop-person').first();
  await person.getByRole('button',{name:'Новая версия персонажа',exact:true}).click();
  await expect.poll(()=>calls.some(c=>c.id===created.id&&c.path==='/dependencies')).toBe(true);
  await page.keyboard.press('Escape');
  await person.getByRole('button',{name:'Изменить fields.Внешность',exact:true}).click();
  await page.getByRole('dialog').getByLabel('Внешность',{exact:true}).fill('Зелёный шарф — identity regression.');
  await page.getByRole('button',{name:'Сохранить поле',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);await invariant();
  await expect(person).toContainText('identity regression');
  await page.locator('.workshop-tabs').getByRole('button',{name:'Ещё',exact:true}).click();
  const downloadPromise=page.waitForEvent('download');
  await page.getByRole('button',{name:'Экспорт JSON',exact:true}).click();
  expect((await downloadPromise).suggestedFilename()).toBe('world.json');await invariant();
  await page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true}).click();
  await page.getByRole('button',{name:'Подтвердить и открыть игру',exact:true}).click();
  await expect(page.getByRole('button',{name:'Начать игру',exact:true})).toBeVisible();
  const imported=calls.find(c=>c.path==='/import')!;
  const author=calls.find(c=>c.method==='GET'&&c.path===''&&c.author==='true')!;
  const confirm=calls.find(c=>c.path==='/confirm')!;
  expect(imported.id).toBe(created.id);expect(author.id).toBe(imported.id);expect(confirm.id).toBe(imported.id);
  expect(calls.filter(c=>c.id!==stale).every(c=>c.id===created.id)).toBe(true);
  expect(calls.some(c=>c.method==='PATCH')).toBe(true);
  expect(calls.some(c=>c.path==='/export')).toBe(true);
  expect(errors).toEqual([]);
  await page.getByRole('button',{name:'Начать игру',exact:true}).click();
  await expect(page.locator('.choices button')).toHaveCount(6);
 });
}

test('late author GET cannot replace a newer player view or workspace identity',async({page,request})=>{
 const seed=await (await request.post('/test/seed')).json();
 const world=await (await request.get(`/api/worlds/${seed.world}`)).json();
 const created=await (await request.post('/api/workspaces',{data:{name:'Проверка гонки загрузки'}})).json();
 expect((await request.post(`/api/workspaces/${created.id}/draft/import`,{data:{revision:created.revision,text:world.source_md}})).ok()).toBeTruthy();
 const draft=await (await request.get(`/api/workspaces/${created.id}/draft?author=true`)).json();
 draft.state.campaign.description='AUTHOR_ONLY_IDENTITY_RACE';
 expect((await request.post(`/api/workspaces/${created.id}/draft/import`,{data:{revision:draft.revision,format:'json',text:JSON.stringify(draft.state)}})).ok()).toBeTruthy();
 await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),created.id);
 let release!:()=>void;const gate=new Promise<void>(resolve=>{release=resolve;});
 let delivered!:()=>void;const lateDelivered=new Promise<void>(resolve=>{delivered=resolve;});
 let observed!:()=>void;const authorRequested=new Promise<void>(resolve=>{observed=resolve;});
 await page.route(`**/api/workspaces/${created.id}/draft?author=true`,async route=>{
  const response=await route.fetch();observed();await gate;
  await route.fulfill({response}).catch(()=>{});delivered(); // The frontend may have aborted this request.
 });
 await page.goto('/');await nav(page,'Создать');
 const workshop=page.locator('.world-workshop');
 await expect(page.getByRole('heading',{name:'Посмотри, что получилось'})).toBeVisible();
 await expect(workshop).toHaveAttribute('aria-busy','false');
 await page.getByRole('button',{name:'Автор мира',exact:true}).click();
 await page.getByRole('button',{name:'Показать всё',exact:true}).click();
 await authorRequested;
 await expect(page.getByRole('heading',{name:'Посмотри, что получилось'})).toBeVisible();
 await page.getByRole('button',{name:'Игрок',exact:true}).click();
 await expect(workshop).toHaveAttribute('aria-busy','false');release();await lateDelivered;
 await expect(page.getByRole('button',{name:'Игрок',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(workshop).toHaveAttribute('data-workspace-id',created.id);
 await expect(workshop).toHaveAttribute('data-draft-workspace-id',created.id);
 await expect(workshop).not.toContainText('AUTHOR_ONLY_IDENTITY_RACE');
 expect(await page.evaluate(()=>localStorage.getItem('draftWorkspace'))).toBe(created.id);
});
