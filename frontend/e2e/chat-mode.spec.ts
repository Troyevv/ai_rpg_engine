import {chooseOption} from './choice-navigation';
import {test,expect,type Page,type Locator} from '@playwright/test';

async function updateMemory(page:Page,next=true){
  await expect(page.getByRole('dialog')).toHaveCount(0);
  const action=page.getByRole('button',{name:next?'Обновить выжимку и продолжить':'Обновить выжимку',exact:true});
  if(!await action.isVisible())await page.getByRole('button',{name:'Действия кампании',exact:true}).click();
  await action.click();
}

async function createChat(page:Page, model='chat-fixture', waitComplete=true) {
  await page.goto('/');
  await page.getByRole('button',{name:'RP-чат',exact:true}).click();
  await page.getByRole('button',{name:'Новая RP-кампания',exact:true}).last().click();
  const dialog=page.getByRole('dialog');
  await dialog.getByRole('button',{name:'Использовать готовую выжимку',exact:true}).click();
  await dialog.getByLabel('Стартовая выжимка',{exact:true}).fill('Лена и Илья у маяка. Дата 9 октября. Тайну знает только Лена. Незавершённый разговор.');
  await dialog.getByLabel('Название кампании',{exact:true}).fill('Непрерывная история');
  await dialog.getByRole('group',{name:'Обычный RP-ответ'}).getByLabel('Модель',{exact:true}).fill(model);
  await dialog.getByText('Дополнительные настройки',{exact:true}).click();
  await dialog.getByRole('group',{name:'Обновление выжимки — отдельный вызов'}).getByLabel('Модель',{exact:true}).fill('chat-summary-fixture');
  await dialog.getByLabel('Подтверждаю первоначальную выжимку',{exact:true}).check();
  await dialog.getByRole('button',{name:'Начать игру',exact:true}).click();
  if(!waitComplete)return;
  await expect(page.getByRole('button',{name:'Остановить',exact:true})).toHaveCount(0);
  await expect(page.locator('.chat-assistant')).toHaveCount(1);
  await expect(page.getByLabel('Твоё сообщение',{exact:true})).toBeEnabled();
  await expect(page.getByRole('heading',{name:'Непрерывная история',exact:true})).toBeVisible();
}

