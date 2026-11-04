import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {act} from 'react';
import {createRoot,type Root} from 'react-dom/client';
import {StoryNotifications} from '../src/StoryNotifications';
import {StorySecrets} from '../src/StorySecrets';
import {presentationKey,wasPresented,markPresented,observeStorySnapshot,pendingStoryNotices} from '../src/lib/storyPresentation';
import type {Save,StoryNotice,StorySecret} from '../src/types';
const fog=vi.hoisted(()=>({painters:new Set<(time:number)=>void>()}));
vi.mock('../src/lib/fogRenderer',()=>({paintFog:vi.fn(),animateFog:vi.fn((paint:(time:number)=>void)=>{fog.painters.add(paint);return()=>fog.painters.delete(paint)})}));
let host:HTMLDivElement,root:Root,sid=100;
const event=(id:string):StoryNotice=>({id,kind:'secret_revealed',text:`Тайна ${id}`,turn_id:1,slot_id:'slot-'+id,character_ids:['b']});
const save=(revision:number,events:StoryNotice[]=[],actor='a')=>({id:sid,revision,state:{controlled_actor_id:actor,notification_history:events}} as Save);
const render=async(s:Save,onOpen=vi.fn())=>act(()=>root.render(<StoryNotifications save={s} enabled onOpen={onOpen}/>));
beforeEach(()=>{
 sid++;localStorage.clear();fog.painters.clear();vi.useFakeTimers();
 vi.stubGlobal('ResizeObserver',class{observe(){}disconnect(){}});
 vi.stubGlobal('IntersectionObserver',class{constructor(private cb:(entries:unknown[])=>void){}observe(){this.cb([{isIntersecting:true}])}disconnect(){}});
 host=document.createElement('div');document.body.append(host);root=createRoot(host);
});
afterEach(async()=>{await act(()=>root.unmount());host.remove();vi.useRealTimers();vi.unstubAllGlobals();vi.restoreAllMocks()});
it('queues only committed additions; rollback removes stale payload; actor changes establish a fresh baseline',async()=>{
 await render(save(0,[event('initial')]));expect(host.querySelector('.story-toast')).toBeNull();
 await render(save(1,[event('initial'),event('a'),event('b')]));
 expect(host.querySelector('.story-toast')?.textContent).toContain('Тайна a');
 await act(()=>vi.advanceTimersByTime(6600));expect(host.querySelector('.story-toast')?.textContent).toContain('Тайна b');
 await render(save(2,[event('initial')]));expect(host.querySelector('.story-toast')).toBeNull();
 await render(save(3,[event('b')],'other'));expect(host.querySelector('.story-toast')).toBeNull();
});
it('reload shows history without replay; navigation uses the exact entity payload',async()=>{
 const open=vi.fn();await render(save(0));await render(save(1,[event('new')]),open);
 await act(()=>host.querySelector<HTMLButtonElement>('.story-toast-body button')!.click());
 expect(open).toHaveBeenCalledWith(event('new'));
 await act(()=>root.unmount());root=createRoot(host);await render(save(1,[event('new')]));
 expect(host.querySelector('.story-toast')).toBeNull();expect(host.querySelector('.story-journal-trigger')?.textContent).toContain('1');
});
it('phone postpones notification presentation and preserves the queued item',async()=>{
 const phone=document.createElement('div');phone.className='phone-device is-open';document.body.append(phone);
 await render(save(0));await render(save(1,[event('phone')]));
 expect(host.querySelector('.story-toast')).toBeNull();
 expect(wasPresented(presentationKey(sid,'a','phone','toast'))).toBe(false);
 await act(()=>phone.remove());expect(host.querySelector('.story-toast')?.textContent).toContain('Тайна phone');
});
it('unknown rows contain no hidden payload; initial knowledge has no reveal and completed branch events do not replay',async()=>{
 const rows:StorySecret[]=[{id:'closed',status:'hidden'},{id:'initial',status:'known',text:'Известно со старта'},{id:'new',status:'known',text:'Открытие',reveal_id:'event'}];
 await act(()=>root.render(<StorySecrets rows={rows} save={save(1)}/>));
 expect(host.querySelector('[data-secret-id="closed"]')?.textContent).toBe('Скрытая тайна');
 expect(host.querySelector('[data-secret-id="initial"] canvas')).toBeNull();
 expect(host.querySelector('[data-secret-id="new"]')?.className).toContain('is-revealing');
 markPresented(presentationKey(sid,'a','event','fog'));
 await act(()=>root.render(<StorySecrets rows={[...rows]} save={save(2)}/>));
 expect(host.querySelector('[data-secret-id="new"] canvas')).toBeNull();
 // Another accepted variant of the same canonical slot owns a different reveal.
 await act(()=>root.render(<StorySecrets rows={[{...rows[2],reveal_id:'sibling'}]} save={save(3)}/>));
 expect(host.querySelector('[data-secret-id="new"]')?.className).toContain('is-revealing');
});
it('storage denial preserves presentation acknowledgements in the current session',()=>{
 vi.spyOn(Storage.prototype,'getItem').mockImplementation(()=>{throw new Error('denied')});
 vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('quota')});
 const key=presentationKey(38,'actor','storage-denial-event','fog');
 expect(wasPresented(key)).toBe(false);markPresented(key);expect(wasPresented(key)).toBe(true);
 vi.restoreAllMocks();
});
it('does not lose a committed addition across unmount and remount',async()=>{
 await render(save(0));
 await act(()=>root.unmount());root=createRoot(host);
 await render(save(1,[event('remount-unread')]));
 expect(host.querySelector('.story-toast')?.textContent).toContain('Тайна remount-unread');
});
it('does not acknowledge a popup before a full visible reading interval',async()=>{
 await render(save(0));await render(save(1,[event('interrupted-unread')]));
 expect(host.querySelector('.story-toast')).not.toBeNull();
 expect(wasPresented(presentationKey(sid,'a','interrupted-unread','toast'))).toBe(false);
});
it('does not consume notifications inside an inert workspace',async()=>{
 host.setAttribute('inert','');await render(save(0));await render(save(1,[event('inactive-unread')]));
 await act(()=>vi.advanceTimersByTime(7000));
 expect(wasPresented(presentationKey(sid,'a','inactive-unread','toast'))).toBe(false);
 host.removeAttribute('inert');
});
it('snapshot admission preserves new delivery before the first component mount without replaying legacy history',async()=>{
 observeStorySnapshot(save(0,[event('historic')]));
 observeStorySnapshot(save(1,[event('historic'),event('late-mount')]));
 await render(save(1,[event('historic'),event('late-mount')]));
 expect(host.querySelector('.story-toast')?.textContent).toContain('Тайна late-mount');
 expect(host.querySelector('.story-toast')?.textContent).not.toContain('Тайна historic');
 expect(JSON.stringify(localStorage)).not.toContain('Тайна');
});
it('unread delivery survives interruption and only a completed presentation settles it across remount',async()=>{
 const after=save(1,[event('read-interval')]),key=presentationKey(sid,'a','read-interval','toast');
 await render(save(0));await render(after);await act(()=>vi.advanceTimersByTime(2000));
 await act(()=>root.unmount());root=createRoot(host);await render(after);
 expect(host.querySelector('.story-toast')).not.toBeNull();expect(wasPresented(key)).toBe(false);
 await act(()=>vi.advanceTimersByTime(6400));expect(wasPresented(key)).toBe(false);
 await act(()=>vi.advanceTimersByTime(100));expect(wasPresented(key)).toBe(true);
 await act(()=>root.unmount());root=createRoot(host);await render(after);
 expect(host.querySelector('.story-toast')).toBeNull();expect(pendingStoryNotices(after)).toEqual([]);
});
it('disabled, inactive and hidden page suspend pending delivery without consuming it',async()=>{
 const after=save(1,[event('suspended')]),key=presentationKey(sid,'a','suspended','toast');
 await render(save(0));
 await act(()=>root.render(<StoryNotifications save={after} enabled={false} onOpen={vi.fn()}/>));
 await act(()=>vi.advanceTimersByTime(8000));expect(wasPresented(key)).toBe(false);
 await act(()=>root.render(<StoryNotifications save={after} enabled active={false} onOpen={vi.fn()}/>));
 await act(()=>vi.advanceTimersByTime(8000));expect(host.querySelector('.story-toast')).toBeNull();
 await render(after);expect(host.querySelector('.story-toast')).not.toBeNull();
 const hidden=vi.spyOn(document,'hidden','get').mockReturnValue(true);
 await act(()=>document.dispatchEvent(new Event('visibilitychange')));
 await act(()=>vi.advanceTimersByTime(8000));expect(wasPresented(key)).toBe(false);
 hidden.mockReturnValue(false);await act(()=>document.dispatchEvent(new Event('visibilitychange')));
 await act(()=>vi.advanceTimersByTime(6500));expect(wasPresented(key)).toBe(true);
});
it('parks unread variant and actor deliveries while rendering only current server membership',async()=>{
 const first=event('branch-first'),sibling=event('branch-sibling');
 await render(save(0));await render(save(1,[first]));
 await render(save(2));expect(host.querySelector('.story-toast')).toBeNull();
 await render(save(3,[sibling]));expect(host.querySelector('.story-toast')?.textContent).toContain('branch-sibling');
 await act(()=>host.querySelector<HTMLButtonElement>('.story-toast-close')!.click());
 await render(save(4,[first]));expect(host.querySelector('.story-toast')?.textContent).toContain('branch-first');
 await render(save(5,[],'other'));expect(host.querySelector('.story-toast')).toBeNull();
 await render(save(6,[event('other-actor')],'other'));expect(host.querySelector('.story-toast')?.textContent).toContain('other-actor');
 await render(save(7,[first]));expect(host.querySelector('.story-toast')?.textContent).toContain('branch-first');
 await act(()=>host.querySelector<HTMLButtonElement>('.story-toast-close')!.click());
 await render(save(8,[sibling]));expect(host.querySelector('.story-toast')).toBeNull();
 await render(save(9,[first]));expect(host.querySelector('.story-toast')).toBeNull();
});
it('interrupted fog remains unacknowledged; completion persists and new branches/actors have independent receipts',async()=>{
 const row:StorySecret={id:'slot',status:'known',text:'Подтверждённый текст',reveal_id:'fog-first'};
 const show=async(rows:StorySecret[],actor='a',active=true)=>act(()=>root.render(<StorySecrets rows={rows} save={save(1,[],actor)} active={active}/>));
 const paint=async(from:number,to:number)=>act(()=>{for(let t=from;t<=to;t+=50)for(const f of [...fog.painters])f(t)});
 const key=presentationKey(sid,'a','fog-first','fog');
 await show([row]);await paint(50,750);expect(wasPresented(key)).toBe(false);
 await show([row],'a',false);expect(fog.painters.size).toBe(0);expect(wasPresented(key)).toBe(false);
 await act(()=>root.unmount());root=createRoot(host);await show([row]);
 expect(host.querySelector('.is-revealing')).not.toBeNull();await paint(1000,3300);expect(wasPresented(key)).toBe(true);
 await act(()=>root.unmount());root=createRoot(host);await show([row]);expect(host.querySelector('.is-revealing')).toBeNull();
 await show([{id:'slot',status:'hidden'}]);expect(host.textContent).not.toContain(row.text);expect(host.querySelector('.is-hidden')).not.toBeNull();
 await show([{...row,reveal_id:'fog-sibling'}]);expect(host.querySelector('.is-revealing')).not.toBeNull();
 await show([row],'other');expect(host.querySelector('.is-revealing')).not.toBeNull();
 await show([row]);expect(host.querySelector('.is-revealing')).toBeNull();
});
it('storage denial keeps delivery pending across component remount within this session',async()=>{
 vi.spyOn(Storage.prototype,'getItem').mockImplementation(()=>{throw new Error('denied')});
 vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('quota')});
 const after=save(1,[event('delivery-no-storage')]);
 observeStorySnapshot(save(0));observeStorySnapshot(after);
 await render(after);await act(()=>root.unmount());root=createRoot(host);await render(after);
 expect(host.querySelector('.story-toast')?.textContent).toContain('delivery-no-storage');
 await act(()=>host.querySelector<HTMLButtonElement>('.story-toast-close')!.click());
 await act(()=>root.unmount());root=createRoot(host);await render(after);
 expect(host.querySelector('.story-toast')).toBeNull();
});
it('a quota failure cannot replace a newer in-memory delivery with stale readable storage',async()=>{
 observeStorySnapshot(save(0));
 vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('quota')});
 const after=save(1,[event('quota-after-baseline')]);observeStorySnapshot(after);await render(after);
 expect(host.querySelector('.story-toast')?.textContent).toContain('quota-after-baseline');
 await act(()=>host.querySelector<HTMLButtonElement>('.story-toast-close')!.click());
 await act(()=>root.unmount());root=createRoot(host);await render(after);expect(host.querySelector('.story-toast')).toBeNull();
});
