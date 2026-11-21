import {useSyncExternalStore} from 'react';

function displayOption(key: string) {
  const snapshot = () => localStorage.getItem(key) !== 'off';
  const subscribe = (notify: () => void) => {
    window.addEventListener(key, notify);
    window.addEventListener('storage', notify);
    return () => {
      window.removeEventListener(key, notify);
      window.removeEventListener('storage', notify);
    };
  };
  return {
    useValue: () => useSyncExternalStore(subscribe, snapshot),
    set(value: boolean) {
      localStorage.setItem(key, value ? 'on' : 'off');
      window.dispatchEvent(new Event(key));
    },
  };
}

export const {useValue: useAnimations, set: setAnimations} = displayOption('presentation.animations');
export const turnTimes = displayOption('presentation.turnTimes');
