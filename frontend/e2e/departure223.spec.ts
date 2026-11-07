import {expect, test} from '@playwright/test';
import {defaults} from '../src/types';

test('Phone #223: future plan plus departure saves unknown location and survives reload', async ({page, request}) => {
  const selection = await (await request.post('/test/departure223-seed')).json();
  const path = `/api/saves/${selection.save}`;
  const view = async () => (await request.get(path)).json();
  const before = await view();
  const profile = `departure-${selection.save}`;
  await request.put(`/api/settings/${profile}`, {data: {...defaults, game: {
    ...defaults.game, model: 'local-model', context_length: 32768, update_tokens: 4096,
  }}});
  await page.addInitScript(({selection, profile}) => {
    localStorage.setItem('selection', JSON.stringify(selection));
    localStorage.setItem('profile', profile);
  }, {selection, profile});
  await page.goto('/');
  await page.getByLabel('Своё действие или реплика').fill('Я остаюсь на месте, занимаюсь своими фотографиями и даю другим возможность связаться со мной.');
  await page.getByRole('button', {name: 'Отправить действие', exact: true}).click();
  await expect.poll(async () => (await view()).job?.status).toBe('saved');
  const saved = await view();
  expect(saved.turns).toHaveLength(before.turns.length + 1);
  expect(saved.state.scene_meta.present_ids).not.toContain('qa_timur');
  const canonical = async () => (await (await request.get(path + '/author-state')).json()).snapshot.world_state;
  const state = await canonical();
  expect(state.characters.qa_timur.location_id).toBeNull();
  await expect(page.getByText('Дверь закрывается.', {exact: false}).first()).toBeVisible();
  const accounting = async () => (await (await request.get(path + '/accounting')).json()).requests;
  const requests = await accounting();
  await page.reload();
  await expect(page.getByText('Дверь закрывается.', {exact: false}).first()).toBeVisible();
  await page.getByLabel('Своё действие или реплика').fill('Продолжаю заниматься фотографиями.');
  await expect(page.getByRole('button', {name: 'Отправить действие', exact: true})).toBeEnabled();
  const reloaded = await view();
  expect(reloaded.state).toEqual(saved.state);
  expect(reloaded.turns).toEqual(saved.turns);
  expect(await canonical()).toEqual(state);
  expect(await accounting()).toEqual(requests);
});
