import {workshopNav,draftsMenu} from './workshop-navigation';
import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {nav} from './navigation';
const fixture=JSON.parse(readFileSync(new URL('../../tests/fixtures/initial_world/runtime_presentation.json',import.meta.url),'utf8'));

test('populated Runtime world has names, typed values, calendar, edit and reload',async({page,request},info)=>{
 const w=await(await request.post('/api/workspaces',{data:{name:'Runtime presentation'}})).json();const url=`/api/workspaces/${w.id}/draft`;
 const imported=await request.post(url+'/import',{data:{revision:0,format:'json',text:JSON.stringify(fixture)}});expect(imported.ok()).toBeTruthy();
 await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),w.id);
 await page.goto('/');await nav(page,'Создать');
 await page.getByRole('button',{name:'Автор мира',exact:true}).click();await page.getByRole('button',{name:'Показать всё',exact:true}).click();

 await workshopNav(page,'Сцена и правила');
 await expect(page.getByText('Пятница, 23 октября 2026, 08:00',{exact:true})).toBeVisible();
 const effective=page.getByRole('region',{name:'Действующий календарь'});
 await expect(effective).toContainText('Понедельник');
 await expect(effective).toContainText('февраля: 28');
 await expect(effective).toContainText('октября: 31');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(await page.evaluate(()=>innerWidth));
 await expect(page.getByText('[object Object]',{exact:false})).toHaveCount(0);
 await page.locator('.workshop-start').scrollIntoViewIfNeeded();
 await page.screenshot({path:`test-results/runtime-calendar-${info.project.name}.png`,fullPage:true});
 await workshopNav(page,'Персонажи');
 await page.locator('.ww-character-card').first().click();
 await expect(page.getByText('Взрослый',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Сейчас',exact:true}).click();
 await expect(page.getByText('Может передвигаться',{exact:true})).toBeVisible();
 await expect(page.getByText('Может воспринимать',{exact:true}).locator('..').getByText('Неизвестно',{exact:true})).toBeVisible();
 await expect(page.getByText('[object Object]',{exact:false})).toHaveCount(0);
 await page.screenshot({path:`test-results/runtime-character-${info.project.name}.png`,fullPage:true});
 await page.getByRole('button',{name:'Готово',exact:true}).click();
 await workshopNav(page,'Места и сообщества');
 await page.getByRole('button',{name:'Проживание',exact:true}).click();
 await page.getByLabel('Группировка проживания').selectOption('location');
 await expect(page.getByRole('heading',{name:'Дом у реки',exact:true})).toBeVisible();
 await expect(page.getByRole('heading',{name:'Анна → Дом у реки',exact:true})).toBeVisible();
 await expect(page.getByRole('heading',{name:'Борис → Дом у реки',exact:true})).toBeVisible();
 await page.locator('.ww-record-card').filter({hasText:'Анна → Дом у реки'}).getByRole('button').click();
 const residence=page.locator('.ww-record-dialog');
 const saveField=async()=>{
  // A nested Radix dialog hides its parent from the accessibility tree, so
  // getByRole('dialog').toHaveCount(1) is also true before the PATCH completes.
  const committed=page.waitForResponse(r=>r.url().endsWith(url)&&r.request().method()==='PATCH');
  await page.locator('.ww-field-dialog').getByRole('button',{name:'Сохранить поле',exact:true}).click();
  const response=await committed;expect(response.ok(),await response.text()).toBe(true);
  await expect(page.locator('.ww-field-dialog')).toHaveCount(0);await expect(residence).toBeVisible();
 };
 await residence.getByRole('button',{name:'Изменить Контекст',exact:true}).first().click();
 await page.getByRole('dialog').last().getByLabel('Контекст',{exact:true}).fill('Дом остаётся прежним; уточнение автора.');
 await saveField();
 await residence.getByRole('button',{name:'Изменить С минуты',exact:true}).first().click();
 await expect(page.getByRole('dialog').last().getByLabel('С минуты',{exact:true})).toHaveAttribute('type','number');
 await page.getByRole('dialog').last().getByLabel('С минуты',{exact:true}).fill('0');
 let release!:()=>void,received!:()=>void;const gate=new Promise<void>(r=>release=r),pending=new Promise<void>(r=>received=r);
 await page.route(`**${url}`,async route=>{received();await gate;await route.continue()},{times:1});
 const saving=saveField();await pending;
 await expect(page.locator('.ww-field-dialog')).toContainText('Сохраняем');
 expect((await(await request.get(url+'?author=true')).json()).state.world.residences.home_a.since).toBeNull();
 release();await saving;
 expect((await(await request.get(url+'?author=true')).json()).state.world.residences.home_a.since).toBe(0);
 await residence.getByRole('button',{name:'Изменить С минуты',exact:true}).first().click();
 await page.getByRole('button',{name:'Оставить неизвестным',exact:true}).click();
 await saveField();
 await expect.poll(async()=>(await(await request.get(url+'?author=true')).json()).state.world.residences.home_a.since).toBeNull();
 const after=await(await request.get(url+'?author=true')).json();expect(after.state.world.residences.home_a.context).toContain('уточнение автора');
 expect(after.state.world.residences.home_a.since).toBeNull();
 expect(after.state.world.residences.home_a.until).toBeNull();
 await residence.getByRole('button',{name:'Закрыть',exact:true}).click();
 await page.getByRole('button',{name:'Контакты',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Анна · Друг · Борис',exact:true})).toBeVisible();
 await page.screenshot({path:`test-results/runtime-residences-${info.project.name}.png`,fullPage:true});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(await page.evaluate(()=>innerWidth));
 await page.reload();await nav(page,'Создать');
 const reloaded=await(await request.get(url+'?author=true')).json();expect(reloaded.state.world.residences).toEqual(after.state.world.residences);
 const player=await(await request.get(url)).json();expect(player.state.world.contacts || {}).toEqual({});
 await page.getByRole('button',{name:'Подтвердить мир и начать игру',exact:true}).click();
 await page.getByRole('button',{name:'Подтвердить и открыть игру',exact:true}).click();
 await page.getByRole('button',{name:'Начать игру',exact:true}).click();await expect(page.locator('.choices button')).toHaveCount(6);
 await page.reload();await expect(page.locator('.choices button')).toHaveCount(6);
});

test('separate family fixture exposes lifecycle structures only in author view',async({page,request},info)=>{
 const family=JSON.parse(readFileSync(new URL('../../tests/fixtures/initial_world/runtime_family.json',import.meta.url),'utf8'));
 const w=await(await request.post('/api/workspaces',{data:{name:'Synthetic family'}})).json();const url=`/api/workspaces/${w.id}/draft`;
 expect((await request.post(url+'/import',{data:{revision:0,format:'json',text:JSON.stringify(family)}})).ok()).toBeTruthy();
 await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),w.id);await page.goto('/');await nav(page,'Создать');
 await page.getByRole('button',{name:'Автор мира',exact:true}).click();await page.getByRole('button',{name:'Показать всё',exact:true}).click();
 for(const [route,tab,title] of [['Связи и семьи','Беременности','Беременности'],['Хронология','Семейные события','Репродуктивные события'],['Хронология','Выбор имён','Выбор имён']]){
  await workshopNav(page,route);await page.getByRole('button',{name:tab,exact:true}).click();
  await expect(page.getByRole('heading',{name:title+' · 1',exact:true})).toBeVisible();
  await page.locator('.ww-record-card').getByRole('button').click();
  await expect(page.locator('.ww-record-dialog')).not.toContainText('[object Object]');
  await page.locator('.ww-record-dialog').getByRole('button',{name:'Закрыть',exact:true}).click();
 }
 await page.screenshot({path:`test-results/runtime-family-${info.project.name}.png`,fullPage:true});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(await page.evaluate(()=>innerWidth));
 const pub=await(await request.get(url)).json();expect(pub.state.world.pregnancies || {}).toEqual({});expect(pub.state.world.naming_decisions || {}).toEqual({});
});
