import {VersionPreview} from '../src/workshop/VersionPreview';
import {reviewIssues} from '../src/workshop/reviewIssues';
import {act,type ReactNode} from 'react';
import {createRoot,type Root} from 'react-dom/client';
import {afterEach,expect,it,vi} from 'vitest';
import {api} from '../src/api';
import {CreateRecordDialog} from '../src/workshop/CreateRecordDialog';
import {RecordEditor} from '../src/workshop/RecordEditor';
import {StartConfirmation,type LaunchSnapshot} from '../src/workshop/StartConfirmation';
import {FeelingEditor} from '../src/workshop/FeelingEditor';
import {workshopSearch} from '../src/workshop/workshopSearch';
import {detectWorldImport} from '../src/worldImport';

vi.mock('../src/api',()=>({api:vi.fn(async()=>({entity_id:'created'}))}));
const roots:Root[]=[];
async function mount(node:ReactNode){const host=document.createElement('div');document.body.append(host);const root=createRoot(host);roots.push(root);await act(()=>root.render(node));return root}
const button=(name:string)=>Array.from(document.querySelectorAll('button')).find(b=>b.textContent===name)!;
async function type(element:HTMLInputElement|HTMLTextAreaElement|HTMLSelectElement,value:string){
 const prototype=element instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:element instanceof HTMLSelectElement?HTMLSelectElement.prototype:HTMLInputElement.prototype;
 await act(()=>{Object.getOwnPropertyDescriptor(prototype,'value')!.set!.call(element,value);element.dispatchEvent(new Event(element instanceof HTMLSelectElement?'change':'input',{bubbles:true}))});
}
afterEach(async()=>{await act(()=>roots.splice(0).forEach(r=>r.unmount()));sessionStorage.clear();document.body.innerHTML='';vi.clearAllMocks()});

it('indexes all five object types by descriptions and rebuilds from the authorized projection',()=>{
 const state={characters:[{id:'c',name:'Анна',fields:{Биография:'Любит абрикосы'}}],locations:[{id:'l',name:'Дом',text:'Сад с абрикосами'}],world:{organizations:{o:{name:'Клуб',context:'Выращивает абрикосы'}},threads:{t:{description:'Собрать абрикосы'}},facts:{f:{text:'Абрикосы поспели'}}}};
 expect(workshopSearch(state,'АБРИКОС').map(x=>x.kind)).toEqual(['character','location','organizations','thread','fact']);
 expect(workshopSearch(state,'')).toHaveLength(5);expect(workshopSearch(state,'нет такого')).toEqual([]);
 expect(workshopSearch({...state,world:{organizations:{},threads:{},facts:{}}},'абрикос')).toHaveLength(2);
 expect(workshopSearch(null,'абрикос')).toEqual([]);
});
it('rejects pasted JSON arrays while preserving Markdown starting with a bracket',()=>{
 expect(detectWorldImport('[{"name":"not a world"}]').error).toContain('Нужен объект');
 expect(detectWorldImport('[Город](https://example.com) — описание')).toEqual({format:'text',error:null});
 expect(detectWorldImport('{ broken').error).toContain('синтаксиса');
});
it('opening and cancelling creation never writes; confirmation submits all fields once',async()=>{
 const close=vi.fn(),created=vi.fn(async()=>{});
 await mount(<CreateRecordDialog wid="a" target={{kind:'character',revision:7}} characters={[]} facts={[]} onClose={close} onCreated={created}/>);
 expect(api).not.toHaveBeenCalled();expect(button('Создать запись').disabled).toBe(true);
 await type(document.querySelector('.ww-create-dialog input')!,'Ольга');await type(document.querySelector('textarea')!,'Живёт у моря.');
 expect(api).not.toHaveBeenCalled();await act(()=>button('Отмена').click());expect(api).not.toHaveBeenCalled();expect(close).toHaveBeenCalledOnce();
 await act(()=>{button('Создать запись').click();button('Создать запись').click()});
 expect(api).toHaveBeenCalledExactlyOnceWith('/workspaces/a/draft',{revision:7,operation:'add',kind:'character',value:{name:'Ольга','fields.Биография':'Живёт у моря.'}},'PATCH');
 expect(created).toHaveBeenCalledWith('character','created');
});
it('relationship creation keeps selected source and requires an explicit different target',async()=>{
 await mount(<CreateRecordDialog wid="a" target={{kind:'relationship',source:'npc',revision:2}} characters={[{id:'hero',name:'Герой'},{id:'npc',name:'Сосед'}]} facts={[]} onClose={()=>{}} onCreated={async()=>{}}/>);
 const select=document.querySelectorAll('select');expect(select[0].value).toBe('npc');expect(select[1].value).toBe('');expect(button('Создать запись').disabled).toBe(true);
 await type(select[1],'npc');expect(button('Создать запись').disabled).toBe(true);
 await type(select[1],'hero');await act(()=>button('Создать запись').click());
 expect(api).toHaveBeenCalledWith('/workspaces/a/draft',expect.objectContaining({value:{source_id:'npc',target_id:'hero',context:''}}),'PATCH');
});
it('record edits persist an isolated buffer and commit several fields atomically',async()=>{
 const target={kind:'character',id:'c',title:'Карточка',revision:3,values:{name:'Анна','fields.Биография':'Было'}};
 await mount(<RecordEditor wid="a" target={target} labels={{}} references={()=>null} onClose={()=>{}} onSaved={async()=>{}}/>);
 const fields=document.querySelectorAll('textarea');await type(fields[0],'Анна Иванова');await type(fields[1],'Стало');
 expect(api).not.toHaveBeenCalled();expect(sessionStorage.getItem('workshop-record:b:character:c')).toBeNull();
 await act(()=>{button('Сохранить изменения').click();button('Сохранить изменения').click()});
 expect(api).toHaveBeenCalledExactlyOnceWith('/workspaces/a/draft',{revision:3,operation:'patch_fields',kind:'character',entity_id:'c',value:{name:'Анна Иванова','fields.Биография':'Стало'},warnings_ack:false},'PATCH');
 expect(sessionStorage.getItem('workshop-record:a:character:c')).toBeNull();
});
it('launch requires each decision and invalidates them when revision changes',async()=>{
 const shown:LaunchSnapshot={wid:'a',revision:3,version:12,title:'Мир',summary:[['Герой','Анна']],warnings:['Замечание'],warning:true,stale:true,running:true,jobId:'job',technical:true,pending:false};
 const root=await mount(<StartConfirmation shown={shown} current={shown} onClose={()=>{}} onGame={()=>{}}/>);
 const launch=()=>button('Подтвердить и открыть игру');expect(launch().disabled).toBe(true);
 const checks=document.querySelectorAll<HTMLInputElement>('input[type=checkbox]');expect(checks).toHaveLength(3);
 await act(()=>checks[0].click());expect(launch().disabled).toBe(true);
 await act(()=>checks[1].click());expect(launch().disabled).toBe(true);
 await act(()=>checks[2].click());expect(launch().disabled).toBe(false);expect(api).not.toHaveBeenCalled();
 await act(()=>root.render(<StartConfirmation shown={shown} current={{...shown,revision:4}} onClose={()=>{}} onGame={()=>{}}/>));
 expect(launch().disabled).toBe(true);expect(document.querySelector('[role=alert]')?.textContent).toContain('изменились');expect(api).not.toHaveBeenCalled();
});
it('feelings preserve unknown dimensions instead of silently assigning zero',async()=>{
 const update=vi.fn();await mount(<FeelingEditor value={{trust:0,custom:23}} onChange={update}/>);
 expect(update).not.toHaveBeenCalled();expect(document.body.textContent).toContain('custom');
 expect(document.querySelectorAll('input[type=range]').length).toBeGreaterThanOrEqual(7);
 expect(document.querySelector('#feeling-trust')?.getAttribute('aria-valuetext')).toBe('0');
 expect(document.querySelector('#feeling-affection')?.getAttribute('aria-valuetext')).toBe('Не задано');
});

