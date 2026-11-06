import {test,expect,type Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {nav} from './navigation';
import {authorView,workshopNav} from './workshop-navigation';

type Sample={elapsed:number;opacity:string;transform:string;translate:string;x:number;y:number;animationTimingFunction:string;transitionTimingFunction:string;animations:{name:string;duration:number|string;delay:number;easing:string;keyframes:{offset:number|null;easing:string}[];state:string}[]};
/** Observe real frames before invoking the UI action, including its first frame. */
async function sample(page:Page,selector:string,action:()=>Promise<unknown>){
 await page.evaluate(selector=>{
  const host=window as typeof window&{motion192?:{done:boolean;frames:Sample[]}};
  host.motion192={done:false,frames:[]};
  document.addEventListener('click',()=>{
   const start=performance.now();
   function frame(){
    const el=document.querySelector(selector),elapsed=performance.now()-start;
    if(el){const style=getComputedStyle(el),box=el.getBoundingClientRect();host.motion192!.frames.push({elapsed,opacity:style.opacity,transform:style.transform,translate:style.translate,x:box.x,y:box.y,animationTimingFunction:style.animationTimingFunction,transitionTimingFunction:style.transitionTimingFunction,animations:el.getAnimations().map(a=>({name:(a as CSSAnimation).animationName||'transition',duration:a.effect!.getTiming().duration,delay:a.effect!.getTiming().delay,easing:a.effect!.getTiming().easing,keyframes:(a.effect as KeyframeEffect).getKeyframes().map(f=>({offset:f.offset,easing:f.easing})),state:a.playState}))})}
    if(elapsed<450)requestAnimationFrame(frame);else host.motion192!.done=true;
   }
   requestAnimationFrame(frame);
  },{once:true,capture:true});
 },selector);
 await action();
 await page.waitForFunction(()=>(window as typeof window&{motion192?:{done:boolean}}).motion192?.done);
 return page.evaluate(()=>(window as typeof window&{motion192:{frames:Sample[]}}).motion192.frames);
}

for(const reduce of [false,true])test(`workshop192 actual section and modal frames, reduced motion=${reduce}`,async({page,request},info)=>{
 const source=JSON.parse(readFileSync(new URL('../../tests/fixtures/initial_world/workshop188.json',import.meta.url),'utf8'));
 const w=await(await request.post('/api/workspaces',{data:{name:'Движение мастерской'}})).json();
 expect((await request.post(`/api/workspaces/${w.id}/draft/import`,{data:{revision:0,format:'json',text:JSON.stringify(source)}})).ok()).toBe(true);
 await page.emulateMedia({reducedMotion:reduce?'reduce':'no-preference'});
 await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),w.id);
 await page.goto('/');await nav(page,'Создать');await authorView(page);
 const reference=await page.context().newPage();await reference.emulateMedia({reducedMotion:reduce?'reduce':'no-preference'});
 await reference.goto('/test/workshop175/reference/world-workshop.html');
 const observations:unknown[]=[];
 for(const [route,label] of [['characters','Персонажи'],['review','Проверка мира'],['ai','Изменить с ИИ']]){
  // Open mobile navigation before starting the section measurement, so the
  // first click is the actual section switch, not opening the menu.
  const mobile=info.project.name==='mobile';
  if(mobile)await page.getByRole('button',{name:'Разделы мастерской',exact:true}).click();
  const frames=await sample(page,'.workshop-content',()=>page.locator(mobile?'.ww-menu-dialog':'.ww-sidebar').getByRole('button',{name:label,exact:true}).click());
  expect(frames.length).toBeGreaterThan(0);
  if(reduce){expect(frames.every(f=>!f.animations.length)).toBe(true);expect(frames.every(f=>f.translate==='none')).toBe(true)}
  else expect(frames.some(f=>f.animations.some(a=>a.name==='ww-page-in'))).toBe(true);
  expect(frames.at(-1)?.opacity).toBe('1');
  await expect(page.locator('.ww-content')).toBeFocused();
  const original=await sample(reference,'#main',()=>reference.locator(`[data-action="navigate"][data-route="${route}"]`).first().evaluate((el:HTMLElement)=>el.click()));
  observations.push({route,current:frames,reference:original});
 }
 await workshopNav(page,'Персонажи');
 const modal=await sample(page,'.ww-dossier-dialog',()=>page.locator('.ww-character-card').first().click());
 const original=await sample(reference,'.modal',()=>reference.locator('[data-action="navigate"][data-route="characters"]').first().evaluate((el:HTMLElement)=>{el.click();document.querySelector<HTMLButtonElement>('.cast-card')!.click()}));
 expect(modal.length).toBeGreaterThan(0);
 if(reduce){
  // Desktop centering uses a static translate(-50%, -50%) transform. Reduced
  // motion forbids movement, not that layout transform (mobile needs none).
  expect(modal.every(f=>!f.animations.length&&f.translate==='none'&&f.opacity==='1')).toBe(true);
  expect(new Set(modal.map(f=>f.transform)).size).toBe(1);
  expect(Math.max(...modal.map(f=>f.x))-Math.min(...modal.map(f=>f.x))).toBeLessThan(.1);
  expect(Math.max(...modal.map(f=>f.y))-Math.min(...modal.map(f=>f.y))).toBeLessThan(.1);
 }
 else expect(modal.some(f=>f.animations.length>0)).toBe(true);
 await page.keyboard.press('Escape');await expect(page.locator('.ww-dossier-dialog,.dialog-overlay')).toHaveCount(0);
 await expect(page.locator('.ww-character-card').first()).toBeFocused();
 observations.push({modal,referenceModal:original});
 if(info.project.name==='mobile'){
  const menu=await sample(page,'.ww-menu-dialog',()=>page.getByRole('button',{name:'Разделы мастерской',exact:true}).click());
  if(reduce)expect(menu.every(f=>!f.animations.length&&f.translate==='none')).toBe(true);
  else {expect(menu.some(f=>f.animations.some(a=>a.name==='ww-menu-in'))).toBe(true);expect(menu.some(f=>f.x<0)).toBe(true)}
  await page.keyboard.press('Escape');await expect(page.locator('.ww-menu-dialog,.dialog-overlay')).toHaveCount(0);
  observations.push({menu});
 }
 await info.attach('motion-frames',{body:JSON.stringify({reduce,viewport:page.viewportSize(),observations}),contentType:'application/json'});
 await reference.close();
});
