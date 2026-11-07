import {expect, test} from '@playwright/test';
import {defaults} from '../src/types';

test('ongoing labor repairs once, persists after reload and rejects repeated clock error atomically', async ({page, request}) => {
  const selection = await (await request.post('/test/birth231-seed')).json();
  const path = `/api/saves/${selection.save}`;
  const view = async () => (await request.get(path)).json();
  const profile = `due240-${selection.save}`;
  expect((await request.put(`/api/settings/${profile}`, {data:{...defaults,
    game:{...defaults.game, model:'local-model', context_length:65536, update_tokens:4096},
  }})).ok()).toBeTruthy();
  await page.addInitScript(({selection, profile}) => {
    localStorage.setItem('selection', JSON.stringify(selection));
    localStorage.setItem('profile', profile);
  }, {selection, profile});
  await page.goto('/');
  const input = page.getByLabel('Своё действие или реплика');
  const send = page.getByRole('button', {name:'Отправить действие', exact:true});
  const abandon = page.getByRole('button', {name:'Отменить неудачный ход', exact:true});
  const action = 'Я остаюсь рядом с Верой и наблюдаю.';
  for (const mode of ['zero','repair']) {
    const before = await view();
    await request.post(`/test/due240-response?sid=${selection.save}&mode=${mode}`);
    await input.fill(action);
    await send.click();
    await expect.poll(async () => (await view()).turns.length).toBe(before.turns.length+1);
    await expect(input).toBeEnabled();
    await expect(input).toHaveValue('');
    await expect(send).toBeDisabled(); // Empty actions are intentionally not submittable.
    const after = await view();
    expect(after.job.status).toBe('saved');
    expect(after.turns.slice(0,-1)).toEqual(before.turns);
    const turn = after.turns.at(-1);
    expect(turn.assistant_text).toContain('Ещё одна потуга.');
    const log = await (await request.get(path+'/accounting')).json();
    const diagnostics = log.turns.find((t: {id: number}) => t.id===turn.id);
    expect(diagnostics.requests.map((r: {stage: string}) => r.stage).sort()).toEqual(
      mode==='zero' ? ['extraction','narrative'] : ['extraction','extraction_repair','narrative']);
    if (mode==='repair') expect(diagnostics.repairs[0].code).toBe('ordinary_temporal_boundary');
    await page.reload();
    expect((await view()).state).toEqual(after.state);
  }
  const before = await view();
  await request.post(`/test/due240-response?sid=${selection.save}&mode=repeat`);
  await input.fill(action);
  await send.click();
  await expect(abandon).toBeVisible();
  const failed = await view();
  expect(failed.job.status).toBe('error');
  expect(failed.job.user_text).toBe(action);
  expect(failed.job.repairs).toHaveLength(2);
  expect(failed.state).toEqual(before.state);
  expect(failed.turns).toEqual(before.turns);
  await page.reload();
  await expect(abandon).toBeVisible();
  const accounting = await (await request.get(path+'/accounting')).json();
  // Retryable Extraction does not restore input automatically. Preserve a draft
  // authored while the failed job is held, as in the existing recovery flow.
  await input.fill(action);
  await abandon.click();
  await expect(abandon).toHaveCount(0);
  await expect(input).toHaveValue(action);
  expect((await (await request.get(path+'/accounting')).json()).requests).toEqual(accounting.requests);
  expect((await view()).state).toEqual(before.state);
});
