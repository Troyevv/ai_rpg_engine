import { useEffect } from 'react';

// A transient control shares its screen's existing history entry. Only the
// foreground control may consume Back before the screen owner handles it.
export function dismissTransient() {
  return !window.dispatchEvent(new Event('control-back', { cancelable: true }));
}

export function useTransientBack(open: boolean, close: () => void | boolean) {
  useEffect(() => {
    if (!open) return;
    const back = (event: Event) => {
      if (close() === false) return;
      event.preventDefault();
      event.stopImmediatePropagation();
    };
    window.addEventListener('control-back', back);
    window.dispatchEvent(new Event('control-layer-change'));
    return () => {
      window.removeEventListener('control-back', back);
      window.dispatchEvent(new Event('control-layer-change'));
    };
  }, [open, close]);
}
