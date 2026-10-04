import { test, expect } from "@playwright/test";
import { build } from "esbuild";
import { canonicalDice } from "../src/tabletop/dice/canonical";
import type { Roll } from "../src/tabletop/types";
const roll = (die: number, raw: number[], advantage = 0, selected = raw[0]) =>
  ({
    expression: `${raw.length}d${die}`,
    raw,
    selected,
    advantage,
    modifier: 5,
    total: selected + 5,
    components: [{ die, raw, selected, sign: 1 }],
  }) as Roll;
test("canonical pools, percentile, modifiers and advantage selection", () => {
  expect(canonicalDice([roll(6, [2, 5])]).dice.map((d) => d.value)).toEqual([
    2, 5,
  ]);
  expect(
    canonicalDice([roll(20, [4, 18], 1, 18)]).dice.map((d) => d.muted),
  ).toEqual([true, false]);
  expect(
    canonicalDice([roll(20, [4, 18], -1, 4)]).dice.map((d) => d.muted),
  ).toEqual([false, true]);
  expect(canonicalDice([roll(100, [100])]).dice.map((d) => d.label)).toEqual([
    "00",
    "0",
  ]);
  expect(canonicalDice([roll(100, [47])]).dice.map((d) => d.label)).toEqual([
    "40",
    "7",
  ]);
  expect(canonicalDice([roll(6, Array(20).fill(3))])).toMatchObject({
    omitted: 8,
  });
  expect(canonicalDice([roll(20, [14])]).dice).toHaveLength(1);
});
for (const reduced of [false, true])
  test(`3D dice all solids, skip and reduced motion=${reduced}`, async ({
    page,
  }, info) => {
    await page.emulateMedia({
      reducedMotion: reduced ? "reduce" : "no-preference",
    });
    const bundled = await build({
      stdin: {
        contents: `import React from 'react';import {createRoot} from 'react-dom/client';import {DiceTray} from './src/tabletop/dice/DiceTray';import {renderDice} from './src/tabletop/dice/renderer';import {canonicalDice} from './src/tabletop/dice/canonical';globalThis.showPhysical=(rolls)=>{const host=document.getElementById('root');host.textContent='';renderDice(host,canonicalDice(rolls).dice,()=>host.dataset.rested='true')};globalThis.showDice=(rolls)=>{const host=document.getElementById('root');const root=createRoot(host);root.render(React.createElement(DiceTray,{rolls,done:()=>{root.unmount();host.textContent='Finished'}}));};`,
        resolveDir: process.cwd(),
        loader: "tsx",
      },
      bundle: true,
      write: false,
      format: "iife",
      loader: { ".css": "empty" },
      define: { "process.env.NODE_ENV": '"production"' },
    });
    await page.setContent(
      '<meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0;background:#171d24;color:white}#root{max-width:800px;width:100%}.tt-dice-surface{width:100%;height:220px}.tt-dice-values{display:flex;flex-wrap:wrap;gap:8px}.tt-die-muted{opacity:.4}</style><div id="root"></div>',
    );
    await page.addScriptTag({ content: bundled.outputFiles[0].text });
    await page.evaluate(
      (rolls) => (window as any).showDice(rolls),
      [4, 6, 8, 10, 12, 20, 100].map((d) => roll(d, [d])),
    );
    if (reduced) {
      await expect(page.locator("#root")).toHaveText("Finished");
      await expect(page.locator("canvas")).toHaveCount(0);
    } else {
      await expect(page.locator("canvas")).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Пропустить анимацию" }),
      ).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page.getByRole("button", { name: "Пропустить анимацию" }).click();
      await expect(page.locator("#root")).toHaveText("Finished");
      await page.evaluate(
        (rolls) => (window as any).showPhysical(rolls),
        [4, 6, 8, 10, 12, 20, 100].map((d) => roll(d, [d])),
      );
      await expect(page.locator("#root")).toHaveAttribute(
        "data-rested",
        "true",
      );
      await page.screenshot({
        path: `test-results/dice-${info.project.name}.png`,
      });
    }
  });
