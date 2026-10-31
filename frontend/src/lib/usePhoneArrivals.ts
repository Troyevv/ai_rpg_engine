import {useEffect, useState, useSyncExternalStore} from 'react';
import type {PhoneEvent} from '../Phone';

const motionQuery = '(prefers-reduced-motion: reduce)';
const subscribeMotion = (notify:()=>void) => {
  const media = window.matchMedia?.(motionQuery);
  media?.addEventListener('change', notify);
  return () => media?.removeEventListener('change', notify);
};
const subscribeVisibility = (notify:()=>void) => {
  document.addEventListener('visibilitychange', notify);
  return () => document.removeEventListener('visibilitychange', notify);
};
const no = () => false;
const reducedMotion = () => !!window.matchMedia?.(motionQuery).matches;
const hiddenDocument = () => document.visibilityState === 'hidden';
const emptyEvents: PhoneEvent[] = [];

// Presentation metadata only. Content, ordering, time and read state always
// come from the current authorized projection. No messages are copied/queued.
export function usePhoneArrivals(events: PhoneEvent[] | undefined, owner: string, view: string, conversation: string | null) {
  const reduced = useSyncExternalStore(subscribeMotion, reducedMotion, no);
  const background = useSyncExternalStore(subscribeVisibility, hiddenDocument, no);
  const rows = events || emptyEvents;
  const activeView = reduced || background ? '' : view;
  const [state, setState] = useState(() => ({
    rows, owner, view: activeView, seen: new Set(rows.map(e=>e.id)),
    pending: new Map<string,number>(), arrivals: new Set<string>(),
  }));
  // Adjust metadata before children commit: a fresh canonical batch must never
  // flash in full for a frame before its presentation delays are installed.
  if (state.rows !== rows || state.owner !== owner || state.view !== activeView) {
    const ids = new Set(rows.map(e=>e.id));
    const added = rows.filter(e=>!state.seen.has(e.id) && e.conversation_id===conversation && e.channel==='TEXT_MESSAGE');
    const reset = state.owner !== owner || state.view !== activeView || !activeView || added.some(e=>e.outgoing);
    const pending = reset ? new Map<string,number>() : new Map([...state.pending].filter(([id])=>ids.has(id)));
    const arrivals = reset ? new Set<string>() : new Set([...state.arrivals].filter(id=>ids.has(id)));
    if (!reset) {
      const incoming = added.filter(e=>!e.outgoing);
      const now = Date.now(), step = Math.min(420, 2400 / Math.max(1,incoming.length));
      const start = Math.max(now + 180, ...[...pending.values()].map(time=>time + step));
      incoming.forEach((event,index)=>{
        pending.set(event.id, Math.min(start + index * step, now + 2600));
        arrivals.add(event.id);
      });
    }
    setState({rows, owner, view:activeView, seen:new Set([...(state.owner===owner?state.seen:[]), ...ids]), pending, arrivals});
  }
  useEffect(()=>{
    if (!state.pending.size) return;
    const next = Math.min(...state.pending.values());
    const timer = window.setTimeout(()=>setState(current=>({
      ...current, pending:new Map([...current.pending].filter(([,at])=>at>Date.now())),
    })), Math.max(0,next-Date.now()));
    return ()=>window.clearTimeout(timer);
  },[state.pending]);
  return {hidden:state.pending, animated:state.arrivals};
}
