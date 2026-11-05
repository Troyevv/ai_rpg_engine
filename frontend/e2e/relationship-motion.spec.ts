import { test, expect, type APIRequestContext, type Locator, type Page } from "@playwright/test";
import { nav, pickCharacter } from "./navigation";
import { themes } from "../src/lib/skins";

async function seed(page: Page, request: APIRequestContext) {
  const selection = await (await request.post("/test/seed")).json();
  let save = await (await request.get(`/api/saves/${selection.save}`)).json();
  const source = save.state.controlled_actor_id;
  const target = save.state.characters.find((c: { id: string }) => c.id !== source).id;
  const path = `/api/saves/${selection.save}/characters/${source}/relationships`;
  const dimensions = { trust: 64, affection: -60, respect: 0, fear: -100, attraction: 100 };
  const response = await request.patch(path, { data: {
    revision: save.revision, target_id: target, context: "Проверка шкал", dimensions,
  } });
  expect(response.ok()).toBeTruthy();
  save = await response.json();
  await page.addInitScript(s => localStorage.setItem("selection", JSON.stringify(s)), selection);
  await page.goto("/");
  await nav(page, "Мир");
  await nav(page, "Персонажи");
  await page.getByRole("tab", { name: "Отношения", exact: true }).click();
  const card = page.locator(`.character-profile .relationship-card[data-source="${source}"][data-target="${target}"]`);
  await expect(card).toBeVisible();
  await card.locator(".inspector-metrics").scrollIntoViewIfNeeded();
  return { selection, save, source, target, path, dimensions, card };
}

async function settled(card: Locator) {
  await expect.poll(() => card.locator(".relationship-meter").evaluateAll(tracks => tracks.map(track => {
    const reveal = track.querySelector(".relationship-meter-reveal")!;
    const fill = track.querySelector(".relationship-meter-fill")!;
    const scale = new DOMMatrixReadOnly(getComputedStyle(reveal).transform).a;
    return [scale, new DOMMatrixReadOnly(getComputedStyle(fill).transform).a];
  }))).toEqual([[1, .82], [1, .2], [1, .5], [1, 0], [1, 1]]);
}

// Inspect real browser animation timelines AND rendered frames, not only classes.
async function cascade(card: Locator) {
  const reveals = card.locator(".relationship-meter-reveal");
  await expect.poll(() => reveals.evaluateAll(nodes => nodes.filter(n => n.getAnimations().length).length)).toBe(5);
  const timing = await reveals.evaluateAll(nodes => nodes.map(n => {
    const animation = n.getAnimations()[0];
    const timing = animation.effect!.getTiming();
    animation.pause();
    animation.currentTime = 180;
    return { duration: timing.duration, delay: timing.delay, easing: getComputedStyle(n).animationTimingFunction };
  }));
  expect(timing.map(t => t.duration)).toEqual([1050, 1050, 1050, 1050, 1050]);
  expect(timing.map(t => t.delay)).toEqual([0, 90, 180, 270, 360]);
  expect(timing.every(t => t.easing === "cubic-bezier(0.22, 1, 0.36, 1)")).toBe(true);
  const scales = await reveals.evaluateAll(nodes => nodes.map(n => new DOMMatrixReadOnly(getComputedStyle(n).transform).a));
  expect(scales[0]).toBeGreaterThan(scales[1]);
  expect(scales[0]).toBeLessThan(1);
  expect(scales[1]).toBeGreaterThan(0);
  expect(scales.slice(2)).toEqual([0, 0, 0]);
  // Resume the real timeline and record actual changing layout bounds per frame.
  const frames = await card.locator(".relationship-meter").first().evaluate(async track => {
    const reveal = track.querySelector(".relationship-meter-reveal")!;
    const fill = track.querySelector(".relationship-meter-fill")!;
    const animation = reveal.getAnimations()[0];
    animation.play();
    const samples: number[] = [];
    const until = performance.now() + 250;
    do {
      await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
      samples.push(fill.getBoundingClientRect().width / track.getBoundingClientRect().width);
    } while (performance.now() < until);
    return samples;
  });
  expect(frames.at(-1)!).toBeGreaterThan(frames[0]);
  expect(frames.every(v => v > 0 && v < .82)).toBe(true);
  await reveals.evaluateAll(nodes => nodes.forEach(n => n.getAnimations().forEach(a => a.play())));
  await settled(card);
}

