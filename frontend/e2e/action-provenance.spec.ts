import {expect, test} from '@playwright/test';
import {defaults} from '../src/types';

for (const scenario of [
  {case: 'social', repeat: false, action: 'Я согласен сейчас сортировать фотографии по датам, оставляя оригинал карты на месте. Прошу Веру показать первую пачку.'},
  {case: 'knowledge', repeat: false, action: 'Я согласен прийти завтра в библиотеку в 15:00. Спрашиваю Веру, подходит ли ей именно это время.'},
  {case: 'campaign', repeat: true, action: 'Я спрашиваю, что стало с договорённостями, делами мастерской и звонком Олегу.'},
]) {
  test(`#238 ${scenario.case}: bounded repair, reload and atomic provenance`, async ({page, request}) => {
    const seed = await request.post(`/test/provenance238-seed?case=${scenario.case}&repeat=${scenario.repeat}`);
    expect(seed.ok()).toBe(true);
    const selection = await seed.json();
    const path = `/api/saves/${selection.save}`;
    const view = async () => (await request.get(path)).json();
    const before = await view();
    const profile = `provenance-${selection.save}`;
    await request.put(`/api/settings/${profile}`, {data: {...defaults, game: {
      ...defaults.game, model: 'local-model', context_length: 40960, update_tokens: 4096,
    }}});
    await page.addInitScript(({selection, profile}) => {
      localStorage.setItem('selection', JSON.stringify(selection));
      localStorage.setItem('profile', profile);
    }, {selection, profile});
    await page.goto('/');
    const input = page.getByLabel('Своё действие или реплика');
    await input.fill(scenario.action);
    await page.getByRole('button', {name: 'Отправить действие', exact: true}).click();
    await expect.poll(async () => (await view()).job.status).toBe(scenario.repeat ? 'error' : 'saved');
    const after = await view();
    const requests = async () => (await (await request.get(path + '/accounting')).json()).requests;
    const spent = await requests();
    expect(spent.filter((r: {job_id: string}) => r.job_id === after.job.id).map((r: {stage: string}) => r.stage).sort()).toEqual(['extraction', 'extraction_repair', 'narrative']);
    await page.reload();
    await expect(input).toBeVisible();
    expect((await view()).state).toEqual(after.state);
    if (scenario.repeat) {
      expect(after.state).toEqual(before.state);
      expect(after.turns).toEqual(before.turns);
      const abandon = page.getByRole('button', {name: 'Отменить неудачный ход', exact: true});
      await expect(abandon).toBeEnabled();
      await input.fill(scenario.action);
      await abandon.click();
      await expect(page.getByRole('button', {name: 'Отправить действие', exact: true})).toBeEnabled();
      expect((await view()).state).toEqual(before.state);
      expect(await requests()).toEqual(spent);
    } else {
      expect(after.turns).toHaveLength(before.turns.length + 1);
      expect((await view()).turns).toEqual(after.turns);
    }
  });
}
