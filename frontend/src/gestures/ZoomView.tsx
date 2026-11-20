import { PanControls } from './PanControls';
import { useEffect, useRef, type ReactNode } from 'react';
import { Minus, Plus, RotateCcw } from 'lucide-react';
import { blockClick, foreground } from './surface';
import { allowed, mastered, subscribe, tr } from './preferences';

type Point = { x: number; y: number };
const midpoint = (a: Point, b: Point) => ({
  x: (a.x + b.x) / 2,
  y: (a.y + b.y) / 2,
});
const distance = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y);
export function anchoredScroll(
  scroll: number,
  oldFocus: number,
  newFocus: number,
  ratio: number
) {
  return (scroll + oldFocus) * ratio - newFocus;
}
export function ZoomView({
  children,
  label,
  className = '',
  portrait = false,
}: {
  children: ReactNode;
  label: string;
  className?: string;
  portrait?: boolean;
}) {
  const pane = useRef<HTMLDivElement>(null),
    range = useRef<HTMLInputElement>(null);
  const change = useRef<(value: number) => void>(() => {});
  useEffect(() => {
    const el = pane.current!,
      slider = range.current!;
    const points = new Map<number, Point>();
    let scale = 1,
      start: Point | null = null,
      dragged = false,
      lastTap: { at: number; p: Point } | null = null;
    function zoom(value: number, from: Point, to = from) {
      const rect = el.getBoundingClientRect(),
        next = Math.min(4, Math.max(1, value)),
        ratio = next / scale;
      const x = anchoredScroll(
        el.scrollLeft,
        from.x - rect.left,
        to.x - rect.left,
        ratio
      );
      const y = anchoredScroll(
        el.scrollTop,
        from.y - rect.top,
        to.y - rect.top,
        ratio
      );
      scale = next;
      el.toggleAttribute('data-zoomed', scale > 1);
      slider.value = String(scale);
      el.style.setProperty('--view-scale', String(scale));
      el.scrollLeft = x;
      el.scrollTop = y;
    }
    change.current = (value) => {
      const r = el.getBoundingClientRect();
      zoom(value, { x: r.left + r.width / 2, y: r.top + r.height / 2 });
    };
    const point = (e: PointerEvent) => ({ x: e.clientX, y: e.clientY });
    function cancel() {
      for (const id of points.keys())
        if (el.hasPointerCapture(id)) el.releasePointerCapture(id);
      if (dragged) blockClick(el);
      delete el.dataset.gestureActive;
      points.clear();
      start = null;
      dragged = false;
      lastTap = null;
    }
    function down(e: PointerEvent) {
      if (
        !foreground(el) ||
        (!allowed('images') && e.pointerType !== 'mouse') ||
        e.button !== 0 ||
        window.getSelection()?.toString()
      )
        return;
      if (points.size >= 2) {
        cancel();
        return;
      }
      if (!points.size) {
        dragged = false;
        start = point(e);
      }
      points.set(e.pointerId, point(e));
      if (points.size === 2) {
        dragged = true;
        lastTap = null;
        for (const id of points.keys()) el.setPointerCapture(id);
      }
      el.dataset.gestureActive = 'true';
      window.dispatchEvent(new Event('gesture-start'));
    }
    function move(e: PointerEvent) {
      const old = points.get(e.pointerId);
      if (!old) return;
      const p = point(e),
        previous = [...points.values()];
      if (!dragged && start && distance(start, p) < 8) return;
      points.set(e.pointerId, p);
      if (!dragged) {
        dragged = true;
        el.setPointerCapture(e.pointerId);
      }
      if (points.size === 2) {
        const [a, b] = previous,
          [c, d] = points.values();
        zoom(
          (scale * distance(c, d)) / Math.max(1, distance(a, b)),
          midpoint(a, b),
          midpoint(c, d)
        );
      } else if (scale > 1) {
        el.scrollLeft += old.x - p.x;
        el.scrollTop += old.y - p.y;
      }
    }
    function up(e: PointerEvent) {
      if (!points.delete(e.pointerId)) return;
      if (dragged) {
        blockClick(el);
        if (!points.size && scale > 1) mastered('image');
      } else if (portrait && e.pointerType !== 'mouse') {
        const p = point(e);
        if (
          lastTap &&
          e.timeStamp - lastTap.at < 320 &&
          distance(lastTap.p, p) < 24
        ) {
          zoom(scale > 1.05 ? 1 : 2.25, p);
          lastTap = null;
          mastered('double');
          blockClick(el);
        } else lastTap = { at: e.timeStamp, p };
      }
      if (!points.size) {
        delete el.dataset.gestureActive;
        start = null;
        dragged = false;
      }
    }
    const controller = new AbortController(),
      signal = controller.signal;
    el.addEventListener('pointerdown', down, { signal });
    el.addEventListener('pointermove', move, { signal });
    el.addEventListener('pointerup', up, { signal });
    el.addEventListener('pointercancel', cancel, { signal });
    el.addEventListener(
      'lostpointercapture',
      (e) => {
        if (e.target === el && points.has(e.pointerId)) cancel();
      },
      { signal }
    );
    window.addEventListener('blur', cancel, { signal });
    window.addEventListener('resize', cancel, { signal });
    document.addEventListener('visibilitychange', cancel, { signal });
    const off = subscribe(cancel);
    return () => {
      controller.abort();
      off();
      cancel();
    };
  }, [portrait]);
  return (
    <div className="zoom-view">
      <div className="gesture-zoom-tools">
        <button
          type="button"
          aria-label={tr('Уменьшить', 'Zoom out')}
          onClick={() => change.current(Number(range.current!.value) - 0.5)}
        >
          <Minus size={17} />
        </button>
        <input
          ref={range}
          type="range"
          aria-label={tr('Масштаб просмотра', 'Viewer zoom')}
          min="1"
          max="4"
          step=".01"
          defaultValue="1"
          onChange={(e) => change.current(+e.target.value)}
        />
        <button
          type="button"
          aria-label={tr('Увеличить', 'Zoom in')}
          onClick={() => change.current(Number(range.current!.value) + 0.5)}
        >
          <Plus size={17} />
        </button>
        <button
          type="button"
          aria-label={tr('Сбросить масштаб', 'Reset zoom')}
          onClick={() => change.current(1)}
        >
          <RotateCcw size={17} />
        </button>
      </div>
      <div
        className={'gesture-zoom ' + className}
        ref={pane}
        tabIndex={0}
        aria-label={label}
        data-gesture="image"
        data-gesture-group="images"
      >
        <div className="gesture-zoom-content">{children}</div>
      </div>
      <PanControls
        move={(x, y) => {
          const el = pane.current;
          if (el)
            el.scrollBy(x * el.clientWidth * 0.6, y * el.clientHeight * 0.6);
        }}
      />
    </div>
  );
}
