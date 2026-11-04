import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {act} from 'react';
import {createRoot,type Root} from 'react-dom/client';
import {StoryNotifications} from '../src/StoryNotifications';
import {StorySecrets} from '../src/StorySecrets';
import {presentationKey,wasPresented,markPresented} from '../src/lib/storyPresentation';
import type {Save,StoryNotice,StorySecret} from '../src/types';
vi.mock('../src/lib/fogRenderer',()=>({paintFog:vi.fn(),animateFog:vi.fn(()=>()=>{})}));
let host:HTMLDivElement,root:Root;
const event=(id:string):StoryNotice=>({id,kind:'secret_revealed',text:`Тайна ${id}`,turn_id:1,slot_id:'slot-'+id,character_ids:['b']});
const save=(revision:number,events:StoryNotice[]=[],actor='a')=>({id:1,revision,state:{controlled_actor_id:actor,notification_history:events}} as Save);
const render=async(s:Save,onOpen=vi.fn())=>act(()=>root.render(<StoryNotifications save={s} enabled onOpen={onOpen}/>));
beforeEach(()=>{
 localStorage.clear();vi.useFakeTimers();
 vi.stubGlobal('ResizeObserver',class{observe(){}disconnect(){}});
 vi.stubGlobal('IntersectionObserver',class{constructor(private cb:(entries:unknown[])=>void){}observe(){this.cb([{isIntersecting:true}])}disconnect(){}});
 host=document.createElement('div');document.body.append(host);root=createRoot(host);
});
afterEach(async()=>{await act(()=>root.unmount());host.remove();vi.useRealTimers();vi.unstubAllGlobals()});
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
 expect(wasPresented(presentationKey(1,'a','phone','toast'))).toBe(false);
 await act(()=>phone.remove());expect(host.querySelector('.story-toast')?.textContent).toContain('Тайна phone');
});
it('unknown rows contain no hidden payload; initial knowledge has no reveal and completed branch events do not replay',async()=>{
 const rows:StorySecret[]=[{id:'closed',status:'hidden'},{id:'initial',status:'known',text:'Известно со старта'},{id:'new',status:'known',text:'Открытие',reveal_id:'event'}];
 await act(()=>root.render(<StorySecrets rows={rows} save={save(1)}/>));
 expect(host.querySelector('[data-secret-id="closed"]')?.textContent).toBe('Скрытая тайна');
 expect(host.querySelector('[data-secret-id="initial"] canvas')).toBeNull();
 expect(host.querySelector('[data-secret-id="new"]')?.className).toContain('is-revealing');
 markPresented(presentationKey(1,'a','event','fog'));
 await act(()=>root.render(<StorySecrets rows={[...rows]} save={save(2)}/>));
 expect(host.querySelector('[data-secret-id="new"] canvas')).toBeNull();
 // Another accepted variant of the same canonical slot owns a different reveal.
 await act(()=>root.render(<StorySecrets rows={[{...rows[2],reveal_id:'sibling'}]} save={save(3)}/>));
 expect(host.querySelector('[data-secret-id="new"]')?.className).toContain('is-revealing');
});
