import {test,expect,type Page} from '@playwright/test';
import {nav} from './navigation';

async function menu(page:Page){
 await page.getByRole('button',{name:'Меню игры',exact:true}).click();
 await expect(page.getByRole('dialog',{name:'Меню игры'})).toBeVisible();
 return page.getByRole('dialog',{name:'Меню игры'});
}
async function seed(page:Page,request:any,longHistory=false){
 const selected=await(await request.post('/test/phone-seed')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selected);
 if(longHistory)await page.route(`**/api/saves/${selected.save}`,async route=>{const response=await route.fetch();const save=await response.json();save.turns[0].assistant_text+='\n\n'+('Длинная история для проверки позиции чтения.\n\n'.repeat(60));await route.fulfill({response,json:save})});
 await page.setViewportSize({width:393,height:850});
 await page.goto('/');await expect(page.locator('.composer')).toBeVisible();
 return selected;
}

test('menu: all destinations, draft, anchor, nested Back and workspace state',async({page,request})=>{
 await seed(page,request,true);
 await page.getByLabel('Своё действие или реплика').fill('Неотправленный черновик');
 await page.locator('.story-scroll').evaluate(el=>{el.scrollTop=el.scrollHeight/2;el.dispatchEvent(new Event('scroll'))});
 await expect(page.getByRole('button',{name:'К последней сцене'})).toBeVisible();
 const top=await page.locator('.story-scroll').evaluate(el=>el.scrollTop);
 for(const section of ['Мир','Сцена','Персонажи','Отношения','Сюжет','Память','Тайны']){
  await nav(page,section);await expect(page.locator('.inspector-workspace')).toBeVisible();
  await expect(page.locator('.inspector-workspace')).toHaveAttribute('aria-label',section);
 }
 await menu(page);await page.evaluate(()=>history.back());
 await expect(page.getByRole('dialog')).toHaveCount(0);
 await expect(page.locator('.inspector-workspace')).toBeVisible();
 await page.evaluate(()=>history.back());await expect(page.locator('.inspector-workspace')).toBeHidden();
 for(const section of ['Календарь','Родословная']){
  await nav(page,section);await expect(page.locator('.save-workspace h1')).toHaveText(section);
  await expect(page.locator('.save-workspace')).toHaveCount(1);
  await page.keyboard.press('Escape');
  await expect(page.locator('.save-workspace')).toHaveCount(0);
 }
 await nav(page,'Календарь');
 const year=page.getByRole('button',{name:'Год',exact:true});
 await year.click();
 await expect(page.locator('.calendar-year')).toBeVisible();
 await page.getByRole('button',{name:'Вернуться в историю',exact:true}).click();
 await nav(page,'Календарь');await expect(page.getByRole('button',{name:'Месяц',exact:true})).toHaveAttribute('aria-pressed','true');
 await page.getByRole('button',{name:'Вернуться в историю',exact:true}).click();
 // A menu above the calendar consumes only its own Back entry.
 await nav(page,'Календарь');
 await menu(page);await page.evaluate(()=>history.back());
 await expect(page.getByRole('dialog')).toHaveCount(0);
 await expect(page.locator('.save-workspace')).toHaveCount(1);
 await page.evaluate(()=>history.back());
 await expect(page.locator('.save-workspace')).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Меню игры'})).toBeFocused();
 // Leaving the Inspector for a workspace must finish its pending popstate first.
 await nav(page,'Персонажи');await nav(page,'Родословная');
 await expect(page.locator('.save-workspace h1')).toHaveText('Родословная');
 await page.evaluate(()=>history.back());await expect(page.locator('.save-workspace')).toHaveCount(0);
 await page.locator('.current-game-entry button').click();
 await page.getByRole('dialog').getByRole('button',{name:'Календарь',exact:true}).click();
 await expect(page.locator('.save-workspace')).toHaveCount(1);
 await page.keyboard.press('Escape');
 await expect(page.locator('.save-workspace')).toHaveCount(0);
 await expect(page.locator('.current-game-entry button')).toBeFocused();
 await nav(page,'Создать');await expect(page.locator('.world-workshop')).toBeVisible();
 await menu(page);await page.locator('.mobile-menu-resume').click();await expect(page.locator('.game')).toBeVisible();
 await nav(page,'Настройки');await expect(page.locator('.settings-dialog')).toBeVisible();await page.keyboard.press('Escape');
 await menu(page);const reading=page.getByRole('switch',{name:'Режим чтения'});
 await expect(reading).toHaveAttribute('aria-checked','false');await reading.click();await expect(reading).toHaveAttribute('aria-checked','true');await reading.click();
 await page.getByRole('button',{name:'Закрыть',exact:true}).click();
 await expect(page.getByLabel('Своё действие или реплика')).toHaveValue('Неотправленный черновик');
 expect(await page.locator('.story-scroll').evaluate(el=>el.scrollTop)).toBe(top);
 await menu(page);await page.keyboard.press('Escape');
 await expect(page.getByRole('button',{name:'Меню игры'})).toBeFocused();
});

