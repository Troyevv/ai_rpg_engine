import {test,expect} from '@playwright/test';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {buildSync} from 'esbuild';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
// Playwright's JSX transform is for locators; compile the actual React module
// with the same automatic JSX runtime as Vite before server rendering it.
const compiled=buildSync({entryPoints:[fileURLToPath(new URL('../src/runtimePresentation.tsx',import.meta.url))],bundle:true,write:false,platform:'node',format:'cjs',jsx:'automatic',external:['react','react/jsx-runtime']});
const loaded={exports:{}};
new Function('require','module','exports',compiled.outputFiles[0].text)(createRequire(import.meta.url),loaded,loaded.exports);
const {RuntimeValue,resolver,recordTitle}=loaded.exports as typeof import('../src/runtimePresentation');
const resolve=resolver({characters:[{id:'a',name:'Анна'},{id:'b',name:'Борис'}],locations:[{id:'l',name:'Дом'}],world:{organizations:{company:{name:'Компания'}}}});
const render=(field:string,value:unknown)=>renderToStaticMarkup(createElement(RuntimeValue,{field,value,resolve,author:false}));

test('typed formatter preserves unknown false zero and nested data',()=>{
 expect(render('capabilities',{can_move:false,can_speak:null,conscious:true})).toContain('Может передвигаться');
 expect(render('capabilities',{can_move:false})).toContain('Нет');
 expect(render('capabilities',{can_move:null})).toContain('Неизвестно');
 expect(render('minute',0)).toContain('>0<');
 expect(render('items',[{description:'Свойство',effects:{can_act:false},status:'active'}])).not.toContain('[object Object]');
 expect(render('evidence',{'opaque-evidence-id':{meaning:'Полученный опыт',kind:'experience'}})).not.toContain('opaque-evidence-id');
 expect(render('evidence',{'opaque-evidence-id':{meaning:'Полученный опыт',kind:'experience'}})).toContain('Полученный опыт');
 expect(render('items',[])).toContain('Нет записей');
 expect(render('life_status','dead')).toContain('Умер');
 expect(render('developmental_stage','adult')).toContain('Взрослый');
 expect(render('field','habits')).toContain('Привычки');
 expect(render('actor_id','missing')).toContain('ссылка не найдена');
 expect(render('organization_id','company')).toContain('Компания');
});

test('reference titles respect direction and concealed contact identity',()=>{
 expect(recordTitle('objective_relations',{source_id:'a',target_id:'b',kind:'adoptive_parent'},resolve)).toBe('Анна → Борис · Приёмный родитель');
 expect(recordTitle('objective_relations',{source_id:'a',target_id:'b',kind:'sibling'},resolve)).toContain('↔');
 const contact={owner_id:'a',character_id:'b',label:'Друг',identity_visible:false};
 expect(recordTitle('contacts',contact,resolve,false)).toBe('Анна · Друг');
 expect(recordTitle('contacts',contact,resolve,true)).toBe('Анна · Друг · Борис');
 expect(recordTitle('residences',{actor_id:'a',location_id:'l'},resolve)).toBe('Анна → Дом');
 expect(render('record',{revision:2,provenance:'private',text:'Доступно'})).not.toContain('private');
});

test('all populated synthetic sections render without object coercion or mutation',async()=>{
 const {readFileSync}=await import('node:fs');
 for(const file of ['runtime_presentation.json','runtime_family.json']){
  const state=JSON.parse(readFileSync(new URL('../../tests/fixtures/initial_world/'+file,import.meta.url),'utf8'));const before=JSON.stringify(state);const lookup=resolver(state);
  for(const [section,value] of Object.entries(state.world)){
   const html=renderToStaticMarkup(createElement(RuntimeValue,{field:section,value,resolve:lookup,author:true}));
   expect(html).not.toContain('[object Object]');
  }
  expect(JSON.stringify(state)).toBe(before);
 }
});
