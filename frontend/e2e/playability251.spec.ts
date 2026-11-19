import {expect, test} from '@playwright/test';
import {defaults} from '../src/types';

for (const scenario of ['002','008','016','020']) {
  test(`Berezovsk 251/${scenario}: ordinary scene and recovery`, async ({page, request}) => {
    const response = await request.post(`/test/playability251-seed?case=${scenario}`);
    expect(response.ok()).toBe(true);
    const selection = await response.json();
    const profile = `playability251-${selection.save}`;
    const path = `/api/saves/${selection.save}`;
    const view = async () => (await request.get(path)).json();
    await request.put(`/api/settings/${profile}`, {data:{...defaults, game:{...defaults.game,
      model:'berezovsk-followup-test', context_length:131072, update_tokens:8192}}});
    await page.addInitScript(({selection,profile}) => {
      localStorage.setItem('selection',JSON.stringify(selection));
      localStorage.setItem('profile',profile);
    },{selection,profile});
    const before = await view();
    const errors:string[]=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto('/');
    const input=page.getByLabel('Своё действие или реплика');
    await input.fill(selection.action);
    await page.getByRole('button',{name:'Отправить действие',exact:true}).click();
    const retry = ['008','016'].includes(scenario);
    // The click can finish before the submit request creates the first job.
    // A null job is still pending here, not a polling callback exception.
    await expect.poll(async () => (await view()).job?.status).toBe(retry?'error':'saved');
    const first = await view();
    if (retry) {
      expect(first.job).toMatchObject({retry_allowed:true,narrative_reauthor_required:false});
      expect(first.state).toEqual(before.state);
      await page.reload();
      // A long expanded LTA report must scroll with history, not consume the
      // mobile viewport and leave Retry underneath the fixed composer/phone.
      if (scenario==='016') {
        await expect(page.locator('.story-scroll .advance-result')).toBeVisible();
        expect((await page.locator('.story-scroll').boundingBox())!.height).toBeGreaterThan(100);
      }
      await page.getByRole('button',{name:'Повторить обработку состояния',exact:true}).click();
      await expect.poll(async () => (await view()).job?.status).toBe('saved');
    }
    const after = await view();
    expect(after.turns).toHaveLength(before.turns.length+1);
    expect(after.job.narrative).toEqual(first.job.narrative);
    if (scenario==='020') expect(after.state.world.characters.char_alexey.location_id).toBe('loc_cafe');
    if (scenario==='016') {
      const plan=after.state.world.scheduled_events.sched_alexey_photo_galina_library;
      expect(plan.temporal).toMatchObject({weekday:3,time:'10:00'});
      expect(plan.time_reference_minute).toBe(558);
      expect(plan.character_ids).toEqual(['char_alexey','char_galina']);
    }
    const attempts=(await (await request.get(path+'/accounting')).json()).requests
      .filter((r:{job_id:string})=>r.job_id===first.job.id);
    expect(attempts.filter((r:{stage:string})=>r.stage==='narrative')).toHaveLength(1);
    await page.reload();
    expect((await view()).state).toEqual(after.state);
    await expect(input).toBeEnabled();
    await input.fill('Продолжаю разговор.');
    await expect(input).toHaveValue('Продолжаю разговор.');
    expect(errors).toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
  });
}
