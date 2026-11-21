import {SkinStamp} from './ThemeProvider';
import {useLayoutEffect, type ReactNode} from 'react';
import {useMobile} from './mobile';
import {createPortal} from 'react-dom';
import {BatteryFull, ChevronDown, Signal, Wifi} from 'lucide-react';
import type {Save} from './types';

const openFrames=new Set<symbol>();

/** Both the phone directory and the live CallScene occupy this device surface. */
export function PhoneFrame({save, open, close, closeLabel, dialogLabel, children}: {
  save: Save; open: boolean; close: () => void; closeLabel: string; dialogLabel?:string; children: ReactNode;
}) {
  const mobile=useMobile();
  useLayoutEffect(()=>{
    if (!open||!mobile) return;
    const shell=document.querySelector<HTMLElement>('.narrative-shell');
    if (!shell) return;
    const token=Symbol();openFrames.add(token);shell.inert=true;
    return ()=>{openFrames.delete(token);shell.inert=openFrames.size>0};
  },[open,mobile]);
  const owner=save.state.characters.find(c=>c.id===save.state.phone?.actor_id);
  return createPortal(<>
    <div className={'phone-scrim'+(open?' is-open':'')} aria-hidden onClick={close}/>
    <div className={'phone-device'+(open?' is-open':'')} inert={!open} aria-hidden={!open} data-testid="phone-device"
      role={open?'dialog':undefined} aria-label={dialogLabel||'Игровой телефон'} aria-modal={open?mobile:undefined}
      onKeyDown={e=>{
        if(e.key==='Escape'&&dialogLabel){e.preventDefault();close();return}
        if(!mobile||e.key!=='Tab')return;
        const nodes=Array.from(e.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),textarea:not(:disabled),a[href],summary')).filter(el=>el.getClientRects().length);
        const first=nodes[0],last=nodes.at(-1),focused=document.activeElement;
        if(e.shiftKey&&(focused===first||!nodes.includes(focused as HTMLElement))){e.preventDefault();last?.focus()}
        else if(!e.shiftKey&&(focused===last||!nodes.includes(focused as HTMLElement))){e.preventDefault();first?.focus()}
      }}>
      <div className="phone-glass">
        <div className="ph-status" aria-hidden><span>{save.state.world_clock?.projection?.time}</span><i className="ph-island"/><span className="ph-status-icons"><Signal/><Wifi/><BatteryFull/></span></div>
        <div className="ph-topbar"><span className="ph-owner"><SkinStamp/><span>{owner?.name}</span></span><span className="ph-demo">В игре</span>
          <button className="ph-close" aria-label={closeLabel} onClick={close}><ChevronDown/></button>
        </div>
        {children}
        <div className="ph-home-bar" aria-hidden><span/></div>
      </div>
    </div>
  </>,document.getElementById('root')!);
}
