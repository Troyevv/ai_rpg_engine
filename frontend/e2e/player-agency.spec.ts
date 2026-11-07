import {expect, test} from '@playwright/test';
import {defaults} from '../src/types';

const action = 'Я, Нина, спрашиваю Веру о состоянии Кирилла и предлагаю практическую помощь.';

test('Crisis/001: rejected substitution survives reload; abandon restores input without a model call', async ({page, request}) => {
  const seed = await request.post('/test/agency232-seed');
  expect(seed.ok()).toBeTruthy();
  const selection = await seed.json();
  const path = `/api/saves/${selection.save}`;
  const view = async () => (await request.get(path)).json();
  const requests = async () => (await (await request.get(path + '/accounting')).json()).requests;
  const before = await view();
  const profile = `agency-${selection.save}`;
  await request.put(`/api/settings/${profile}`, {data: {...defaults, game: {
    ...defaults.game, model:'local-model', context_length:32768, update_tokens:4096,
  }}});
  await page.addInitScript(({s, profile}) => {
    localStorage.setItem('selection', JSON.stringify(s));
    localStorage.setItem('profile', profile);
  }, {s:selection, profile});
  await page.goto('/');
  const input = page.getByLabel('Своё действие или реплика');
  const send = page.getByRole('button', {name:'Отправить действие', exact:true});
  const abandon = page.getByRole('button', {name:'Отменить неудачный ход', exact:true});
  const retry = page.getByRole('button', {name:'Повторить обработку состояния', exact:true});
  await input.fill(action);
  await send.click();
  await expect(abandon).toBeEnabled();
  await expect(retry).toHaveCount(0);
  await expect(page.getByText('Повествование изменило или не подтвердило выбранное действие игрока.', {exact:false})).toBeVisible();
  const failed = await view();
  expect(failed.job).toMatchObject({status:'error', retry_allowed:false, user_text:action});
  expect(failed.state).toEqual(before.state);
  expect(failed.turns).toEqual(before.turns);
  const spent = await requests();
  await page.reload();
  await expect(abandon).toBeEnabled();
  await expect(retry).toHaveCount(0);
  await abandon.click();
  await expect(input).toHaveValue(action);
  await expect(send).toBeEnabled();
  expect(await requests()).toEqual(spent);
  await page.reload();
  await expect(input).toHaveValue(action);
  await send.click();
  await expect.poll(async () => (await view()).job.status).toBe('saved');
  const after = await view();
  expect(after.turns.at(-1).user_text).toBe(action);
  expect(after.turns).toHaveLength(before.turns.length + 1);
  expect(after.turns.at(-1).narrative).not.toContain('окликает Марину');
  const old = await (await request.get(`/api/jobs/${failed.job.id}`)).json();
  expect(old.status).toBe('abandoned');
});
