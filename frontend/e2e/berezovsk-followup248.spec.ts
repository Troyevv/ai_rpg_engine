import {expect, test} from '@playwright/test';
import {defaults} from '../src/types';

for (const scenario of ['002','005']) {
  test(`Berezovsk D/${scenario}: sources and recovery survive reload`, async ({page, request}) => {
    const seed = await request.post(`/test/berezovsk-followup-seed?case=${scenario}`);
    expect(seed.ok()).toBe(true);
    const selection = await seed.json();
    const profile = `berezovsk-${selection.save}`;
    const path = `/api/saves/${selection.save}`;
    const view = async () => (await request.get(path)).json();
    await request.put(`/api/settings/${profile}`, {data: {...defaults, game: {
      ...defaults.game, model:'berezovsk-followup-test', context_length:131072, update_tokens:8192,
    }}});
    await page.addInitScript(({selection,profile}) => {
      localStorage.setItem('selection',JSON.stringify(selection));
      localStorage.setItem('profile',profile);
    },{selection,profile});
    const before=await view();
    await page.goto('/');
    const input=page.getByLabel('Своё действие или реплика');
    await input.fill(selection.action);
    await page.getByRole('button',{name:'Отправить действие',exact:true}).click();
    await expect.poll(async () => (await view()).job.status).toBe(scenario==='002'?'saved':'error');
    const first=await view();
    await page.reload();
    expect((await view()).state).toEqual(first.state);
    if (scenario==='002') {
      await expect(page.locator('.choices button')).toHaveCount(5);
      await expect(page.locator('.choices')).not.toContainText('Про письмо');
      expect(first.state.world.knowledge).toEqual(before.state.world.knowledge);
      await expect(input).toBeEnabled();
      await input.fill('Спрошу о письме, если такое есть.');
      await expect(input).toHaveValue('Спрошу о письме, если такое есть.');
    } else {
      expect(first.state).toEqual(before.state);
      expect(first.turns).toEqual(before.turns);
      await page.getByRole('button',{name:'Повторить обработку состояния',exact:true}).click();
      await expect.poll(async () => (await view()).job.status).toBe('saved');
      const after=await view();
      expect(after.state.world.characters.char_alexey.location_id).toBe('loc_home_viktor');
      expect(after.turns).toHaveLength(before.turns.length+1);
      const requests=(await (await request.get(path+'/accounting')).json()).requests;
      const attempts=requests.filter((r:{job_id:string}) => r.job_id===first.job.id);
      expect(attempts).toHaveLength(4);
      expect(attempts.filter((r:{stage:string})=>r.stage==='narrative')).toHaveLength(1);
      await page.reload();
      expect((await view()).state).toEqual(after.state);
      await expect(input).toBeEnabled();
    }
    expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
  });
}
