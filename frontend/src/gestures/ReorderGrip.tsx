import { GripVertical } from 'lucide-react';
import { surface } from './surface';
import { tr } from './preferences';

export function ReorderGrip({ move }: { move: (index: number) => void }) {
  let rows: HTMLElement[] = [],
    source = -1,
    at = -1;
  let scroller: HTMLElement | null = null,
    frame = 0,
    pointerY = 0;
  const scroll = () => {
    if (!scroller) return;
    const r = scroller.getBoundingClientRect(),
      edge = 52;
    const top = Math.max(0, r.top),
      bottom = Math.min(innerHeight, r.bottom);
    const speed =
      pointerY < top + edge
        ? -Math.min(14, (top + edge - pointerY) * 0.32)
        : pointerY > bottom - edge
          ? Math.min(14, (pointerY - bottom + edge) * 0.32)
          : 0;
    if (speed) {
      scroller.scrollTop += speed;
      mark(pointerY);
    }
    frame = requestAnimationFrame(scroll);
  };
  function mark(y: number) {
    const boundary = rows.findIndex((row) => {
      const r = row.getBoundingClientRect();
      return y < r.top + r.height / 2;
    });
    at = boundary < 0 ? rows.length : boundary;
    rows.forEach((row, i) => {
      row.toggleAttribute(
        'data-insert-before',
        at === i && at !== source && at !== source + 1
      );
      row.toggleAttribute(
        'data-insert-after',
        at === rows.length && i === at - 1 && source !== i
      );
    });
  }
  const grip = surface({
    id: 'reorder',
    axis: 'y',
    group: 'context',
    begin: (host) => {
      const row = host.parentElement!;
      rows = Array.from(
        row.parentElement!.querySelectorAll<HTMLElement>(
          ':scope > .ww-structured-row'
        )
      );
      source = rows.indexOf(row);
      for (let el = row.parentElement; el; el = el.parentElement) {
        if (
          el.scrollHeight > el.clientHeight &&
          /auto|scroll/.test(getComputedStyle(el).overflowY)
        ) {
          scroller = el;
          break;
        }
      }
      return source !== -1;
    },
    move: ({ y }) => {
      pointerY = y;
      mark(y);
      if (!frame && scroller) frame = requestAnimationFrame(scroll);
    },
    reset: () => {
      cancelAnimationFrame(frame);
      frame = 0;
      scroller = null;
      rows.forEach((row) => {
        row.removeAttribute('data-insert-before');
        row.removeAttribute('data-insert-after');
      });
    },
    finish: ({ y }) => {
      const boundary = rows.findIndex(
        (row) => y < row.getBoundingClientRect().top + row.offsetHeight / 2
      );
      const to = boundary < 0 ? rows.length : boundary;
      if (to !== source && to !== source + 1) move(to > source ? to - 1 : to);
    },
  });
  return (
    <span
      {...grip}
      className="gesture-sort-grip"
      aria-label={tr('Переместить запись', 'Move record')}
    >
      <GripVertical size={19} />
    </span>
  );
}
