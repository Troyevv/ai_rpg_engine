import {test,expect} from '@playwright/test';
import {nav} from './navigation';

test('creation settings and JSON continuation survive editor start and reload',async({page,request})=>{
  const workspace=await(await request.post('/api/workspaces',{data:{name:'Runtime v4 settings'}})).json();
  await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),workspace.id);
  await page.goto('/');await nav(page,'Создать');
  await page.getByText('Настройки генератора',{exact:true}).click();
  await page.getByLabel('Основной жанр',{exact:true}).selectOption('family_saga');
  await page.getByLabel('Выразительность NPC',{exact:true}).selectOption('hyperbolized');
  await page.getByLabel('Темп истории',{exact:true}).selectOption('calm');
  await page.getByLabel('Риск последствий',{exact:true}).selectOption('safe');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(await page.evaluate(()=>innerWidth));
  await page.screenshot({path:`test-results/draft-v4-settings-${page.viewportSize()?.width}.png`,fullPage:true});
  await page.getByLabel('Описание мира или текст импорта').fill('TEST_JSON_CONTINUATION. Соседи разговаривают на кухне.');
  const sent=page.waitForRequest(r=>r.url().endsWith('/draft/generate'));
  await page.getByRole('button',{name:'Развить идею и создать мир',exact:true}).click();
  expect((await sent).postDataJSON().creation_settings.primary_genre).toBe('family_saga');
  await expect(page.getByRole('heading',{name:'Посмотри, что получилось'})).toBeVisible();
  const draft=await(await request.get(`/api/workspaces/${workspace.id}/draft?author=true`)).json();
  expect(draft.state.creation_settings.npc_expressiveness).toBe('hyperbolized');
  expect(draft.validation.errors).toEqual([]);
  const requests=await(await request.get(`/api/workspaces/${workspace.id}/requests`)).json();
  expect(requests.filter((r:{stage:string})=>r.stage==='draft_world')).toHaveLength(2);
  expect(requests.filter((r:{stage:string})=>r.stage==='draft_world_validation')).toHaveLength(1);
  expect(requests.some((r:{finish_reason:string,status:string})=>r.finish_reason==='length' || r.status==='length')).toBeTruthy();
  expect(draft.job).not.toHaveProperty('response_journal');
  await page.reload();await nav(page,'Создать');
  await page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true}).click();
  await page.getByRole('button',{name:'Подтвердить и открыть игру',exact:true}).click();
  await page.getByRole('button',{name:'Начать игру',exact:true}).click();
  await expect(page.locator('.choices button')).toHaveCount(6);
  await page.reload();
  await expect(page.locator('.choices button')).toHaveCount(6);
});

test('failed world remains editable and starts without regeneration',async({page,request})=>{
  const workspace=await(await request.post('/api/workspaces',{data:{name:'Candidate recovery'}})).json();
  await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),workspace.id);
  await page.goto('/');await nav(page,'Создать');
  await page.getByLabel('Описание мира или текст импорта').fill('TEST_CANDIDATE_RECOVERY. Соседи на кухне.');
  await page.getByRole('button',{name:'Развить идею и создать мир',exact:true}).click();
  const url=`/api/workspaces/${workspace.id}/draft`;
  await expect.poll(async()=> (await(await request.get(url)).json()).job?.status).toBe('error');
  await page.reload();await nav(page,'Создать');
  await page.getByRole('button',{name:'Открыть результат в редакторе автора'}).click();
  await page.getByRole('button',{name:'Показать всё',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('heading',{name:'Восстановление черновика'})).toBeVisible();
  const before=await(await request.get(url+'?author=true')).json();
  await page.getByRole('button',{name:'Исправить поле',exact:true}).first().click();
  await page.getByLabel('Путь поля кандидата').fill('/protagonist_id');
  await page.getByLabel('Значение поля кандидата JSON').fill(JSON.stringify(before.candidate.controlled_actor_id));
  await page.getByRole('button',{name:'Сохранить исправление',exact:true}).click();
  await page.getByRole('button',{name:'Повторить проверку',exact:true}).click();
  await expect(page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true})).toBeEnabled();
  await page.screenshot({path:`test-results/draft-recovery-${page.viewportSize()?.width}.png`,fullPage:true});
  const after=await(await request.get(url+'?author=true')).json();
  expect(after.state.world.facts).toEqual(before.candidate.world.facts);
  await page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true}).click();
  await page.getByRole('button',{name:'Подтвердить и открыть игру',exact:true}).click();
  await page.getByRole('button',{name:'Начать игру',exact:true}).click();
  await expect(page.locator('.choices button')).toHaveCount(6);
});

