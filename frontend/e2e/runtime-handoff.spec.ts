import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {defaults} from '../src/types';
import {nav} from './navigation';

test('original export identities and rejected opening recover through real API then turn reload turn',async({page,request},info)=>{
 const source=JSON.parse(readFileSync(new URL('../../tests/fixtures/runtime_handoff/world.json',import.meta.url),'utf8'));
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const w=await(await request.post('/api/workspaces',{data:{name:'Runtime handoff exact export'}})).json();
 expect((await request.post(`/api/workspaces/${w.id}/draft/import`,{data:{revision:w.revision,text:JSON.stringify(source),format:'json'}})).ok()).toBeTruthy();
 const d=await(await request.get(`/api/workspaces/${w.id}/draft?author=true`)).json();
 const selected=await(await request.post(`/api/workspaces/${w.id}/draft/confirm`,{data:{revision:d.revision,version_id:d.version_id,accept_warnings:true}})).json();
 const profile=`handoff-${info.project.name}`;
 expect((await request.put(`/api/settings/${profile}`,{data:{...defaults,game:{...defaults.game,model:'handoff-test',context_length:131072,max_tokens:2000,update_tokens:4096}}})).ok()).toBeTruthy();
 await page.addInitScript(({selected,profile})=>{localStorage.setItem('selection',JSON.stringify(selected));localStorage.setItem('profile',profile);},{selected,profile});
 const view=async()=> (await(await request.get(`/api/saves/${selected.save}`)).json());
 const first=await view();
 expect(Object.fromEntries(first.state.characters.map((c:{id:string,name:string})=>[c.id,c.name]))).toEqual(Object.fromEntries(source.characters.map((c:{id:string,name:string})=>[c.id,c.name])));
 expect(first.state.scene_meta.present_ids).toEqual(['ilya']);
 await page.goto('/');await nav(page,'Мир');await page.locator('.panel-tabs').getByRole('button',{name:'Персонажи',exact:true}).click();
 await page.getByLabel('Только рядом').uncheck();
 await page.getByLabel('Найти персонажа').fill('Виктория');
 await expect(page.getByRole('heading',{name:'Виктория Соловьёва',exact:true})).toBeVisible();
 await page.getByLabel('Найти персонажа').fill('');
 await expect(page.getByLabel('Персонаж',{exact:true}).locator('option')).toHaveCount(19);
 await page.screenshot({path:`test-results/handoff-identities-${info.project.name}.png`,fullPage:true});
 // Close the inspector using the normal game navigation on both layouts.
 await page.keyboard.press('Escape');
 await request.post('/test/runtime-handoff-provider');
 try {
  await page.getByRole('button',{name:'Начать игру',exact:true}).click();
  await expect(page.getByRole('button',{name:'Повторить обработку состояния',exact:true})).toBeEnabled();
  await expect(page.getByRole('button',{name:'Начать игру',exact:true})).toHaveCount(0);
  expect((await view()).turns).toHaveLength(0);
  await page.screenshot({path:`test-results/handoff-rejected-${info.project.name}.png`,fullPage:true});
  await page.reload();
  await page.getByRole('button',{name:'Повторить обработку состояния',exact:true}).click();
  await expect(page.locator('.turn')).toHaveCount(1);
  expect((await view()).state.scene_meta.present_ids).toEqual(['ilya','viktoria_solovyova']);
  await page.locator('.choices button').filter({hasText:'Ждать ответа'}).click();
  await expect(page.locator('.turn')).toHaveCount(2);
  await page.reload();
  await expect(page.locator('.turn')).toHaveCount(2);
  await page.locator('.choices button').filter({hasText:'Ждать ответа'}).click();
  await expect(page.locator('.turn')).toHaveCount(3);
  const last=await view();expect(last.state.characters).toHaveLength(19);
  expect(last.state.world_clock.minute).toBe(first.state.world_clock.minute+3);
  await page.screenshot({path:`test-results/handoff-played-${info.project.name}.png`,fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
 } finally {
  const calls=await(await request.post('/test/runtime-handoff-provider?enabled=false')).json();
  expect(calls.narratives).toBe(3);expect(calls.extractions).toBe(5);
 }
 expect(errors).toEqual([]);
});
