import { useLayoutEffect, useRef, type ReactNode } from 'react';
import { surface, type Surface } from './surface';
import { RefreshList } from './panels';

export function listPull(host: HTMLElement): Surface | undefined {
  const region = host.closest<HTMLElement>('[data-refresh-region]');
  if (!region?.hasAttribute('data-at-start')) return;
  const grip = region.querySelector<HTMLElement>('.gesture-refresh');
  if (!grip) return;
  return {
    id: 'refresh',
    group: 'context',
    axis: 'y',
    sign: 1,
    allowButton: true,
    begin: () => region.hasAttribute('data-at-start'),
    move: ({ delta }) =>
      grip.style.setProperty(
        '--pull',
        Math.min(28, Math.max(0, delta * 0.36)) + 'px'
      ),
    reset: () => grip.style.removeProperty('--pull'),
    finish: () => grip.click(),
  };
}
export function RefreshRegion({
  children,
  refresh,
}: {
  children: ReactNode;
  refresh: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const node = ref.current!;
    const parents: HTMLElement[] = [];
    for (let el: HTMLElement | null = node; el; el = el.parentElement)
      parents.push(el);
    const check = () =>
      node.toggleAttribute(
        'data-at-start',
        parents.every((el) => el.scrollTop <= 1)
      );
    parents.forEach((el) =>
      el.addEventListener('scroll', check, { passive: true })
    );
    check();
    return () =>
      parents.forEach((el) => el.removeEventListener('scroll', check));
  }, []);
  const drag = surface({
    id: 'refresh',
    group: 'context',
    axis: 'y',
    sign: 1,
    begin: () => !!ref.current?.hasAttribute('data-at-start'),
    move: (t) => listPull(t.host)?.move?.(t),
    reset: (host) =>
      host
        .querySelector<HTMLElement>('.gesture-refresh')
        ?.style.removeProperty('--pull'),
    finish: refresh,
  });
  return (
    <div ref={ref} {...drag} data-refresh-region="">
      <RefreshList refresh={refresh} />
      {children}
    </div>
  );
}
