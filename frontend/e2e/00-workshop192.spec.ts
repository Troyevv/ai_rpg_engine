import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {nav} from './navigation';
import {authorView,workshopNav} from './workshop-navigation';
import {creationMethod} from './idea-navigation';

const source=JSON.parse(readFileSync(new URL('../../tests/fixtures/initial_world/workshop188.json',import.meta.url),'utf8'));
test('W61 W62 scenario follows explicit world and preserves separate input buffers',async({page,request})=>{
 const a=await(await request.post('/api/workspaces',{data:{name:'Сценарий A'}})).json();
 const b=await(await request.post('/api/workspaces',{data:{name:'Сценарий B'}})).json();
 for(const w of [a,b]){const h=await(await request.get(`/api/documents/idea/${w.id}`)).json();expect((await request.post(`/api/documents/idea/${w.id}`,{data:{content:w.name,expected_head:h.active_id}})).ok()).toBe(true)}
 await page.addInitScript(({a,b})=>{localStorage.setItem('workspace',a);localStorage.setItem('draftWorkspace',b)}, {a:a.id,b:b.id});
 await page.goto('/');await nav(page,'Создать');await creationMethod(page,'Со Сценаристом');
 await expect(page.getByLabel('Подготовка',{exact:true})).toHaveValue(b.id);await expect(page.locator('.preparation')).toContainText('Сценарий B');
 const input=page.getByLabel('Идея или правки сценария');await input.fill('Несохранённое уточнение B');
 await page.getByLabel('Подготовка',{exact:true}).selectOption(a.id);await expect(input).toHaveValue('');await input.fill('Отдельный ввод A');
 await page.getByLabel('Подготовка',{exact:true}).selectOption(b.id);await expect(input).toHaveValue('Несохранённое уточнение B');
 await page.getByRole('button',{name:'← Генератор мира',exact:true}).click();await creationMethod(page,'Со Сценаристом');await expect(input).toHaveValue('Несохранённое уточнение B');
 for(const w of [a,b]){const data=await(await request.get(`/api/workspaces/${w.id}`)).json();expect(data.idea).toBe(w.name)}
 await expect(page.locator('.ww-shell .preparation')).toBeVisible();
});
test('W01 W16 W34 W52 real SQLite creation, cancellation, search and version preview',async({page,request})=>{
 const workspace=await(await request.post('/api/workspaces',{data:{name:'Проверка 192'}})).json();const url=`/api/workspaces/${workspace.id}/draft`;
 expect((await request.post(url+'/import',{data:{revision:0,format:'json',text:JSON.stringify(source)}})).ok()).toBe(true);
 const before=await(await request.get(url+'?author=true')).json();
 await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),workspace.id);await page.goto('/');await nav(page,'Создать');await authorView(page);
 await workshopNav(page,'Персонажи');await page.getByRole('button',{name:'Персонаж',exact:true}).click();
 const form=page.locator('.ww-create-dialog');await expect(form.getByRole('button',{name:'Создать запись',exact:true})).toBeDisabled();
 await form.getByLabel('Имя',{exact:true}).fill('Не сохранять');await form.getByRole('button',{name:'Отмена',exact:true}).click();
 expect((await(await request.get(url+'?author=true')).json()).revision).toBe(before.revision);
 await workshopNav(page,'Сюжеты');await page.locator('.ww-records-thread').getByRole('button',{name:'Добавить',exact:true}).click();
 await form.getByLabel('Название или краткое описание').fill('Найти старый телескоп');await form.getByLabel('Описание',{exact:true}).fill('Уникальная обсерватория на крыше.');
 await form.getByRole('button',{name:'Создать запись',exact:true}).click();await expect(page.locator('.ww-record-dialog')).toContainText('Уникальная обсерватория');
 const after=await(await request.get(url+'?author=true')).json();expect(after.revision).toBe(before.revision+1);expect(after.history).toHaveLength(before.history.length+1);
 await page.keyboard.press('Escape');await page.locator('.ww-topbar').getByRole('button',{name:'Поиск по миру',exact:true}).click();
 await page.getByRole('dialog').getByRole('textbox',{name:'Поиск по миру',exact:true}).fill('обсерватория');await page.locator('.ww-search-results button').click();await expect(page.locator('.ww-record-dialog')).toContainText('Найти старый телескоп');
 await page.keyboard.press('Escape');await workshopNav(page,'История и файлы');await page.getByText(`История версий · ${after.history.length}`,{exact:true}).click();
 await page.locator('.workshop-version').last().getByRole('button',{name:'Посмотреть версию',exact:true}).click();await expect(page.locator('.ww-version-preview h2')).toHaveText(source.campaign.title);
 expect((await(await request.get(url+'?author=true')).json()).revision).toBe(after.revision);
 await page.getByRole('button',{name:'Закрыть просмотр',exact:true}).click();expect((await(await request.get(url+'?author=true')).json()).state).toEqual(after.state);
});

