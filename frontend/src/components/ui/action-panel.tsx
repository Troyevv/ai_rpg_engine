import { useId, useState, type ReactNode } from 'react';
import { tr } from '../../lib/interfaceText';
import { ChevronDown, ChevronUp } from 'lucide-react';

export function ActionPanel({
  children,
  label,
  hidden = false,
}: {
  hidden?: boolean;
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
      <button
        className="action-panel-toggle"
        type="button"
        title={nextAction}
        aria-label={label + ' · ' + nextAction}
        aria-expanded={step > 0}
        aria-controls={bodyId}
        onClick={() => setStep((s) => (s === 2 ? 0 : s + 1))}
      >
        {label}
        {step === 2 ? <ChevronUp aria-hidden="true" size={16} /> : <ChevronDown aria-hidden="true" size={16} />}
      </button>
      <div className="action-panel-body" id={bodyId} inert={step === 0}>
        {children}
      </div>
    </div>
  );
}
