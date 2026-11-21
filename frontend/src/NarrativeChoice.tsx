import { Check, ArrowUpRight, LoaderCircle, MessageCircle } from 'lucide-react';
import { memo, useLayoutEffect, type ReactElement, type RefObject } from 'react';
import type { Choice } from './types';

export function choiceText({ action, speech }: Choice) {
  if (!speech || !action) return action || speech;
  return action + (action.trimEnd().endsWith(':') ? ' ' : ': ') + '«' + speech + '»';
}

type ColumnPlan = {
  difference: number; // Left height minus right height, including the space after each card.
  column: number;
  previous: ColumnPlan | null;
};

function balancedColumns(heights: number[], gap: number) {
  let plans: ColumnPlan[] = [{ difference: 0, column: 0, previous: null }];
  for (const height of heights) {
    const next = new Map<number, ColumnPlan>();
    for (const plan of plans) {
      // Prefer the earlier visual position when equally balanced layouts exist.
      const shorter = plan.difference <= 0 ? 0 : 1;
      for (const column of [shorter, 1 - shorter]) {
        const difference = plan.difference + (column === 0 ? 1 : -1) * (height + gap);
        const imbalance = Math.abs(difference);
        // Mirror-image and equal differences have the same possible final heights.
        if (!next.has(imbalance)) next.set(imbalance, { difference, column, previous: plan });
      }
    }
    plans = Array.from(next.values());
    // Ten cards have at most 512 distinct partitions. Bound work for oversized saved menus.
    if (plans.length > 512) {
      plans.sort((a, b) => Math.abs(a.difference) - Math.abs(b.difference));
      plans.length = 512;
    }
  }
  let best = plans.reduce((a, b) => Math.abs(a.difference) <= Math.abs(b.difference) ? a : b);
  const columns = [];
  while (best.previous) {
    columns.push(best.column);
    best = best.previous;
  }
  return columns.reverse();
}

export function NarrativeChoiceList({ ref, children }: {
  ref: RefObject<HTMLDivElement | null>;
  children: ReactElement[];
}) {
  const count = children.length;
  useLayoutEffect(() => {
    const list = ref.current;
    if (!list || !count) return;
    const cards = Array.from(list.children) as HTMLButtonElement[];

    const pack = () => {
      const style = getComputedStyle(list);
      if (style.gridTemplateColumns.split(' ').length !== 2) return;
      const gap = parseFloat(style.rowGap);
      const heights = cards.map(card => card.getBoundingClientRect().height);
      const columns = balancedColumns(heights, gap);
      const nextTop = [0, 0];

      // Position the existing buttons without changing screen-reader or keyboard order.
      cards.forEach((card, i) => {
        const column = columns[i];
        card.style.setProperty('--choice-column', String(column + 1));
        card.style.setProperty('--choice-offset', nextTop[column] + 'px');
        nextTop[column] += heights[i] + gap;
      });
      list.dataset.packed = '';
    };

    pack();
    const observer = new ResizeObserver(pack);
    observer.observe(list);
    cards.forEach(card => observer.observe(card, { box: 'border-box' }));
    return () => observer.disconnect();
  }, [ref, count]);

  return <div className="choices" ref={ref}>{children}</div>;
}

type CardProps = {
  choice: Choice;
  disabled: boolean;
  selected: boolean;
  sending: boolean;
  choose: (text: string) => void;
};

export const NarrativeChoiceCard = memo(function NarrativeChoiceCard({ choice, disabled, selected, sending, choose }: CardProps) {
  const Icon = sending ? LoaderCircle : selected ? Check : choice.speech ? MessageCircle : ArrowUpRight;
  return <button type="button" className={'narrative-choice-card' + (selected ? ' choice-selected' : '')}
    disabled={disabled} aria-pressed={selected} aria-busy={sending || undefined}
    onClick={() => choose(choiceText(choice))}>
    <span className="choice-mark" aria-hidden="true"><Icon size={16} strokeWidth={1.6}/></span>
    <span className="narrative-choice">
      {choice.action && <strong className="choice-action">{choice.action}</strong>}
      {choice.speech && <span className="choice-speech">«{choice.speech}»</span>}
    </span>
  </button>;
});
