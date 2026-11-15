import {expect,test} from '@playwright/test';
import {defaults} from '../src/types';

test.afterEach(async({request})=>{await request.post('/test/scene255-reset')});

test('v6 rejected scene retains input, targeted repair cap and explicit recovery after reload',async({page,request})=>{
  const selection=await (await request.post('/test/scene255-seed')).json();
  const path=`/api/saves/${selection.save}`;
  const profile=`scene255-${selection.save}`;
  await request.put(`/api/settings/${profile}`,{data:{...defaults,game:{...defaults.game,model:'scene255-test',context_length:65536,update_tokens:8192}}});
  await page.addInitScript(({selection,profile})=>{localStorage.setItem('selection',JSON.stringify(selection));localStorage.setItem('profile',profile)},{selection,profile});
  await page.goto('/');
  const input=page.getByLabel('Своё действие или реплика');
  await input.fill('Иду в парк.');
  await page.getByRole('button',{name:'Отправить действие',exact:true}).click();
  const retry=page.getByRole('button',{name:'Повторить обработку состояния',exact:true});
  await expect(retry).toBeEnabled();
  const view=async()=>(await request.get(path)).json();
  const failed=await view();
  expect(failed.job.status).toBe('error');
  expect(failed.job.error).toContain('Нет однозначного источника действия');
  const stages=async()=>{
    const accounting=await(await request.get(`${path}/accounting`)).json();
    return accounting.requests.filter((r:{job_id:string})=>r.job_id===failed.job.id).map((r:{stage:string})=>r.stage).sort();
  };
  expect(await stages()).toEqual(['extraction','extraction_repair','narrative']);
  expect(failed.job.user_text).toBe('Иду в парк.');
  expect(failed.job.narrative).toContain('дошёл до парка');
  await expect(page.getByText('Сцена не сохранена.',{exact:false})).toBeVisible();
  await page.reload();
  await page.getByRole('button',{name:'К восстановлению хода',exact:true}).click();
  await expect(retry).toBeInViewport();
  await expect(page.getByRole('button',{name:'Отправить действие',exact:true})).toBeDisabled();
  await retry.click();
  await expect.poll(async()=>(await view()).job.status).toBe('saved');
  const saved=await view();
  expect(saved.revision).toBe(failed.revision+1);
  expect(saved.job.narrative).toBe(failed.job.narrative);
  expect(await stages()).toEqual(['extraction','extraction','extraction_repair','narrative']);
  await page.reload();
  await expect(input).toBeEnabled();
  await input.fill('Иду в парк.');
  await page.getByRole('button',{name:'Отправить действие',exact:true}).click();
  await expect.poll(async()=>(await view()).revision).toBe(saved.revision+1);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
