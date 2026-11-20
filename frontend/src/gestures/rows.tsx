import { useTransientBack } from '../lib/transientBack';
import { listPull } from './RefreshRegion';
import { useCallback, useEffect, useLayoutEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { surface, foreground } from './surface';
import { subscribe, tr } from './preferences';

type Menu = {
  anchor: HTMLElement;
  owner: HTMLElement;
  buttons: HTMLButtonElement[];
};
const eventName = 'gesture-row-actions';
export function actionsForRow(anchor: HTMLElement): Menu | null {
  const selector = anchor.dataset.actionOwner;
  const owner = selector ? anchor.closest<HTMLElement>(selector) : anchor;
  if (!owner) return null;
  const buttons = owner.matches('button')
    ? [owner as HTMLButtonElement]
    : Array.from(
        owner.querySelectorAll<HTMLButtonElement>(
          anchor.dataset.actionButtons || 'button'
        )
      );
  const visible = buttons.filter(
    (b) =>
      !b.disabled && b.getClientRects().length && !b.closest('[hidden],[inert]')
  );
  return visible.length ? { owner, anchor, buttons: visible } : null;
}
export function rowActions(ownerSelector?: string, buttonSelector = 'button') {
  function open(anchor: HTMLElement) {
    const menu = actionsForRow(anchor);
    if (!menu) return false;
    window.dispatchEvent(new CustomEvent<Menu>(eventName, { detail: menu }));
    return true;
  }
  return {
    'data-action-owner': ownerSelector,
    'data-action-buttons': buttonSelector,
    ...surface({
      begin: (host) => !!actionsForRow(host),
      id: 'row',
      group: 'context',
      axis: 'x',
      sign: -1,
      allowButton: true,
      alternate: listPull,
      move: ({ host, delta }) => {
        host.style.translate =
          Math.max(-38, Math.min(0, delta * 0.45)) + 'px 0';
      },
      reset: (host) => host.style.removeProperty('translate'),
      finish: ({ host }) => open(host),
      hold: open,
    }),
  };
}
export function RowActionsHost() {
  const [menu, setMenu] = useState<Menu | null>(null);
  useEffect(() => {
    const show = (e: Event) => setMenu((e as CustomEvent<Menu>).detail);
    window.addEventListener(eventName, show);
    const off = subscribe(() => setMenu(null));
    return () => {
      off();
      window.removeEventListener(eventName, show);
    };
  }, []);
  useTransientBack(
    !!menu,
    useCallback(() => {
      if (!menu || !foreground(menu.owner)) return false;
      setMenu(null);
    }, [menu])
  );
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  useLayoutEffect(() => {
    if (!menu) return;
    const slot = document.createElement('div');
    slot.className = 'gesture-row-strip';
    menu.owner.insertAdjacentElement('afterend', slot);
    menu.owner.setAttribute('data-actions-open', 'true');
    setSlot(slot);
    return () => {
      slot.remove();
      menu.owner.removeAttribute('data-actions-open');
      setSlot(null);
    };
  }, [menu]);
  useEffect(() => {
    if (!menu) return;
    const close = () => setMenu(null);
    const outside = (e: Event) => {
      if (!(e.target as Element).closest('.gesture-actions')) close();
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopImmediatePropagation();
        close();
        menu.anchor.focus({ preventScroll: true });
      }
    };
    const observer = new MutationObserver(() => {
      if (!foreground(menu.owner)) close();
    });
    observer.observe(document.body, { subtree: true, childList: true });
    const events = new AbortController(),
      signal = events.signal;
    document.addEventListener('pointerdown', outside, {
      signal,
      capture: true,
    });
    window.addEventListener('keydown', key, { signal, capture: true });
    window.addEventListener('resize', close, { signal });
    return () => {
      events.abort();
      observer.disconnect();
    };
  }, [menu]);
  if (!menu || !slot?.isConnected || !menu.owner.isConnected) return null;
  // Keep the strip inside the active focus scope (including the phone).

  return createPortal(
    <div
      className="gesture-actions"
      role="group"
      aria-label={tr('Действия строки', 'Row actions')}
    >
      {menu.buttons.map((b, i) => (
        <button
          type="button"
          key={i}
          onClick={() => {
            setMenu(null);
            if (b.isConnected && !b.disabled) b.click();
          }}
        >
          {b.getAttribute('aria-label') || b.title || b.textContent}
        </button>
      ))}
      <button
        type="button"
        onClick={() => {
          setMenu(null);
          menu.anchor.focus({ preventScroll: true });
        }}
        aria-label={tr('Свернуть действия', 'Hide actions')}
      >
        ×
      </button>
    </div>,
    slot
  );
}
