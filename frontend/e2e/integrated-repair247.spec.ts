import {expect, test} from '@playwright/test';
import {defaults} from '../src/types';

for (const scenario of ['knowledge', 'family', 'phone', 'crisis', 'retry', 'live-knowledge', 'live-family', 'live-phone', 'live-crisis', 'live-social']) {
  test(`#247 ${scenario}: recovery preserves state and input after reload`, async ({page, request}) => {
    const live = scenario.startsWith('live-');
    const base = scenario.replace('live-', '');
    const seed = await request.post(`/test/integrated247-seed?case=${base === 'retry' ? 'knowledge' : base}&repeat=${base === 'retry'}&live=${live}`);
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
    const refused = base === 'crisis' || base === 'retry';
    await expect.poll(async () => (await view()).job?.status).toBe(refused ? 'error' : 'saved');
    const after = await view();
    const accounting = async () => (await (await request.get(path + '/accounting')).json()).requests;
    const spent = await accounting();
    // #250/#251: optional audit and duplicate Movement sources buy no repair.
    // The old phone extraction falsely asserts arrivals: Runtime cannot infer
    // that semantic error from prose. Keep it visible as a replay risk.
    const firstPass = base === 'phone' || (live && ['family', 'social'].includes(base));
    expect(spent.filter((r: {job_id: string}) => r.job_id === after.job.id)).toHaveLength(firstPass ? 2 : 3);
    await page.reload();
    await expect(input).toBeVisible();
    expect((await view()).state).toEqual(after.state);
    const retry = page.getByRole('button', {name: 'Повторить обработку состояния', exact: true});
    if (base === 'crisis') {
      expect(after.state).toEqual(before.state);
      expect(after.turns).toEqual(before.turns);
      await expect(retry).toHaveCount(0);
      await page.getByRole('button', {name: 'Отменить неудачный ход', exact: true}).click();
      await expect(input).toHaveValue(selection.action);
      await expect(page.getByRole('button', {name: 'Отправить действие', exact: true})).toBeEnabled();
      expect(await accounting()).toEqual(spent);
    } else if (base === 'retry') {
      expect(after.state).toEqual(before.state);
      await request.post('/test/integrated247-allow-repair');
      await retry.click();
      await expect.poll(async () => (await view()).job?.status).toBe('saved');
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