test("cascade, stable rerenders, reopen, fast selection and refreshing values", async ({ page, request }, info) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  if (info.project.name === "mobile") await page.setViewportSize({ width: 360, height: 800 });
  const { card, source, target, path, dimensions, selection } = await seed(page, request);
  await cascade(card);
  // A query rerenders the card but leaves the same selected row mounted.
  await page.getByLabel("Поиск отношений").fill("Проверка");
  await expect(card.locator(".relationship-meter-reveal").first()).toHaveCSS("transform", "matrix(1, 0, 0, 1, 0, 0)");
  expect(await card.locator(".relationship-meter-reveal").evaluateAll(nodes => nodes.some(n => n.getAnimations().length))).toBe(false);
  await page.getByLabel("Поиск отношений").fill("");
  await page.getByRole("tab", { name: "Обзор", exact: true }).click();
  await page.getByRole("tab", { name: "Отношения", exact: true }).click();
  await card.locator(".inspector-metrics").scrollIntoViewIfNeeded();
  await cascade(card);
  for (const id of [target, source, target, source]) await pickCharacter(page, id);
  await page.getByRole("tab", { name: "Отношения", exact: true }).click();
  await card.locator(".inspector-metrics").scrollIntoViewIfNeeded();
  await settled(card);
  // Apply through the existing UI while a fresh entry animation is running.
  await page.getByRole("tab", { name: "Обзор", exact: true }).click();
  await page.getByRole("tab", { name: "Отношения", exact: true }).click();
  await card.locator("summary").click();
  await card.getByRole("button", { name: "Редактировать", exact: true }).click();
  const form = page.locator(".relationship-dialog");
  await form.getByLabel("Доверие", { exact: true }).fill("-80");
  await form.getByLabel("Привязанность", { exact: true }).fill("");
  await form.getByRole("button", { name: "Сохранить", exact: true }).click();
  await expect(form).toHaveCount(0);
  await card.locator(".inspector-metrics").scrollIntoViewIfNeeded();
  await expect(card.locator('[data-dimension="trust"] meter')).toHaveAttribute("value", "-80");
  await expect(card.locator('[data-dimension="affection"]')).toHaveCount(0);
  await expect(card.locator('[data-dimension="trust"] .relationship-meter-fill')).toHaveCSS("transform", "matrix(0.1, 0, 0, 1, 0, 0)");
  // Restore fixture values, then reload to exercise asynchronously loaded data.
  const latest = await (await request.get(`/api/saves/${selection.save}`)).json();
  const restored = await request.patch(path, { data: { revision: latest.revision, target_id: target, context: "Проверка шкал", dimensions } });
  expect(restored.ok(), await restored.text()).toBeTruthy();
  await page.reload();
  await nav(page, "Мир");
  await nav(page, "Отношения");
  const overview = page.locator(`.relationship-card[data-source="${source}"][data-target="${target}"]`).filter({ visible: true }).first();
  await overview.locator(".inspector-metrics").scrollIntoViewIfNeeded();
  await cascade(overview);
  await nav(page, "Мир"); // kept-mounted section is hidden, not destroyed
  await expect(overview).toHaveCount(0);
  await expect(page.locator(".relationship-meter[data-visible=\"true\"]")).toHaveCount(0);
  await nav(page, "Отношения");
  await overview.locator(".inspector-metrics").scrollIntoViewIfNeeded();
  await cascade(overview);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await overview.screenshot({ path: info.outputPath("relationship-meters.png") });
});

test("reduced motion stays final in every skin, including live preference changes", async ({ page, request }, info) => {
  test.setTimeout(120_000);
  await page.emulateMedia({ reducedMotion: "reduce" });
  if (info.project.name === "mobile") await page.setViewportSize({ width: 393, height: 851 });
  const { selection, card, save } = await seed(page, request);
  for (const theme of themes) {
    const response = await request.put(`/api/worlds/${selection.world}/presentation`, { data: { theme_id: theme.id } });
    expect(response.ok()).toBeTruthy();
    await page.reload();
    await nav(page, "Мир");
    await nav(page, "Персонажи");
    await page.getByRole("tab", { name: "Отношения", exact: true }).click();
    await card.locator(".inspector-metrics").scrollIntoViewIfNeeded();
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme.id);
    await settled(card);
    const styles = await card.locator(".relationship-meter").evaluateAll(nodes => nodes.map(node => {
      const reveal = node.querySelector(".relationship-meter-reveal")!;
      const fill = node.querySelector(".relationship-meter-fill")!;
      return { animation: getComputedStyle(reveal).animationName, transition: getComputedStyle(fill).transitionDuration, color: getComputedStyle(fill).backgroundColor };
    }));
    expect(styles.every(s => s.animation === "none" && s.transition === "0s" && s.color !== "rgba(0, 0, 0, 0)")).toBe(true);
    await expect(card.getByRole("meter")).toHaveCount(5);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.getByRole("tab", { name: "Обзор", exact: true }).click();
  await page.getByRole("tab", { name: "Отношения", exact: true }).click();
  await card.locator(".inspector-metrics").scrollIntoViewIfNeeded();
  await page.emulateMedia({ reducedMotion: "reduce" });
  await settled(card);
  expect(await card.locator(".relationship-meter-reveal").evaluateAll(nodes => nodes.some(n => n.getAnimations().length))).toBe(false);
  const after = await (await request.get(`/api/saves/${selection.save}`)).json();
  expect(after.state.world.relationships).toEqual(save.state.world.relationships);
});
