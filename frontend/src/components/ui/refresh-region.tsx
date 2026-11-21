import type { ReactNode } from 'react';
import { RefreshCw } from 'lucide-react';
import { tr } from '../../lib/interfaceText';

export function RefreshRegion({ children, refresh }: { children: ReactNode; refresh: () => void }) {
  return <div>
    <button type="button" className="list-refresh" onClick={refresh}>
      <RefreshCw size={15} aria-hidden="true" />{tr('Обновить список', 'Refresh list')}
    </button>
    {children}
  </div>;
}
