import {test,expect} from '@playwright/test';
import {initialWorkshopIdentity,workshopIdentityReducer as reduce} from '../src/workshopIdentity';

test('stale stored identity is atomically replaced after import',()=>{
 const stale=initialWorkshopIdentity<{id:string;revision:number}>('missing-workspace');
 const created={id:'created-workspace',revision:1};
 const opened=reduce(stale,{type:'select',id:created.id,draft:created,request:2});
 expect(opened.id).toBe(created.id);
 expect(opened.draft?.id).toBe(opened.id);
 expect(opened.loading).toBe(false);
});

test('late workspace GET and failure cannot overwrite an imported draft',()=>{
 let state=initialWorkshopIdentity<{id:string}>('old');
 state=reduce(state,{type:'load',id:'old',request:1});
 state=reduce(state,{type:'select',id:'new',draft:{id:'new'},request:2});
 expect(reduce(state,{type:'loaded',id:'old',draft:{id:'old'},request:1})).toBe(state);
 expect(reduce(state,{type:'failed',id:'old',request:1})).toBe(state);
 expect(reduce(state,{type:'update',id:'old',update:()=>({id:'old'})})).toBe(state);
});

test('author view keeps identity and rejects older player responses',()=>{
 let state=reduce(initialWorkshopIdentity<{id:string;author:boolean}>('world'),{
  type:'select',id:'world',draft:{id:'world',author:false},request:1});
 state=reduce(state,{type:'load',id:'world',request:2});
 state=reduce(state,{type:'load',id:'world',request:3});
 expect(state.draft?.id).toBe(state.id);
 state=reduce(state,{type:'loaded',id:'world',draft:{id:'world',author:true},request:3});
 expect(reduce(state,{type:'loaded',id:'world',draft:{id:'world',author:false},request:2})).toBe(state);
 expect(reduce(state,{type:'failed',id:'world',request:2})).toBe(state);
 expect(state.draft?.author).toBe(true);
});

test('returning to the same workspace still rejects previous selection responses',()=>{
 let state=initialWorkshopIdentity<{id:string}>('a');
 state=reduce(state,{type:'load',id:'a',request:1});
 state=reduce(state,{type:'select',id:'b',draft:null,request:2});
 state=reduce(state,{type:'select',id:'a',draft:null,request:3});
 expect(reduce(state,{type:'loaded',id:'a',draft:{id:'a'},request:1})).toBe(state);
});

test('new history clears the previous draft and invariant rejects mismatched IDs',()=>{
 const opened=reduce(initialWorkshopIdentity<{id:string}>(''),{type:'select',id:'world',draft:{id:'world'},request:1});
 const empty=reduce(opened,{type:'select',id:'',draft:null,request:2});
 expect(empty.id).toBe('');expect(empty.draft).toBeNull();
 expect(()=>reduce(empty,{type:'select',id:'new',draft:{id:'old'},request:3})).toThrow('identity mismatch');
 const loading=reduce(empty,{type:'select',id:'new',draft:null,request:3});
 expect(()=>reduce(loading,{type:'loaded',id:'new',draft:{id:'old'},request:3})).toThrow('identity mismatch');
});
