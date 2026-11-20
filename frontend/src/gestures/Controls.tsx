import { useEffect } from 'react';
import {
  defaults,
  allowed,
  familiar,
  remember,
  repeatTraining,
  tr,
  updateControls,
  useControls,
  type Controls,
  type Group,
} from './preferences';
import { foreground, interacting } from './surface';
import { RowActionsHost } from './rows';
import { Choice } from '../components/ui/choice';

const guide = {
  menu: [
    'Потяни кнопку меню внутрь экрана, чтобы открыть меню.',
    'Drag the menu button inwards to open the menu.',
    'Кнопка меню',
    'Menu button',
  ],
  'menu-close': [
    'Потяни заголовок меню к краю, чтобы закрыть.',
    'Drag the menu header towards its edge to close.',
    'Закрыть',
    'Close',
  ],
  'phone-up': [
    'Потяни выступ телефона вверх, чтобы открыть его.',
    'Pull the phone handle up to open it.',
    'Кнопка «Телефон»',
    'Phone button',
  ],
  'phone-down': [
    'Потяни кнопку сворачивания вниз, чтобы убрать телефон.',
    'Drag the collapse button down to put the phone away.',
    'Свернуть телефон',
    'Collapse phone',
  ],
  tabs: [
    'Проведи по вкладкам для перехода в соседний раздел.',
    'Swipe the tabs to visit the adjacent section.',
    'Вкладки и меню разделов',
    'Tabs and section menu',
  ],
  back: [
    'Проведи вправо по заголовку, чтобы вернуться на один уровень.',
    'Swipe right on the header to go back one level.',
    'Назад',
    'Back',
  ],
  cards: [
    'Проведи по переключателю, чтобы посмотреть соседнее досье.',
    'Swipe the selector to view the adjacent dossier.',
    'Выбор персонажа',
    'Character selector',
  ],
  period: [
    'Проведи по названию периода, чтобы перелистнуть календарь.',
    'Swipe the period heading to browse the calendar.',
    'Стрелки календаря',
    'Calendar arrows',
  ],
  dismiss: [
    'Потяни за ручку вниз, чтобы закрыть верхнее окно.',
    'Pull down on the handle to close the top window.',
    'Закрыть окно',
    'Close window',
  ],
  sheet: [
    'Потяни ручку панели вверх или вниз, чтобы изменить её высоту.',
    'Drag the panel handle up or down to change its height.',
    'Нажатие на ручку',
    'Tap the handle',
  ],
  row: [
    'Проведи влево или удерживай карточку, чтобы открыть её действия.',
    'Swipe left or hold the card to show its actions.',
    'Кнопки карточки',
    'Card buttons',
  ],
  notice: [
    'Смахни уведомление в сторону, чтобы убрать его.',
    'Swipe the notification sideways to dismiss it.',
    'Кнопка закрытия',
    'Dismiss button',
  ],
  image: [
    'Разведи пальцы для увеличения. Перемещай двумя пальцами или одним после увеличения.',
    'Spread two fingers to zoom. Drag with two fingers or pan after zooming.',
    'Масштаб, сброс и прокрутка',
    'Zoom, reset and scroll controls',
  ],
  double: [
    'Коснись портрета дважды, чтобы увеличить или вернуть исходный размер.',
    'Double-tap a portrait to zoom in or return to its original size.',
    'Масштаб просмотра',
    'Viewer zoom',
  ],
  refresh: [
    'Потяни кнопку обновления вниз в начале списка.',
    'Pull the refresh control down at the top of the list.',
    'Обновить список',
    'Refresh list',
  ],
  reorder: [
    'Потяни за захват записи к нужной позиции в редакторе списка.',
    'Drag a record by its grip to a new position in the list editor.',
    'Выше или ниже',
    'Move up or down',
  ],
} as const;
const groups = [
  ['navigation', 'Навигация', 'Navigation'],
  ['panels', 'Панели и уведомления', 'Panels and notices'],
  ['context', 'Действия со списками', 'List actions'],
  ['images', 'Изображения и графы', 'Images and graphs'],
] as const;
export function GestureSettings() {
  const settings = useControls();
  function toggle(
    key: Exclude<keyof Controls, 'sensitivity'>,
    ru: string,
    en: string
  ) {
    return (
      <label key={key}>
        <input
          type="checkbox"
          checked={settings[key]}
          onChange={(e) => updateControls({ [key]: e.target.checked })}
        />
        {tr(ru, en)}
      </label>
    );
  }
  return (
    <details className="gesture-settings">
      <summary>{tr('Управление', 'Controls')}</summary>
      {toggle('enabled', 'Управление жестами', 'Gesture controls')}
      {groups.map(([g, ru, en]) => toggle(g, ru, en))}
      {toggle('hints', 'Подсказки по управлению', 'Gesture tips')}
      <label>
        {tr('Чувствительность', 'Sensitivity')}
        <Choice
          value={settings.sensitivity}
          onValueChange={(s) =>
            updateControls({ sensitivity: s as Controls['sensitivity'] })
          }
        >
          <option value="low">{tr('Низкая', 'Low')}</option>
          <option value="normal">{tr('Обычная', 'Normal')}</option>
          <option value="high">{tr('Высокая', 'High')}</option>
        </Choice>
      </label>
      {typeof navigator.vibrate === 'function' &&
        toggle('haptics', 'Тактильный отклик', 'Haptic feedback')}
      <details>
        <summary>{tr('Управление и жесты', 'Controls and gestures')}</summary>
        <ul>
          {Object.entries(guide).map(([id, [ru, en, alt, altEn]]) => (
            <li key={id}>
              {tr(ru, en)} <small>{tr(alt, altEn)}</small>
            </li>
          ))}
        </ul>
        <button type="button" onClick={repeatTraining}>
          {tr('Повторить обучение', 'Repeat training')}
        </button>
      </details>
      <button type="button" onClick={() => updateControls(defaults)}>
        {tr('Сбросить настройки управления', 'Reset gesture settings')}
      </button>
    </details>
  );
}

