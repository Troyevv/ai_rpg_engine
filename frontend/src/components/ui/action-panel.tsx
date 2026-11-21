import { useId, useState, type ReactNode } from 'react';
import { tr } from '../../lib/interfaceText';
import { ChevronDown, ChevronUp, Sparkles } from 'lucide-react';

export function ActionPanel({
  children, count,
  label,
  hidden = false,
}: {
  count?: number; hidden?: boolean;
  children: ReactNode;
  label: string;
}) {
  const [step, setStep] = useState(2);
  const bodyId = useId();
  const nextAction = [
    tr('Раскрыть компактный список', 'Open compact list'),
    tr('Показать весь список', 'Show full list'),
    tr('Свернуть список', 'Collapse list'),
  ][step];
  return (
    <div className="action-panel" data-stop={step} hidden={hidden}>
      <div className="action-panel-heading">
      <button
        className="action-panel-toggle"
        type="button"
        title={nextAction}
        aria-label={label + ' · ' + nextAction}
        aria-expanded={step > 0}
        aria-controls={bodyId}
        onClick={() => setStep((s) => (s === 2 ? 0 : s + 1))}
      >
        <Sparkles aria-hidden size={16}/>{label}{count!==undefined&&<span className="choice-count">{count}</span>}<span className="choice-level">{['Свёрнуто','Компактно','Полностью'][step]}</span>
        {step === 2 ? <ChevronUp aria-hidden="true" size={16} /> : <ChevronDown aria-hidden="true" size={16} />}
      </button>
      {count!==undefined&&<span className="action-panel-hint">или напиши своё</span>}
      </div>
      <div className="action-panel-body" id={bodyId} inert={step === 0}>
        {children}
      </div>
    </div>
  );
}
