import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  direction,
  committed,
  surface,
  foreground,
} from '../src/gestures/surface';
import { anchoredScroll } from '../src/gestures/ZoomView';
import {
  defaults,
  normalize,
  remember,
  familiar,
  repeatTraining,
  updateControls,
} from '../src/gestures/preferences';
afterEach(() => {
  document.body.replaceChildren();
  updateControls(defaults);
  vi.useRealTimers();
});
describe('touch thresholds', () => {
  it.each([
    [4, 3, 'pending'],
    [17, 2, 'locked'],
    [-60, 12, 'locked'],
    [13, -15, 'cancelled'],
    [0, 40, 'cancelled'],
  ] as const)('%s by %s gives %s', (x, y, expected) =>
    expect(direction(x, y)).toBe(expected)
  );
  it('uses release velocity in the locked direction and an absolute minimum', () => {
    expect(committed(8, 2, 'high')).toBe(false);
    expect(committed(-30, -1, 'normal')).toBe(true);
    expect(committed(-30, 1, 'normal')).toBe(false);
    expect(committed(48, 0.01, 'low')).toBe(false);
    expect(committed(48, 0.01, 'high')).toBe(true);
  });
  it('keeps the old content point under the new pinch midpoint', () => {
    expect(anchoredScroll(40, 100, 115, 2)).toBe(165);
  });
});
it('prefers a nested layer and excludes input, the background and selected text', () => {
  const done = vi.fn(),
    parent = surface({
      id: 'back',
      axis: 'x',
      group: 'navigation',
      finish: done,
    });
  document.body.innerHTML =
    '<section data-gesture="back"><div data-gesture="tabs"></div></section><aside role="dialog" data-gesture="back"><textarea></textarea>Text</aside>';
  const outer = document.querySelector('section')!,
    dialog = document.querySelector('aside')!;
  expect(foreground(outer)).toBe(false);
  expect(foreground(dialog)).toBe(true);
  const listen = vi.spyOn(window, 'addEventListener');
  function start(host: HTMLElement, target: Element) {
    parent.onPointerDown({
      currentTarget: host,
      target,
      pointerType: 'touch',
      isPrimary: true,
      button: 0,
    } as never);
  }
  start(outer, outer);
  start(dialog, dialog.firstElementChild!);
  dialog.remove();
  start(outer, outer.firstElementChild!);
  document.body.append(dialog);
  const range = document.createRange();
  range.selectNodeContents(dialog.lastChild!);
  window.getSelection()!.addRange(range);
  start(dialog, dialog);
  expect(
    listen.mock.calls.filter(([type]) => type === 'pointermove')
  ).toHaveLength(0);
  window.getSelection()!.removeAllRanges();
  listen.mockRestore();
});
it('recovers defaults independently and preserves learning by gesture ID', () => {
  expect(
    normalize({ panels: false, navigation: 1, sensitivity: 'extreme' })
  ).toEqual({ ...defaults, panels: false });
  expect(normalize(null)).toEqual(defaults);
  repeatTraining();
  remember('tabs');
  remember('period');
  updateControls({ hints: false });
  expect(familiar('period')).toBe(true);
  expect(familiar('back')).toBe(false);
  repeatTraining();
  expect(familiar('tabs')).toBe(false);
});
