import {describe,it,expect,afterEach} from 'vitest';
import {personalRelationships as select} from '../src/lib/personalRelationships';
import {personalRelationshipLabel as label,dossierText} from '../src/lib/dossier';
import type {SocialRelation} from '../src/types';
const cards=[{id:'a',name:'Александр'},{id:'b',name:'Вера'},{id:'c',name:'Ася'}];
const relation=(overrides:Partial<SocialRelation>={}):SocialRelation=>({id:'r',kind:'partner',source_id:'a',target_id:'b',status:'active',certainty:'known',outcome:'',...overrides});
afterEach(()=>{document.documentElement.lang='ru'});
describe('authorized personal relationship presentation',()=>{
 it('T01/T08: absence and suspicion do not establish single status',()=>{
  expect(select('a',undefined,cards)).toEqual([]);
  expect(select('a',[relation({certainty:'suspected'})],cards)).toEqual([]);
  expect(select('a',[relation({kind:'friend'})],cards)).toEqual([]);
  expect(dossierText('noPersonal')).toBe('Нет сведений');
 });
 it.each(['partner','engaged','spouse'])('T02–T04: %s accepts either endpoint',kind=>{
  const r=relation({kind});
  expect(select('a',[r],cards)).toEqual([{kind,partnerId:'b'}]);
  expect(select('b',[r],cards)).toEqual([{kind,partnerId:'a'}]);
 });
 it('T05–T07: closed partners are not divorces, active phases suppress history',()=>{
  expect(select('a',[relation({status:'closed',outcome:'ended'})],cards)).toEqual([]);
  for(const outcome of ['divorced','widowed']){
   const closed=relation({kind:'spouse',status:'closed',outcome,until:12});
   expect(select('a',[closed],cards)).toEqual([{kind:outcome}]);
   expect(select('a',[closed,relation({id:'new',target_id:'c'})],cards)).toEqual([{kind:'partner',partnerId:'c'}]);
  }
  expect(select('a',[relation({kind:'spouse',status:'closed',outcome:'superseded'})],cards)).toEqual([]);
 });
 it('T07: keeps all partners, deduplicates symmetric and overlapping phases deterministically',()=>{
  const rows=[relation(),relation({id:'engage',kind:'engaged'}),relation({id:'marry',kind:'spouse'}),relation({id:'inverse',kind:'spouse',source_id:'b',target_id:'a'}),relation({id:'second',target_id:'c'})];
  const expected=[{kind:'spouse',partnerId:'b'},{kind:'partner',partnerId:'c'}];
  expect(select('a',rows,cards)).toEqual(expected);expect(select('a',[...rows].reverse(),cards)).toEqual(expected);
  expect(rows[0].kind).toBe('partner');
 });
 it('T08/T10: no unavailable names/IDs, no guesses about unprojected closure',()=>{
  expect(select('a',[relation({target_id:'secret'})],cards)).toEqual([]);
  expect(select('a',[relation({target_id:'a'})],cards)).toEqual([]);
  expect(select('a',[relation({source_id:'c',target_id:'b'})],cards)).toEqual([]);
  expect(select('a',[relation({kind:'spouse'})],cards)).toEqual([{kind:'spouse',partnerId:'b'}]);
  expect(select('a',[relation({kind:'spouse',status:'closed',outcome:'divorced'}),relation({id:'unavailable',target_id:'secret'})],cards)).toEqual([]);
 });
 it('T05/T12: only the latest known closure is displayed, independent of input order',()=>{
  const rows=[relation({id:'old',kind:'spouse',status:'closed',outcome:'widowed',until:10}),relation({id:'new',kind:'spouse',status:'closed',outcome:'divorced',until:20})];
  expect(select('a',rows,cards)).toEqual([{kind:'divorced'}]);
  expect(select('a',rows.reverse(),cards)).toEqual([{kind:'divorced'}]);
 });
 it('ambiguous closure chronology does not invent a latest marital status',()=>{
  const rows=[relation({kind:'spouse',status:'closed',outcome:'widowed'}),relation({id:'other',kind:'spouse',status:'closed',outcome:'divorced'})];
  expect(select('a',rows,cards)).toEqual([]);
  expect(select('a',rows.map(r=>({...r,until:12})),cards)).toEqual([]);
 });
 it('T02–T06: RU/EN and known/unknown sex use safe names without declension',()=>{
  expect(label('engaged','male')).toBe('Помолвлен с:');
  expect(label('engaged','female')).toBe('Помолвлена с:');
  expect(label('engaged','unknown')).toBe('Помолвка с:');
  expect(label('spouse','female')).toBe('В браке с:');
  expect(label('divorced','female')).toBe('Разведена');
  expect(label('widowed','male')).toBe('Вдовец');
  expect(label('widowed','female')).toBe('Вдова');
  expect(label('divorced')).toBe('В разводе');
  document.documentElement.lang='en';
  expect(['partner','engaged','spouse','divorced','widowed'].map(kind=>label(kind as Parameters<typeof label>[0]))).toEqual(['Dating:','Engaged to:','Married to:','Divorced','Widowed']);
 });
});
