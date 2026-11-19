import {expect, test, type Locator, type Page, type TestInfo} from '@playwright/test';
import {nav} from './navigation';
import {chooseOption} from './choice-navigation';

type Frame = {time: number; state: string | undefined; drawer: boolean; title: string; width: number;
  sameNodes: boolean; sameContent: boolean; scroll: number; menu: boolean; url: string};
declare global {interface Window {workshopCloseFrames: Frame[]}}

async function verifyExit(page: Page, dialog: Locator, opener: Locator, close: () => Promise<void>, info: TestInfo) {
  await expect(dialog).toHaveCSS('opacity', '1');
  await dialog.evaluate(node => {
    const scroller = document.querySelector('.ww-scroll')!;
    const title = node.querySelector('.dialog-title')!;
    const body = node.querySelector('.modal-body')!;
    const content = body.lastElementChild;
    const frames: Frame[] = [];
    window.workshopCloseFrames = frames;
    function sample() {
      if (!node.isConnected) return;
      frames.push({
        time: performance.now(), state: node.dataset.state, drawer: node.classList.contains('drawer'),
        title: title.textContent ?? '', width: node.getBoundingClientRect().width,
        sameNodes: node === document.querySelector('.atelier-dialog') && scroller === document.querySelector('.ww-scroll'),
        sameContent: content === body.lastElementChild && body.isConnected, scroll: scroller.scrollTop,
        menu: !!document.querySelector('.ww-menu-dialog'), url: location.href,
      });
      requestAnimationFrame(sample);
    }
    sample();
  });
  await close();
  await expect(dialog).toHaveCount(0);
  await expect(opener).toBeFocused();
  const frames = await page.evaluate(() => window.workshopCloseFrames);
  const first = frames[0];
  await info.attach(first.title + ' — кадры', {body: JSON.stringify(frames), contentType: 'application/json'});
  expect(frames.some(f => f.state === 'closed')).toBe(true);
  for (const frame of frames) {
    expect(frame).toMatchObject({drawer: first.drawer, title: first.title, sameContent: true,
      sameNodes: true, scroll: first.scroll, menu: false, url: first.url});
  }
}

for (const width of [360, 393]) test('Мастерская — выбор и последовательное закрытие панелей · '+width, async ({page}, info) => {
  test.skip(info.project.name !== 'mobile');
  await page.setViewportSize({width, height: 820});
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.goto('/');
  await nav(page, 'Создать');

  // Change the skin from the actual nested workshop menu.
  await page.getByRole('button', {name:'Разделы мастерской',exact:true}).click();
  await page.getByRole('button', {name:'Оформление',exact:true}).click();
  const skin = width === 360 ? 'parchment' : 'noir';
  await chooseOption(page.getByRole('combobox', {name:'Тема мира'}), skin);
  await expect(page.locator('html')).toHaveAttribute('data-theme', skin);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog',{name:'Оформление мастерской'})).toHaveCount(0);
  await page.keyboard.press('Escape');
  await expect(page.locator('.ww-menu-dialog')).toHaveCount(0);

  const dialog = page.locator('.atelier-dialog');
  const examples = page.getByRole('button',{name:'Примеры',exact:true});
  await examples.click();
  await verifyExit(page, dialog, examples, () => dialog.locator('.dialog-close').click(), info);

  for (const [group, label, option] of [
    ['Персонажи', 'Выразительность NPC', 'Реалистичная'],
    ['Мир и география', 'Тип мира', 'Альтернативная реальность'],
    ['Календарь и начало', 'Календарь начала игры', 'Григорианский'],
  ]) {
    const opener = page.locator('.atelier-param').filter({hasText: group});
    await opener.click();
    const field = dialog.getByRole('combobox',{name:label,exact:true});
    await expect(field).toHaveJSProperty('tagName','BUTTON');
    await field.tap();
    const list = page.getByRole('listbox');
    await expect(list).toHaveCSS('opacity','1');
    const bounds = (await list.boundingBox())!;
    expect(bounds.x).toBeCloseTo(0,0);
    expect(bounds.width).toBeCloseTo(width,0);
    expect(bounds.y + bounds.height).toBeCloseTo(820,0);
    expect(await list.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    if (group === 'Мир и география') {
      const path = info.outputPath('world-type-' + width + '.png');
      await page.screenshot({path, scale:'css'});
      await info.attach('Мир и география — '+width, {path, contentType:'image/png'});
    }
    await page.keyboard.press('Escape');
    await expect(field).toBeFocused();
    await field.tap();
    await page.touchscreen.tap(2, 2);
    await expect(list).toHaveCount(0);
    await expect(field).toBeFocused();
    await field.tap();
    await list.getByRole('option',{name:option,exact:true}).tap();
    await expect(field).toHaveText(option);
    await expect(field).toBeFocused();
    await verifyExit(page, dialog, opener, group === 'Персонажи' ? () => page.keyboard.press('Escape') :
      group === 'Мир и география' ? () => page.touchscreen.tap(2, 2) : () => dialog.locator('.dialog-close').tap(), info);
  }
});