test('review protocol failure survives reload and resumes only review',async({page,request},info)=>{
  const workspace=await(await request.post('/api/workspaces',{data:{name:'Reviewer recovery'}})).json();
  const url=`/api/workspaces/${workspace.id}/draft`;
  await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),workspace.id);
  await page.goto('/');await nav(page,'Создать');
  await page.getByLabel('Описание мира или текст импорта').fill(`TEST_REVIEW_PROTOCOL ${info.project.name}. Соседи на кухне.`);
  await page.getByRole('button',{name:'Развить идею и создать мир',exact:true}).click();
  await expect.poll(async()=> (await(await request.get(url)).json()).job?.status).toBe('error');
  await page.reload();await nav(page,'Создать');
  await expect(page.getByRole('heading',{name:'Смысловая проверка не завершена'})).toBeVisible();
  await page.getByRole('button',{name:'Открыть результат в редакторе автора'}).click();
  await page.getByRole('button',{name:'Показать всё',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByLabel('Путь поля кандидата')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Исправить поле',exact:true})).toHaveCount(0);
  await page.screenshot({path:`test-results/reviewer-failure-${info.project.name}.png`,fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(await page.evaluate(()=>innerWidth));
  const before=await(await request.get(url+'?author=true')).json();
  await page.getByRole('button',{name:'Повторить проверку',exact:true}).click();
  await expect.poll(async()=> (await(await request.get(url)).json()).job?.status).toBe('saved');
  const after=await(await request.get(url+'?author=true')).json();
  expect(after.state.world.facts).toEqual(before.candidate.world.facts);
  const requests=await(await request.get(`/api/workspaces/${workspace.id}/requests`)).json();
  expect(requests.filter((r:{stage:string})=>r.stage==='draft_world')).toHaveLength(1);
  expect(requests.filter((r:{stage:string})=>r.stage==='draft_world_validation')).toHaveLength(4);
  await expect(page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true})).toBeEnabled();
  await page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true}).click();
  await page.getByRole('button',{name:'Подтвердить и открыть игру',exact:true}).click();
  await page.getByRole('button',{name:'Начать игру',exact:true}).click();
  await expect(page.locator('.choices button')).toHaveCount(6);
  await page.reload();await expect(page.locator('.choices button')).toHaveCount(6);
});

test('structured motivations render and edit without losing lifecycle metadata',async({page,request})=>{
  const workspace=await(await request.post('/api/workspaces',{data:{name:'Structured motivations'}})).json();
  const url=`/api/workspaces/${workspace.id}/draft`;
  await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),workspace.id);
  await page.goto('/');await nav(page,'Создать');
  await page.getByLabel('Описание мира или текст импорта').fill('TEST_MOTIVATION_OBJECTS. Сохрани заданные цели и намерения.');
  await page.getByRole('button',{name:'Развить идею и создать мир',exact:true}).click();
  await expect.poll(async()=> (await(await request.get(url)).json()).job?.status).toBe('saved');
  await page.getByRole('group',{name:'Разделы мира'}).getByRole('button',{name:'Персонажи',exact:true}).click();
  await expect(page.getByText('Цели: Текущая goals',{exact:true})).toBeVisible();
  await expect(page.getByText('[object Object]',{exact:false})).toHaveCount(0);
  await page.getByRole('button',{name:'Автор мира',exact:true}).click();
  await page.getByRole('button',{name:'Показать всё',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByText('Состояние, цели и намерения',{exact:true}).click();
  const before=await(await request.get(url+'?author=true')).json();
  const cid=before.state.protagonist_id;
  for (const [field,label] of [['goals','Цели'],['intentions','Намерения'],['obligations','Обязательства']]) {
    await page.getByRole('button',{name:`Изменить ${label}`,exact:true}).click();
    const input=page.getByRole('dialog').getByLabel(label,{exact:true});
    const records=JSON.parse(await input.inputValue());
    expect(records).toEqual(before.state.world.characters[cid][field]);
    records[0].text=`Редактирование ${field}`;
    await input.fill(JSON.stringify(records,null,2));
    await page.getByRole('button',{name:'Сохранить поле',exact:true}).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect.poll(async()=> (await(await request.get(url+'?author=true')).json()).state.world.characters[cid][field]).toEqual(records);
  }
  await page.getByRole('button',{name:'Повторить проверку',exact:true}).click();
  await expect.poll(async()=> (await(await request.get(url)).json()).job?.status).toBe('saved');
  await page.screenshot({path:`test-results/motivations-${page.viewportSize()?.width}.png`,fullPage:true});
  await page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true}).click();
  const confirm=page.waitForResponse(r=>r.url().endsWith('/draft/confirm'));
  await page.getByRole('button',{name:'Подтвердить и открыть игру',exact:true}).click();
  const {save}=await(await confirm).json();
  await page.getByRole('button',{name:'Начать игру',exact:true}).click();
  await expect(page.locator('.choices button')).toHaveCount(6);
  await page.reload();await expect(page.locator('.choices button')).toHaveCount(6);
  // API save-load path is exercised here; canonical metadata is asserted by backend smoke.
  expect((await request.get(`/api/saves/${save}`)).ok()).toBeTruthy();
});


