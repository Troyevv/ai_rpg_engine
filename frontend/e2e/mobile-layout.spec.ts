import {test,expect} from '@playwright/test';
for(const width of [360,390,412,430])test(`mobile story layout ${width}px`,async({page,request},info)=>{
 test.skip(info.project.name!=='desktop','Explicit width matrix uses one Chromium project');
 await page.setViewportSize({width,height:820});
 const selected=await(await request.post('/test/seed')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selected);
 await page.goto('/');await page.getByRole('button',{name:'Начать игру',exact:true}).click();
 await expect(page.locator('.choices button')).toHaveCount(6);
 await expect(page.locator('.nav-rail')).toHaveCount(0);
 await expect(page.locator('.mobile-context')).toBeVisible();
 const story=await page.locator('.story-scroll').boundingBox();expect(story!.height).toBeGreaterThan(480);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
 await page.getByLabel('Своё действие или реплика').fill(Array(12).fill('Длинная строка действия').join('\n'));
 const input=await page.getByLabel('Своё действие или реплика').boundingBox();expect(input!.height).toBeLessThanOrEqual(134);
 await page.getByLabel('Своё действие или реплика').fill('Посмотреть в окно');
 await page.getByRole('button',{name:'Отправить действие'}).click();
 await expect(page.locator('.turn')).toHaveCount(2);
 await page.locator('.story-scroll').evaluate(el=>{el.scrollTop=0});
 await expect(page.getByRole('button',{name:'К последней сцене'})).toBeVisible();
 await page.getByRole('button',{name:'К последней сцене'}).click();
 await expect(page.getByRole('button',{name:'К последней сцене'})).toHaveCount(0);
 // Emulate a keyboard-driven visualViewport resize; physical keyboard behaviour is a separate device check.
 await page.getByLabel('Своё действие или реплика').focus();
 await page.evaluate(()=>{Object.defineProperty(visualViewport,'height',{configurable:true,value:440});visualViewport!.dispatchEvent(new Event('resize'))});
 await expect(page.locator('html')).toHaveClass(/keyboard-open/);
 const composer=await page.locator('.composer').boundingBox();expect(composer!.y+composer!.height).toBeLessThanOrEqual(441);
 await page.evaluate(()=>{delete (visualViewport as unknown as {height?:number}).height;visualViewport!.dispatchEvent(new Event('resize'))});
 await page.getByLabel('Своё действие или реплика').blur();
 await page.locator('.story-scroll').evaluate(el=>{el.scrollTop=0});
 await page.screenshot({path:`test-results/mobile-${width}.png`});
});

test('PWA manifest, worker and offline recovery',async({page,request},info)=>{
 test.skip(info.project.name!=='desktop');
 const manifest=await(await request.get('/manifest.webmanifest')).json();
 expect(manifest.display).toBe('standalone');expect(manifest.icons).toHaveLength(3);
 for(const icon of manifest.icons)expect((await request.get(icon.src)).headers()['content-type']).toContain('image/png');
 expect((await request.get('/sw.js')).headers()['content-type']).toContain('javascript');
 await page.goto('/');await page.evaluate(()=>navigator.serviceWorker.ready);await page.reload();
 await expect.poll(()=>page.evaluate(()=>!!navigator.serviceWorker.controller)).toBe(true);
 await page.context().setOffline(true);await page.reload();
 await expect(page.getByText('История подождёт',{exact:true})).toBeVisible();
 await page.context().setOffline(false);await page.getByRole('button',{name:'Повторить подключение'}).click();
 await expect(page.getByRole('button',{name:'Выбрать мир'})).toBeVisible();
});
