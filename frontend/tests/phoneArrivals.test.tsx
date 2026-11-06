import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';
import {usePhoneArrivals} from '../src/lib/usePhoneArrivals';
import {PhoneMessages} from '../src/PhoneContent';
import type {PhoneEvent} from '../src/Phone';

const event=(id:string,extra:Partial<PhoneEvent>={}):PhoneEvent=>({id,channel:'TEXT_MESSAGE',conversation_id:'g',world_time:12,time_label:'2026-10-05 09:00',status:'delivered',outgoing:false,unread:false,content:`Точный текст ${id}`,read_count:null,recipient_count:null,label:'NPC',subject:{id:'b',name:'NPC',silhouette:'neutral'},destination:'',...extra});
let host:HTMLDivElement,root:Root,reduced=false,changed:()=>void;
function Chat({rows,view='g',owner='a'}:{rows:PhoneEvent[];view?:string;owner?:string}) {
 const arrivals=usePhoneArrivals(rows,owner,view,view||'g');
 return <PhoneMessages events={rows.filter(e=>!arrivals.hidden.has(e.id))} animated={arrivals.animated} group locked={false} read={()=>{}}/>;
}
const ids=()=>[...host.querySelectorAll('[data-event-id]')].map(e=>e.getAttribute('data-event-id'));
const render=async(rows:PhoneEvent[],view='g',owner='a')=>act(()=>root.render(<Chat rows={rows} view={view} owner={owner}/>));
const advance=async(ms:number)=>act(()=>vi.advanceTimersByTime(ms));
beforeEach(()=>{
 vi.useFakeTimers();reduced=false;
 vi.stubGlobal('matchMedia',()=>({get matches(){return reduced},addEventListener:(_:string,cb:()=>void)=>{changed=cb},removeEventListener:()=>{}}));
 host=document.createElement('div');document.body.append(host);root=createRoot(host);
});
afterEach(async()=>{await act(()=>root.unmount());host.remove();vi.useRealTimers();vi.unstubAllGlobals()});
it('reveals only fresh incoming IDs sequentially, preserving full canonical content and time',async()=>{
 const old=event('old');await render([old]);
 const rows=[old,event('1'),event('2',{content:'Длинный текст\n'.repeat(300)}),event('3')];
 const original=JSON.stringify(rows);await render(rows);
 expect(ids()).toEqual(['old']);await advance(180);expect(ids()).toEqual(['old','1']);
 await advance(420);expect(ids()).toEqual(['old','1','2']);
 expect(host.querySelector('[data-event-id="2"] p')?.textContent).toBe(rows[2].content);
 await advance(420);expect(ids()).toEqual(['old','1','2','3']);expect(JSON.stringify(rows)).toBe(original);
 await render(structuredClone(rows));expect(ids()).toEqual(['old','1','2','3']);expect(vi.getTimerCount()).toBe(0);
});
it.each(['','another'])('flushes on close/chat switch %s; return and reload never replay history',async(view)=>{
 await render([]);const rows=[event('1'),event('2'),event('3')];await render(rows);await advance(180);
 await render(rows,view);expect(ids()).toEqual(['1','2','3']);expect(vi.getTimerCount()).toBe(0);
 await render(rows);expect(ids()).toEqual(['1','2','3']);expect(host.querySelector('.phone-message-arrival')).toBeNull();
 await act(()=>root.unmount());root=createRoot(host);await render(rows);expect(ids()).toEqual(['1','2','3']);
});
it('never replays a known ID after Retry, rollback/reappearance or reading a known unread message',async()=>{
 const unread=event('old',{unread:true,content:null});await render([unread]);
 await render([event('old')]);expect(ids()).toEqual(['old']);expect(vi.getTimerCount()).toBe(0);
 await render([event('old'),event('new')]);await advance(1000);await render([]);
 await render([event('old'),event('new')]);expect(ids()).toEqual(['old','new']);expect(host.querySelector('.phone-message-arrival')).toBeNull();
});
it('shows reduced-motion history immediately and flushes an active animation when preference changes',async()=>{
 await render([]);await render([event('1'),event('2')]);expect(ids()).toEqual([]);
 await act(()=>{reduced=true;changed()});expect(ids()).toEqual(['1','2']);expect(vi.getTimerCount()).toBe(0);
 await render([event('1'),event('2'),event('3')]);expect(ids()).toEqual(['1','2','3']);
});
it('does not animate outgoing messages or arrivals outside the open group; bounds large series',async()=>{
 await render([],'');const first=[event('1')];await render(first,'');await render(first);expect(ids()).toEqual(['1']);
 await render([...first,event('sent',{outgoing:true})]);expect(ids()).toEqual(['1','sent']);
 const many=[...first,event('sent',{outgoing:true}),...Array.from({length:30},(_,i)=>event(`n${i}`))];
 await render(many);for(let i=0;i<26;i++)await advance(100);expect(ids()).toHaveLength(many.length);expect(vi.getTimerCount()).toBe(0);
});
it('flushes on backgrounding, cancels timers on unmount and isolates owners',async()=>{
 await render([]);const rows=[event('1'),event('2')];await render(rows);
 await act(()=>{Object.defineProperty(document,'visibilityState',{value:'hidden',configurable:true});document.dispatchEvent(new Event('visibilitychange'))});
 expect(ids()).toEqual(['1','2']);expect(vi.getTimerCount()).toBe(0);
 await act(()=>{Object.defineProperty(document,'visibilityState',{value:'visible',configurable:true});document.dispatchEvent(new Event('visibilitychange'))});
 await render(rows,'g','other-owner');expect(host.querySelector('.phone-message-arrival')).toBeNull();
 await render([...rows,event('3')],'g','other-owner');expect(vi.getTimerCount()).toBe(1);
 await act(()=>root.unmount());root=createRoot(host);expect(vi.getTimerCount()).toBe(0);
});
