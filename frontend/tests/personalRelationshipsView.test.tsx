import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {it,expect,vi} from 'vitest';
import {CharacterView} from '../src/CharacterDossier';
import type {State,Character,SocialRelation} from '../src/types';
const card=(id:string,name:string):Character=>({id,name,is_player:id==='a',fields:{},dossier:{sex:'female',conditions:[],restrictions:[]}});
it('re-renders from canonical dossier projection: death, rename, loss of visibility, RU/EN',async()=>{
 const host=document.createElement('div');document.body.append(host);const root=createRoot(host);const onCharacter=vi.fn();
 const a=card('a','Анна'),b=card('b','Борис');
 const relation:SocialRelation={id:'r',source_id:'a',target_id:'b',kind:'spouse',status:'active',certainty:'known',outcome:''};
 let state:State={characters:[a,b],relationships:[],scene:'',sections:{},locations:[],story_notes:'',dossier_personal_relations:[relation],objective_relations:[],world:{version:4,characters:{},scenes:{},objective_relations:{secret:{...relation,target_id:'secret'}}}};
 const render=async()=>act(()=>root.render(<CharacterView state={state} card={a} onCharacter={onCharacter}/>));
 try{
  await render();expect(host.querySelector('.dossier-personal')?.textContent).toContain('Борис');
  await act(()=>host.querySelector<HTMLButtonElement>('[data-partner-id="b"]')!.click());expect(onCharacter).toHaveBeenCalledWith('b');
  state={...state,characters:[a,{...b,name:'Борис Новое имя'}]};await render();expect(host.textContent).not.toContain('secret');expect(host.textContent).toContain('Борис Новое имя');
  state={...state,dossier_personal_relations:[{...relation,status:'closed',outcome:'widowed'}]};await render();expect(host.textContent).toContain('Вдова');expect(host.querySelector('[data-partner-id]')).toBeNull();
  state={...state,genealogy:{nodes:[{id:'a',name:'Анна',life_status:'dead'}],edges:[],kinship:[],truncated:false}};await render();expect(host.textContent).not.toContain('Вдова');expect(host.textContent).toContain('Брак завершён');
  state={...state,dossier_personal_relations:[]};await render();expect(host.querySelector('.dossier-personal')?.textContent).toContain('Нет сведений');
  state={...state,dossier_personal_relations:[relation],characters:[a]};await render();expect(host.querySelector('[data-partner-id]')).toBeNull();
  document.documentElement.lang='en';await render();expect(host.querySelector('.dossier-personal')?.textContent).toBe('Personal relationshipsNo information');
 }finally{await act(()=>root.unmount());host.remove();document.documentElement.lang='ru'}
});
