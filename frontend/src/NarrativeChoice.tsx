import type { Choice } from './types';

export function choiceText({ action, speech }: Choice) {
  if (!speech || !action) return action || speech;
  return action + (action.trimEnd().endsWith(':') ? ' ' : ': ') + '«' + speech + '»';
}

export function NarrativeChoice({ choice }: { choice: Choice }) {
  return <span className="narrative-choice">
    {choice.action && <strong className="choice-action">{choice.action}{choice.speech && !choice.action.trimEnd().endsWith(':') ? ':' : ''}</strong>}
    {choice.speech && <span className="choice-speech">«{choice.speech}»</span>}
  </span>;
}