export function GestureHost() {
  const controls = useControls();
  useEffect(() => {
    const root = document.documentElement;
    root.dataset.gestures = groups
      .filter(([g]) => allowed(g))
      .map(([g]) => g)
      .join(' ');
    if (
      !controls.enabled ||
      !controls.hints ||
      (!navigator.maxTouchPoints &&
        !matchMedia('(any-pointer: coarse)').matches)
    )
      return;
    let timer = 0,
      cooldown = 0,
      anchor: HTMLElement | null = null,
      tip: HTMLDivElement | null = null;
    function hide() {
      clearTimeout(timer);
      timer = 0;
      tip?.remove();
      tip = null;
      anchor = null;
    }
    function blocked() {
      return (
        document.hidden ||
        interacting() ||
        document.activeElement?.matches(
          'input,textarea,[contenteditable=true]'
        ) ||
        !!document.querySelector(
          '[data-gesture-active], .react-flow__pane.dragging, [data-gesture-busy=true], [data-gesture-confirm], [role=alertdialog], .gesture-actions'
        )
      );
    }
    function eligible(node: HTMLElement) {
      if (node.matches(':disabled') || node.closest('fieldset:disabled'))
        return false;
      if (
        familiar(node.dataset.gesture!) ||
        !allowed(node.dataset.gestureGroup as Group) ||
        !foreground(node)
      )
        return false;
      const r = node.getBoundingClientRect(),
        x = r.left + r.width / 2,
        y = r.top + r.height / 2;
      return (
        r.width > 8 &&
        r.height > 8 &&
        x > 0 &&
        x < innerWidth &&
        y > 0 &&
        y < innerHeight &&
        node.contains(document.elementFromPoint(x, y))
      );
    }
    function show() {
      timer = 0;
      if (!anchor || blocked() || !eligible(anchor)) return;
      const id = anchor.dataset.gesture as keyof typeof guide,
        entry = guide[id];
      if (!entry) return;
      const box = document.createElement('div');
      box.className = 'gesture-tip';
      box.setAttribute('role', 'note');
      box.setAttribute('popover', 'manual');
      const msg = document.createElement('span');
      msg.textContent = tr(entry[0], entry[1]);
      const close = document.createElement('button');
      close.type = 'button';
      close.textContent = '×';
      close.ariaLabel = tr('Закрыть подсказку', 'Dismiss tip');
      close.onclick = () => {
        remember(id);
        hide();
      };
      const off = document.createElement('button');
      off.type = 'button';
      off.textContent = tr('Больше не показывать', 'Hide all tips');
      off.onclick = () => updateControls({ hints: false });
      box.append(msg, close, off);
      (anchor.closest('[role=dialog]') || document.body).append(box);
      box.showPopover?.();
      const r = anchor.getBoundingClientRect(),
        h = box.offsetHeight,
        w = box.offsetWidth;
      const x = Math.max(
        8,
        Math.min(innerWidth - w - 8, r.left + r.width / 2 - w / 2)
      );
      const y = [r.bottom + 5, r.top - h - 5].find((y) => {
        if (y < 8 || y + h > innerHeight - 8) return false;
        // Keep actionable controls and the keyboard clear even in dense editors.
        return !Array.from(
          (anchor!.closest('[role=dialog]') || document).querySelectorAll(
            'textarea,input,button,[role=combobox]'
          )
        ).some((el) => {
          if (box.contains(el)) return false;
          const b = el.getBoundingClientRect();
          return (
            b.width > 0 &&
            b.height > 0 &&
            x < b.right &&
            x + w > b.left &&
            y < b.bottom &&
            y + h > b.top
          );
        });
      });
      if (y === undefined) {
        box.remove();
        cooldown = Date.now() + 12000;
        return;
      }
      box.style.left = x + 'px';
      box.style.top = y + 'px';
      tip = box;
      cooldown = Date.now() + 60000;
    }
    function schedule() {
      if (tip && (!anchor || !eligible(anchor) || blocked())) hide();
      if (timer && anchor && (!anchor.isConnected || !foreground(anchor)))
        hide();
      if (timer || tip || Date.now() < cooldown || blocked()) return;
      anchor =
        Array.from(
          document.querySelectorAll<HTMLElement>('[data-gesture]')
        ).find(eligible) || null;
      if (anchor) timer = window.setTimeout(show, 1800);
    }
    const observer = new MutationObserver(schedule);
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['hidden', 'inert', 'data-gesture-busy', 'data-state'],
    });
    const events = new AbortController(),
      signal = events.signal;
    let retry = 0;
    const pause = () => {
      hide();
      clearTimeout(retry);
      cooldown = Math.max(cooldown, Date.now() + 2200);
      retry = window.setTimeout(schedule, cooldown - Date.now() + 20);
    };
    window.addEventListener('gesture-start', pause, { signal });
    document.addEventListener(
      'focusin',
      () => {
        if (blocked()) pause();
      },
      { signal }
    );
    document.addEventListener('focusout', pause, { signal });
    document.addEventListener('visibilitychange', pause, { signal });
    window.addEventListener('resize', pause, { signal });
    document.addEventListener('scroll', pause, {
      signal,
      capture: true,
      passive: true,
    });
    window.addEventListener(
      'gesture-replay',
      () => {
        hide();
        cooldown = 0;
        schedule();
      },
      { signal }
    );
    schedule();
    return () => {
      observer.disconnect();
      events.abort();
      clearTimeout(retry);
      hide();
    };
  }, [controls]);
  return <RowActionsHost />;
}
