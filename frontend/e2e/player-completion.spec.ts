import {expect, test} from '@playwright/test';
import {defaults} from '../src/types';

test('Crisis #237: false completion after repair refuses atomically; reload and abandon preserve input', async ({page, request}) => {
  const selection = await (await request.post('/test/agency232-seed?completion=true')).json();
  const path = `/api/saves/${selection.save}`;
  const view = async () => (await request.get(path)).json();
  const before = await view();
  const profile = `completion-${selection.save}`;
  await request.put(`/api/settings/${profile}`, {data: {...defaults, game: {
    ...defaults.game, model: 'local-model', context_length: 32768, update_tokens: 4096,
  }}});
  await page.addInitScript(({selection, profile}) => {
    localStorage.setItem('selection', JSON.stringify(selection));
    localStorage.setItem('profile', profile);
  }, {selection, profile});
  await page.goto('/');
  const action = 'Я, Нина, спрашиваю Веру о состоянии Кирилла и предлагаю практическую помощь.';
  const input = page.getByLabel('Своё действие или реплика');
  const send = page.getByRole('button', {name: 'Отправить действие', exact: true});
  const abandon = page.getByRole('button', {name: 'Отменить неудачный ход', exact: true});
  await input.fill(action);
  await send.click();
  await expect(abandon).toBeEnabled();
  const failed = await view();
  expect(failed.job.status).toBe('error');
  expect(failed.job.user_text).toBe(action);
  expect(failed.state).toEqual(before.state);
  expect(failed.turns).toEqual(before.turns);
  const accounting = async () => (await (await request.get(path + '/accounting')).json()).requests;
  const spent = await accounting();
  await page.reload();
  await expect(abandon).toBeEnabled();
  // Retryable Extraction failures do not auto-restore the original input.
  // A draft prepared while the rejected job is held must survive abandon.
  await input.fill(action);
  await expect(send).toBeDisabled();
  await abandon.click();
  await expect(input).toHaveValue(action);
  await expect(send).toBeEnabled();
  expect(await accounting()).toEqual(spent);
  expect((await (await request.get(`/api/jobs/${failed.job.id}`)).json()).user_text).toBe(action);
  await send.click();
  await expect.poll(async () => (await view()).job.status).toBe('saved');
  expect((await view()).turns).toHaveLength(before.turns.length + 1);
});
