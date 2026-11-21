import { Check, ArrowUpRight, LoaderCircle, MessageCircle } from 'lucide-react';
import { memo, useLayoutEffect, type ReactElement, type RefObject } from 'react';
import type { Choice } from './types';

export function choiceText({ action, speech }: Choice) {
  if (!speech || !action) return action || speech;
  return action + (action.trimEnd().endsWith(':') ? ' ' : ': ') + '«' + speech + '»';
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
      const nextTop = [0, 0];

      // Place in reading order. Margins in one grid row give the list its natural height.
      cards.forEach((card, i) => {
        const column = nextTop[0] <= nextTop[1] ? 0 : 1;
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
