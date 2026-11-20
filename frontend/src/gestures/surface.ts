import type { PointerEvent as ReactPointer } from 'react';
import {
  allowed,
  getControls,
  mastered,
  subscribe,
  type Group,
  type Controls,
} from './preferences';

type Axis = 'x' | 'y';
export type Travel = { delta: number; x: number; y: number; host: HTMLElement };
export type Surface = {
  id: string;
  group: Group;
  axis: Axis;
  sign?: 1 | -1;
  begin?: (host: HTMLElement) => boolean | void;
  move?: (travel: Travel) => void;
  finish: (travel: Travel) => void;
  reset?: (host: HTMLElement, committed: boolean) => void;
  hold?: (host: HTMLElement) => void;
  allowButton?: boolean;
  opensLayer?: boolean;
  alternate?: (host: HTMLElement) => Surface | undefined;
};
const field =
  'input,textarea,select,[contenteditable]:not([contenteditable=false]),[role=slider],[role=combobox],[role=listbox],a[href],summary';
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
export function direction(
  primary: number,
  cross: number
): 'pending' | 'locked' | 'cancelled' {
  if (Math.max(Math.abs(primary), Math.abs(cross)) < 9) return 'pending';
  return Math.abs(primary) >= Math.abs(cross) * 1.35 ? 'locked' : 'cancelled';
}
export function committed(
  delta: number,
  velocity: number,
  preset: Controls['sensitivity']
) {
  const distance = { low: 78, normal: 56, high: 40 }[preset];
  return (
    Math.abs(delta) >= distance ||
    (Math.abs(delta) >= distance * 0.45 && Math.sign(delta) * velocity >= 0.48)
  );
}
let active: (() => void) | null = null;
export const interacting = () => !!active;
export function blockClick(host: HTMLElement) {
  // The compatibility click is dispatched immediately after pointerup. Another
  // real pointerdown always starts a fresh tap, including at the same position.
  const controller = new AbortController();
  const clear = () => controller.abort();
  window.addEventListener('pointerdown', clear, {
    capture: true,
    once: true,
    signal: controller.signal,
  });
  window.addEventListener(
    'click',
    (e) => {
      if (
        e.detail &&
        (host.contains(e.target as Node) ||
          !host.isConnected ||
          document.elementFromPoint(e.clientX, e.clientY) === e.target)
      ) {
        e.preventDefault();
        e.stopImmediatePropagation();
      }
      clear();
    },
    { capture: true, signal: controller.signal }
  );
  window.setTimeout(clear, 500);
}
export function surface(primary: Surface) {
  return {
    'data-gesture': primary.id,
    'data-gesture-group': primary.group,
    'data-gesture-axis': primary.axis,
    onPointerDown: (event: ReactPointer<HTMLElement>) => {
      const host = event.currentTarget,
        target = event.target as Element;
      let config = primary;
      const alternate = primary.alternate?.(host);
      if (
        event.pointerType === 'mouse' ||
        !event.isPrimary ||
        event.button !== 0 ||
        active ||
        (!allowed(config.group) && !(alternate && allowed(alternate.group))) ||
        !foreground(host) ||
        target.closest('[data-gesture]') !== host ||
        target.closest(field) ||
        (!config.allowButton && target.closest('button,[role=button]')) ||
        (config.hold &&
          target.closest('p,blockquote,pre,.prose') &&
          !target.closest('button')) ||
        window.getSelection()?.toString()
      )
        return;
      const startX = event.clientX,
        startY = event.clientY,
        id = event.pointerId;
      const controller = new AbortController(),
        signal = controller.signal;
      let phase: 'pending' | 'dragging' | 'held' | 'cancelled' = 'pending';
      let timer = 0,
        last = 0,
        lastTime = event.timeStamp,
        velocity = 0;
      const travel = (e: PointerEvent): Travel => ({
        delta: config.axis === 'x' ? e.clientX - startX : e.clientY - startY,
        x: e.clientX,
        y: e.clientY,
        host,
      });
      const stop = (success = false) => {
        if (signal.aborted) return;
        controller.abort();
        clearTimeout(timer);
        active = null;
        unsubscribe();
        observer.disconnect();
        delete host.dataset.tracking;
        if (host.hasPointerCapture(id)) host.releasePointerCapture(id);
        if (phase !== 'pending') blockClick(host);
        if (phase === 'dragging') config.reset?.(host, success);
      };
      const cancel = () => stop(false);
      const valid = () =>
        host.isConnected &&
        ((phase === 'dragging' && config.opensLayer) || foreground(host));
      active = cancel;
      const unsubscribe = subscribe(cancel);
      const observer = new MutationObserver(() => {
        if (!valid()) cancel();
      });
      observer.observe(document.body, { childList: true, subtree: true });
      const move = (e: PointerEvent) => {
        if (e.pointerId !== id || phase === 'held' || phase === 'cancelled')
          return;
        if (phase === 'pending' && alternate) {
          const dx = Math.abs(e.clientX - startX),
            dy = Math.abs(e.clientY - startY);
          const crossDominates = primary.axis === 'x' ? dy > dx : dx > dy;
          config = crossDominates ? alternate : primary;
        }
        const p = travel(e);
        if (!valid() || window.getSelection()?.toString()) {
          cancel();
          return;
        }
        if (phase === 'pending') {
          const result = direction(
            p.delta,
            config.axis === 'x' ? p.y - startY : p.x - startX
          );
          if (result === 'pending') return;
          clearTimeout(timer);
          if (
            result === 'cancelled' ||
            !allowed(config.group) ||
            (config.sign && config.sign * p.delta <= 0) ||
            config.begin?.(host) === false
          ) {
            phase = 'cancelled';
            return;
          }
          phase = 'dragging';
          host.dataset.tracking = 'true';
          try {
            host.setPointerCapture(id);
          } catch {
            /* A closing portal can release the pointer. */
          }
        }
        if (e.cancelable) e.preventDefault();
        if (e.timeStamp > lastTime) {
          velocity = (p.delta - last) / (e.timeStamp - lastTime);
          lastTime = e.timeStamp;
          last = p.delta;
        }
        config.move?.(p);
      };
      const up = (e: PointerEvent) => {
        if (e.pointerId !== id) return;
        const p = travel(e);
        const success =
          phase === 'dragging' &&
          valid() &&
          (!config.sign || config.sign * p.delta > 0) &&
          committed(
            p.delta,
            e.timeStamp - lastTime > 100 ? 0 : velocity,
            getControls().sensitivity
          );
        stop(success);
        if (success) {
          mastered(config.id);
          config.finish(p);
        }
      };
      if (primary.hold && allowed(primary.group))
        timer = window.setTimeout(() => {
          if (!valid() || window.getSelection()?.toString()) {
            cancel();
            return;
          }
          phase = 'held';
          mastered(primary.id);
          primary.hold?.(host);
        }, 520);
      window.dispatchEvent(new Event('gesture-start'));
      window.addEventListener('pointermove', move, { signal, passive: false });
      window.addEventListener('pointerup', up, { signal, capture: true });
      window.addEventListener('pointercancel', cancel, {
        signal,
        capture: true,
      });
      window.addEventListener(
        'pointerdown',
        (e) => {
          if (e.pointerId !== id) cancel();
        },
        { signal, capture: true }
      );
      host.addEventListener(
        'contextmenu',
        (e) => {
          if (config.hold) e.preventDefault();
        },
        { signal }
      );
      host.addEventListener(
        'lostpointercapture',
        (e) => {
          if (e.target === host) cancel();
        },
        { signal }
      );
      window.addEventListener('blur', cancel, { signal });
      window.addEventListener('resize', cancel, { signal });
      window.visualViewport?.addEventListener('resize', cancel, { signal });
      document.addEventListener('visibilitychange', cancel, { signal });
    },
  };
}
export function pages<T>(
  items: readonly T[],
  value: T,
  select: (v: T) => void,
  id = 'tabs'
) {
  if (items.length < 2) return {};
  return surface({
    id,
    group: 'navigation',
    axis: 'x',
    allowButton: true,
    finish: ({ delta, host }) => {
      const index = items.indexOf(value),
        next = index + (delta < 0 ? 1 : -1);
      if (index >= 0 && next >= 0 && next < items.length) {
        select(items[next]);
        requestAnimationFrame(() => {
          const active = host.querySelector<HTMLElement>(
            '[aria-selected=true],[aria-current=page],[aria-pressed=true]'
          );
          if (!active || host.scrollWidth <= host.clientWidth) return;
          const strip = host.getBoundingClientRect(),
            button = active.getBoundingClientRect();
          if (button.left < strip.left)
            host.scrollLeft += button.left - strip.left;
          else if (button.right > strip.right)
            host.scrollLeft += button.right - strip.right;
        });
      }
    },
  });
}
export const backSwipe = (back: () => void) =>
  surface({
    id: 'back',
    group: 'navigation',
    axis: 'x',
    sign: 1,
    finish: back,
  });
export const closeButtonSwipe = () =>
  surface({
    id: 'back',
    group: 'navigation',
    axis: 'x',
    sign: 1,
    allowButton: true,
    finish: ({ host }) => host.click(),
  });
