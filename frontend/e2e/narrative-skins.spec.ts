import {gameAction} from './navigation';
import {test,expect} from '@playwright/test';
import {themes} from '../src/lib/skins';
test('all skins, four mobile widths, time skip and rollback',async({page,request},info)=>{
 test.setTimeout(180000);
 const selection=await(await request.post('/test/seed')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selection);
 await page.goto('/');
 await page.getByRole('button',{name:'Начать игру',exact:true}).click();
 await expect(page.locator('.choices button')).toHaveCount(6);
 const baseline=await(await request.get(`/api/saves/${selection.save}`)).json();
 const fingerprints=new Set<string>();
 for(const theme of themes){
  expect((await request.put(`/api/worlds/${selection.world}/presentation`,{data:{theme_id:theme.id}})).ok()).toBe(true);
  await page.reload();await expect(page.locator('html')).toHaveAttribute('data-theme',theme.id);
  if(theme.decoration!=='none')await expect(page.locator('.theme-decoration')).toHaveCSS('pointer-events','none');
  for(const width of info.project.name==='mobile'?[360,390,412,430]:[1440]){
   await page.setViewportSize({width,height:900});
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
   await gameAction(page,'Пропустить время');
   await expect(page.getByRole('dialog').last()).toBeVisible();
   expect(await page.getByRole('dialog').last().evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
   if(width===390||width===1440){
    fingerprints.add(await page.getByRole('dialog').last().evaluate(el=>{const c=getComputedStyle(el);return [c.borderRadius,c.borderWidth,c.borderStyle,c.backgroundImage,c.backgroundColor,c.color,getComputedStyle(document.querySelector('h1')!).fontFamily].join('|')}));
    if(['industrial','parchment','cyberpunk','biotech'].includes(theme.id))await page.screenshot({path:info.outputPath(`${theme.id}-${width}.png`),animations:'disabled'});
   }
   await page.getByRole('dialog').last().getByRole('button',{name:'Закрыть',exact:true}).click();
  }
 }
 expect(fingerprints.size).toBeGreaterThanOrEqual(9);
 await gameAction(page,'Пропустить время');
 await page.getByRole('button',{name:'+10 мин',exact:true}).click();
 await page.getByRole('button',{name:'Пропустить 0 ч 10 мин',exact:true}).click();
 await expect(page.locator('.turn')).toHaveCount(2);await expect(page.locator('.choices button')).toHaveCount(6);
 const after=await(await request.get(`/api/saves/${selection.save}`)).json();
 expect(after.state.world_clock.minute-baseline.state.world_clock.minute).toBe(10);
 expect(after.state.last_time_skip.living_world_llm_calls).toBe(0);
 await expect(page.locator('.skip-diagnostics')).toContainText('10 мин');
 page.once('dialog',dialog=>dialog.accept());await page.getByRole('button',{name:'Откатить',exact:true}).click();
 await expect(page.locator('.turn')).toHaveCount(1);
 expect((await(await request.get(`/api/saves/${selection.save}`)).json()).state.world_clock.minute).toBe(baseline.state.world_clock.minute);
});

// Screenshots are CI artifacts; assertions catch missing/intrusive art as well as borders.
test('skins preserve distinct palettes and a clear V3 reading surface',async({page,request},info)=>{
 const selection=await(await request.post('/test/seed')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selection);
 await page.emulateMedia({reducedMotion:'reduce'});
 await page.goto('/');await page.getByRole('button',{name:'Начать игру',exact:true}).click();
 await expect(page.locator('.choices button')).toHaveCount(6);
 const drawings=new Set<string>();
 for(const id of ['graphite','cyberpunk','medieval','noir','arcane','terminal']){
  await request.put(`/api/worlds/${selection.world}/presentation`,{data:{theme_id:id}});
  await page.reload();await expect(page.locator('html')).toHaveAttribute('data-theme',id);
  await page.locator('.story-scroll').evaluate(el=>el.scrollTop=0);
  const reader=page.locator('.nr-content');
  await expect(reader).toBeVisible();
  await expect(page.locator('.skin-header-art')).toHaveCount(0);
  drawings.add(await reader.evaluate(el=>['--bg','--surface-1','--accent'].map(v=>getComputedStyle(el).getPropertyValue(v)).join('|')));
  const composer=await page.locator('.composer').boundingBox();
  const panel=await page.locator('.story-scroll').boundingBox();
  expect(panel!.y+panel!.height).toBeLessThanOrEqual(composer!.y+1);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.getByRole('textbox',{name:'Своё действие или реплика'}).fill('Осматриваюсь');
  await expect(page.getByRole('button',{name:'Отправить действие'})).toBeEnabled();
  await page.screenshot({path:info.outputPath(`skin-${id}.png`),animations:'disabled'});
  await gameAction(page,'Пропустить время');
  await expect(page.getByRole('dialog').last()).toBeVisible();
  await page.getByRole('dialog').last().getByRole('button',{name:'Закрыть',exact:true}).click();
 }
 expect(drawings.size).toBe(6);
});

test('skin compositions lay out real action and speech slots without clipping',async({page,request},info)=>{
 const selected=await(await request.post('/test/choices-seed')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selected);
 const mobile=info.project.name==='mobile';
 await page.setViewportSize({width:mobile?320:1440,height:mobile?844:900});
 await page.emulateMedia({reducedMotion:'reduce'});
 const layouts=new Set<string>();
 for(const theme of themes){
  await request.put('/api/worlds/'+selected.world+'/presentation',{data:{theme_id:theme.id}});
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('data-theme',theme.id);
  const cards=page.locator('.choices button');
  await expect(cards).toHaveCount(6);
  await cards.first().focus();
  await expect(cards.first()).toBeFocused();
  const rows=await cards.evaluateAll(nodes=>nodes.map(card=>{
   const style=getComputedStyle(card);
   return {
    fits:card.scrollWidth<=card.clientWidth+1 && card.scrollHeight<=card.clientHeight+1,
    areas:style.gridTemplateAreas,
    animated:style.animationName!=='none',
   };
  }));
  expect(rows.every(row=>row.fits&&!row.animated),theme.name).toBe(true);
  layouts.add(rows[0].areas);
 }
 // An accidental return to the universal V3 two-column card survives palette tests.
 expect(layouts.size).toBeGreaterThanOrEqual(4);
});

test('presets preserve Narrative surfaces and the semantic colors of the game menu', async ({page, request}) => {
  test.setTimeout(180_000);
  const selection = await (await request.post('/test/choices-seed')).json();
  await page.addInitScript(s => localStorage.setItem('selection', JSON.stringify(s)), selection);
  await page.setViewportSize({width: 390, height: 844});
  await page.emulateMedia({reducedMotion: 'reduce'});

  // Resolve the pre-#275 component roles in their actual scope. Graphite has
  // local overrides in both Narrative and the mobile inspector palette.
  async function expectPaint(selector: string, ink: string, fill: string) {
    const element = page.locator(selector).first();
    const colors = await element.evaluate((el, [ink, fill]) => {
      const probe = document.createElement('span');
      probe.style.color = ink;
      probe.style.backgroundColor = fill;
      el.append(probe);
      const style = getComputedStyle(probe);
      const expected = {ink: style.color, fill: style.backgroundColor};
      probe.remove();
      return expected;
    }, [ink, fill]);
    await expect(element).toHaveCSS('color', colors.ink);
    await expect(element).toHaveCSS('background-color', colors.fill);
    await expect(element).toHaveCSS('background-image', 'none');
  }

  for (const theme of themes) {
    const response = await request.put(`/api/worlds/${selection.world}/presentation`, {data: {theme_id: theme.id}});
    expect(response.ok()).toBe(true);
    await page.goto('/');
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme.id);
    const choice = page.locator('.choices button').first();
    await expect(choice).toBeVisible();
    await page.getByLabel('Своё действие или реплика').fill('');
    await expectPaint('.choices button', 'var(--text)', 'var(--v3-panel, #1d2125)');
    await expectPaint('.choices .choice-mark', 'var(--v3-text, #d7bd83)', 'var(--v3-panel, #393226)');
    await choice.click();
    await page.mouse.move(0, 0);
    await expect(choice).toHaveAttribute('aria-pressed', 'true');
    await expectPaint('.choices button', 'var(--text)', 'var(--v3-panel, #2f2b23)');
    await expectPaint('.choices .choice-mark', 'var(--v3-ink, #26241e)', 'var(--accent)');

    await page.getByRole('button', {name: 'Меню игры', exact: true}).click();
    await expect(page.locator('.mobile-game-menu')).toHaveCSS('border-width', '0px');
    await expectPaint('.mobile-game-menu', 'var(--text)', 'var(--bg)');
    await expectPaint('.mobile-menu-resume', 'var(--text)', 'var(--accent-soft)');
    await expectPaint('.menu-world', 'var(--text)', 'var(--surface-2)');
    for (const [section, role] of Object.entries({
      world: 'overview', scene: 'family', characters: 'personality', relations: 'relationships',
    })) {
      const ink = `var(--dossier-${role})`;
      await expectPaint(`.menu-${section} .mobile-menu-icon`, ink, `color-mix(in srgb, ${ink} 12%, transparent)`);
    }
  }
});
