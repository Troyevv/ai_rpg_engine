import { ArrowLeft, ArrowRight, ArrowUp, ArrowDown } from 'lucide-react';
import { tr } from './preferences';

export function PanControls({
  move,
}: {
  move: (x: number, y: number) => void;
}) {
  const directions = [
    [ArrowLeft, -1, 0, 'Влево', 'Left'],
    [ArrowRight, 1, 0, 'Вправо', 'Right'],
    [ArrowUp, 0, -1, 'Вверх', 'Up'],
    [ArrowDown, 0, 1, 'Вниз', 'Down'],
  ] as const;
  return (
    <details className="gesture-pan-menu nopan nodrag">
      <summary>{tr('Перемещение', 'Pan')}</summary>
      <div>
        {directions.map(([Icon, x, y, ru, en]) => (
          <button
            type="button"
            key={en}
            aria-label={tr(ru, en)}
            onClick={() => move(x, y)}
          >
            <Icon size={17} />
          </button>
        ))}
      </div>
    </details>
  );
}
