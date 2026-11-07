import {expect, test} from '@playwright/test';
import {defaults} from '../src/types';

test('birth contradiction rejects the scene, survives reload and needs new authorship', async ({page, request}) => {
  const selection = await (await request.post('/test/birth231-seed')).json();
  const path = `/api/saves/${selection.save}`;
  const view = async () => (await request.get(path)).json();
  const before = await view();
  const profile = `birth231-${selection.save}`;
  expect((await request.put(`/api/settings/${profile}`, {data:{...defaults,
    game:{...defaults.game, model:'local-model', context_length:65536, update_tokens:4096},
  }})).ok()).toBeTruthy();
  await page.addInitScript(({selection, profile}) => {
    localStorage.setItem('selection', JSON.stringify(selection));
    localStorage.setItem('profile', profile);
  }, {selection, profile});
  await request.post(`/test/birth231-response?sid=${selection.save}&wrong=true`);
  await page.goto('/');
  const input = page.getByLabel('Своё действие или реплика');
  const send = page.getByRole('button', {name:'Отправить действие', exact:true});
  const retry = page.getByRole('button', {name:'Повторить обработку состояния', exact:true});
  const abandon = page.getByRole('button', {name:'Отменить неудачный ход', exact:true});
  await input.fill('Я остаюсь рядом с Верой и наблюдаю.');
  await send.click();
  await expect(abandon).toBeVisible();
  await expect(retry).toHaveCount(0);
  await expect(send).toBeDisabled();
  const failed = await view();
  expect(failed.job).toMatchObject({status:'error', narrative_reauthor_required:true, retry_allowed:false});
  expect(failed.turns).toEqual(before.turns);
  expect(failed.state).toEqual(before.state);
  await page.reload();
  await expect(abandon).toBeVisible();
  await expect(retry).toHaveCount(0);
  await expect(send).toBeDisabled();
  const accounting = await (await request.get(path+'/accounting')).json();
  const denied = await request.post(`/api/jobs/${failed.job.id}/retry`, {data:{config:defaults.game}});
  expect(denied.ok()).toBeFalsy();
  expect((await (await request.get(path+'/accounting')).json()).requests).toEqual(accounting.requests);
  await abandon.click();
  await expect(abandon).toHaveCount(0);
  await expect(input).toHaveValue('Я остаюсь рядом с Верой и наблюдаю.');
  expect((await (await request.get(path+'/accounting')).json()).requests).toEqual(accounting.requests);
  await request.post(`/test/birth231-response?sid=${selection.save}`);
  await input.fill('Я остаюсь рядом с Верой и наблюдаю.');
  await send.click();
  await expect.poll(async () => (await view()).job.status).toBe('saved');
  const after = await view();
  expect(after.turns.at(-1).assistant_text).toContain('Мальчик');
  expect(after.turns.at(-1).assistant_text).not.toContain('Девочка');
  expect(after.turns.slice(0,-1)).toEqual(before.turns);
  await page.reload();
  await expect(abandon).toHaveCount(0);
  expect((await view()).state).toEqual(after.state);
});
