import {test,expect} from '@playwright/test';
import {spawn,type ChildProcess} from 'node:child_process';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {nav} from './navigation';

test('staged creation survives browser closure and backend restart before resume and ordinary play',async({browser},info)=>{
 test.setTimeout(120000);
 const dir=mkdtempSync(join(tmpdir(),'staged-recovery-'));
 const base='http://127.0.0.1:8015';let server:ChildProcess|undefined;
 const start=async()=>{
  server=spawn(process.env.E2E_PYTHON||'python',[resolve('../tests/e2e_server.py')],{env:{...process.env,E2E_PORT:'8015',E2E_DB_PATH:join(dir,'world.db')},stdio:'ignore'});
  await expect.poll(async()=>{try{return(await fetch(base+'/api/health')).status}catch{return 0}},{timeout:20000}).toBe(200);
 };
 const stop=async()=>{if(server&&server.exitCode===null){const stopped=new Promise<void>(r=>server!.once('exit',()=>r()));server.kill('SIGTERM');await stopped}};
 let context=await browser.newContext({viewport:info.project.use.viewport});
 try{
  await start();await context.request.post(base+'/test/pause-next-staged');
  let page=await context.newPage();await page.goto(base);await nav(page,'Создать');
  await page.getByLabel('Описание мира или текст импорта').fill('Восемь соседей собрались на кухне.');
  const submitted=page.waitForResponse(r=>r.url().endsWith('/draft/generate')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Развить идею и создать мир',exact:true}).click();
  const job=await(await submitted).json();
  await expect(page.getByRole('heading',{name:'На паузе',exact:true})).toBeVisible();
  const checkpoint=await(await context.request.get(base+`/api/jobs/${job.id}/generation/checkpoints/places?author=true`)).json();
  const storageState=await context.storageState();
  await context.close();await stop();await start();
  context=await browser.newContext({storageState,viewport:info.project.use.viewport});
  page=await context.newPage();await page.goto(base);await nav(page,'Создать');
  await expect(page.getByRole('heading',{name:'На паузе',exact:true})).toBeVisible();
  const restored=await(await context.request.get(base+`/api/jobs/${job.id}/generation/checkpoints/places?author=true`)).json();
  expect(restored.artifact_version).toBe(checkpoint.artifact_version);
  expect(restored.artifact).toEqual(checkpoint.artifact);
  await page.getByRole('button',{name:'Продолжить генерацию',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Посмотри, что получилось'})).toBeVisible();
  const completed=await(await context.request.get(base+`/api/jobs/${job.id}/generation/checkpoints/places?author=true`)).json();
  expect(completed.artifact_version).toBe(checkpoint.artifact_version);
  await page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true}).click();
  await page.getByRole('button',{name:'Подтвердить и открыть игру',exact:true}).click();
  await page.getByRole('button',{name:'Начать игру',exact:true}).click();
  await expect(page.locator('.choices button')).toHaveCount(6);
  await page.reload();await expect(page.locator('.choices button')).toHaveCount(6);
 }finally{await context.close();await stop();rmSync(dir,{recursive:true,force:true})}
});
