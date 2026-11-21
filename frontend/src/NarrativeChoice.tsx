import { Check, ArrowUpRight, LoaderCircle, MessageCircle } from 'lucide-react';
import { memo } from 'react';
import type { Choice } from './types';

export function choiceText({ action, speech }: Choice) {
  if (!speech || !action) return action || speech;
  return action + (action.trimEnd().endsWith(':') ? ' ' : ': ') + '«' + speech + '»';
}

type CardProps = {
  choice: Choice;
  compact?: boolean;
  disabled: boolean;
  selected: boolean;
  sending: boolean;
  choose: (text: string) => void;
};

export const NarrativeChoiceCard = memo(function NarrativeChoiceCard({ choice, disabled, selected, sending, choose, compact }: CardProps) {
  const Icon = sending ? LoaderCircle : selected ? Check : choice.speech ? MessageCircle : ArrowUpRight;
  return <button type="button" className={'narrative-choice-card' + (selected ? ' choice-selected' : '')}
    aria-label={compact ? choiceText(choice) : undefined} title={compact ? choiceText(choice) : undefined}
    disabled={disabled} aria-pressed={selected} aria-busy={sending || undefined}
    onClick={() => choose(choiceText(choice))}>
    <span className="choice-mark skin-stamp" aria-hidden="true"><Icon size={16} strokeWidth={1.6}/></span>
    <span className="narrative-choice skin-copy">
      <small className="choice-kind" aria-hidden="true">{choice.speech ? 'Реплика' : 'Действие'}</small>
      {choice.action && <strong className="choice-action">{choice.action}</strong>}
      {choice.speech && (!compact || !choice.action) && <span className="choice-speech">«{choice.speech}»</span>}
    </span>
  </button>;
});
