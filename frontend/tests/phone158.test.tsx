import {expect,it} from 'vitest';
import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {conversationRows,PhoneMessages,messageStatus} from '../src/PhoneContent';
import type {PhoneEvent,PhoneState} from '../src/Phone';
const event=(id:string,time:number,extra:Partial<PhoneEvent>={}):PhoneEvent=>({id,channel:'TEXT_MESSAGE',conversation_id:id,world_time:time,time_label:'2026-10-05 09:00',status:'delivered',outgoing:false,unread:false,content:'Точный текст\nВторая строка',read_count:null,recipient_count:null,label:'Вера',subject:{id:'b',name:'Вера',silhouette:'neutral'},destination:'',...extra});
it('orders chats by canonical event order, counts unread, never invents previews',()=>{
 const events=[event('a',12),event('b',12,{unread:true,content:null}),event('b',13,{unread:true,content:null})];
 const state={conversations:[{id:'empty'},{id:'a'},{id:'b'}],events} as PhoneState;
 const rows=conversationRows(state);
 expect(rows.map(r=>r.conversation.id)).toEqual(['b','a','empty']);
 expect(rows[0].unread).toBe(2);expect(rows[0].event?.content).toBeNull();expect(rows[2].event).toBeUndefined();
 expect(messageStatus(event('a',1,{outgoing:true,status:'sent'}))).toBe('Отправлено');
 expect(messageStatus(event('a',1,{outgoing:true,read_count:1,recipient_count:2}))).toBe('Прочитано: 1 из 2');
});
it('renders full text, canonical day boundaries and group authors without exposing unread content',async()=>{
 const host=document.createElement('div');document.body.append(host);const root=createRoot(host);
 const long='Длинное сообщение\n'.repeat(400);
 try {
  await act(()=>root.render(<PhoneMessages events={[event('a',1,{content:long,sender:{id:'b',name:'Вера',silhouette:'neutral'}}),event('b',2,{outgoing:true,time_label:'2026-10-06 09:00'}),event('c',3,{content:null,unread:true,time_label:'2026-10-06 09:01'})]} group locked={false} read={()=>{}}/>));
  expect(host.querySelector('p')?.textContent).toBe(long);
  expect(host.querySelectorAll('.phone-day')).toHaveLength(2);
  expect(host.querySelectorAll('.outgoing')).toHaveLength(1);
  expect(host.querySelector('.phone-message-sender')?.textContent).toBe('Вера');
  expect(host.textContent).toContain('Непрочитанное сообщение');
 }finally{await act(()=>root.unmount());host.remove()}
});

it('retains an uncertain send ID across unrelated successful commands and legacy cache upgrades',async()=>{
 const {phoneOperation}=await import('../src/lib/phoneRequests');
 const key='phone-request:test';const command={action:'send',content:'Точный текст',character_id:'b'};
 sessionStorage.setItem(key,JSON.stringify({intent:JSON.stringify(command),command:{operation_id:'legacy-pending-id',...command}}));
 const read=phoneOperation(key,{action:'read',conversation_id:'another-chat'});read.complete();
 const retry=phoneOperation(key,command);expect(retry.payload.operation_id).toBe('legacy-pending-id');
 const other=phoneOperation(key,{action:'send',content:'Другое сообщение',character_id:'c'});other.complete();
 expect(phoneOperation(key,command).payload.operation_id).toBe(retry.payload.operation_id);
 retry.complete();expect(sessionStorage.getItem(key)).toBeNull();
 expect(phoneOperation(key,command).payload.operation_id).not.toBe('legacy-pending-id');
 sessionStorage.removeItem(key);
});

it.each([false,true])('preserves literal Unicode and punctuation in direct/group text (%s), including rerender',async(group)=>{
 const content='Да 🙂 / okay... 👩🏽‍💻 ❤️ — e\u0301\n\n'+'Русский + English; без шаблона!.. '.repeat(90);
 const rows=[event('unicode',1,{content}),event('plain',2,{content:'Понял. Обсудим позже.'})];
 const host=document.createElement('div');document.body.append(host);const root=createRoot(host);
 try {
  for(const events of [rows,JSON.parse(JSON.stringify(rows))]) {
   await act(()=>root.render(<PhoneMessages events={events} group={group} locked={false} read={()=>{}}/>));
   expect([...host.querySelectorAll('.phone-message p')].map(el=>el.textContent)).toEqual(rows.map(e=>e.content));
  }
 } finally {await act(()=>root.unmount());host.remove()}
});
