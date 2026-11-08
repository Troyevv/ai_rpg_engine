import {expect, test} from '@playwright/test';
import {defaults} from '../src/types';

for (const mode of ['saved', 'missing', 'uncertain', 'invalid', 'reauthor']) {
  test(`#250 ${mode}: optional audit and genuine recovery survive reload`, async ({page, request}) => {
    const seed = await request.post(`/test/agency249-seed?mode=${mode}`);
    expect(seed.ok()).toBe(true);
    const selection = await seed.json();
    const path = `/api/saves/${selection.save}`;
    const view = async () => (await request.get(path)).json();
    const before = await view();
    const profile = `agency249-${selection.save}`;
    await request.put(`/api/settings/${profile}`, {data: {...defaults, game: {
      ...defaults.game, model: 'agency249-test', context_length: 49152, update_tokens: 4096,
    }}});
    await page.addInitScript(({selection, profile}) => {
      localStorage.setItem('selection', JSON.stringify(selection));
      localStorage.setItem('profile', profile);
    }, {selection, profile});
    await page.goto('/');
    const input = page.getByLabel('Своё действие или реплика');
    await input.fill(selection.action);
    await page.getByRole('button', {name: 'Отправить действие', exact: true}).click();
    await expect.poll(async () => (await view()).job.status).toBe(['reauthor','invalid'].includes(mode) ? 'error' : 'saved');
    const after = await view();
    const requests = (await (await request.get(path + '/accounting')).json()).requests;
    expect(requests.filter((r: {job_id: string}) => r.job_id === after.job.id)).toHaveLength(mode === 'invalid' ? 3 : 2);
    await page.reload();
    await expect(input).toBeVisible();
    expect((await view()).state).toEqual(after.state);
    await expect(page.getByText('narrative_audit', {exact: true})).toHaveCount(0);
    const retry = page.getByRole('button', {name: 'Повторить обработку состояния', exact: true});
    if (mode === 'reauthor') {
      expect(after.state).toEqual(before.state);
      expect(after.turns).toEqual(before.turns);
      await expect(retry).toHaveCount(0);
      await page.getByRole('button', {name: 'Отменить неудачный ход', exact: true}).click();
      await expect(input).toHaveValue(selection.action);
    } else if (mode === 'invalid') {
      expect(after.state).toEqual(before.state);
      await request.post('/test/agency249-allow');
      await retry.click();
      await expect.poll(async () => (await view()).job.status).toBe('saved');
      const recovered = (await (await request.get(path + '/accounting')).json()).requests;
      expect(recovered.filter((r: {job_id: string}) => r.job_id === after.job.id)).toHaveLength(4);
      expect(recovered.filter((r: {job_id: string; stage: string}) => r.job_id === after.job.id && r.stage === 'narrative')).toHaveLength(1);
    } else {
      expect(after.turns).toHaveLength(before.turns.length + 1);
      await expect(input).toBeEnabled();
      await expect(page.getByRole('button', {name: /Посмотреть в окно/})).toBeVisible();
      await input.fill(selection.action);
      await page.getByRole('button', {name: 'Отправить действие', exact: true}).click();
      await expect.poll(async () => (await view()).turns.length).toBe(after.turns.length + 1);
      expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    }
  });
}
