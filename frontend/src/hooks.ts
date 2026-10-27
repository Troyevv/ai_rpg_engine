import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { active, type Job } from "./types";
// A delayed refresh/reconnect must not roll an observed snapshot backwards.
function latestSnapshot(previous:Job|null,incoming:Job|null):Job|null {
  if(!previous||!incoming||previous.id!==incoming.id)return incoming;
  const oldEpoch=previous.attempt_epoch??0,newEpoch=incoming.attempt_epoch??0;
  if(oldEpoch!==newEpoch)return newEpoch>oldEpoch?incoming:previous;
  const rank:Record<string,number>={generating:0,extracting:1,validating:2,error:3,stopped:3,saved:4};
  if((rank[incoming.status]??0)<(rank[previous.status]??0))return previous;
  if(previous.narrative.length>incoming.narrative.length&&previous.narrative.startsWith(incoming.narrative))return {...incoming,narrative:previous.narrative};
  return incoming;
}
export function useJob(initial: Job | null | undefined, completed: () => void) {
  const [job, setJob] = useState(initial ?? null);
  const [reconnecting, setReconnecting] = useState(false);
  const callback = useRef(completed);
  callback.current = completed;
  useEffect(() => {
    setJob(previous=>latestSnapshot(previous,initial??null));
  }, [initial]);
  const id = initial?.id;
  const running = active(initial)||!!initial?.live&&initial.status!=="saved";
  useEffect(() => {
    setReconnecting(false);
    if (!id || !running) return;
    const stream = new EventSource(`/api/jobs/${id}/events`);
    stream.onopen = () => setReconnecting(false);
    stream.onerror = () => setReconnecting(true);
    stream.addEventListener("snapshot", (event) => {
      const next = JSON.parse((event as MessageEvent).data) as Job;
      setJob(previous=>latestSnapshot(previous,next));
      setReconnecting(false);
      if (!active(next)&&(next.status==="saved"||!next.live)) {
        stream.close();
        callback.current();
        if (next.error) toast.error(next.error);
      }
    });
    return () => stream.close();
  }, [id, running, initial?.attempt_epoch]);
  return { job, reconnecting };
}

/** Stable event identity lets memoized history ignore unrelated SSE snapshots. */
export function useStableEvent<T extends (...args: any[])=>any>(callback:T):T {
  const latest=useRef(callback);latest.current=callback;
  const stable=useRef(((...args:Parameters<T>)=>latest.current(...args)) as T);
  return stable.current;
}
