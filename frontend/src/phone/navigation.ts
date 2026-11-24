import { useRef, useState, type RefObject } from 'react';

export interface AppRoute {
  screen: string;
  id?: string;
}

/** Home leaves each app's nested stack intact. Back removes exactly one screen. */
export function usePhoneNavigation(
  app: string,
  select: (id: string) => void,
  screen: RefObject<HTMLDivElement | null>,
) {
  const [paths, setPaths] = useState<Record<string, AppRoute[]>>({});
  const launcherFocus = useRef<string | null>(null);
  const routes = paths[app] || [];
  const home = () => {
    if (app !== 'home') launcherFocus.current = app;
    select('home');
    requestAnimationFrame(() => {
      const buttons = Array.from(
        screen.current?.querySelectorAll<HTMLButtonElement>('.smart-grid button') || [],
      );
      (buttons.find((b) => b.dataset.app === launcherFocus.current) || buttons[0])?.focus({
        preventScroll: true,
      });
    });
  };
  const navigate = (id: string, route?: AppRoute) => {
    if (route) setPaths((prev) => ({ ...prev, [id]: [route] }));
    select(id);
  };
  const push = (screen: string, id?: string) =>
    setPaths((prev) => ({ ...prev, [app]: [...(prev[app] || []), { screen, id }] }));
  const pop = () => setPaths((prev) => ({ ...prev, [app]: (prev[app] || []).slice(0, -1) }));
  return { home, navigate, push, pop, routes, route: routes.at(-1) };
}