test('fragment recovery survives reload and repeats only rejected continuation',async({page,request},info)=>{
  const workspace=await(await request.post('/api/workspaces',{data:{name:'Fragment recovery'}})).json();
  const url=`/api/workspaces/${workspace.id}/draft`;
  await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),workspace.id);
  await page.goto('/');await nav(page,'Создать');
  await page.getByLabel('Описание мира или текст импорта').fill(`TEST_FRAGMENT_RECOVERY ${info.project.name}. Соседи на кухне.`);
  await page.getByRole('button',{name:'Развить идею и создать мир',exact:true}).click();
  await expect.poll(async()=> (await(await request.get(url)).json()).job?.status).toBe('error');
  const before=await(await request.get(url+'/raw')).json();
  await page.reload();await nav(page,'Создать');
  await expect(page.getByRole('heading',{name:'Восстановление ответа'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Открыть результат в редакторе автора'})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Исправить поле',exact:true})).toHaveCount(0);
  await page.getByText('Повторить проблемное продолжение',{exact:true}).click();
  await page.screenshot({path:`test-results/fragment-recovery-${info.project.name}.png`,fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(await page.evaluate(()=>innerWidth));
  await page.getByRole('button',{name:'Запросить только последнее продолжение',exact:true}).click();
  await expect.poll(async()=> (await(await request.get(url)).json()).job?.status).toBe('saved');
  const after=await(await request.get(url+'/raw')).json();
  expect(after.responses.world.parts[0]).toEqual(before.responses.world.parts[0]);
  expect(after.fragment_recoveries[0].part).toEqual(before.responses.world.parts[1]);
  expect(after.responses.world.parts).toHaveLength(2);
  await page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true}).click();
  await page.getByRole('button',{name:'Подтвердить и открыть игру',exact:true}).click();
  await page.getByRole('button',{name:'Начать игру',exact:true}).click();
  await expect(page.locator('.choices button')).toHaveCount(6);
  await page.reload();await expect(page.locator('.choices button')).toHaveCount(6);
});

test('previous world is labelled separately from an incomplete new response',async({page,request},info)=>{
  const seed=await(await request.post('/test/seed')).json();
  const source=await(await request.get(`/api/worlds/${seed.world}`)).json();
  const w=await(await request.post('/api/workspaces',{data:{name:'Previous world'}})).json();
  const url=`/api/workspaces/${w.id}/draft`;
  expect((await request.post(url+'/import',{data:{revision:0,text:source.source_md}})).ok()).toBeTruthy();
  await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),w.id);
  await page.goto('/');await nav(page,'Создать');
  await page.getByRole('button',{name:'Изменить замысел',exact:true}).click();
  await page.getByLabel('Описание мира или текст импорта').fill(`TEST_FRAGMENT_RECOVERY previous ${info.project.name}. Новый мир.`);
  await page.getByRole('button',{name:'Создать новую версию мира',exact:true}).click();
  await expect.poll(async()=> (await(await request.get(url)).json()).job?.status).toBe('error');
  await page.reload();await nav(page,'Создать');
  await expect(page.getByRole('heading',{name:'Ранее сохранённый мир',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Посмотри, что получилось',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Начать игру в предыдущем мире',exact:true})).toBeVisible();
  await page.getByText('Повторить проблемное продолжение',{exact:true}).click();
  await page.getByRole('button',{name:'Запросить только последнее продолжение',exact:true}).click();
  await expect.poll(async()=> (await(await request.get(url)).json()).job?.status).toBe('saved');
  await expect(page.getByRole('heading',{name:'Посмотри, что получилось',exact:true})).toBeVisible();
});