for(const skin of ['graphite','parchment'])test(`Chat: campaign, stream, memory, chapters, edit and reload (${skin})`,async({page},info)=>{
  if(info.project.name==='mobile')await page.setViewportSize({width:360,height:780});
  await page.addInitScript(s=>localStorage.setItem('workshop-theme',JSON.stringify({theme_id:s,mode:'manual'})),skin);
  await createChat(page);
  await page.getByLabel('Твоё сообщение',{exact:true}).fill('Я оставляю обещанную книгу на столе. «Ты хотел сказать…»');
  await page.getByRole('button',{name:'Отправить',exact:true}).click();
  await expect(page.getByRole('button',{name:'Остановить',exact:true})).toBeVisible();
  await expect(page.locator('.chat-assistant').last()).toContainText('Лена ставит чашку');
  await expect(page.getByRole('button',{name:'Остановить',exact:true})).toHaveCount(0);
  await page.getByLabel('Твоё сообщение',{exact:true}).fill('Неотправленный ввод переживёт reload');
  await page.reload();
  await expect(page.getByLabel('Твоё сообщение',{exact:true})).toHaveValue('Неотправленный ввод переживёт reload');
  await updateMemory(page);
  const dialog=page.getByRole('dialog');
  await expect(dialog.getByRole('heading',{name:'Проверка новой выжимки'})).toBeVisible();
  await expect(dialog.getByLabel('Текст выжимки',{exact:true})).toContainText('Ошибочно считает:');
  const value=await dialog.getByLabel('Текст выжимки',{exact:true}).inputValue();
  await dialog.getByLabel('Текст выжимки',{exact:true}).fill(value+'\nАвторская проверка: дата и тайна сохранены.');
  await dialog.getByRole('button',{name:'Утвердить и продолжить',exact:true}).click();await expect(dialog.getByRole('heading',{name:'Журнал кампании',exact:true})).toBeVisible();await dialog.getByRole('button',{name:'Вернуться в игру',exact:true}).click();await expect(dialog).toHaveCount(0);
  await expect(page.locator('.chat-heading')).toContainText('Глава 2');
  await page.getByLabel('Твоё сообщение',{exact:true}).fill('Продолжай незавершённый разговор.');
  await page.getByRole('button',{name:'Отправить',exact:true}).click();
  await expect(page.locator('.chat-assistant')).toHaveCount(3);
  await page.locator('.chat-scroll').evaluate(el=>{el.scrollTop=0});
  await expect(page.getByRole('button',{name:'Остановить',exact:true})).toHaveCount(0);
  expect(await page.locator('.chat-scroll').evaluate(el=>el.scrollTop)).toBeLessThan(5);
  await page.getByLabel('Твоё сообщение',{exact:true}).fill('Черновик основной ветки');
  await page.getByRole('button',{name:'Главы и ветки',exact:true}).click();
  await dialog.getByRole('button',{name:'Глава 1 Архив · читать'}).click();
  await expect(page.getByRole('button',{name:'К активной главе',exact:true})).toBeVisible();
  await expect(page.getByLabel('Твоё сообщение',{exact:true})).toHaveCount(0);
  await page.locator('.chat-user').first().getByRole('button',{name:'Редактировать',exact:true}).click();
  await dialog.getByLabel('Новый текст',{exact:true}).fill('Я оставляю книгу у себя.');
  await dialog.getByRole('button',{name:'Сохранить как новую ветку',exact:true}).click();
  await expect(page.locator('.chat-message')).toHaveCount(2);
  await expect(page.locator('.chat-user')).toContainText('Я оставляю книгу у себя.');
  await expect(page.getByLabel('Твоё сообщение',{exact:true})).toHaveValue('');
  await page.getByLabel('Твоё сообщение',{exact:true}).fill('Черновик альтернативной ветки');
  await page.getByRole('button',{name:'Главы и ветки',exact:true}).click();
  await dialog.getByRole('button',{name:/Основная ветка/}).click();
  await expect(page.locator('.chat-message')).toHaveCount(5);
  await expect(page.getByLabel('Твоё сообщение',{exact:true})).toHaveValue('Черновик основной ветки');
  await page.getByRole('button',{name:'Выжимка',exact:true}).click();
  await dialog.getByRole('tab',{name:'Правка',exact:true}).click();
  await expect(dialog.getByLabel('Текст выжимки',{exact:true})).toHaveValue(/Авторская проверка/);
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  const box=await page.getByLabel('Твоё сообщение',{exact:true}).boundingBox();
  expect(box!.x).toBeGreaterThanOrEqual(0);expect(box!.y+box!.height).toBeLessThanOrEqual((await page.viewportSize())!.height);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
  await expect(page.locator('html')).toHaveAttribute('data-theme',skin);
  if(process.env.CHAT_QA_SCREENSHOTS)await page.screenshot({path:`/tmp/chat260-${info.project.name}-${skin}.png`});
});

