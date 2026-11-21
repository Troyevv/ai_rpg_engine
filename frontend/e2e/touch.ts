import type { Locator, Page } from '@playwright/test';

export async function scrollByTouch(
  page: Page,
  element: Locator,
  dy: number,
  options: { from?: number } = {}
) {
  await element.scrollIntoViewIfNeeded();
  const box = (await element.boundingBox())!;
  const x = box.x + box.width * (options.from ?? 0.5),
    y = box.y + Math.min(box.height / 2, 30);
  const c = await page.context().newCDPSession(page);
  try {
    await c.send('Input.dispatchTouchEvent', {type: 'touchStart', touchPoints: [{x, y}]});
    for (let i = 1; i <= 6; i++)
      await c.send('Input.dispatchTouchEvent', {type: 'touchMove', touchPoints: [{x, y: y + dy * i / 6}]});
    await c.send('Input.dispatchTouchEvent', {type: 'touchEnd', touchPoints: []});
  } finally {
    await c.detach();
  }
}