test('W01–W69 reference/current browser evidence at required viewport widths',async({page,request,browser},info)=>{
 test.setTimeout(240000);
 const referenceURL='/test/workshop175/reference/world-workshop.html';
 const bytes=await(await request.get(referenceURL)).body();expect(bytes.length).toBe(468501);
 expect(createHash('sha256').update(bytes).digest('hex')).toBe('4122bcf37cbfd4c979e264e655896cc8d8783d51899a2aa9d170bd9f5c3e82e1');
 const w=await(await request.post('/api/workspaces',{data:{name:'Сравнение 192'}})).json();
 expect((await request.post(`/api/workspaces/${w.id}/draft/import`,{data:{revision:0,format:'json',text:JSON.stringify(source)}})).ok()).toBe(true);
 await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),w.id);await page.goto('/');await nav(page,'Создать');await authorView(page);
 const ref=await page.context().newPage();await ref.goto(referenceURL);await ref.evaluate(()=>document.fonts.ready);
 const widths=info.project.name==='desktop'?[1280,1440,1920]:[360,390,412,430];
 const screens=[['overview','Обзор мира'],['characters','Персонажи'],['places','Места и сообщества'],['relations','Связи и семьи'],['story','Сюжеты'],['timeline','Хронология'],['knowledge','Факты и знания'],['settings','Сцена и правила'],['review','Проверка мира'],['ai','Изменить с ИИ'],['history','История и файлы']];
 const metadata:{width:number;route:string;fonts:string[];scrollWidth:number;viewport:number}[]=[];
 for(const width of widths){
  await page.setViewportSize({width,height:900});await ref.setViewportSize({width,height:900});
  for(const [route,label] of screens){
   await ref.locator(`[data-action="navigate"][data-route="${route}"]`).first().evaluate((el:HTMLElement)=>el.click());
   await workshopNav(page,label);await page.evaluate(()=>document.fonts.ready);await expect(page.locator('.ww-content')).toBeVisible();
   const metrics=await page.evaluate(()=>({fonts:[getComputedStyle(document.querySelector('.ww-content')!).fontFamily,getComputedStyle((document.querySelector('.ww-content h1,.ww-content h2,.ww-content h3')||document.querySelector('.ww-content'))!).fontFamily],scrollWidth:document.documentElement.scrollWidth,viewport:innerWidth}));
   expect(metrics.scrollWidth,`${width} ${route} horizontal overflow`).toBeLessThanOrEqual(width);
   metadata.push({width,route,...metrics});
   await ref.screenshot({path:info.outputPath(`${width}-${route}-reference.png`),animations:'disabled'});
   await page.screenshot({path:info.outputPath(`${width}-${route}-current.png`),animations:'disabled'});
  }
 }
 await info.attach('comparison-metadata',{body:JSON.stringify({browser:browser.version(),referenceSHA256:'4122bcf37cbfd4c979e264e655896cc8d8783d51899a2aa9d170bd9f5c3e82e1',note:'Current branch and original reference; not pre-change master baseline or automatic visual acceptance.',metadata},null,2),contentType:'application/json'});
 await ref.close();
});
