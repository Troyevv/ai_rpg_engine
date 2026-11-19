import {test,expect} from '@playwright/test';
import {authorView,workshopNav} from './workshop-navigation';
import {nav} from './navigation';

for(const width of [360,393,1280])test(`saved creative recovery at ${width}px`,async({page,request},info)=>{
 test.skip((width<760)!==(info.project.name==='mobile'));
 const {wid}=await(await request.post('/test/generation266')).json();
 await page.setViewportSize({width,height:800});
 if(width===393){
   const device=await page.context().newCDPSession(page);
   await device.send('Emulation.setSafeAreaInsetsOverride',{insets:{top:24,bottom:32}});
 }
 const skin=width===360?'parchment':'graphite';
 await page.addInitScript(({wid,skin})=>{
   if(!localStorage.getItem('draftWorkspace'))localStorage.setItem('draftWorkspace',wid);
   localStorage.setItem('workshop-theme',JSON.stringify({theme_id:skin,mode:'manual'}));
 },{wid,skin});
 await page.goto('/');await nav(page,'Создать');await authorView(page);
 await workshopNav(page,'Идея и генерация');
 await expect(page.locator('.fl-stages li').filter({hasText:'Творческое развитие'})).toHaveAttribute('data-state','partial');
 const trigger=page.getByRole('button',{name:'Восстановить полученное дополнение'});
 await expect(page.locator('html')).toHaveAttribute('data-theme',skin);
 await trigger.click();
 const dialog=page.getByRole('dialog',{name:'Сохранённое дополнение'});
 await expect(dialog.getByText(/Текущий черновик изменился/)).toBeVisible();
 await dialog.getByRole('combobox').click();
 await expect(page.getByRole('option',{name:'Дополнение 2'})).toBeVisible();
 await page.keyboard.press('Escape');await expect(dialog).toBeVisible();
 const field=dialog.getByRole('combobox');
 await expect(field).toBeFocused();await field.press('ArrowDown');
 await expect(page.getByRole('option',{name:'Дополнение 1'})).toBeFocused();
 await page.keyboard.press('End');
 await expect(page.getByRole('option',{name:'Дополнение 2'})).toBeFocused();await page.keyboard.press('Enter');
 await expect(dialog.getByRole('button',{name:'Применить дополнение'})).toBeVisible();
 await page.keyboard.press('Escape');await expect(trigger).toBeFocused();
 await trigger.click();await dialog.getByRole('combobox').click();
 await page.getByRole('option',{name:'Дополнение 1'}).click();
 await dialog.getByText('Изменения (1)',{exact:true}).click();
 await page.setViewportSize({width,height:width<760?465:800});
 const button=dialog.getByRole('button',{name:'Создать отдельную копию'});
 await button.scrollIntoViewIfNeeded();
 await expect(button).toBeInViewport();await expect(dialog.getByRole('button',{name:'Закрыть',exact:true})).toBeInViewport();
 if(width===393){
   const bounds=await button.boundingBox();
   expect(bounds!.y+bounds!.height).toBeLessThanOrEqual(page.viewportSize()!.height-32);
 }
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await page.screenshot({path:info.outputPath('recovery.png')});
 await button.click();await dialog.getByRole('button',{name:'Открыть восстановленный мир'}).click();
 await expect(page.locator('.world-workshop')).not.toHaveAttribute('data-workspace-id',wid);
 const original=await(await request.get(`/api/workspaces/${wid}/draft?author=true`)).json();
 expect(original.state.campaign.title).toBe('Поздняя редакция автора');
 expect(original.creative_packages.filter((p:{recovered:unknown})=>p.recovered)).toHaveLength(1);
 await page.reload();await nav(page,'Создать');
 await expect(page.locator('.ww-hero h1')).toBeVisible();
});

test('author can compare and restore the world prompt without losing history',async({page,request})=>{
 const endpoint='/api/documents/prompt/draft_world_prompt.md';
 const initial=await(await request.get(endpoint)).json();
 const override=initial.template+'\nЭтот мир начинается летом.';
 const edit=await request.post(endpoint,{data:{content:override,expected_head:initial.active_id}});
 expect(edit.ok()).toBeTruthy();
 await page.goto('/');await nav(page,'Настройки');
 await page.getByText('Основные промпты и версии',{exact:true}).click();
 await page.getByRole('button',{name:'draft_world_prompt.md',exact:true}).click();
 const modal=page.getByRole('dialog').filter({has:page.getByRole('heading',{name:/История версий/})});
 await expect(modal).toContainText('Активен авторский промпт');
 await modal.getByRole('button',{name:'Подставить актуальный шаблон для сохранения'}).click();
 await expect(modal.getByLabel('Содержимое версии')).toHaveValue(initial.template);
 await modal.getByRole('button',{name:'Сохранить новую версию'}).click();
 await expect(modal).toContainText('Активен актуальный встроенный промпт');
 const current=await(await request.get(endpoint)).json();
 expect(current.versions.some((v:{content:string})=>v.content===override)).toBeTruthy();
});
