import {useRef, useState, type ReactNode} from 'react';
import {flushSync} from 'react-dom';
import {Minus, Plus, RotateCcw} from 'lucide-react';
import {PanControls} from './pan-controls';
import {tr} from '../../lib/interfaceText';

export function ZoomView({children, label, className = ''}: {children: ReactNode; label: string; className?: string}) {
  const pane = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  function zoom(value: number) {
    const el = pane.current;
    if (!el) return;
    const next = Math.min(4, Math.max(1, value));
    const ratio = next / scale;
    const x = (el.scrollLeft + el.clientWidth / 2) * ratio - el.clientWidth / 2;
    const y = (el.scrollTop + el.clientHeight / 2) * ratio - el.clientHeight / 2;
    flushSync(() => setScale(next));
    el.scrollTo(x, y);
  }
  return (
    <div className="zoom-view">
      <div className="viewer-zoom-tools">
        <button
          type="button"
          aria-label={tr('Уменьшить', 'Zoom out')}
          onClick={() => zoom(scale - 0.5)}
        >
          <Minus size={17} />
        </button>
        <input
          value={scale}
          type="range"
          aria-label={tr('Масштаб просмотра', 'Viewer zoom')}
          min="1"
          max="4"
          step=".01"
          onChange={(e) => zoom(+e.target.value)}
        />
        <button
          type="button"
          aria-label={tr('Увеличить', 'Zoom in')}
          onClick={() => zoom(scale + 0.5)}
        >
          <Plus size={17} />
        </button>
        <button
          type="button"
          aria-label={tr('Сбросить масштаб', 'Reset zoom')}
          onClick={() => zoom(1)}
        >
          <RotateCcw size={17} />
        </button>
      </div>
      <div
        className={'viewer-zoom ' + className}
        ref={pane}
        role="region"
        tabIndex={0}
        aria-label={label}
        data-zoomed={scale > 1 || undefined}
      >
        <div className="viewer-zoom-content" style={{transform: `scale(${scale})`}}>{children}</div>
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
