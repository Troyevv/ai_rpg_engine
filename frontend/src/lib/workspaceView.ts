import { useEffect, useState, type Dispatch, type SetStateAction } from "react";

// App owns this UI-only cache for one save/controlled actor. Closed workspaces
// unmount (including their listeners and requests), without losing their view.
export type WorkspaceView = Map<string, unknown>;
export function useWorkspaceView<T>(cache: WorkspaceView | undefined, key: string, initial: T): [T, Dispatch<SetStateAction<T>>] {
  const [value, setValue] = useState<T>(() => cache?.has(key) ? cache.get(key) as T : initial);
  useEffect(() => { cache?.set(key, value); }, [cache, key, value]);
  return [value, setValue];
}
