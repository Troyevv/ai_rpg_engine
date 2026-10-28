import {describe,it,expect} from 'vitest';
import {presentationEntries,surfaceEntries,physicalChoiceTurn} from '../src/presentationEntries';
import type {Save,Job,Turn} from '../src/types';
const turn=(id:number,surface:'physical'|'phone'|'call'):Turn=>({id,sequence:id,node_id:String(id),active_variant_id:String(id),memory_archived:false,user_text:'source',assistant_text:'text',choices:[],kind:surface==='phone'?'communication':'turn',presentation:{surface,actor_id:'a',call_id:surface==='call'?'call-a':null},variants:[{id:String(id),job_id:`j${id}`,ordinal:1,can_regenerate:true}]});
const save={id:1,revision:4,state:{camera:{}},turns:[turn(0,'physical'),turn(1,'phone'),turn(2,'call')]} as Save;
describe('physical choice source is independent of communication history',()=>{
 for(const status of ['generating','extracting','validating','saved','error','stopped'])it(`keeps the same source through ${status}`,()=>{
   const current={...save,job:{status}} as Save;
   expect(physicalChoiceTurn(current)?.id).toBe(0);
 });
 it('honors canonical invalidation and active variant identity',()=>{
   expect(physicalChoiceTurn({...save,physical_choice_source:null})).toBeUndefined();
   expect(physicalChoiceTurn({...save,physical_choice_source:{turn_id:0,variant_id:'old'}})).toBeUndefined();
   expect(physicalChoiceTurn({...save,physical_choice_source:{turn_id:0,variant_id:'0'}})?.id).toBe(0);
 });
 it('never revives old suggestions across a mixed physical event',()=>{
   const mixed={...turn(3,'call'),presentation:{surface:'call' as const,physical_text:'Дверь открылась.'}};
   expect(physicalChoiceTurn({...save,turns:[...save.turns,mixed]})).toBeUndefined();
   const next={...turn(4,'physical'),choices:[]};
   expect(physicalChoiceTurn({...save,turns:[...save.turns,mixed,next]})).toBe(next);
   expect(physicalChoiceTurn({...save,turns:save.turns.slice(0,1)})?.id).toBe(0);
 });
});
describe('one history projected into independent reading surfaces',()=>{
 for(const status of ['generating','extracting','validating','saved','error','stopped']){
  it(`never projects phone streaming/status into story: ${status}`,()=>{
   const job={id:'pending',kind:'communication',status,narrative:'receipt',revision:4,presentation:{surface:'phone',actor_id:'a'}} as Job;
   const entries=presentationEntries(save,job);
   expect(surfaceEntries(entries,'physical').map(e=>e.turn.id)).toEqual([0]);
   expect(surfaceEntries(entries,'phone','a')).toHaveLength(2);
   expect(surfaceEntries(entries,'phone','b')).toHaveLength(0);
  });
 }
 it('stable stream identity survives commit in the same call',()=>{
  const job={id:'j2',kind:'turn',status:'extracting',narrative:'text',revision:4,presentation:{surface:'call',actor_id:'a',call_id:'call-a'}} as Job;
  const before=surfaceEntries(presentationEntries({...save,turns:save.turns.slice(0,2)},job),'call','a','call-a');
  const after=surfaceEntries(presentationEntries(save,{...job,status:'saved'}),'call','a','call-a');
  expect(before[0].identity).toBe(after[0].identity);expect(after).toHaveLength(1);
  expect(surfaceEntries(presentationEntries(save,job),'call','b','call-a')).toHaveLength(0);
  expect(surfaceEntries(presentationEntries(save,job),'call','a','another-call')).toHaveLength(0);
 });
 it('mixed accepted physical event survives without telephone prose or duplicate command',()=>{
  const mixed=turn(3,'call');mixed.presentation!.physical_text='Кто-то вошёл.';
  const entries=presentationEntries({...save,turns:[mixed]},null);
  const main=surfaceEntries(entries,'physical');
  expect(main[0].turn.assistant_text).toBe('Кто-то вошёл.');expect(main[0].turn.user_text).toBe('');
  expect(surfaceEntries(entries,'call','a','call-a')[0].turn.assistant_text).toBe('text');
 });
 it('ambiguous legacy prose is never classified by words or locale',()=>{
  const legacy=turn(5,'physical');delete legacy.presentation;legacy.assistant_text='Обработка сообщения завершена.';
  expect(surfaceEntries(presentationEntries({...save,turns:[legacy]},null),'physical')).toHaveLength(1);
  legacy.kind='communication';expect(surfaceEntries(presentationEntries({...save,turns:[legacy]},null),'physical')).toHaveLength(0);
 });
});