test('menu: five widths, skins, low viewport and no legacy entries',async({page,request},info)=>{
 const selected=await seed(page,request);
 for(const skin of ['graphite','parchment']){
  await request.put(`/api/worlds/${selected.world}/presentation`,{data:{theme_id:skin}});await page.reload();
  for(const width of [320,360,393,412,430]){
   await page.setViewportSize({width,height:720});const dialog=await menu(page);
   await expect.poll(async()=>(await dialog.boundingBox())!.y).toBe(0);
   const rect=await dialog.boundingBox();expect(rect!.x).toBe(0);expect(rect!.y).toBe(0);expect(rect!.width).toBe(width);expect(rect!.height).toBe(720);
   expect(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
   await expect(dialog.getByRole('button',{name:/Ветки|Tabletop|Настольная/})).toHaveCount(0);
   await expect(dialog.locator('.mobile-menu-card')).toHaveCount(9);
   for(const button of await dialog.locator('button').all()){
    const box=await button.boundingBox();if(box)expect(box.height).toBeGreaterThanOrEqual(44);
   }
   if(process.env.MENU_QA&&width===393&&info.project.name==='mobile')await page.screenshot({path:`/tmp/menu126-${skin}.png`});
   await page.keyboard.press('Escape');
  }
 }
 await page.setViewportSize({width:320,height:420});const dialog=await menu(page);
 await dialog.getByRole('switch').scrollIntoViewIfNeeded();await expect(dialog.getByRole('switch')).toBeInViewport();
 await page.keyboard.press('Escape');
});

test('phone dock: textarea, keyboard, viewport and safe area stay attached',async({page,request})=>{
 await seed(page,request);
 const dock=async()=>{
  const peek=await page.locator('.phone-peek').evaluate(el=>{const r=el.getBoundingClientRect();return {y:r.y,height:r.height}});const composer=await page.locator('.composer').boundingBox();
  expect(Math.abs(peek!.y+peek!.height-composer!.y)).toBeLessThanOrEqual(1);
  const send=await page.getByRole('button',{name:'Отправить действие'}).boundingBox();expect(send!.y).toBeGreaterThanOrEqual(peek!.y+peek!.height);
  await page.locator('.story-scroll').evaluate(el=>el.scrollTop=el.scrollHeight);
  const last=await page.locator('.choices button').last().boundingBox();expect(last!.y+last!.height).toBeLessThanOrEqual(peek!.y+1);
 };
 for(const width of [320,430]){
  await page.setViewportSize({width,height:850});
  await expect.poll(async()=>{const p=await page.locator('.phone-peek').evaluate(el=>{const r=el.getBoundingClientRect();return {y:r.y,height:r.height}});const c=await page.locator('.composer').boundingBox();return Math.abs(p!.y+p!.height-c!.y)}).toBeLessThanOrEqual(1);
  await dock();
  await page.getByLabel('Своё действие или реплика').fill('Многострочное действие\n'.repeat(8));await dock();
  await page.locator('.composer').evaluate(el=>(el as HTMLElement).style.paddingBottom='34px');await dock();
 }
 await page.getByLabel('Своё действие или реплика').focus();
 await page.evaluate(()=>{Object.defineProperty(visualViewport,'height',{configurable:true,value:440});Object.defineProperty(visualViewport,'offsetTop',{configurable:true,value:12});visualViewport!.dispatchEvent(new Event('resize'))});
 await expect(page.locator('html')).toHaveClass(/keyboard-open/);
 // Existing keyboard policy hides the collapsed phone; it must still track the composer.
 await dock();
 await page.evaluate(()=>{delete (visualViewport as any).height;delete (visualViewport as any).offsetTop;visualViewport!.dispatchEvent(new Event('resize'))});
 await page.getByLabel('Своё действие или реплика').blur();
 await page.locator('.phone-peek').click();await expect(page.locator('.phone-device')).toHaveClass(/is-open/);
 await expect.poll(async()=>{const p=await page.locator('.phone-device').boundingBox();const c=await page.locator('.composer').boundingBox();return Math.abs(p!.y+p!.height-c!.y)}).toBeLessThanOrEqual(1);
 await page.locator('.phone-peek').click();await expect(page.locator('.phone-device')).not.toHaveClass(/is-open/);
 // Resize the visual viewport with the chat already focused, as an OS keyboard does.
 await page.getByLabel('Своё действие или реплика').fill('');
 await page.setViewportSize({width:393,height:850});
 await page.locator('.phone-peek').click();
 const phone=page.getByRole('region',{name:'Телефон персонажа'});
 await phone.getByRole('button',{name:'Вера работа',exact:true}).click();
 await phone.getByRole('button',{name:'Написать',exact:true}).click();
 await phone.getByLabel('Сообщение в телефоне').fill('Черновик при открытии клавиатуры');
 await page.evaluate(()=>{Object.defineProperty(visualViewport,'height',{configurable:true,value:440});Object.defineProperty(visualViewport,'offsetTop',{configurable:true,value:12});visualViewport!.dispatchEvent(new Event('resize'))});
 await expect(phone.getByLabel('Сообщение в телефоне')).toBeInViewport({ratio:1});
 await expect(phone.getByRole('button',{name:'Отправить сообщение',exact:true})).toBeInViewport({ratio:1});
 await expect.poll(async()=>{const device=await page.locator('.phone-device').boundingBox();const composer=await page.locator('.composer').boundingBox();return device!.y>=0&&device!.y+device!.height<=composer!.y}).toBe(true);
 await page.keyboard.press('Escape');await expect(page.locator('.phone-peek')).toBeFocused();
});

test('menu: empty save and English focus/keyboard controls',async({page})=>{
 await page.emulateMedia({reducedMotion:'reduce'});
 await page.setViewportSize({width:320,height:640});await page.goto('/');
 await page.evaluate(()=>document.documentElement.lang='en');
 await page.getByRole('button',{name:'Game menu'}).click();
 const dialog=page.getByRole('dialog',{name:'Game menu'});
 await expect(dialog).toContainText('No world selected');await expect(dialog).toContainText('No active playthrough');
 await expect(dialog.locator('.mobile-menu-card:disabled')).toHaveCount(9);
 await expect(dialog.getByRole('button',{name:'Create world'})).toBeEnabled();
 await page.keyboard.press('Tab');expect(await dialog.evaluate(el=>el.contains(document.activeElement))).toBe(true);
 await page.keyboard.press('Escape');await expect(page.getByRole('button',{name:'Game menu'})).toBeFocused();
});

test('menu summary follows controlled actor rather than POV; all skin bases and long names',async({page,request})=>{
 const selected=await seed(page,request);
 let actorId:string|null=null;
 let actorName='';
 await page.route(`**/api/saves/${selected.save}`,async route=>{
  const response=await route.fetch();const save=await response.json();
  const actor=save.state.characters.find((c:any)=>c.id!==save.state.camera?.pov_actor_id)!;
  actorName=actor.name;save.state.controlled_actor_id=actorId===null?null:actor.id;
  await route.fulfill({response,json:save});
 });
 await page.route(`**/api/worlds/${selected.world}`,async route=>{const response=await route.fetch();const world=await response.json();world.name='Очень длинное название мира '.repeat(12);await route.fulfill({response,json:world})});
 for(const skin of ['cyberpunk','industrial','medieval','arcane','street','noir','terminal','biotech','retro']){
  await request.put(`/api/worlds/${selected.world}/presentation`,{data:{theme_id:skin}});
  await page.reload();const dialog=await menu(page);
  await expect(dialog.locator('.mobile-menu-resume')).toContainText('Без управляемого персонажа');
  expect(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
  await page.keyboard.press('Escape');
 }
 actorId='controlled';await page.reload();const dialog=await menu(page);
 await expect(dialog.locator('.mobile-menu-resume')).toContainText(actorName);
 await expect(dialog.locator('.mobile-menu-resume')).not.toContainText('Без управляемого персонажа');
});
