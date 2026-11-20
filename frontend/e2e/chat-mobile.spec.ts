import {swipe} from './touch';
import {chooseOption} from './choice-navigation';
import {test,expect,type Page,type TestInfo} from '@playwright/test';
import {mkdir} from 'node:fs/promises';
import {themes} from '../src/lib/skins';

const shot=async(page:Page,info:TestInfo,name:string)=>{
  if(!process.env.CHAT_MOBILE_SCREENSHOTS)return;
  await mkdir(process.env.CHAT_MOBILE_SCREENSHOTS,{recursive:true});
  // Capture settled UI, not a transition frame; motion itself has separate coverage.
  await page.waitForFunction(()=>!document.getAnimations().some(a=>a.playState==='running'&&a.effect?.getComputedTiming().iterations!==Infinity));
  await page.screenshot({scale:'css',path:`${process.env.CHAT_MOBILE_SCREENSHOTS}/${info.project.name}-${name}.png`});
};
async function enter(page:Page){await page.goto('/');await page.getByRole('button',{name:'RP-чат',exact:true}).click();await page.getByRole('dialog').getByRole('button',{name:'Новая RP-кампания',exact:true}).click()}
async function create(page:Page){
  await enter(page);const d=page.getByRole('dialog');
  await d.getByRole('button',{name:'Использовать готовую выжимку',exact:true}).click();
  await d.getByLabel('Название кампании',{exact:true}).fill('Долгая история у осеннего маяка');
  await d.getByLabel('Стартовая выжимка',{exact:true}).fill('9 октября. Лена и Илья у маяка. Тайну знает только Лена.');
  await d.getByRole('button',{name:'Использовать готовую выжимку',exact:true}).click();await expect(d.getByLabel('Стартовая выжимка',{exact:true})).toHaveValue('9 октября. Лена и Илья у маяка. Тайну знает только Лена.');
  await d.getByRole('group',{name:'Обычный RP-ответ'}).getByLabel('Модель',{exact:true}).fill('chat-mobile-fixture');
  await d.getByText('Дополнительные настройки',{exact:true}).click();
  await d.getByRole('group',{name:'Обновление выжимки — отдельный вызов'}).getByLabel('Модель',{exact:true}).fill('chat-summary-fixture');
  await d.getByLabel('Подтверждаю первоначальную выжимку',{exact:true}).check();await d.getByRole('button',{name:'Начать игру',exact:true}).click();
  await expect(d).toHaveCount(0);await expect(page.locator('.chat-assistant header')).toContainText('Сохранено');
}
async function update(page:Page){await expect(page.getByRole('dialog')).toHaveCount(0);const b=page.getByRole('button',{name:'Обновить выжимку и продолжить',exact:true});if(!await b.isVisible())await page.getByRole('button',{name:'Действия кампании',exact:true}).click();await b.click()}
async function fits(page:Page){
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  const dialog=page.getByRole('dialog');if(await dialog.count()){
    await dialog.evaluate(el=>Promise.all(el.getAnimations().map(a=>a.finished.catch(()=>{}))));
    const b=await dialog.boundingBox();const v=page.viewportSize()!;
    expect(b!.x).toBeGreaterThanOrEqual(-1);expect(b!.y).toBeGreaterThanOrEqual(-1);expect(b!.x+b!.width).toBeLessThanOrEqual(v.width+1);expect(b!.y+b!.height).toBeLessThanOrEqual(v.height+1);
    expect(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
    expect(await dialog.locator('.chat-dialog-body').evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
    await expect(dialog.getByRole('button',{name:'Закрыть',exact:true})).toBeInViewport();
  }
}

for(const width of [320,360,375,393,412,430,768,1024,1440])test(`Chat mobile layout ${width}: reading, touch actions, modal and keyboard viewport`,async({page},info)=>{
  test.skip((width<768)!==(info.project.name==='mobile'),'Mobile widths in touch Chrome; tablet/desktop in desktop Chrome');
  await page.setViewportSize({width,height:width<768?780:1000});
  await page.addInitScript(s=>localStorage.setItem('workshop-theme',JSON.stringify({theme_id:s,mode:'manual'})),width%2?'parchment':'graphite');
  await create(page);await fits(page);
  const article=page.locator('.chat-assistant').last();
  await expect(article.locator('.prose hr')).toHaveCount(2);await expect(article.locator('.prose ol li strong')).toHaveCount(4);
  await expect(page.locator('.chat-column')).not.toContainText('Стоимость по ставкам');
  for(const label of ['Редактировать','Перегенерировать','Запрос и расход']){
    const button=article.getByRole('button',{name:label,exact:true});await expect(button).toBeVisible();
    const box=await button.boundingBox();if(width<768){expect(box!.width).toBeGreaterThanOrEqual(44);expect(box!.height).toBeGreaterThanOrEqual(44)}
    expect(await button.locator('svg').count()).toBe(1);expect(await button.innerText()).toBe('');
  }
  if(width<768)expect((await page.locator('.chat-toolbar').boundingBox())!.height).toBeLessThanOrEqual(50);
  const story=await page.locator('.chat-scroll').boundingBox();expect(story!.height).toBeGreaterThan((page.viewportSize()!.height)*.55);
  await article.getByRole('heading',{name:'Варианты действий',exact:true}).scrollIntoViewIfNeeded();await shot(page,info,`chat-${width}`);
  if(width===1440){const pencil=article.getByRole('button',{name:'Редактировать',exact:true});await pencil.hover();await expect(article.getByRole('tooltip',{name:'Редактировать',exact:true})).toBeVisible();await pencil.focus();await page.keyboard.press('Tab');const refresh=article.getByRole('button',{name:'Перегенерировать',exact:true});await expect(refresh).toBeFocused();await expect(article.getByRole('tooltip',{name:'Редактировать',exact:true})).toBeHidden();expect(await refresh.evaluate(el=>getComputedStyle(el).outlineStyle)).not.toBe('none');await shot(page,info,'desktop-keyboard-focus')}
  if(width===360){await article.getByRole('button',{name:'Редактировать',exact:true}).scrollIntoViewIfNeeded();await shot(page,info,'chat-actions-360')}
  await article.getByRole('button',{name:'Редактировать',exact:true}).click();await fits(page);
  const edit=page.getByLabel('Новый текст',{exact:true});await edit.fill('Несохранённая правка сохраняется после Back и reload.');
  if(width===320)await shot(page,info,'edit-320');
  if(width===393)await swipe(page,page.getByRole('dialog').locator('.dialog-title'),0,90);else await page.goBack();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await article.getByRole('button',{name:'Редактировать',exact:true}).click();await expect(edit).toHaveValue('Несохранённая правка сохраняется после Back и reload.');
  await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).toHaveCount(0);
  const input=page.getByLabel('Твоё сообщение',{exact:true});await input.fill('Длинная реплика игрока. '.repeat(60));
  if(width<768){
    await input.focus();await page.setViewportSize({width,height:420});await expect(page.locator('html')).toHaveClass(/keyboard-open/);
    const send=await page.getByRole('button',{name:'Отправить',exact:true}).boundingBox();expect(send!.y+send!.height).toBeLessThanOrEqual(420);
    const text=await input.boundingBox();expect(text!.height).toBeGreaterThan(70);await fits(page);
    if(width===320||width===393)await shot(page,info,`keyboard-${width}`);
    await page.setViewportSize({width,height:780});await input.blur();
  }
  await page.getByRole('button',{name:'Развернуть ввод',exact:true}).click();await fits(page);await expect(page.getByLabel('Действие или реплика',{exact:true})).toHaveValue('Длинная реплика игрока. '.repeat(60));
  await page.getByRole('button',{name:'Вернуться в чат',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);await expect(input).toHaveValue('Длинная реплика игрока. '.repeat(60));
  await page.getByRole('button',{name:'Настройки RP-чата',exact:true}).click();await fits(page);
  if(width===320||width===768)await shot(page,info,`settings-${width}`);
  await page.getByRole('dialog').getByText('Дополнительные настройки',{exact:true}).click();await page.getByLabel('Системный RP-промпт',{exact:true}).fill('Черновик системного промпта');
  await page.keyboard.press('Escape');await page.getByRole('button',{name:'Настройки RP-чата',exact:true}).click();
  await page.getByRole('dialog').getByText('Дополнительные настройки',{exact:true}).click();await expect(page.getByLabel('Системный RP-промпт',{exact:true})).toHaveValue('Черновик системного промпта');
  await page.keyboard.press('Escape');await page.reload();await expect(input).toHaveValue('Длинная реплика игрока. '.repeat(60));await fits(page);
});

test('Chat mobile journey: creation recovery, memory tabs, chapter, variants and input preservation',async({page,request},info)=>{
  test.setTimeout(120000);if(info.project.name==='mobile')await page.setViewportSize({width:360,height:780});
  await page.addInitScript(()=>localStorage.setItem('workshop-theme',JSON.stringify({theme_id:'parchment',mode:'manual'})));
  await enter(page);const d=page.getByRole('dialog');await expect(d.getByLabel('Идея игры',{exact:true})).toBeVisible();await fits(page);await shot(page,info,'01-create');
  await d.getByLabel('Название кампании',{exact:true}).fill('Идея и долгий разговор');await d.getByLabel('Идея игры',{exact:true}).fill('Маяк, осень, Лена и Илья. Незавершённый разговор.');
  await d.getByRole('group',{name:'Обычный RP-ответ'}).getByLabel('Модель',{exact:true}).fill('chat-mobile-fixture');
  await page.keyboard.press('Escape');await page.getByRole('button',{name:'Новая RP-кампания',exact:true}).click();
  await expect(d.getByLabel('Название кампании',{exact:true})).toHaveValue('Идея и долгий разговор');
  await d.getByRole('button',{name:'Сгенерировать первоначальную выжимку',exact:true}).click();
  await expect(d.getByLabel('Поступающая выжимка',{exact:true})).toBeVisible();await fits(page);await expect(d.getByRole('button',{name:'Закрыть',exact:true})).toBeInViewport();await shot(page,info,'02-initial-stream');
  await expect(d.getByRole('button',{name:'Остановить генерацию выжимки',exact:true})).toHaveCount(0);
  const initial=d.getByLabel('Стартовая выжимка',{exact:true});await expect(initial).toHaveValue(/ПРАВИЛА И НЕИЗМЕННЫЕ ФАКТЫ/);await initial.fill((await initial.inputValue())+'\nАвторская правка в конце большого документа.');await shot(page,info,'03-initial-editor');
  await page.reload();await page.getByRole('dialog').getByRole('button',{name:'Новая RP-кампания',exact:true}).click();await expect(initial).toHaveValue(/Авторская правка/);
  await d.getByText('Идея и параметры кампании',{exact:true}).click();await d.getByText('Дополнительные настройки',{exact:true}).click();await d.getByRole('group',{name:'Обновление выжимки — отдельный вызов'}).getByLabel('Модель',{exact:true}).fill('chat-summary-fixture');
  await d.getByLabel('Подтверждаю первоначальную выжимку',{exact:true}).check();await d.getByRole('button',{name:'Начать игру',exact:true}).click();await expect(d).toHaveCount(0);await expect(page.locator('.chat-assistant header')).toContainText('Сохранено');await shot(page,info,'04-opening');await page.locator('.chat-scroll').evaluate(el=>{el.scrollTop=0});await shot(page,info,'04-opening-prose');await page.getByRole('button',{name:'К последнему сообщению',exact:true}).click();
  const input=page.getByLabel('Твоё сообщение',{exact:true});await input.fill('Я продолжаю разговор у окна.');await page.getByRole('button',{name:'Отправить',exact:true}).click();await expect(page.locator('.chat-assistant')).toHaveCount(2);
  await page.locator('.chat-scroll').evaluate(el=>{el.scrollTop=0});await expect(page.locator('.chat-assistant').last().locator('header')).toContainText('Сохранено');expect(await page.locator('.chat-scroll').evaluate(el=>el.scrollTop)).toBeLessThan(10);
  await expect(page.locator('.chat-user').getByRole('button',{name:'Редактировать',exact:true})).toBeVisible();await expect(page.locator('.chat-user').getByRole('button',{name:'Перегенерировать',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'К последнему сообщению',exact:true}).click();await shot(page,info,'05-long-history');
  await input.fill('Черновик, который должен пережить работу с памятью.');await page.getByRole('button',{name:'Выжимка',exact:true}).click();await fits(page);await shot(page,info,'06-memory-read');
  await d.getByRole('tab',{name:'Правка',exact:true}).click();const memory=d.getByLabel('Текст выжимки',{exact:true});await memory.fill((await memory.inputValue())+'\nЛокальная заметка.');await page.goBack();await page.getByRole('button',{name:'Выжимка',exact:true}).click();await d.getByRole('tab',{name:'Правка',exact:true}).click();await expect(memory).toHaveValue(/Локальная заметка/);await page.keyboard.press('Escape');
  await update(page);await expect(d.getByRole('heading',{name:'Проверка новой выжимки'})).toBeVisible();await shot(page,info,'07-memory-review');
  await d.getByRole('tab',{name:'Сравнение',exact:true}).click();await fits(page);await shot(page,info,'08-memory-compare');await d.getByRole('tab',{name:'Версии',exact:true}).click();await expect(d.getByRole('heading',{name:'Версии памяти · архив'})).toBeVisible();await shot(page,info,'09-memory-versions');
  await d.getByRole('tab',{name:'Правка',exact:true}).click();await d.getByRole('button',{name:'Утвердить и продолжить',exact:true}).click();await expect(d.getByRole('heading',{name:'Журнал кампании',exact:true})).toBeVisible();await d.getByRole('button',{name:'Вернуться в игру',exact:true}).click();await expect(d).toHaveCount(0);await expect(page.locator('.chat-heading')).toContainText('Глава 2');await expect(input).toHaveValue('Черновик, который должен пережить работу с памятью.');
  await page.getByRole('button',{name:'Главы и ветки',exact:true}).click();await shot(page,info,'10-chapters');await d.getByRole('button',{name:'Глава 1 Архив · читать'}).click();await expect(page.getByRole('button',{name:'К активной главе',exact:true})).toBeVisible();await shot(page,info,'11-archive');await page.getByRole('button',{name:'К активной главе',exact:true}).click();
  const id=await page.evaluate(()=>localStorage.getItem('chat-selection'));const before=await (await request.get(`/api/chat/campaigns/${id}`)).json();
  await page.locator('.chat-assistant').last().getByRole('button',{name:'Перегенерировать',exact:true}).click();await expect.poll(async()=>{const c=await (await request.get(`/api/chat/campaigns/${id}`)).json();return c.job.id!==before.job.id&&c.job.status==='complete'}).toBe(true);
  await page.locator('.chat-assistant').last().getByRole('button',{name:'Запрос и расход',exact:true}).click();await expect(d).toContainText('Входные токены');await shot(page,info,'12-request');await page.keyboard.press('Escape');await page.getByRole('button',{name:'Главы и ветки',exact:true}).click();await expect(d.getByRole('button',{name:/Основная ветка/})).toBeVisible();
});


test('Chat mobile recovery: errors, stop, retry, context warning and nested Back',async({page,request},info)=>{
  test.setTimeout(120000);if(info.project.name==='mobile')await page.setViewportSize({width:320,height:780});
  await create(page);
  await page.getByRole('button',{name:'Настройки RP-чата',exact:true}).click();
  await page.getByRole('button',{name:'Подключения и серверный ключ',exact:true}).click();
  await expect(page.getByRole('dialog').getByRole('heading',{name:'Настройки',exact:true})).toBeVisible();
  await page.goBack();await expect(page.getByRole('dialog')).toHaveCount(0);await expect(page.getByRole('main',{name:'RP-чат',exact:true})).toBeVisible();
  await page.emulateMedia({reducedMotion:'reduce'});
  await request.post('/test/chat-cancel-window');
  await page.getByLabel('Твоё сообщение',{exact:true}).fill('Я продолжаю разговор.');await page.getByRole('button',{name:'Отправить',exact:true}).click();
  await expect(page.getByRole('button',{name:'Остановить',exact:true})).toBeVisible();
  await expect(page.locator('.chat-assistant').first().getByRole('button',{name:'Редактировать',exact:true})).toBeDisabled();expect(await page.locator('.chat-assistant').first().getByRole('button',{name:'Редактировать',exact:true}).evaluate(el=>Number(getComputedStyle(el).opacity))).toBeLessThan(1);await shot(page,info,'13-streaming');
  await page.getByRole('button',{name:'Остановить',exact:true}).click();await expect(page.getByRole('button',{name:'Повторить явно (новый вызов)'})).toBeVisible();await shot(page,info,'14-stopped');
  const id=await page.evaluate(()=>localStorage.getItem('chat-selection'));const stopped=await (await request.get(`/api/chat/campaigns/${id}`)).json();
  await page.reload();await expect(page.getByRole('button',{name:'Повторить явно (новый вызов)'})).toBeVisible();expect((await (await request.get(`/api/chat/campaigns/${id}`)).json()).job.id).toBe(stopped.job.id);
  await page.getByRole('button',{name:'Повторить явно (новый вызов)'}).click();await expect(page.locator('.chat-assistant').last().locator('header')).toContainText('Сохранено');
  await page.getByLabel('Твоё сообщение',{exact:true}).fill('Очень большой ввод '.repeat(4000));await expect(page.getByText('Ввод не помещается в контекст.',{exact:false})).toBeVisible();await expect(page.getByRole('button',{name:'Отправить',exact:true})).toBeDisabled();await fits(page);const notice=await page.locator('.chat-notice').first().boundingBox();const memoryAction=await page.getByRole('button',{name:'Редактор памяти',exact:true}).boundingBox();expect(memoryAction!.y+memoryAction!.height).toBeLessThanOrEqual(notice!.y+notice!.height);await shot(page,info,'15-context-warning');
  if(info.project.name==='mobile'){await page.getByLabel('Твоё сообщение',{exact:true}).focus();await page.setViewportSize({width:320,height:420});await expect(page.getByRole('button',{name:'Редактор памяти',exact:true})).toBeInViewport();await expect(page.getByRole('button',{name:'Отправить',exact:true})).toBeInViewport();await shot(page,info,'15-context-keyboard');await page.setViewportSize({width:320,height:780});await page.getByLabel('Твоё сообщение',{exact:true}).blur()}
  await page.getByLabel('Твоё сообщение',{exact:true}).fill('Черновик перед возвратом');await page.goBack();await expect(page.getByRole('button',{name:'RP-чат',exact:true})).toBeVisible();await page.getByRole('button',{name:'RP-чат',exact:true}).click();await expect(page.getByLabel('Твоё сообщение',{exact:true})).toHaveValue('Черновик перед возвратом');
  await page.getByRole('button',{name:'Кампании RP-чата',exact:true}).click();await page.getByRole('dialog').getByRole('button',{name:'Новая RP-кампания',exact:true}).click();const d=page.getByRole('dialog');
  await d.getByRole('button',{name:'Создать по идее',exact:true}).click();await d.getByLabel('Идея игры',{exact:true}).fill('Новая история');await d.getByRole('group',{name:'Обычный RP-ответ'}).getByLabel('Модель',{exact:true}).fill('unknown-fixture');
  await d.getByRole('button',{name:'Сгенерировать первоначальную выжимку',exact:true}).click();await expect(d.getByRole('alert')).toContainText('Размер контекста неизвестен');await fits(page);await shot(page,info,'16-creation-error');
  await d.getByRole('group',{name:'Обычный RP-ответ'}).getByLabel('Модель',{exact:true}).fill('chat-mobile-fixture');await d.getByRole('button',{name:'Сгенерировать первоначальную выжимку',exact:true}).click();await d.getByRole('button',{name:'Остановить генерацию выжимки',exact:true}).click();await expect(d.getByText('Ответ неполный.',{exact:false})).toBeVisible();await fits(page);await shot(page,info,'17-initial-stopped');await expect(d.getByRole('button',{name:'Начать игру',exact:true})).toBeDisabled();
  await d.getByRole('button',{name:'Сгенерировать заново',exact:true}).click();await expect(d.getByRole('button',{name:'Остановить генерацию выжимки',exact:true})).toHaveCount(0);await expect(d.getByLabel('Стартовая выжимка',{exact:true})).toHaveValue(/ПРАВИЛА И НЕИЗМЕННЫЕ ФАКТЫ/);
});


test('Chat skins keep controls and reading layout usable',async({page},info)=>{
  test.setTimeout(120000);if(info.project.name==='mobile')await page.setViewportSize({width:320,height:780});
  await create(page);
  for(const skin of themes){
    await page.getByRole('button',{name:'Настройки RP-чата',exact:true}).click();await chooseOption(page.getByRole('combobox',{name:'Тема мира',exact:true}), skin.id);await fits(page);await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page.locator('html')).toHaveAttribute('data-theme',skin.id);await fits(page);
    const tooltip=page.locator('.chat-header').getByRole('tooltip',{name:'Настройки RP-чата',exact:true});if(await tooltip.isVisible()){const b=await tooltip.boundingBox();expect(b!.x).toBeGreaterThanOrEqual(0);expect(b!.y).toBeGreaterThanOrEqual(0);expect(b!.x+b!.width).toBeLessThanOrEqual(page.viewportSize()!.width)}
    if(info.project.name==='mobile')expect((await page.locator('.chat-toolbar').boundingBox())!.height).toBeLessThanOrEqual(50);
    const action=page.locator('.chat-assistant').last().getByRole('button',{name:'Редактировать',exact:true});await expect(action).toBeVisible();await action.scrollIntoViewIfNeeded();
    if(skin.id==='terminal'||skin.id==='cyberpunk')await shot(page,info,`skin-${skin.id}`);
  }
});
