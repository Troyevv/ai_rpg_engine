import {confirmWorkshopStart} from './workshop-navigation';
import {test,expect} from '@playwright/test';
import {nav} from './navigation';
import {workshopNav} from './workshop-navigation';

test.use({video:'off'});
for(const skin of ['graphite','parchment']) {
 test(`174 localized legacy calendar and overrides survive editing and reload · ${skin}`,async({page,request})=>{
  const w=await(await request.post('/test/calendar-policy-e5')).json();
  const url=`/api/workspaces/${w.id}/draft`;
  let d=await(await request.get(url+'?author=true')).json();
  const calendar={...d.candidate.world_clock.calendar,start_date:'2026-01-01',start_minute:d.candidate.world_clock.minute};
  let response=await request.patch(url+'/candidate',{data:{revision:d.revision,path:'/world_clock/calendar',value:calendar}});
  expect(response.ok()).toBeTruthy();d=await response.json();
  response=await request.post(url+'/calendar-presets',{data:{revision:d.revision,presets:{holidays:'country',country:'RU',seasons:'north'}}});
  expect(response.ok()).toBeTruthy();d=await response.json();
  const before=d.candidate.world_clock.calendar.profile;
  expect(before.regional.language).toBe('en_US');
  const english=await(await request.get(url+'/calendar-preview?display_language=en_US')).json();
  const original=(date:string)=>english.events.find((e:{date:string})=>e.date===date);
  await page.goto('/');
  await page.evaluate(({id,skin})=>{localStorage.setItem('draftWorkspace',id);localStorage.setItem('workshop-theme',JSON.stringify({theme_id:skin,mode:'manual'}));},{id:w.id,skin});
  await page.reload();await nav(page,'Создать');
  await page.getByRole('button',{name:'Автор мира',exact:true}).click();
  await page.getByRole('button',{name:'Показать всё',exact:true}).click();
  await workshopNav(page,'Сцена и правила');
  await expect(page.locator('html')).toHaveAttribute('data-theme',skin);
  await page.getByText('Праздники и сезоны мира',{exact:true}).click();
  const preview=page.getByLabel('Предпросмотр календаря');
  await expect(preview).toContainText('Новогодние каникулы');
  await expect(preview).toContainText('Рождество Христово');
  await expect(preview).not.toContainText('Christmas Day');
  await page.getByText('Изменить конкретные вхождения (только этот год)',{exact:true}).click();
  const editor=page.locator('details').filter({has:page.locator('summary',{hasText:'Изменить конкретные вхождения (только этот год)'})}).last();
  const row=(date:string)=>editor.locator('div').filter({has:page.locator(`input[type=date][value="${date}"]`)});
  await expect(row('2026-01-07').getByLabel('Название',{exact:true})).toHaveValue('Рождество Христово');
  await row('2026-01-01').getByLabel('Название',{exact:true}).fill('Our New Year');
  await row('2026-01-01').getByLabel('Дата',{exact:true}).fill('2026-01-10');
  await row('2026-01-02').getByRole('checkbox').check();
  await page.getByRole('button',{name:'Сохранить свои даты',exact:true}).click();
  await expect.poll(async()=>{
   const current=await(await request.get(url+'?author=true')).json();
   return current.candidate.world_clock.calendar.profile.regional.overrides.length;
  }).toBe(2);
  d=await(await request.get(url+'?author=true')).json();
  const edited=d.candidate.world_clock.calendar.profile;
  expect(edited.regional.overrides).toEqual(expect.arrayContaining([
   expect.objectContaining({id:original('2026-01-01').id,name:'Our New Year',date:'2026-01-10'}),
   expect.objectContaining({id:original('2026-01-02').id,removed:true}),
  ]));
  expect(edited.regional.overrides.some((o:{id:string})=>o.id===original('2026-01-07').id)).toBe(false);
  await page.reload();await nav(page,'Создать');
  await page.getByRole('button',{name:'Начать с предупреждениями',exact:true}).click();
  await confirmWorkshopStart(page);
  await expect(page.getByRole('button',{name:'Начать игру',exact:true})).toBeVisible();
  const selection=await page.evaluate(()=>JSON.parse(localStorage.getItem('selection')||'{}'));
  expect(selection.save).toBeTruthy();
  expect((await request.put(`/api/worlds/${selection.world}/presentation`,{data:{theme_id:skin}})).ok()).toBeTruthy();
  await page.reload();await nav(page,'Календарь');
  await expect(page.locator('html')).toHaveAttribute('data-theme',skin);
  const area=page.locator('.calendar-screen');
  const detail=area.getByRole('region',{name:'События дня'});
  const choose=async(day:number)=>area.locator('.rdp-day_button').filter({has:page.locator('.calendar-day-number',{hasText:new RegExp(`^${day}$`)})}).click();
  await choose(7);await expect(detail).toContainText('Рождество Христово');
  await choose(10);await expect(detail).toContainText('Our New Year');
  await choose(2);await expect(detail).not.toContainText('Новогодние каникулы');
  expect(await area.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBeTruthy();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  const saved=await(await request.get(`/api/saves/${selection.save}`)).json();
  const range=`/api/saves/${selection.save}/calendar?start_date=2026-01-01&end_date=2026-01-31`;
  const ru=await(await request.get(range)).json();
  const en=await(await request.get(range+'&display_language=en_US')).json();
  expect(ru.events.map(({name,...event}:{name:string})=>event)).toEqual(en.events.map(({name,...event}:{name:string})=>event));
  await page.reload();await nav(page,'Календарь');await choose(7);
  await expect(detail).toContainText('Рождество Христово');
  const after=await(await request.get(`/api/saves/${selection.save}`)).json();
  expect(after.state).toEqual(saved.state);expect(after.revision).toBe(saved.revision);
  if(process.env.CALENDAR_VISUAL)await page.screenshot({path:`/tmp/holiday174-${skin}-${test.info().project.name}.png`});
 });
}
