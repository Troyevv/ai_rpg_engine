import { useLayoutEffect, type RefObject } from 'react';

// Keep the menu mounted through the whole outside gesture. Closing on pointerdown
// makes the browser hit-test the newly exposed control for pointerup or click.
export function useMenuDismiss(open: boolean, popup: RefObject<HTMLElement | null>, close: () => void) {
  useLayoutEffect(() => {
    if (!open) return;
    let outsidePress = false;
    const intercept = (event: Event) => {
      if (!popup.current) return;
      const outside = !event.composedPath().includes(popup.current);
      if (event.type === 'pointerdown') outsidePress = outside;
      if (event.type === 'pointercancel') outsidePress = false;
      if (!outside) return;
      if (event.type === 'click' || event.type === 'contextmenu') {
        // A mouse trigger opens on pointerdown. Its trailing click belongs to
        // that opening gesture. Keyboard and assistive clicks have detail zero.
        event.stopImmediatePropagation();
        event.preventDefault();
        if (outsidePress || (event as MouseEvent).detail === 0 || event.type === 'contextmenu') close();
      } else if (outsidePress) {
        event.stopImmediatePropagation();
        if (event.type === 'mousedown') event.preventDefault();
      }
    };
    const events = [
      'pointerdown',
      'pointerup',
      'pointercancel',
      'touchstart',
      'touchend',
      'mousedown',
      'mouseup',
      'click',
      'contextmenu',
    ];
    for (const type of events) window.addEventListener(type, intercept, true);
    return () => {
      for (const type of events) window.removeEventListener(type, intercept, true);
    };
  }, [open, popup, close]);
}
