import {test,expect} from '@playwright/test';
import {spawn,type ChildProcess} from 'node:child_process';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {nav} from './navigation';

test('author contract exposes one editable document and preserves its biography on reload',async({browser},info)=>{
 test.setTimeout(120000);
 const dir=mkdtempSync(join(tmpdir(),'author-contract-'));
 const base='http://127.0.0.1:8016';let server:ChildProcess|undefined;
 const context=await browser.newContext({viewport:info.project.use.viewport});
 try{
  server=spawn(process.env.E2E_PYTHON||'python',[resolve('../tests/e2e_server.py')],{env:{...process.env,E2E_PORT:'8016',E2E_DB_PATH:join(dir,'world.db'),E2E_AUTHORING:'1'},stdio:'ignore'});
  await expect.poll(async()=>{try{return(await fetch(base+'/api/health')).status}catch{return 0}},{timeout:20000}).toBe(200);
  const page=await context.newPage();await page.goto(base);await nav(page,'Создать');
  await page.getByLabel('Описание мира или текст импорта').fill('Переезд и работа в НИИ.');
  await page.getByRole('button',{name:'Развить идею и создать мир',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Посмотри, что получилось'})).toBeVisible();
  await page.getByRole('button',{name:'Автор мира',exact:true}).click();
  await page.getByRole('button',{name:'Показать всё',exact:true}).click();
  await page.getByRole('button',{name:'Открыть полный редактор',exact:true}).click();
  const editor=page.getByRole('region',{name:'Полный редактор начального мира'});
  await editor.getByLabel('Расширенный JSON',{exact:true}).check();
  const area=editor.getByRole('textbox',{name:'JSON раздела мира'});
  const people=JSON.parse(await area.inputValue());
  people[0].biography='Автор сохранил подробную биографию.';
  await area.fill(JSON.stringify(people));
  await editor.getByRole('button',{name:'Сохранить раздел мира'}).click();
  await expect(editor.getByRole('button',{name:'Открыть полный редактор'})).toBeVisible();
  await page.reload();await nav(page,'Создать');
  await page.getByRole('button',{name:'Автор мира',exact:true}).click();
  await page.getByRole('button',{name:'Показать всё',exact:true}).click();
  await page.getByRole('button',{name:'Открыть полный редактор',exact:true}).click();
  await editor.getByLabel('Расширенный JSON',{exact:true}).check();
  await expect(area).toHaveValue(/Автор сохранил подробную биографию\./);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
  await editor.getByRole('button',{name:'Закрыть редактор',exact:true}).click();
  await page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true}).click();
  await page.getByRole('button',{name:'Подтвердить и открыть игру',exact:true}).click();
  await page.getByRole('button',{name:'Начать игру',exact:true}).click();
  await expect(page.locator('.choices button')).toHaveCount(6);
  await page.reload();
  await expect(page.locator('.choices button')).toHaveCount(6);
 }finally{
  await context.close();
  if(server&&server.exitCode===null){const stopped=new Promise<void>(r=>server!.once('exit',()=>r()));server.kill('SIGTERM');await stopped;}
  rmSync(dir,{recursive:true,force:true});
 }
});
