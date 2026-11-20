import { useMemo, useRef, useState } from 'react';

type Buffer = { text: string; file: string; format: 'text' | 'json' };
const empty: Buffer = { text: '', file: '', format: 'text' };

// Imported source and an author's idea are independent forms. Keep a file that
// has already been read accessible after Back without restoring a File input.
export function useImportBuffer(workspace: string, author: boolean) {
  const key = 'workshop-import:' + JSON.stringify([workspace, author]);
  const cache = useRef(new Map<string, Buffer>());
  const [, render] = useState(0);
  const initial = useMemo(() => {
    try {
      const value = JSON.parse(sessionStorage.getItem(key) || 'null');
      if (
        value &&
        typeof value.text === 'string' &&
        typeof value.file === 'string' &&
        ['text', 'json'].includes(value.format)
      )
        return value as Buffer;
    } catch {
      /* Storage may be unavailable or contain a stale draft. */
    }
    return empty;
  }, [key]);
  function set(value: Buffer = empty) {
    cache.current.set(key, value);
    try {
      if (value.text || value.file)
        sessionStorage.setItem(key, JSON.stringify(value));
      else sessionStorage.removeItem(key);
    } catch {
      /* Keep large files in memory if the browser quota is exhausted. */
    }
    render((n) => n + 1);
  }
  return [cache.current.get(key) ?? initial, set] as const;
}
