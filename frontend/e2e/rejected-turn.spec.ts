import {expect, test} from '@playwright/test';
import {defaults} from '../src/types';

const question = 'Вера, во сколько завтра встретимся в библиотеке?';
const consent = 'Я согласен прийти завтра в библиотеку в 15:00. Спрашиваю Веру, подходит ли ей именно это время.';

test('Stage C Knowledge: reload rejected agreement and continue from the accepted turn', async ({page, request}) => {
  const seed = await request.post('/test/knowledge-seed');
  expect(seed.ok()).toBeTruthy();
  const selection = await seed.json();
  const path = `/api/saves/${selection.save}`;
  const view = async () => (await request.get(path)).json();
  const requests = async () => (await (await request.get(path + '/accounting')).json()).requests;
  const before = await view();
  const profile = `recovery-${selection.save}`;
  expect((await request.put(`/api/settings/${profile}`, {data: {
    ...defaults, game: {...defaults.game, model:'local-model', context_length:32768, update_tokens:4096},
  }})).ok()).toBeTruthy();
  await page.addInitScript(({s, profile}) => {
    localStorage.setItem('selection', JSON.stringify(s));
    localStorage.setItem('profile', profile);
  }, {s:selection, profile});
  await page.goto('/');
  const input = page.getByLabel('Своё действие или реплика');
  const send = page.getByRole('button', {name: 'Отправить действие', exact: true});
  const retry = page.getByRole('button', {name: 'Повторить обработку состояния', exact: true});
  const rollback = page.getByRole('button', {name: 'Откатить', exact: true});
  await input.fill(question);
  await send.click();
  await expect(retry).toBeEnabled();
  const failed = await view();
  expect(failed.job).toMatchObject({status: 'error', narrative_complete: 1, revision: before.revision});
  expect(failed.job.repairs.at(-1).repair_error_code).toBe('controlled_actor_unsupported');
  expect(failed.turns).toEqual(before.turns);
  expect(failed.state).toEqual(before.state);
  const spent = await requests();
  await page.reload();
  await input.fill(consent);
  await expect(send).toBeDisabled();
  await expect(rollback).toBeEnabled();
  const abandon = page.getByRole('button', {name: 'Отменить неудачный ход', exact: true});
  const recoveryRequests: string[] = [];
  page.on('request', r => { if (r.url().endsWith('/abandon')) recoveryRequests.push(r.url()); });
  await abandon.focus();
  // Two activation events in the same tick exercise the synchronous request lock.
  await page.route('**/abandon', async route => {
    await new Promise(resolve => setTimeout(resolve, 100));
    await route.continue();
  });
  await page.keyboard.press('Enter');
  await page.keyboard.press('Enter');
  await expect(abandon).toHaveCount(0);
  await expect(input).toHaveValue(consent);
  await expect(send).toBeEnabled();
  expect(recoveryRequests).toHaveLength(1);
  await page.reload();
  await expect(send).toBeEnabled();
  await expect(abandon).toHaveCount(0);
  expect((await view()).turns).toEqual(before.turns);
  expect(await requests()).toEqual(spent);
  await send.click();
  await expect.poll(async () => (await view()).job.status).toBe('saved');
  const after = await view();
  expect(after.turns.slice(0, -1)).toEqual(before.turns);
  expect(after.turns.at(-1).user_text).toBe(consent);
  expect(after.revision).toBe(before.revision + 1);
  const oldJob = await (await request.get(`/api/jobs/${failed.job.id}`)).json();
  expect(oldJob).toMatchObject({status:'abandoned', error:failed.job.error, repairs:failed.job.repairs});
  await page.reload();
  await expect(rollback).toBeEnabled();
});
