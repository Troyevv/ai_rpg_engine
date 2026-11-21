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

export function foreground(host: HTMLElement) {
  if (
    !host.isConnected ||
    host.closest(
      '[hidden],[inert],[aria-hidden=true],[data-state=closed][role=dialog]'
    )
  )
    return false;
  const layers = document.querySelectorAll<HTMLElement>(
    '[role=dialog]:not([data-state=closed]),[role=alertdialog],[role=listbox][data-state=open]'
  );
  const top =
    layers[layers.length - 1] ||
    document.querySelector('.phone-device.is-open');
  return !top || top.contains(host);
}
