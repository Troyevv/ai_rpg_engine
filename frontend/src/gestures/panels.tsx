import { useRef, useState, type ReactNode } from 'react';
import { flushSync } from 'react-dom';
import { ChevronDown, ChevronUp, RefreshCw } from 'lucide-react';
import { surface, type Surface } from './surface';
import { tr } from './preferences';

function slide(el: HTMLElement, x: number, y: number) {
  el.style.translate = x + 'px ' + y + 'px';
}
function settle(el: HTMLElement) {
  const from = el.style.translate;
  el.style.removeProperty('translate');
  if (from && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
    el.animate([{ translate: from }, { translate: '0px 0px' }], {
      duration: 170,
      easing: 'ease-out',
    });
  }
}
export function drawer(
  open: () => void,
  close: () => void,
  selector: string,
  side: 1 | -1
) {
  let panel: HTMLElement | null = null;
  let overlay: HTMLElement | null = null;
  return surface({
    id: 'menu',
    axis: 'x',
    sign: -side as 1 | -1,
    group: 'panels',
    allowButton: true,
    opensLayer: true,
    begin: () => {
      flushSync(open);
      panel = document.querySelector(selector);
      overlay = panel?.previousElementSibling as HTMLElement | null;
    },
    move: ({ delta }) => {
      if (!panel) return;
      const distance = Math.max(0, panel.offsetWidth - Math.abs(delta));
      slide(panel, side * distance, 0);
      if (overlay)
        overlay.style.opacity = String(1 - distance / panel.offsetWidth);
    },
    reset: (_, success) => {
      if (overlay) overlay.style.removeProperty('opacity');
      if (panel) settle(panel);
      if (!success) close();
    },
    finish: () => {},
  });
}
// The dock is clipped to its lip when closed. Reveal it during the drag and
// animate from the release position into the existing phone layout.
export function phoneDock(open: boolean, toggle: () => void) {
  let device: HTMLElement | null = null;
  const clear = () => {
    device?.style.removeProperty('clip-path');
    device?.style.removeProperty('translate');
  };
  return surface({
    id: open ? 'phone-down' : 'phone-up',
    axis: 'y',
    sign: open ? 1 : -1,
    group: 'panels',
    allowButton: true,
    begin: (host) => {
      device = host.closest('.phone-device');
      return !!device;
    },
    move: ({ delta }) => {
      if (!device) return;
      device.style.clipPath = 'inset(0)';
      slide(
        device,
        0,
        (open ? 1 : -1) *
          Math.min(
            device.offsetHeight - 44,
            Math.max(0, (open ? 1 : -1) * delta)
          )
      );
    },
    reset: (_, success) => {
      if (device && !success) {
        settle(device);
        clear();
      }
    },
    finish: () => {
      if (!device) return;
      const y = device.getBoundingClientRect().top;
      clear();
      flushSync(toggle);
      const offset = y - device.getBoundingClientRect().top;
      if (!matchMedia('(prefers-reduced-motion: reduce)').matches)
        device.animate(
          [
            { translate: '0 ' + offset + 'px', clipPath: 'inset(0)' },
            { translate: '0 0' },
          ],
          { duration: 180, easing: 'ease-out' }
        );
    },
  });
}
export function dismissLayer(horizontal: 0 | 1 | -1 = 0, back?: () => void) {
  let layer: HTMLElement | null = null;
  const backOnTitle: Surface = {
    id: 'back',
    group: 'navigation',
    axis: 'x',
    sign: 1,
    finish: ({ host }) =>
      host
        .closest('[role=dialog]')
        ?.querySelector<HTMLButtonElement>(':scope > .dialog-close')
        ?.click(),
  };
  return surface({
    alternate: horizontal ? undefined : () => backOnTitle,
    id: horizontal ? 'menu-close' : 'dismiss',
    axis: horizontal ? 'x' : 'y',
    sign: horizontal || 1,
    group: 'panels',
    begin: (host) => {
      layer = host.closest('[role=dialog]');
      return !!layer;
    },
    move: ({ delta }) => {
      if (layer) {
        const distance = Math.max(0, delta * (horizontal || 1));
        slide(layer, horizontal * distance, horizontal ? 0 : distance);
      }
    },
    reset: () => {
      if (layer) settle(layer);
    },
    finish: () => {
      if (back) back();
      else
        layer
          ?.querySelector<HTMLButtonElement>(':scope > .dialog-close')
          ?.click();
    },
  });
}

