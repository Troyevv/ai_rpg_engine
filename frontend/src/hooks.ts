import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { active, type Job } from "./types";
export function useJob(initial: Job | null | undefined, completed: () => void) {
  const [job, setJob] = useState(initial ?? null);
  const [reconnecting, setReconnecting] = useState(false);
  const callback = useRef(completed);
  callback.current = completed;
  useEffect(() => {
    setJob(initial ?? null);
  }, [initial]);
  const id = initial?.id;
  const running = active(initial);
  useEffect(() => {
    if (!id || !running) return;
    const stream = new EventSource(`/api/jobs/${id}/events`);
    stream.onopen = () => setReconnecting(false);
    stream.onerror = () => setReconnecting(true);
    stream.addEventListener("snapshot", (event) => {
      const next = JSON.parse((event as MessageEvent).data) as Job;
      setJob(next);
      setReconnecting(false);
      if (!active(next)) {
        stream.close();
        callback.current();
        if (next.error) toast.error(next.error);
      }
    });
    return () => stream.close();
  }, [id, running]);
  return { job, reconnecting };
}
