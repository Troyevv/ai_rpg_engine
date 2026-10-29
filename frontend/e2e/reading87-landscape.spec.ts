import {test,expect} from '@playwright/test';
for(const size of [{width:844,height:393},{width:1024,height:768}])test(`87 landscape ${size.width}x${size.height}`,async({page,request},info)=>{
 test.skip(info.project.name!=='desktop');await page.setViewportSize(size);
 const s=await(await request.post('/test/phone-seed?incoming=false')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);await page.goto('/');
 await expect(page.locator('.choices button').first()).toBeEnabled();
 await page.locator('.choices button').first().scrollIntoViewIfNeeded();
 await page.screenshot({path:`../docs/manual_qa/narrative_v4/issue87/after-landscape-${size.width}.png`});
 const story=await page.locator('.story-scroll').boundingBox();expect(story!.height).toBeGreaterThan(100);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(size.width);
 await page.getByLabel('Своё действие или реплика').fill('Черновик в альбомной ориентации');
 await expect(page.getByRole('button',{name:'Отправить действие',exact:true})).toBeInViewport();
});