export function ActionPanel({
  children,
  label,
}: {
  children: ReactNode;
  label: string;
}) {
  const [step, setStep] = useState(2);
  const box = useRef<HTMLDivElement>(null);
  const start = useRef(0);
  const resize = surface({
    id: 'sheet',
    group: 'panels',
    axis: 'y',
    allowButton: true,
    begin: () => {
      start.current = box.current?.offsetHeight || 0;
    },
    move: ({ delta }) => {
      if (box.current)
        box.current.style.maxHeight =
          Math.max(
            0,
            Math.min(box.current.scrollHeight, start.current - delta)
          ) + 'px';
    },
    reset: () => box.current?.style.removeProperty('max-height'),
    finish: ({ delta }) =>
      setStep((s) => Math.max(0, Math.min(2, s + (delta < 0 ? 1 : -1)))),
  });
  return (
    <div className="gesture-sheet" data-stop={step}>
      <button
        className="gesture-sheet-grip"
        type="button"
        {...resize}
        aria-expanded={step > 0}
        onClick={() => setStep((s) => (s === 2 ? 0 : s + 1))}
      >
        <i aria-hidden="true" />
        {label}
        {step === 2 ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
      </button>
      <div className="gesture-sheet-body" ref={box} inert={step === 0}>
        {children}
      </div>
    </div>
  );
}
export function RefreshList({ refresh }: { refresh: () => void }) {
  let start = 0;
  const pull = surface({
    id: 'refresh',
    group: 'context',
    axis: 'y',
    sign: 1,
    allowButton: true,
    begin: (host) => {
      for (
        let el: HTMLElement | null = host.parentElement;
        el;
        el = el.parentElement
      ) {
        if (el.scrollTop > 1 && el.scrollHeight > el.clientHeight) return false;
      }
      start = host.getBoundingClientRect().top;
    },
    move: ({ host, y }) =>
      host.style.setProperty(
        '--pull',
        Math.min(28, Math.max(0, (y - start) * 0.32)) + 'px'
      ),
    reset: (host) => host.style.removeProperty('--pull'),
    finish: refresh,
  });
  return (
    <button
      type="button"
      className="gesture-refresh"
      {...pull}
      onClick={refresh}
    >
      <RefreshCw size={15} />
      {tr('Обновить список', 'Refresh list')}
    </button>
  );
}
export const dismissNotice = (dismiss: () => void) =>
  surface({
    id: 'notice',
    group: 'panels',
    axis: 'x',
    move: ({ host, delta }) => slide(host, delta, 0),
    reset: (host, committed) => {
      if (!committed) settle(host);
    },
    finish: ({ host, delta }) => {
      if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
        host.style.removeProperty('translate');
        dismiss();
        return;
      }
      const motion = host.animate(
        [
          { translate: host.style.translate, opacity: 1 },
          {
            translate: Math.sign(delta) * host.offsetWidth + 'px 0',
            opacity: 0,
          },
        ],
        { duration: 145, easing: 'ease-in', fill: 'forwards' }
      );
      motion.onfinish = () => {
        host.style.removeProperty('translate');
        motion.cancel();
        if (host.isConnected) dismiss();
      };
    },
  });

/** A bottom sheet has its own scroll container. Only the grip resizes it. */
export function SheetHeight() {
  const [compact, setCompact] = useState(false);
  const grip = useRef<HTMLButtonElement>(null);
  let layer: HTMLElement | null = null,
    start = 0;
  function resize(next: boolean) {
    const el = grip.current?.closest<HTMLElement>('[role=dialog]');
    if (!el) return;
    el.toggleAttribute('data-sheet-compact', next);
    setCompact(next);
  }
  const gesture = surface({
    id: 'sheet',
    axis: 'y',
    group: 'panels',
    allowButton: true,
    begin: (host) => {
      layer = host.closest('[role=dialog]');
      start = layer?.offsetHeight || 0;
      return !!start;
    },
    move: ({ delta }) =>
      layer?.style.setProperty(
        '--sheet-limit',
        Math.max(72, start - delta) + 'px'
      ),
    reset: () => layer?.style.removeProperty('--sheet-limit'),
    finish: ({ delta }) => {
      if (delta < 0) resize(false);
      else if (compact || start < innerHeight * 0.45)
        layer
          ?.querySelector<HTMLButtonElement>(':scope>.dialog-close')
          ?.click();
      else resize(true);
    },
  });
  return (
    <button
      {...gesture}
      ref={grip}
      type="button"
      className="gesture-height"
      aria-expanded={!compact}
      aria-label={
        compact
          ? tr('Развернуть панель', 'Expand panel')
          : tr('Свернуть панель', 'Collapse panel')
      }
      onClick={() => resize(!compact)}
    >
      <span />
    </button>
  );
}
