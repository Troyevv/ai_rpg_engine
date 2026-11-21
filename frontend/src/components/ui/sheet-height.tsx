import {useRef, useState} from 'react';
import {ChevronUp, ChevronDown} from 'lucide-react';
import {tr} from '../../lib/interfaceText';

export function SheetHeight() {
  const [compact, setCompact] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  function resize(next: boolean) {
    const el = button.current?.closest<HTMLElement>('[role=dialog]');
    if (!el) return;
    el.toggleAttribute('data-sheet-compact', next);
    setCompact(next);
  }
  return (
    <button
      ref={button}
      type="button"
      className="sheet-size-button"
      aria-expanded={!compact}
      aria-label={
        compact
          ? tr('Развернуть панель', 'Expand panel')
          : tr('Свернуть панель', 'Collapse panel')
      }
      onClick={() => resize(!compact)}
    >
      {compact ? <ChevronUp size={18}/> : <ChevronDown size={18}/>}
    </button>
  );
}
