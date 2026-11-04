import { test, expect } from '@playwright/test';
import { nav } from './navigation';
for (const theme of ['graphite', 'parchment']) {
  test(`private message and confirmed secret through API, inspector and reload: ${theme}`, async ({page,request}) => {
    const seedResponse=await request.post('/test/story-secrets178-seed');
    expect(seedResponse.ok()).toBeTruthy();
    const seed=await seedResponse.json();
    await request.put(`/api/worlds/${seed.world}/presentation`,{data:{theme_id:theme}});
    await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify({world:s.world,save:s.save})),seed);
    const before=await (await request.get(`/api/saves/${seed.save}`)).json();
    const serialized=JSON.stringify(before);
    expect(serialized).not.toContain('NEVER-EXPOSE-178');
    expect(serialized).not.toContain('RAW-HIDDEN-178');
    expect(serialized).not.toContain('Вера тайно написала роман.');
    expect(serialized).toContain('Купи хлеб');
    const slot=before.state.story_secrets.personal.qa_vera[0];
    expect(Object.keys(slot).sort()).toEqual(['id','status']);
    await page.goto('/');await nav(page,'Тайны');
    const area=page.locator('.inspector-workspace');
    await expect(area).not.toContainText('Купи хлеб');
    await expect(area).not.toContainText('Вера тайно написала роман.');
    const read=await request.post(`/api/saves/${seed.save}/phone`,{data:{revision:before.revision,command:{action:'read',event_id:seed.event,operation_id:'e2e-secret178-reading'}}});
    expect(read.ok()).toBeTruthy();
    const after=await read.json();
    expect(after.state.story_secrets.personal.qa_vera[0].id).toBe(slot.id);
    expect(after.state.story_secrets.personal.qa_vera[0].status).toBe('known');
    await page.reload();await nav(page,'Тайны');
    await expect(area).toContainText('Вера тайно написала роман.');
    await expect(area).not.toContainText('Купи хлеб');
    await area.getByRole('textbox',{name:'Поиск тайн'}).fill('хлеб');
    await expect(area).not.toContainText('Вера тайно написала роман.');
    await area.getByRole('textbox',{name:'Поиск тайн'}).fill('роман');
    await expect(area).toContainText('Вера тайно написала роман.');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    if(process.env.SECRET178_SCREENSHOTS) await page.screenshot({path:`/tmp/secret178-${theme}-${test.info().project.name}.png`});
    const author=await (await request.get(`/api/saves/${seed.save}/author-state`)).text();
    expect(author).toContain('NEVER-EXPOSE-178');
  });
}
