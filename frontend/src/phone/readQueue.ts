import { useRef, useState } from 'react';
import { api } from '../api';
import { phoneOperation } from '../lib/phoneRequests';
import type { Save } from '../types';

// Only pending perceptions survive an interrupted request. Knowledge belongs to the server.
export function useReadQueue(scope: string, save: Save, actor: string) {
  const key = 'phone-pending-perception:' + scope;
  const [queue, setQueue] = useState<Record<string, string[]>>(() => {
    try {
      return JSON.parse(sessionStorage.getItem(key) || '{}');
    } catch {
      return {};
    }
  });
  const current = useRef(queue);
  const observed = useRef(new Set<string>());
  const update = (next: Record<string, string[]>) => {
    current.current = next;
    if (Object.keys(next).length) sessionStorage.setItem(key, JSON.stringify(next));
    else sessionStorage.removeItem(key);
    setQueue(next);
  };
  const observe = (app: string, ids: string[]) => {
    const fresh = ids.filter((id) => !observed.current.has(id));
    if (!fresh.length) return;
    fresh.forEach((id) => observed.current.add(id));
    update({ ...current.current, [app]: [...new Set([...(current.current[app] || []), ...fresh])] });
  };
  const flush = async (onSave: (s: Save) => void) => {
    let revision = save.revision;
    for (const app of Object.keys(current.current)) {
      while (current.current[app]?.length) {
        const ids = current.current[app].slice(0, 80);
        const operation = phoneOperation(key + ':receipt', { app, action: 'read', actor_id: actor, ids });
        const next = await api<Save>(`/saves/${save.id}/apps/command`, {
          revision,
          command: operation.payload,
        });
        revision = next.revision;
        operation.complete();
        const rest = { ...current.current, [app]: current.current[app].filter((id) => !ids.includes(id)) };
        if (!rest[app].length) delete rest[app];
        update(rest);
        onSave(next);
      }
    }
    return revision;
  };
  return { queue, observe, flush };
}
