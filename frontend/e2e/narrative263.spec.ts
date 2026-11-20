import {test,expect} from '@playwright/test';
import {defaults} from '../src/types';

test.afterEach(async({request})=>{await request.post('/test/scene255-reset')});

for (const width of [360,393,1280]) {
  test(`published prose, partial Extraction and editable suggestions at ${width}px`,async({page,request},info)=>{
    test.skip((width===1280)!==(info.project.name==='desktop'));
    await page.setViewportSize({width,height:width===1280?900:612});
    const selection=await (await request.post('/test/scene263-seed')).json();
    const path=`/api/saves/${selection.save}`, profile=`scene263-${selection.save}`;
    await request.put(`/api/settings/${profile}`,{data:{...defaults,game:{...defaults.game,model:'scene263-test',context_length:65536}}});
    await page.addInitScript(({selection,profile})=>{
      localStorage.setItem('selection',JSON.stringify(selection));
      localStorage.setItem('profile',profile);
    },{selection,profile});
    await page.goto('/');
    const view=async()=>(await request.get(path)).json();
    const before=await view();
    const input=page.getByLabel('Своё действие или реплика');
    const send=page.getByRole('button',{name:'Отправить действие',exact:true});
    await input.fill('Рассматриваю фотографию.');
    await send.click();
    await input.fill('Спрошу о погоде.');
    const correction=page.getByRole('button',{name:'Исправить противоречие в сцене'});
    await expect.poll(async()=>(await view()).revision).toBe(before.revision+2);
    const after=await view();
    expect(after.revision).toBe(before.revision+2);
    expect(after.turns).toHaveLength(before.turns.length+1);
    const scene=after.turns.at(-1);
    expect(scene.assistant_text).toContain('Кирилл отказывается от чая.');
    expect(scene.assistant_text).not.toContain('<action_suggestions>');
    expect(scene.changes.interpretation).toBe('partial');
    expect(after.job.repairs).toHaveLength(0);
    await expect(correction).toHaveCount(0);
    await expect(send).toBeEnabled();
    await expect(page.getByText('Чужой секрет')).toHaveCount(0);
    await page.reload();
    await expect(input).toHaveValue('Спрошу о погоде.');
    await expect(page.locator('.turn').last().getByText('Сцена сохранена. Есть замечания к состоянию мира.')).toBeVisible();
    const choice=page.locator('.choices button').filter({hasText:'Налить воды'});
    await expect(choice).toBeEnabled();
    await expect(page.locator('.turn').last().locator('strong').filter({hasText:'В альбоме'})).toBeVisible();
    await expect(page.locator('.turn').last().locator('hr')).toHaveCount(1);
    await expect(page.getByText('Чужой секрет')).toHaveCount(0);
    await choice.click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(input).toHaveValue('Спрошу о погоде.');
    await choice.click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.goBack();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await choice.click();
    await page.getByRole('button',{name:'Добавить к черновику'}).click();
    await expect(input).toHaveValue('Спрошу о погоде.\nНалить воды');
    await expect(input).toBeFocused();
    await choice.click();
    await page.getByRole('button',{name:'Заменить черновик'}).click();
    await expect(input).toHaveValue('Налить воды');
    if(width<400) await page.setViewportSize({width,height:430});
    await expect(input).toBeInViewport();
    await page.reload();
    await expect(input).toHaveValue('Налить воды');
    expect((await view()).revision).toBe(after.revision);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  });
}