it('review display keeps strongest priority and every path without duplicate serialized diagnostics',()=>{
 const rows=reviewIssues([{message:'Не задан участник',severity:'blocker',path:'/world/scenes/a/participants'},{message:'Подробнее опиши город',severity:'recommendation'}],{warnings:['/world/scenes/a/participants: Не задан участник'],diagnostics:[{message:'Не задан участник',path:'/world/scenes/b/participants'}]},['Не задан участник']);
 expect(rows).toHaveLength(2);expect(rows[0]).toMatchObject({message:'Не задан участник',severity:'error',paths:['/world/scenes/a/participants','/world/scenes/b/participants']});expect(rows[0].sources).toContain('Импорт');expect(rows[1].severity).toBe('recommendation');
 expect(reviewIssues()).toEqual([]);
});

it('version preview can inspect an incomplete saved candidate without mutation',async()=>{
 vi.mocked(api).mockResolvedValueOnce({id:1,created_at:'2026-11-05T10:00:00Z',reason:'generation_candidate',state:{campaign:null,characters:[null,{id:'partial'}],locations:null,world:{scenes:{scene:{participants:['missing'],text:'Сохранённый фрагмент'}}}},presentation:{clock:{label:'Дата неизвестна'}}});
 await mount(<VersionPreview wid="a" version={1} revision={5} head={2} onClose={()=>{}} onRestore={async()=>{}}/>);
 expect(document.querySelector('.ww-version-preview')?.textContent).toContain('Неполный снимок мира');expect(document.body.textContent).toContain('Сохранённый фрагмент');
 expect(api).toHaveBeenCalledExactlyOnceWith('/workspaces/a/draft/versions/1?author=true',undefined,'GET',expect.any(AbortSignal));
 expect(button('Восстановить выбранную версию').disabled).toBe(true);
});