test('Chat: stop, explicit retry, safe markdown, hard limit and no hidden replay',async({page,request})=>{
  await createChat(page);
  // The external fixture stream stays open until cancellation; no race against a short response.
  expect((await request.post('/test/chat-cancel-window')).ok()).toBeTruthy();
  await page.getByLabel('Твоё сообщение',{exact:true}).fill('<script>window.chatXss=true</script>');
  await page.getByRole('button',{name:'Отправить',exact:true}).click();
  await page.getByRole('button',{name:'Остановить',exact:true}).click();
  await expect(page.getByRole('button',{name:'Повторить явно (новый вызов)'})).toBeVisible();
  const stoppedId=await page.evaluate(()=>localStorage.getItem('chat-selection'));
  expect((await (await request.get(`/api/chat/campaigns/${stoppedId}`)).json()).job.status).toBe('stopped');
  await expect(page.locator('.chat-user')).toContainText('<script>');
  expect(await page.evaluate(()=>('chatXss' in window))).toBeFalsy();
  await page.reload();
  await expect(page.getByRole('button',{name:'Повторить явно (новый вызов)'})).toBeVisible();
  await page.getByRole('button',{name:'Повторить явно (новый вызов)'}).click();
  await expect(page.getByRole('button',{name:'Остановить',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Остановить',exact:true})).toHaveCount(0);
  await expect(page.locator('.chat-assistant').last()).toContainText('Лена ставит чашку');
  await page.getByLabel('Твоё сообщение',{exact:true}).fill('Очень большой ввод '.repeat(4000));
  await expect(page.getByRole('button',{name:'Отправить',exact:true})).toBeDisabled();
  await expect(page.getByText('Ввод не помещается в контекст.',{exact:false})).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Твоё сообщение',{exact:true})).toHaveValue(/Очень большой ввод/);
});

test('Chat: persisted draft review, settings, request receipts and browser Back',async({page,request},info)=>{
  await createChat(page);
  await page.getByLabel('Твоё сообщение',{exact:true}).fill('Начать сцену');
  await page.getByRole('button',{name:'Отправить',exact:true}).click();
  await expect(page.getByRole('button',{name:'Остановить',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Остановить',exact:true})).toHaveCount(0);
  await page.locator('.chat-assistant').last().getByRole('button',{name:'Запрос и расход',exact:true}).click();
  await page.getByRole('dialog').getByText('Записанный контекст и диагностика',{exact:true}).click();
  await expect(page.getByRole('dialog')).toContainText('prompt_tokens');
  await page.goBack();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await updateMemory(page,false);
  const dialog=page.getByRole('dialog');
  await expect(dialog.getByLabel('Текст выжимки',{exact:true})).toBeVisible();
  await dialog.getByLabel('Текст выжимки',{exact:true}).fill('Проверенный серверный черновик. Тайна остаётся у Лены.');
  await dialog.getByRole('button',{name:'Сохранить черновик',exact:true}).click();
  await page.reload();
  await page.getByRole('button',{name:'Черновик выжимки',exact:true}).click();
  await expect(dialog.getByLabel('Текст выжимки',{exact:true})).toHaveValue('Проверенный серверный черновик. Тайна остаётся у Лены.');
  await dialog.getByRole('button',{name:'Утвердить в этой главе',exact:true}).click();await expect(dialog.getByRole('heading',{name:'Журнал кампании',exact:true})).toBeVisible();await dialog.getByRole('button',{name:'Вернуться в игру',exact:true}).click();await expect(dialog).toHaveCount(0);
  await expect(page.locator('.chat-heading')).toContainText('Глава 1');
  await page.getByRole('button',{name:'Настройки RP-чата',exact:true}).click();
  await dialog.getByRole('group',{name:'Обычный RP-ответ'}).getByText('Дополнительные параметры модели',{exact:true}).click();
  await dialog.getByRole('group',{name:'Обычный RP-ответ'}).getByLabel('Температура',{exact:true}).fill('0.5');
  await dialog.getByRole('button',{name:'Сохранить настройки',exact:true}).click();
  await expect(dialog).toHaveCount(0);
  const id=await page.evaluate(()=>localStorage.getItem('chat-selection'));
  const campaign=await (await request.get(`/api/chat/campaigns/${id}`)).json();
  expect(campaign.settings.reply.temperature).toBe(.5);
  expect(campaign.memory.text).toContain('Тайна остаётся');
  if(info.project.name==='mobile'){
    const main=await page.getByRole('button',{name:'Действия кампании',exact:true}).boundingBox();
    const nav=await page.locator('.chat-toolbar').boundingBox();
    expect(main!.y+main!.height).toBeLessThanOrEqual(nav!.y+nav!.height);
  }
});

test('Chat: explicit Narrative snapshot copy leaves source unchanged',async({page,request})=>{
  const seed=await (await request.post('/test/seed')).json();
  const before=await (await request.get(`/api/saves/${seed.save}/author-state`)).json();
  const save=await(await request.get(`/api/saves/${seed.save}`)).json();
  const defaults=await(await request.get('/api/chat/defaults')).json();
  // The Narrative header no longer offers an import shortcut. Keep exercising
  // existing snapshot persistence and its ordinary saved-draft review UI.
  const prepared=await request.post('/api/chat/creations',{data:{token:crypto.randomUUID(),name:'Снимок Narrative',settings:defaults.settings,source:{save_id:seed.save,revision:save.revision}}});
  expect(prepared.ok()).toBe(true);const draft=await prepared.json();
  await page.addInitScript(({seed,id})=>{localStorage.setItem('selection',JSON.stringify(seed));localStorage.setItem('chat-create-active',id)},{seed,id:draft.id});
  await page.goto('/');
  await expect(page.locator('.chat-copy-entry')).toHaveCount(0);
  await page.getByRole('button',{name:'RP-чат',exact:true}).click();
  await page.getByRole('button',{name:'Новая RP-кампания',exact:true}).click();
  const dialog=page.getByRole('dialog');
  await expect(dialog.getByText('Снимок подготовлен',{exact:true})).toBeVisible();
  await expect(dialog.getByLabel('Стартовая выжимка',{exact:true})).toHaveValue(/ИСХОДНЫЙ СНИМОК/);
  await dialog.getByRole('group',{name:'Обычный RP-ответ'}).getByLabel('Модель',{exact:true}).fill('chat-fixture');
  await dialog.getByText('Дополнительные настройки',{exact:true}).click();
  await dialog.getByRole('group',{name:'Обновление выжимки — отдельный вызов'}).getByLabel('Модель',{exact:true}).fill('chat-summary-fixture');
  await dialog.getByLabel('Подтверждаю первоначальную выжимку',{exact:true}).check();
  await dialog.getByRole('button',{name:'Начать игру',exact:true}).click();
  await expect(page.getByRole('button',{name:'Остановить',exact:true})).toHaveCount(0);
  await expect(page.locator('.chat-assistant')).toHaveCount(1);
  await expect(page.getByLabel('Твоё сообщение',{exact:true})).toBeEnabled();
  await expect(dialog).toHaveCount(0);
  const id=await page.evaluate(()=>localStorage.getItem('chat-selection'));
  const c=await (await request.get(`/api/chat/campaigns/${id}`)).json();
  expect(c.source.origin.save_id).toBe(seed.save);
  expect(await (await request.get(`/api/saves/${seed.save}/author-state`)).json()).toEqual(before);
  await page.getByRole('button',{name:'Вернуться в Narrative',exact:true}).click();
  await expect(page.getByRole('button',{name:'RP-чат',exact:true})).toBeVisible();
  await expect(page.locator('.chat-copy-entry')).toHaveCount(0);
});

test('Chat: thousand-message archive renders bounded pages across chapters',async({page,request})=>{
  const seeded=await request.post('/test/chat-history');
  expect(seeded.ok(),await seeded.text()).toBeTruthy();
  const c=await seeded.json();
  expect(c.branch.head).toBe(1000);expect(c.chapters).toHaveLength(5);
  await page.addInitScript(id=>{localStorage.setItem('active-mode','chat');localStorage.setItem('chat-selection',id)},c.id);
  await page.goto('/');
  await expect(page.locator('.chat-message')).toHaveCount(40);
  await page.getByRole('button',{name:'Ранее в истории',exact:true}).click();
  await expect(page.locator('.chat-message')).toHaveCount(80);
  await page.getByRole('button',{name:'Главы и ветки',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Глава 1 Архив · читать'}).click();
  await expect(page.locator('.chat-message')).toHaveCount(40);
  await expect(page.locator('.chat-message').first()).toContainText('Глава 1');
  await page.getByRole('button',{name:'К активной главе',exact:true}).click();
  await expect(page.locator('.chat-heading')).toContainText('Глава 5');
  const after=await (await request.get(`/api/chat/campaigns/${c.id}`)).json();
  expect(after.active_branch).toBe(c.active_branch);expect(after.branch.head).toBe(1000);
  expect(after.budgets.reply.estimated_tokens).toBeLessThan(12000);
});

test('Chat: idea review, automatic opening, variants and reload without duplicate calls',async({page,request},info)=>{
  if(info.project.name==='mobile')await page.setViewportSize({width:360,height:780});
  await page.goto('/');await page.getByRole('button',{name:'RP-чат',exact:true}).click();
  await page.getByRole('button',{name:'Новая RP-кампания',exact:true}).last().click();
  const dialog=page.getByRole('dialog');
  await dialog.getByLabel('Название кампании',{exact:true}).fill('Идея маяка');
  await dialog.getByLabel('Идея игры',{exact:true}).fill('9 октября. Лена и Илья у маяка. Тайна Лены неизвестна Илье. Игрок сам решает, что делать.');
  await dialog.getByRole('group',{name:'Обычный RP-ответ'}).getByLabel('Модель',{exact:true}).fill('chat-fixture');
  await expect(dialog.getByLabel('Автоматический контекст',{exact:true}).first()).toBeChecked();
  await expect(dialog.getByText(/Окно: 65/).first()).toBeVisible();
  await dialog.getByRole('button',{name:'Сгенерировать первоначальную выжимку',exact:true}).click();
  await expect(dialog.getByRole('button',{name:'Остановить генерацию выжимки',exact:true})).toBeVisible();
  await expect(dialog.getByLabel('Стартовая выжимка',{exact:true})).toHaveValue(/ПРАВИЛА И НЕИЗМЕННЫЕ ФАКТЫ/);
  await expect(dialog.getByRole('button',{name:'Остановить генерацию выжимки',exact:true})).toHaveCount(0);
  await expect(dialog).toContainText('input 321, output 120');
  const creations=await (await request.get('/api/chat/creations')).json();
  const d=creations.find((x:{name:string})=>x.name==='Идея маяка');expect(d.campaign_id).toBeNull();expect(d.jobs).toHaveLength(1);
  if(process.env.CHAT_QA_SCREENSHOTS)await page.screenshot({path:`/tmp/chat261-creation-${info.project.name}.png`});
  const original=await dialog.getByLabel('Стартовая выжимка',{exact:true}).inputValue();
  await dialog.getByLabel('Стартовая выжимка',{exact:true}).fill(original+'\nАвторская дата: 9 октября.');
  await dialog.getByRole('button',{name:'Сохранить черновик создания',exact:true}).click();
  await page.reload();await page.getByRole('button',{name:'Новая RP-кампания',exact:true}).last().click();
  // The latest draft resumes without another generation or a search through the list.
  await expect(dialog.getByLabel('Стартовая выжимка',{exact:true})).toHaveValue(/Авторская дата: 9 октября/);
  await dialog.getByLabel('Подтверждаю первоначальную выжимку',{exact:true}).check();
  await dialog.getByRole('button',{name:'Начать игру',exact:true}).dblclick();
  await expect(dialog).toHaveCount(0);await expect(page.locator('.chat-assistant')).toHaveCount(1);
  await expect(page.getByLabel('Твоё сообщение',{exact:true})).toBeEnabled();
  expect(await page.locator('.chat-user').count()).toBe(0);
  const id=await page.evaluate(()=>localStorage.getItem('chat-selection'));
  const before=await (await request.get(`/api/chat/campaigns/${id}`)).json();expect(before.job.kind).toBe('start');
  await page.reload();await expect(page.locator('.chat-assistant')).toHaveCount(1);
  const after=await (await request.get(`/api/chat/campaigns/${id}`)).json();expect(after.job.id).toBe(before.job.id);
  await page.locator('.chat-assistant').getByRole('button',{name:'Перегенерировать',exact:true}).click();
  // The old enabled composer/absent Stop can still be visible before POST returns.
  // Budget probes must use the complete regenerated scene, not a streaming prefix.
  await expect.poll(async()=>{
    const c=await (await request.get(`/api/chat/campaigns/${id}`)).json();
    return {changed:c.job.id!==before.job.id,status:c.job.status};
  }).toEqual({changed:true,status:'complete'});
  await expect(page.getByRole('button',{name:'Остановить',exact:true})).toHaveCount(0);
  await expect(page.getByLabel('Твоё сообщение',{exact:true})).toBeEnabled();
  const variant=await (await request.get(`/api/chat/campaigns/${id}`)).json();expect(variant.branches).toHaveLength(2);expect(variant.branch.head).toBe(1);
  // Find a soft-warning input using the real budget API, without any inference calls.
  let warningInput='';
  for(let n=100;n<=2000;n+=100){
    const text='Я спрашиваю о маяке. '+'Описываю окружающую обстановку. '.repeat(n);
    const budget=await (await request.post(`/api/chat/campaigns/${id}/budget`,{data:{revision:variant.revision,token:crypto.randomUUID(),text}})).json();
    if(budget.warning&&budget.reply.fits&&budget.summary.fits){warningInput=text;break}
  }
  expect(warningInput).not.toBe('');
  await page.getByLabel('Твоё сообщение',{exact:true}).fill(warningInput);
  await expect(page.getByText('Контекст почти заполнен.',{exact:false})).toBeVisible();
  await page.getByRole('button',{name:'Позже',exact:true}).click();
  await page.getByRole('button',{name:'Отправить',exact:true}).click();
  await expect(page.locator('.chat-assistant')).toHaveCount(2);await expect(page.getByRole('button',{name:'Остановить',exact:true})).toHaveCount(0);
  await updateMemory(page);
  await expect(dialog.getByLabel('Текст выжимки',{exact:true})).toBeVisible();
  await dialog.getByRole('button',{name:'Утвердить и продолжить',exact:true}).click();await expect(dialog.getByRole('heading',{name:'Журнал кампании',exact:true})).toBeVisible();await dialog.getByRole('button',{name:'Вернуться в игру',exact:true}).click();await expect(dialog).toHaveCount(0);
  await expect(page.locator('.chat-heading')).toContainText('Глава 2');
  await page.getByLabel('Твоё сообщение',{exact:true}).fill('Продолжаю разговор.');await page.getByRole('button',{name:'Отправить',exact:true}).click();
  await expect(page.locator('.chat-assistant')).toHaveCount(3);await expect(page.getByRole('button',{name:'Остановить',exact:true})).toHaveCount(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  if(process.env.CHAT_QA_SCREENSHOTS)await page.screenshot({path:`/tmp/chat261-idea-${info.project.name}.png`});
});

test('Chat: cancel initial generation, restore draft and require manual unknown context',async({page})=>{
  await page.goto('/');await page.getByRole('button',{name:'RP-чат',exact:true}).click();
  await page.getByRole('button',{name:'Новая RP-кампания',exact:true}).last().click();
  const dialog=page.getByRole('dialog');const model=dialog.getByRole('group',{name:'Обычный RP-ответ'});
  await dialog.getByLabel('Идея игры',{exact:true}).fill('История у маяка');await model.getByLabel('Модель',{exact:true}).fill('unknown-fixture');
  await expect(dialog.getByText(/Окно неизвестно/).first()).toBeVisible();
  await dialog.getByRole('button',{name:'Сгенерировать первоначальную выжимку',exact:true}).click();
  await expect(dialog.getByRole('alert')).toContainText('Размер контекста неизвестен');
  await model.getByLabel('Модель',{exact:true}).fill('chat-fixture');
  await dialog.getByRole('button',{name:'Сгенерировать первоначальную выжимку',exact:true}).click();
  await dialog.getByRole('button',{name:'Остановить генерацию выжимки',exact:true}).click();
  await expect(dialog.getByText('Ответ неполный.',{exact:false})).toBeVisible();
  await expect(dialog.getByRole('button',{name:'Начать игру',exact:true})).toBeDisabled();
  await dialog.getByRole('button',{name:'Сгенерировать заново',exact:true}).click();
  await expect(dialog.getByRole('button',{name:'Остановить генерацию выжимки',exact:true})).toHaveCount(0);
  await expect(dialog.getByLabel('Стартовая выжимка',{exact:true})).toHaveValue(/ПРАВИЛА И НЕИЗМЕННЫЕ ФАКТЫ/);
  await dialog.getByText('Идея и параметры кампании',{exact:true}).click();
  await model.getByLabel('Модель',{exact:true}).fill('chat-small-fixture');await expect(dialog.getByText(/Окно: 8/).first()).toBeVisible();
  await dialog.getByRole('button',{name:'Сгенерировать заново',exact:true}).click();
  await expect(dialog.getByRole('alert')).toContainText('не менее 8192');
});

test('Chat: import Markdown or existing world through the creation chooser',async({page,request})=>{
  const seed=await (await request.post('/test/seed')).json();
  const before=await (await request.get(`/api/worlds/${seed.world}`)).json();
  await page.goto('/');await page.getByRole('button',{name:'RP-чат',exact:true}).click();
  await page.getByRole('button',{name:'Новая RP-кампания',exact:true}).last().click();
  const dialog=page.getByRole('dialog');
  await dialog.getByRole('button',{name:'Использовать готовую выжимку',exact:true}).click();
  await dialog.getByLabel('Импорт первоначальной выжимки',{exact:true}).setInputFiles({name:'story.md',mimeType:'text/markdown',buffer:Buffer.from('# Выжимка\nЛена у маяка. Дата 9 октября.')});
  await expect(dialog.getByLabel('Стартовая выжимка',{exact:true})).toHaveValue(/Лена у маяка/);
  await dialog.getByRole('button',{name:'Импортировать существующий мир',exact:true}).click();
  await chooseOption(dialog.getByRole('combobox',{name:'Исходный мир',exact:true}), String(seed.world));
  await dialog.getByRole('button',{name:'Подготовить снимок бесплатно',exact:true}).click();
  await expect(dialog.getByLabel('Стартовая выжимка',{exact:true})).toHaveValue(/ИСХОДНЫЙ СНИМОК/);
  await dialog.getByRole('group',{name:'Обычный RP-ответ'}).getByLabel('Модель',{exact:true}).fill('chat-fixture');
  await dialog.getByLabel('Подтверждаю первоначальную выжимку',{exact:true}).check();
  await dialog.getByRole('button',{name:'Начать игру',exact:true}).click();
  await expect(dialog).toHaveCount(0);await expect(page.locator('.chat-assistant')).toHaveCount(1);
  await expect(page.getByLabel('Твоё сообщение',{exact:true})).toBeEnabled();
  expect(await (await request.get(`/api/worlds/${seed.world}`)).json()).toEqual(before);
});

test('Chat: Markdown blocks render during streaming, persist and reopen without replay',async({page,request},info)=>{
  const mobile=info.project.name==='mobile';
  if(mobile)await page.setViewportSize({width:360,height:900});
  await page.addInitScript(s=>localStorage.setItem('workshop-theme',JSON.stringify({theme_id:s,mode:'manual'})),mobile?'parchment':'graphite');
  const renders:string[]=[];
  page.on('request',r=>{
    if(r.url().endsWith('/api/markdown')&&r.postDataJSON()?.text?.startsWith('Лена ставит чашку на стол.'))renders.push(r.postDataJSON().text);
  });
  const formatted=async(article:Locator)=>{
    await expect(article.locator('.prose hr')).toHaveCount(2);
    await expect(article.locator('.prose h3')).toHaveText(['Варианты действий','Текущая сцена']);
    await expect(article.locator('.prose ol li strong')).toHaveText(['Спросить Лену:','Осмотреть дверь:','Позвать гостя:','Подождать:']);
    await expect(article.locator('.prose p>strong')).toHaveText(['Свободный ввод:','Время:','Место:','Рядом:']);
    await expect.poll(()=>article.locator('.prose ol').evaluate(el=>getComputedStyle(el).listStyleType)).toBe('decimal');
    await expect.poll(()=>article.locator('.prose hr').first().evaluate(el=>parseFloat(getComputedStyle(el).borderTopWidth))).toBeGreaterThan(0);
    await expect.poll(()=>article.locator('.prose ol strong').first().evaluate(el=>Number(getComputedStyle(el).fontWeight))).toBeGreaterThanOrEqual(600);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  };
  const release=async()=>expect((await request.post('/test/chat-markdown-release')).ok()).toBeTruthy();
  await createChat(page,'chat-markdown-fixture',false);
  const opening=page.locator('.chat-assistant').first();
  await formatted(opening);
  await expect(opening.locator('header')).toContainText('Ответ поступает');
  await expect(opening.locator('.chat-action')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Остановить',exact:true})).toBeVisible();
  expect(renders).toHaveLength(0); // Local formatting, no server render per chunk.
  if(process.env.CHAT_QA_SCREENSHOTS){
    await opening.getByRole('heading',{name:'Варианты действий',exact:true}).scrollIntoViewIfNeeded();
    await page.screenshot({path:`/tmp/chat261-markdown-stream-${info.project.name}.png`});
  }
  await release();await expect(opening.locator('header')).toContainText('Сохранено');
  expect(renders).toHaveLength(0); // Completed Chat actions use the same local AST renderer.
  await expect(opening.locator('.chat-action')).toHaveCount(4);
  await formatted(opening);
  const id=await page.evaluate(()=>localStorage.getItem('chat-selection'));
  const original=await (await request.get(`/api/chat/campaigns/${id}`)).json();
  expect(original.job.kind).toBe('start');
  await page.getByLabel('Твоё сообщение',{exact:true}).fill('Я спрашиваю, кто пришёл.');
  await page.getByRole('button',{name:'Отправить',exact:true}).click();
  await expect(page.locator('.chat-assistant')).toHaveCount(2);
  const reply=page.locator('.chat-assistant').last();
  await formatted(reply);await expect(reply.locator('header')).toContainText('Ответ поступает');await expect(reply.locator('.chat-action')).toHaveCount(0);await expect(opening.locator('.chat-action').first()).toBeDisabled();
  await release();await expect(reply.locator('header')).toContainText('Сохранено');
  const before=await (await request.get(`/api/chat/campaigns/${id}`)).json();
  const saved=await (await request.get(`/api/chat/campaigns/${id}/messages`)).json();
  expect(saved.messages.filter((m:{role:string})=>m.role==='assistant')).toHaveLength(2);
  expect(saved.messages[0].content).toContain('\n\n---\n\n### Варианты действий\n\n');
  expect(saved.messages[0].content).toContain('**Время:**');
  await page.reload();await expect(page.locator('.chat-assistant')).toHaveCount(2);await formatted(reply);
  expect((await (await request.get(`/api/chat/campaigns/${id}`)).json()).job.id).toBe(before.job.id);
  expect(await (await request.get(`/api/chat/campaigns/${id}/messages`)).json()).toEqual(saved);
  if(process.env.CHAT_QA_SCREENSHOTS){
    await reply.getByRole('heading',{name:'Текущая сцена',exact:true}).scrollIntoViewIfNeeded();
    await page.screenshot({path:`/tmp/chat261-markdown-reopened-${info.project.name}.png`});
  }
  await reply.getByRole('button',{name:'Перегенерировать',exact:true}).click();
  await expect.poll(async()=>{
    const c=await (await request.get(`/api/chat/campaigns/${id}`)).json();
    return {changed:c.job.id!==before.job.id,status:c.job.status};
  }).toEqual({changed:true,status:'running'});
  await formatted(reply);await expect(reply.locator('header')).toContainText('Ответ поступает');await expect(reply.locator('.chat-action')).toHaveCount(0);await expect(opening.locator('.chat-action').first()).toBeDisabled();
  await release();await expect(reply.locator('header')).toContainText('Сохранено');
  const after=await (await request.get(`/api/chat/campaigns/${id}`)).json();
  expect(after.branches).toHaveLength(2);
  expect(after.job.kind).toBe('regenerate');
});

// A failed visual assertion must not leave the deliberately held external stream
// occupying the shared model lease and cause unrelated following tests to fail.
test.afterEach(async({request},info)=>{
  if(info.title.includes('Markdown blocks render during streaming'))await request.post('/test/chat-markdown-release');
});