test('six authored actions survive reload and keep the editable draft', async ({page, request}) => {
  const selection = await (await request.post('/test/scene263-seed?delay_interpretation=true')).json();
  const profile = 'frame263-' + selection.save;
  await request.put('/api/settings/' + profile, {data: {...defaults, game: {...defaults.game, model:'frame263-test', context_length:65536}}});
  await page.addInitScript(({selection, profile}) => {
    localStorage.setItem('selection',JSON.stringify(selection));
    localStorage.setItem('profile',profile);
  }, {selection, profile});
  await page.goto('/');
  const input = page.getByLabel('Своё действие или реплика');
  await input.fill('Что видно у окна?');
  await page.getByRole('button',{name:'Отправить действие',exact:true}).click();
  const choices = page.locator('.choices button');
  try {
    await expect.poll(async () => (await (await request.get('/api/saves/' + selection.save)).json()).turns.at(-1).changes.interpretation).toBe('pending');
    await page.reload();
    await expect(page.getByText('Сцена сохранена. Время, место и последствия ещё уточняются.').first()).toBeVisible();
    await expect(page.locator('.scene-clock:visible').first()).toContainText('по сохранению');
  } finally {
    await request.post('/test/scene264-release');
  }
  await expect(choices).toHaveCount(6);
  const read = async () => (await request.get('/api/saves/' + selection.save)).json();
  await expect.poll(async () => (await read()).job.status).toBe('saved');
  const revision = (await read()).revision;
  await input.fill('Мой черновик');
  await page.reload();
  await expect(choices).toHaveCount(6);
  await choices.filter({hasText:'Открыть альбом'}).click();
  await page.getByRole('button',{name:'Добавить к черновику'}).click();
  await expect(input).toHaveValue('Мой черновик\nОткрыть альбом');
  await input.fill('');
  await choices.filter({hasText:'Позвать хозяйку'}).click();
  await expect(input).toHaveValue('Позвать хозяйку: «Анна, можно взглянуть на альбом?»');
  expect((await read()).turns.at(-1).choices[2]).toMatchObject({
    action:'Позвать хозяйку', speech:'Анна, можно взглянуть на альбом?'
  });
  await input.fill('Открываю альбом на первой странице.');
  expect((await read()).revision).toBe(revision);
});

test('a free direction from an incapacitated hero follows the observer camera', async ({page, request}) => {
  const selection = await (await request.post('/test/family-seed?checkpoint=family-incapacitated&current=true')).json();
  const profile = 'observer263-' + selection.save;
  await request.put('/api/settings/' + profile, {data: {...defaults, game: {...defaults.game, model:'frame263-test', context_length:65536}}});
  await page.addInitScript(({selection, profile}) => {
    localStorage.setItem('selection',JSON.stringify(selection));
    localStorage.setItem('profile',profile);
  }, {selection, profile});
  await page.goto('/');
  const before = await (await request.get('/api/saves/' + selection.save)).json();
  const direction = 'Показать, что происходит у окна.';
  await page.getByRole('textbox',{name:'Направление истории',exact:true}).fill(direction);
  const sent = page.waitForRequest(r => r.method()==='POST' && r.url().endsWith('/camera'));
  await page.getByRole('button',{name:'Отправить направление истории',exact:true}).click();
  expect((await sent).postDataJSON()).toMatchObject({actor_id:before.state.protagonist_id,direction});
  const read = async () => (await request.get('/api/saves/' + selection.save)).json();
  await expect.poll(async () => (await read()).turns.length).toBe(before.turns.length+1);
  const after = await read();
  expect(after.turns.at(-1)).toMatchObject({kind:'background',user_text:direction});
  expect(after.state.controlled_actor_id).toBeNull();
  await expect(page.locator('.choices button')).toHaveCount(6);
});

test('canceling a blank provider reply restores the original editable input', async ({page, request}) => {
  const selection = await (await request.post('/test/scene263-seed')).json();
  const profile = 'blank263-' + selection.save;
  await request.put('/api/settings/' + profile, {data: {...defaults, game: {...defaults.game, model:'blank263-test',context_length:65536}}});
  await page.addInitScript(({selection,profile}) => {
    localStorage.setItem('selection',JSON.stringify(selection));
    localStorage.setItem('profile',profile);
  }, {selection,profile});
  const read = async () => (await request.get('/api/saves/' + selection.save)).json();
  const before = await read();
  await page.goto('/');
  const input = page.getByLabel('Своё действие или реплика',{exact:true});
  const action = 'Спрашиваю, что слышно во дворе.';
  await input.fill(action);
  await page.getByRole('button',{name:'Отправить действие',exact:true}).click();
  await expect.poll(async () => (await read()).job?.status).toBe('error');
  await page.reload();
  const cancel = page.getByRole('button',{name:'Отменить неудачный ход',exact:true});
  await cancel.focus();
  await page.keyboard.press('Enter');
  await expect(input).toHaveValue(action);
  await page.reload();
  await expect(input).toHaveValue(action);
  const after = await read();
  expect(after.revision).toBe(before.revision);
  expect(after.turns).toHaveLength(before.turns.length);
});
