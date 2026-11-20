import type { CDPSession, Locator, Page } from '@playwright/test';

export type Finger = { x: number; y: number; id?: number };
export async function contact(
  session: CDPSession,
  type: 'touchStart' | 'touchMove' | 'touchEnd' | 'touchCancel',
  ...touchPoints: Finger[]
) {
  await session.send('Input.dispatchTouchEvent', { type, touchPoints });
}
export async function swipe(
  page: Page,
  element: Locator,
  dx: number,
  dy: number,
  options: { cancel?: boolean; hold?: number; from?: number } = {}
) {
  await element.scrollIntoViewIfNeeded();
  const box = (await element.boundingBox())!;
  const x = box.x + box.width * (options.from ?? 0.5),
    y = box.y + Math.min(box.height / 2, 30);
  const c = await page.context().newCDPSession(page);
  try {
    await contact(c, 'touchStart', { x, y });
    if (options.hold) await page.waitForTimeout(options.hold);
    for (let i = 1; i <= 6; i++)
      await contact(c, 'touchMove', {
        x: x + (dx * i) / 6,
        y: y + (dy * i) / 6,
      });
    await contact(c, options.cancel ? 'touchCancel' : 'touchEnd');
  } finally {
    await c.detach();
  }
}
export async function pinch(page: Page, element: Locator) {
  await element.scrollIntoViewIfNeeded();
  const r = (await element.boundingBox())!,
    x = r.x + r.width / 2,
    y = r.y + r.height / 2;
  const session = await page.context().newCDPSession(page);
  const points = (d: number) => [
    { x: x - d, y, id: 1 },
    { x: x + d, y, id: 2 },
  ];
  try {
    await contact(session, 'touchStart', ...points(20));
    for (const d of [25, 35, 45, 55])
      await contact(session, 'touchMove', ...points(d));
    await contact(session, 'touchEnd');
  } finally {
    await session.detach();
  }
}
