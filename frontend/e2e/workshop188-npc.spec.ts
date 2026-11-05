import {confirmWorkshopStart} from './workshop-navigation';
import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {defaults} from '../src/types';
import {nav} from './navigation';
import {authorView,workshopNav} from './workshop-navigation';

for(const cid of ['vera','olya']) {
const name=cid==='vera'?'Вера Соколова':'Оля Соколова';
const instruction=cid==='vera'?'Создай сестру Ильи':'Создай сестру Ильи — Олю';
test(`recorded sister ${cid}: unchanged draft, preview, confirmation and Runtime`,async({page,request},info)=>{
 const fixture=JSON.parse(readFileSync(new URL(`../../tests/fixtures/draft_editor/ilya_sister${cid==='olya'?'_olya':''}.json`,import.meta.url),'utf8'));
 const w=await(await request.post('/test/editor173',{data:{fail:false}})).json();const url=`/api/workspaces/${w.id}/draft`;
 const imported=await request.post(url+'/import',{data:{revision:0,format:'json',text:JSON.stringify(fixture.base.state)}});expect(imported.ok(),await imported.text()).toBeTruthy();
 const before=await(await request.get(url+'?author=true')).json();
 await request.post('/test/editor173/release');
 await page.addInitScript(wid=>localStorage.setItem('draftWorkspace',wid),w.id);await page.goto('/');
 const profile=await page.evaluate(()=>localStorage.getItem('profile'));
 expect((await request.put(`/api/settings/${profile}`,{data:{...defaults,summary:{...defaults.summary,model:'handoff-test',context_length:131072,max_tokens:24000}}})).ok()).toBeTruthy();
 await page.reload();await nav(page,'Создать');await authorView(page);await workshopNav(page,'Изменить с ИИ');
 const editor=page.locator('.world-ai-editor');
 await editor.getByLabel('Что изменить в мире?').fill(instruction);await editor.getByRole('button',{name:'Предложить изменения',exact:true}).click();
 await expect(editor.getByRole('heading',{name:'Ожидает решения',exact:true})).toBeVisible();
 await expect(editor.getByRole('button',{name:'Применить пакет…',exact:true})).toBeEnabled();
 const preview=await(await request.get(url+'/edits?author=true')).json();expect(preview.edits[0].proposal.changes).toHaveLength(cid==='vera'?15:13);
 expect((await(await request.get(url+'?author=true')).json()).state).toEqual(before.state);
 const vera=editor.locator('.ai-diff-entity').filter({hasText:name}).first();if(await vera.getAttribute('open')===null)await vera.locator(':scope > summary').click();await expect(vera).toHaveAttribute('open','');await expect(vera).toContainText(name);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:test.info().outputPath(`sister-preview-${info.project.name}.png`),scale:'css'});
 await editor.getByRole('button',{name:'Применить пакет…',exact:true}).click();await page.keyboard.press('Escape');
 expect((await(await request.get(url+'?author=true')).json()).state).toEqual(before.state);
 await editor.getByRole('button',{name:'Применить пакет…',exact:true}).click();await page.getByRole('button',{name:'Подтвердить изменения',exact:true}).click();
 await expect(editor.locator('.ai-preview')).toContainText('Изменения сохранены');
 const accepted=await(await request.get(url+'?author=true')).json();expect(accepted.version_id).not.toBe(before.version_id);
 expect(accepted.state.world.characters[cid].goals[0].revision).toBe(0);expect(accepted.state.world.characters.ilya).toEqual(before.state.world.characters.ilya);
 for(const [id,fact] of Object.entries(before.state.world.facts))expect(accepted.state.world.facts[id]).toEqual(fact);
 await workshopNav(page,'Персонажи');await page.getByRole('button',{name:`Досье ${name}`,exact:true}).click();
 await expect(page.getByRole('dialog')).toContainText(name);await page.getByRole('button',{name:'Готово',exact:true}).click();
 await page.locator('.ww-topbar .ww-primary').click();await confirmWorkshopStart(page);await expect(page.locator('.world-workshop')).toHaveCount(0);
 const selected=await page.evaluate(()=>JSON.parse(localStorage.getItem('selection')!));
 const snapshot=(await(await request.get(`/api/saves/${selected.save}/author-state`)).json()).snapshot;
 expect(snapshot.world_state.characters[cid].location_id).toBe(cid==='vera'?'loc_sokolovy_tver':'loc_sokolov_tver');expect(snapshot.world_state.camera.present_character_ids).not.toContain(cid);
 expect(snapshot.world_state.objective_relations[`obj_rel_ilya_${cid}_sibling`].kind).toBe('sibling');expect(snapshot.world_state.knowledge[`${cid}:fact_ilya_sister`].status).toBe('known');
 await page.reload();expect((await(await request.get(`/api/saves/${selected.save}/author-state`)).json()).snapshot).toEqual(snapshot);
});

}
