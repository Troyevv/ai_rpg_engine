import {expect, test} from '@playwright/test';
import {defaults} from '../src/types';

for (const scenario of ['knowledge', 'family', 'phone', 'crisis', 'retry']) {
  test(`#247 ${scenario}: recovery preserves state and input after reload`, async ({page, request}) => {
    const seed = await request.post(`/test/integrated247-seed?case=${scenario === 'retry' ? 'knowledge' : scenario}&repeat=${scenario === 'retry'}`);
    expect(seed.ok()).toBe(true);
    const selection = await seed.json();
    const path = `/api/saves/${selection.save}`;
    const view = async () => (await request.get(path)).json();
    const before = await view();
    const profile = `integrated-${selection.save}`;
    await request.put(`/api/settings/${profile}`, {data: {...defaults, game: {
      ...defaults.game, model: 'integrated-test', context_length: 49152, update_tokens: 4096,
    }}});
    await page.addInitScript(({selection, profile}) => {
      localStorage.setItem('selection', JSON.stringify(selection));
      localStorage.setItem('profile', profile);
    }, {selection, profile});
    await page.goto('/');
    const input = page.getByLabel('Своё действие или реплика');
    await input.fill(selection.action);
    await page.getByRole('button', {name: 'Отправить действие', exact: true}).click();
    const refused = scenario === 'crisis' || scenario === 'retry';
    await expect.poll(async () => (await view()).job.status).toBe(refused ? 'error' : 'saved');
    const after = await view();
    const accounting = async () => (await (await request.get(path + '/accounting')).json()).requests;
    const spent = await accounting();
    expect(spent.filter((r: {job_id: string}) => r.job_id === after.job.id)).toHaveLength(3);
    await page.reload();
    await expect(input).toBeVisible();
    expect((await view()).state).toEqual(after.state);
    const retry = page.getByRole('button', {name: 'Повторить обработку состояния', exact: true});
    if (scenario === 'crisis') {
      expect(after.state).toEqual(before.state);
      expect(after.turns).toEqual(before.turns);
      await expect(retry).toHaveCount(0);
      await page.getByRole('button', {name: 'Отменить неудачный ход', exact: true}).click();
      await expect(input).toHaveValue(selection.action);
      await expect(page.getByRole('button', {name: 'Отправить действие', exact: true})).toBeEnabled();
      expect(await accounting()).toEqual(spent);
    } else if (scenario === 'retry') {
      expect(after.state).toEqual(before.state);
      await request.post('/test/integrated247-allow-repair');
      await retry.click();
      await expect.poll(async () => (await view()).job.status).toBe('saved');
      const requests = await accounting();
      expect(requests.filter((r: {job_id: string}) => r.job_id === after.job.id)).toHaveLength(4);
      expect(requests.filter((r: {job_id: string; stage: string}) => r.job_id === after.job.id && r.stage === 'narrative')).toHaveLength(1);
      await page.reload();
      expect((await view()).turns).toHaveLength(before.turns.length + 1);
    } else {
      expect(after.turns).toHaveLength(before.turns.length + 1);
      expect((await view()).turns).toEqual(after.turns);
    }
  });
}
