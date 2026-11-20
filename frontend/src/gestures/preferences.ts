import { useSyncExternalStore } from 'react';

export const defaults = {
  enabled: true,
  navigation: true,
  panels: true,
  context: true,
  images: true,
  hints: true,
  haptics: false,
  sensitivity: 'normal' as 'low' | 'normal' | 'high',
};
export type Controls = typeof defaults;
export type Group = 'navigation' | 'panels' | 'context' | 'images';
const key = 'interface.gestures.v1';
const progressKey = 'interface.gesture-learning.v1';
function read(key: string) {
  try {
    return JSON.parse(localStorage.getItem(key) || 'null');
  } catch {
    return null;
  }
}
function write(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* Private browsing keeps the current session usable. */
  }
}
export function normalize(value: unknown): Controls {
  const result = { ...defaults };
  if (value && typeof value === 'object') {
    for (const key of Object.keys(defaults) as (keyof Controls)[]) {
      const entry = (value as Record<string, unknown>)[key];
      if (key === 'sensitivity') {
        if (entry === 'low' || entry === 'normal' || entry === 'high')
          result[key] = entry;
      } else if (typeof entry === 'boolean') result[key] = entry;
    }
  }
  return result;
}
let controls = normalize(read(key));
const saved = read(progressKey);
const learned = new Set<string>(
  Array.isArray(saved) ? saved.filter((x) => typeof x === 'string') : []
);
const subscribers = new Set<() => void>();
export const getControls = () => controls;
export const allowed = (group: Group) => controls.enabled && controls[group];
export const subscribe = (fn: () => void) => {
  subscribers.add(fn);
  return () => {
    subscribers.delete(fn);
  };
};
export const useControls = () => useSyncExternalStore(subscribe, getControls);
export function updateControls(change: Partial<Controls>) {
  controls = normalize({ ...controls, ...change });
  write(key, controls);
  subscribers.forEach((fn) => fn());
}
export const familiar = (id: string) => learned.has(id);
export function remember(id: string) {
  if (!learned.has(id)) {
    learned.add(id);
    write(progressKey, [...learned]);
  }
}
export function repeatTraining() {
  learned.clear();
  write(progressKey, []);
  window.dispatchEvent(new Event('gesture-replay'));
}
export function mastered(id: string) {
  remember(id);
  if (controls.haptics && navigator.vibrate) navigator.vibrate(10);
}
export const english = () => document.documentElement.lang.startsWith('en');
export const tr = (ru: string, en: string) => (english() ? en : ru);
