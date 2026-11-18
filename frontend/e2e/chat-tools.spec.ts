import {test,expect,type Page,type TestInfo,type APIRequestContext} from '@playwright/test';
import {mkdir} from 'node:fs/promises';
import {themes} from '../src/lib/skins';
test.use({actionTimeout:15000});

const shot=async(page:Page,info:TestInfo,name:string)=>{
  if(!process.env.CHAT_TOOLS_SCREENSHOTS)return;
  await mkdir(process.env.CHAT_TOOLS_SCREENSHOTS,{recursive:true});
  await page.waitForFunction(()=>!document.getAnimations().some(a=>a.playState==='running'&&a.effect?.getComputedTiming().iterations!==Infinity));
  await page.screenshot({scale:'css',path:`${process.env.CHAT_TOOLS_SCREENSHOTS}/${info.project.name}-${name}.png`});
};
const fits=async(page:Page)=>{
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  const d=page.getByRole('dialog');if(await d.count()){
    await d.evaluate(el=>Promise.all(el.getAnimations().map(a=>a.finished.catch(()=>{}))));
    const b=await d.boundingBox(),v=page.viewportSize()!;expect(b!.x).toBeGreaterThanOrEqual(-1);expect(b!.y).toBeGreaterThanOrEqual(-1);expect(b!.x+b!.width).toBeLessThanOrEqual(v.width+1);expect(b!.y+b!.height).toBeLessThanOrEqual(v.height+1);
    expect(await d.locator('.chat-dialog-body').evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
    await expect(d.getByRole('button',{name:'Закрыть',exact:true})).toBeInViewport();
  }
};
async function journal(page:Page,tab='Закладки'){
  await expect(page.getByRole('dialog')).toHaveCount(0);await page.getByRole('button',{name:'Действия кампании',exact:true}).click();
  await page.getByRole('button',{name:'Закладки, персонажи и изменения',exact:true}).click();
  await page.getByRole('tab',{name:tab,exact:true}).click();
}
async function closeJournal(page:Page){await page.getByRole('button',{name:'Вернуться в игру',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0)}
async function create(page:Page){
  await page.goto('/');await page.getByRole('button',{name:'RP-чат',exact:true}).click();await page.getByRole('dialog').getByRole('button',{name:'Новая RP-кампания',exact:true}).click();
  const d=page.getByRole('dialog');await d.getByLabel('Название кампании',{exact:true}).fill('Маяк — журнал долгой истории');await d.getByLabel('Идея игры',{exact:true}).fill('Лена и Илья у осеннего маяка. Дата 9 октября. Тайну ключа знает только Лена.');
  await d.getByRole('group',{name:'Обычный RP-ответ'}).getByLabel('Модель',{exact:true}).fill('chat-tools-fixture');await d.getByText('Дополнительные настройки',{exact:true}).click();await d.getByRole('group',{name:'Обновление выжимки — отдельный вызов'}).getByLabel('Модель',{exact:true}).fill('chat-tools-summary-fixture');
  await d.getByRole('button',{name:'Сгенерировать первоначальную выжимку',exact:true}).click();await expect(d.getByRole('button',{name:'Остановить генерацию выжимки',exact:true})).toHaveCount(0);
  await expect(d.getByLabel('Стартовая выжимка',{exact:true})).toHaveValue(/👤 Лена/);await d.getByLabel('Подтверждаю первоначальную выжимку',{exact:true}).check();await d.getByRole('button',{name:'Начать игру',exact:true}).click();await expect(d).toHaveCount(0);
  await expect(page.locator('.chat-assistant header')).toContainText('Сохранено');await expect(page.locator('.chat-action')).toHaveCount(4);
}
const campaign=async(page:Page,request:APIRequestContext)=>{const id=await page.evaluate(()=>localStorage.getItem('chat-selection'));return await(await request.get(`/api/chat/campaigns/${id}`)).json()};
async function bookmark(page:Page,index:number,note:string){
  await page.locator('.chat-assistant').nth(index).getByRole('button',{name:'Добавить закладку',exact:true}).click();
  await page.getByLabel('Заметка автора',{exact:true}).fill(note);await page.getByLabel('Приоритет при обновлении выжимки',{exact:true}).selectOption('2');await page.getByRole('button',{name:'Сохранить закладку',exact:true}).click();
  await expect(page.locator('.chat-bookmark-card').filter({hasText:note})).toBeVisible();await closeJournal(page);
}

test('Chat tools: idea, choices, bookmarks, character edit, memory history and branch isolation',async({page,request},info)=>{
  test.setTimeout(180000);if(info.project.name==='mobile')await page.setViewportSize({width:360,height:780});
  await create(page);const original=await campaign(page,request);const input=page.getByLabel('Твоё сообщение',{exact:true});let calls=0;page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/generate'))calls++});
  await page.locator('.chat-action').first().click();await expect(input).toHaveValue('Спросить Лену: «Ты ждёшь гостей?»');expect(calls).toBe(0);
  await input.fill('Я ставлю книгу на стол.');await page.locator('.chat-action').nth(1).click();await expect(page.getByRole('dialog')).toContainText('Текущий черновик сохранён');await page.getByRole('button',{name:'Добавить к черновику',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);await expect(input).toHaveValue(/Я ставлю книгу на стол\.\n\nОсмотреть дверь:/);expect(calls).toBe(0);
  await shot(page,info,'01-interactive-actions');await input.fill('Я ставлю книгу на стол. «Ты ждёшь гостей?»');await page.getByRole('button',{name:'Отправить',exact:true}).click();await expect(page.locator('.chat-assistant')).toHaveCount(2);await expect(page.locator('.chat-assistant').last().locator('header')).toContainText('Сохранено');expect(calls).toBe(1);
  await bookmark(page,0,'Начало разговора; ключ остаётся тайной.');await bookmark(page,1,'Книга возвращена. Невыбранные варианты не совершены.');await journal(page);await shot(page,info,'02-bookmarks');await closeJournal(page);
  await input.fill('Черновик игрока во время работы с библиотекой.');await journal(page,'Персонажи');await fits(page);await shot(page,info,'03-character-library');await page.getByLabel('Поиск персонажей и сведений',{exact:true}).fill('ЛЕНА');await page.locator('.chat-character-card').filter({hasText:'Лена'}).click();await expect(page.getByRole('dialog')).toContainText('ключ спрятан под камнем');await shot(page,info,'04-character-detail');
  await page.getByRole('button',{name:'Редактировать раздел персонажа',exact:true}).click();const editor=page.getByLabel('Markdown раздела персонажа',{exact:true});const old=await editor.inputValue();await editor.fill(old.replace('рыжие волосы','короткие рыжие волосы'));await page.getByRole('button',{name:'Предпросмотр изменений',exact:true}).click();await fits(page);await shot(page,info,'05-character-review');
  await page.getByRole('button',{name:'Проверить новую выжимку',exact:true}).click();await expect(page.getByRole('heading',{name:'Проверка новой выжимки',exact:true})).toBeVisible();expect((await campaign(page,request)).memory.id).toBe(original.memory.id);
  await page.getByRole('button',{name:'Утвердить в этой главе',exact:true}).click();await expect(page.getByRole('heading',{name:'Журнал кампании',exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'Точные текстовые различия',exact:true})).toBeVisible();await shot(page,info,'06-approved-changes');expect(calls).toBe(1);await closeJournal(page);await expect(input).toHaveValue('Черновик игрока во время работы с библиотекой.');
  const authored=await campaign(page,request);expect(authored.memory.text).toBe(original.memory.text.replace('рыжие волосы','короткие рыжие волосы'));
  const update=page.getByRole('button',{name:'Обновить выжимку и продолжить',exact:true});if(!await update.isVisible())await page.getByRole('button',{name:'Действия кампании',exact:true}).click();await update.click();await expect(page.getByRole('heading',{name:'Проверка новой выжимки',exact:true})).toBeVisible();await page.getByRole('button',{name:'Утвердить и продолжить',exact:true}).click();await expect(page.getByRole('heading',{name:'Точные текстовые различия',exact:true})).toBeVisible();await expect(page.getByRole('dialog')).toContainText('книга возвращена');await shot(page,info,'07-summary-history');expect(calls).toBe(2);await closeJournal(page);await expect(page.locator('.chat-heading')).toContainText('Глава 2');
  const summarized=await campaign(page,request);const receipts=await(await request.get(`/api/chat/campaigns/${summarized.id}/jobs/${summarized.job.id}/requests`)).json();expect(JSON.stringify(receipts)).toContain('Невыбранные варианты не совершены');
  await input.fill('Черновик исходной ветки');await journal(page);await page.locator('.chat-bookmark-card').filter({hasText:'Книга возвращена.'}).getByRole('button',{name:'К сообщению',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);await expect(page.getByRole('button',{name:'К активной главе',exact:true})).toBeVisible();await expect(page.locator('.chat-message-target')).toBeInViewport();await shot(page,info,'08-archive-bookmark');
  await page.locator('.chat-message-target').getByRole('button',{name:'Редактировать',exact:true}).click();await page.getByLabel('Новый текст',{exact:true}).fill('Лена оставляет дверь открытой.');await page.getByRole('button',{name:'Сохранить как новую ветку',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);
  await journal(page);await expect(page.locator('.chat-bookmark-card')).toHaveCount(1);await expect(page.locator('.chat-bookmark-card')).toContainText('Начало разговора');await page.getByRole('tab',{name:'Изменения',exact:true}).click();await expect(page.locator('.chat-version-card')).toHaveCount(1);await closeJournal(page);
  await page.getByRole('button',{name:'Главы и ветки',exact:true}).click();await page.getByRole('dialog').getByRole('button',{name:/Основная ветка/}).click();await expect(page.getByRole('dialog')).toHaveCount(0);await expect(input).toHaveValue('Черновик исходной ветки');await page.reload();await expect(input).toHaveValue('Черновик исходной ветки');await journal(page,'Персонажи');await page.locator('.chat-character-card').filter({hasText:'Лена'}).click();await expect(page.getByRole('dialog')).toContainText('короткие рыжие волосы');expect(calls).toBe(2);
});

test('Chat tools: large archive, bookmark pagination, Unicode library, Back and draft recovery',async({page,request},info)=>{
  test.setTimeout(180000);if(info.project.name==='mobile')await page.setViewportSize({width:320,height:780});
  const seed=await(await request.post('/test/chat-tools-history')).json();const c=seed.campaign;
  await page.addInitScript(id=>{localStorage.setItem('active-mode','chat');localStorage.setItem('chat-selection',id)},c.id);await page.goto('/');await expect(page.locator('.chat-message')).toHaveCount(40);await page.getByLabel('Твоё сообщение',{exact:true}).fill('Длинная кампания: черновик не теряется.');
  await journal(page);await expect(page.locator('.chat-bookmark-card')).toHaveCount(30);await page.getByRole('button',{name:'Ещё закладки',exact:true}).click();await expect(page.locator('.chat-bookmark-card')).toHaveCount(60);await fits(page);await shot(page,info,'09-many-bookmarks');
  await page.getByLabel('Поиск по закладкам и заметкам',{exact:true}).fill('ЗАКЛАДКА 0011');await expect(page.locator('.chat-bookmark-card')).toHaveCount(1);await page.getByRole('button',{name:'К сообщению',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);await expect(page.locator('.chat-message-target')).toContainText('сообщение 12');await expect(page.locator('.chat-message-target')).toBeInViewport();expect(await page.locator('.chat-message').count()).toBeLessThanOrEqual(40);
  await page.getByRole('button',{name:'Позже в истории',exact:true}).click();expect(await page.locator('.chat-message').count()).toBeLessThanOrEqual(80);await page.getByRole('button',{name:'К активной главе',exact:true}).click();await expect(page.getByLabel('Твоё сообщение',{exact:true})).toHaveValue('Длинная кампания: черновик не теряется.');
  await journal(page,'Персонажи');await expect(page.locator('.chat-character-card')).toHaveCount(40);await page.getByRole('button',{name:'Ещё персонажи',exact:true}).click();await expect(page.locator('.chat-character-card')).toHaveCount(80);await page.getByLabel('Поиск персонажей и сведений',{exact:true}).fill('сосед 090');await expect(page.locator('.chat-character-card')).toHaveCount(1);await page.locator('.chat-character-card').filter({hasText:'Сосед 090'}).click();await expect(page.getByRole('dialog')).toContainText('Не знает: тайну ключа');await page.getByRole('button',{name:'Редактировать раздел персонажа',exact:true}).click();const editor=page.getByLabel('Markdown раздела персонажа',{exact:true});await editor.fill((await editor.inputValue())+'\nНесохранённая заметка про паром.');
  await page.goBack();await expect(page.getByRole('dialog')).toBeVisible();await expect(editor).toHaveCount(0);await page.getByRole('button',{name:'Редактировать раздел персонажа',exact:true}).click();await expect(editor).toHaveValue(/Несохранённая заметка/);await fits(page);await shot(page,info,'10-large-library-editor');
  if(info.project.name==='mobile'){await editor.focus();await page.setViewportSize({width:320,height:420});await fits(page);await expect.poll(async()=>{const r=await editor.boundingBox();return !!r&&r.y>=100&&r.y+r.height<=410}).toBe(true);await shot(page,info,'11-editor-keyboard-height');await page.setViewportSize({width:320,height:780})}
  await page.getByRole('button',{name:'Закрыть',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);await page.reload();await journal(page,'Персонажи');await page.getByLabel('Поиск персонажей и сведений',{exact:true}).fill('сосед 090');await page.locator('.chat-character-card').filter({hasText:'Сосед 090'}).click();await page.getByRole('button',{name:'Редактировать раздел персонажа',exact:true}).click();await expect(editor).toHaveValue(/Несохранённая заметка/);
});

test('Chat tools: explicit character conflict resolution preserves the latest other sections',async({page,request},info)=>{
  test.setTimeout(120000);await create(page);await journal(page,'Персонажи');await page.locator('.chat-character-card').filter({hasText:'Лена'}).click();await page.getByRole('button',{name:'Редактировать раздел персонажа',exact:true}).click();const editor=page.getByLabel('Markdown раздела персонажа',{exact:true});await editor.fill((await editor.inputValue()).replace('серый свитер','синий свитер'));
  let c=await campaign(page,request);const other=c.memory.text.replace('комната у маяка','комната на втором этаже маяка').replace('рыжие волосы','волнистые рыжие волосы');const d=await(await request.post(`/api/chat/campaigns/${c.id}/memory`,{data:{revision:c.revision,token:crypto.randomUUID(),text:other}})).json();c=await campaign(page,request);expect((await request.post(`/api/chat/campaigns/${c.id}/drafts/${d.draft}/confirm`,{data:{revision:c.revision,token:crypto.randomUUID(),text:other,next_chapter:false}})).ok()).toBeTruthy();
  await page.getByRole('button',{name:'Проверить новую выжимку',exact:true}).click();await expect(page.getByRole('alert')).toBeVisible();await expect(editor).toHaveValue(/синий свитер/);await page.getByRole('button',{name:'Загрузить актуальную память для сравнения',exact:true}).click();await expect(page.getByRole('heading',{name:'Актуальный раздел с тем же именем',exact:true})).toBeVisible();await expect(page.locator('.chat-conflict-review')).toContainText('волнистые рыжие волосы');await fits(page);await shot(page,info,'12-character-conflict');
  await page.getByRole('button',{name:'Перенести мою правку в актуальный раздел',exact:true}).click();await page.getByRole('button',{name:'Продолжить редактирование',exact:true}).click();await editor.fill((await editor.inputValue()).replace('рыжие волосы','волнистые рыжие волосы'));await page.getByRole('button',{name:'Проверить новую выжимку',exact:true}).click();await page.getByRole('button',{name:'Утвердить в этой главе',exact:true}).click();await expect(page.getByRole('heading',{name:'Точные текстовые различия',exact:true})).toBeVisible();c=await campaign(page,request);expect(c.memory.text).toContain('комната на втором этаже маяка');expect(c.memory.text).toContain('волнистые рыжие волосы, синий свитер');
});

for(const width of [320,360,375,393,412,430,768,1024,1440])test(`Chat tools layout ${width}: cards, editor, bookmark controls`,async({page},info)=>{
  test.skip((width<768)!==(info.project.name==='mobile'),'Touch widths on mobile project; tablets and desktop on desktop project');test.setTimeout(120000);await page.setViewportSize({width,height:width<768?780:1000});await create(page);
  await page.locator('.chat-assistant').getByRole('button',{name:'Добавить закладку',exact:true}).click();await fits(page);const button=await page.getByRole('button',{name:'Сохранить закладку',exact:true}).boundingBox();expect(button!.height).toBeGreaterThanOrEqual(44);await page.getByLabel('Заметка автора',{exact:true}).fill('Длинная заметка с Unicode: Ёж 🦔 — разговор у маяка. '.repeat(12));await page.getByRole('button',{name:'Сохранить закладку',exact:true}).click();await page.getByRole('tab',{name:'Персонажи',exact:true}).click();await page.locator('.chat-character-card').filter({hasText:'Лена'}).click();await fits(page);if([320,393,430,768,1440].includes(width))await shot(page,info,`layout-${width}`);await page.getByRole('button',{name:'Редактировать раздел персонажа',exact:true}).click();await fits(page);await page.emulateMedia({reducedMotion:'reduce'});await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).toBeVisible();await expect(page.getByLabel('Markdown раздела персонажа',{exact:true})).toHaveCount(0);
});


test('Chat tools: journal skins, errors, retry and untouched input',async({page,request},info)=>{
  test.setTimeout(180000);if(info.project.name==='mobile')await page.setViewportSize({width:393,height:852});await create(page);
  const input=page.getByLabel('Твоё сообщение',{exact:true});await input.fill('Сохранённый свободный ввод.');
  await page.locator('.chat-action').first().click();await page.getByRole('button',{name:'Заменить черновик этим вариантом',exact:true}).click();await expect(input).toHaveValue('Спросить Лену: «Ты ждёшь гостей?»');
  await page.route('**/api/chat/campaigns/*/bookmarks?*',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Тестовая недоступность хранилища'})}));
  await journal(page);await expect(page.getByRole('alert')).toContainText('Тестовая недоступность');await fits(page);await shot(page,info,'13-journal-error');
  await page.unroute('**/api/chat/campaigns/*/bookmarks?*');await page.getByRole('button',{name:'Повторить загрузку',exact:true}).click();await expect(page.getByRole('heading',{name:'Сохраните важный момент',exact:true})).toBeVisible();await closeJournal(page);
  for(const theme of themes){
    await page.getByRole('button',{name:'Настройки RP-чата',exact:true}).click();await page.getByRole('combobox',{name:'Тема мира',exact:true}).selectOption(theme.id);await page.keyboard.press('Escape');await expect(page.locator('html')).toHaveAttribute('data-theme',theme.id);await journal(page,'Персонажи');await expect(page.locator('.chat-character-card')).toHaveCount(2);await fits(page);
    const target=page.locator('.chat-character-card').filter({hasText:'Лена'});await page.keyboard.press('Tab');await target.focus();expect(await target.evaluate(el=>getComputedStyle(el).outlineStyle)).not.toBe('none');await target.click();await fits(page);
    if(['graphite','parchment','terminal'].includes(theme.id))await shot(page,info,`skin-${theme.id}`);await closeJournal(page);await expect(input).toHaveValue('Спросить Лену: «Ты ждёшь гостей?»');
  }
  const c=await campaign(page,request);expect(c.branch.head).toBe(1); // Selecting/replacing and browsing never sends a turn.
});


test('Chat tools: delayed and lost acknowledgements preserve a newer draft without duplicate turns',async({page,request})=>{
  test.setTimeout(90000);await create(page);const input=page.getByLabel('Твоё сообщение',{exact:true});
  let arrived!:()=>void,release!:()=>void;const responseReady=new Promise<void>(r=>arrived=r),gate=new Promise<void>(r=>release=r);
  await page.route('**/api/chat/campaigns/*/generate',async route=>{const response=await route.fetch();arrived();await gate;await route.fulfill({response})});
  await input.fill('Первый отправленный ход.');await page.getByRole('button',{name:'Отправить',exact:true}).click();await responseReady;
  await input.fill('Новый черновик до подтверждения отправки.');release();await expect(page.locator('.chat-assistant')).toHaveCount(2);await expect(page.locator('.chat-assistant').last().locator('header')).toContainText('Сохранено');await expect(input).toHaveValue('Новый черновик до подтверждения отправки.');
  await page.unroute('**/api/chat/campaigns/*/generate');
  await page.route('**/api/chat/campaigns/*/generate',async route=>{await route.fetch();await route.abort('failed')});
  await input.fill('Второй отправленный ход.');await page.getByRole('button',{name:'Отправить',exact:true}).click();await expect(page.getByRole('button',{name:'Проверить отправку без повторного вызова',exact:true})).toBeEnabled();
  await input.fill('Черновик после сетевой ошибки.');await page.unroute('**/api/chat/campaigns/*/generate');await page.getByRole('button',{name:'Проверить отправку без повторного вызова',exact:true}).click();await expect(page.locator('.chat-assistant')).toHaveCount(3);await expect(page.locator('.chat-assistant').last().locator('header')).toContainText('Сохранено');await expect(input).toHaveValue('Черновик после сетевой ошибки.');
  const c=await campaign(page,request);expect(c.branch.head).toBe(5);await page.reload();await expect(input).toHaveValue('Черновик после сетевой ошибки.');expect((await campaign(page,request)).job.id).toBe(c.job.id);
});