test('saved symmetric duplicates offer lossless merge after reconnect',async({page,request},info)=>{
  const workspace=await(await request.post('/api/workspaces',{data:{name:'Relation merge '+info.project.name}})).json();
  const url=`/api/workspaces/${workspace.id}/draft`;
  await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),workspace.id);
  await page.goto('/');await nav(page,'Создать');
  await page.getByLabel('Описание мира или текст импорта').fill('TEST_REVIEW_PROTOCOL sibling '+info.project.name);
  await page.getByRole('button',{name:'Развить идею и создать мир',exact:true}).click();
  await expect.poll(async()=> (await(await request.get(url)).json()).job?.status).toBe('error');
  const d=await(await request.get(url+'?author=true')).json();
  const [a,b]=d.candidate.characters.map((c:{id:string})=>c.id);
  const relation={id:'a',kind:'sibling',source_id:a,target_id:b,context:'Брат и сестра'};
  await request.patch(url+'/candidate',{data:{revision:d.revision,path:'/world/objective_relations',value:{a:relation,b:{...relation,id:'b',source_id:b,target_id:a,context:'Сестра и брат'}}}});
  await page.reload();await nav(page,'Создать');
  await page.getByRole('button',{name:'Открыть результат в редакторе автора',exact:true}).click();
  await page.getByRole('button',{name:'Показать всё',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Две записи одной связи'})).toBeVisible();
  await expect(page.getByText('/world/objective_relations/a',{exact:true})).toBeVisible();
  await expect(page.getByText('/world/objective_relations/b',{exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(await page.evaluate(()=>innerWidth));
  await page.screenshot({path:`test-results/relation-merge-${info.project.name}.png`,fullPage:true});
  await page.getByRole('button',{name:'Объединить связи',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Две записи одной связи'})).toHaveCount(0);
  const merged=await(await request.get(url+'?author=true')).json();
  expect(Object.keys(merged.candidate.world.objective_relations)).toEqual(['a']);
  expect(merged.candidate.world.objective_relations.a.context).toBe('Брат и сестра\nСестра и брат');
  expect(merged.review.status).toBe('stale');
  await page.getByRole('button',{name:'Повторить проверку',exact:true}).click();
  await expect(page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true})).toBeEnabled();
});


test('malformed review automatically reaches a playable draft through alternate audit',async({page,request},info)=>{
  const w=await(await request.post('/api/workspaces',{data:{name:'Automatic report recovery'}})).json();
  await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),w.id);
  await page.goto('/');await nav(page,'Создать');
  await page.getByLabel('Описание мира или текст импорта').fill(`TEST_REVIEW_AUTOMATIC ${info.project.name}`);
  await page.getByRole('button',{name:'Развить идею и создать мир',exact:true}).click();
  await expect.poll(async()=> (await(await request.get(`/api/workspaces/${w.id}/draft`)).json()).job?.status).toBe('saved');
  await page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true}).click();
  await page.getByRole('button',{name:'Подтвердить и открыть игру',exact:true}).click();
  await page.getByRole('button',{name:'Начать игру',exact:true}).click();
  await expect(page.locator('.choices button')).toHaveCount(6);
});

for (const marker of ['TEST_RELEASE_NESTED','TEST_RELEASE_QUALITY']) {
 test(`release untrusted response ${marker} preserves ready world`,async({page,request},info)=>{
  const w=await(await request.post('/api/workspaces',{data:{name:'Release protocol'}})).json();const url=`/api/workspaces/${w.id}/draft`;
  await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),w.id);
  await page.goto('/');await nav(page,'Создать');
  await page.getByLabel('Описание мира или текст импорта').fill(`${marker} ${info.project.name}. Соседи разговаривают на кухне.`);
  await page.getByRole('button',{name:'Развить идею и создать мир',exact:true}).click();
  await expect.poll(async()=> (await(await request.get(url)).json()).job?.status).toBe('saved');
  const raw=await(await request.get(url+'/raw')).json();
  if(marker==='TEST_RELEASE_QUALITY'){
   expect(raw.quality.status).toBe('partial');
   await expect(page.getByText(/Некоторые творческие детали модель оставила неполными/)).toBeVisible();
  }else expect(raw.review_failures.length).toBeGreaterThanOrEqual(2);
  expect(raw.requests.filter((r:{stage:string})=>r.stage==='draft_world')).toHaveLength(1);
  await expect(page.getByRole('button',{name:'Повторить проверку',exact:true})).toHaveCount(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(await page.evaluate(()=>innerWidth));
  await page.screenshot({path:`test-results/release-${marker}-${info.project.name}.png`,fullPage:true});
  await page.reload();await nav(page,'Создать');
  await page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true}).click();
  await page.getByRole('button',{name:'Подтвердить и открыть игру',exact:true}).click();
  await page.getByRole('button',{name:'Начать игру',exact:true}).click();
  await expect(page.locator('.choices button')).toHaveCount(6);
  await page.reload();await expect(page.locator('.choices button')).toHaveCount(6);
 });
}
