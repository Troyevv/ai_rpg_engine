import {
  test,
  expect,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import { nav, actor } from "./navigation";
test.use({ video: "off" });
async function seed(
  page: Page,
  request: APIRequestContext,
  checkpoint = "ui-calendar",
) {
  const response = await request.post(
    `/test/ui-completion-seed?checkpoint=${checkpoint}`,
  );
  expect(response.ok()).toBeTruthy();
  const s = await response.json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    s,
  );
  return s;
}
test("155 real projection: event details, privacy, skins, responsive year and immutable browsing", async ({
  page,
  request,
}, info) => {
  const s = await seed(page, request);
  const before = await (await request.get(`/api/saves/${s.save}`)).json();
  for (const [skin, width] of [
    ["graphite", 1440],
    ["parchment", 360],
    ["graphite", 393],
    ["parchment", 820],
  ] as const) {
    await page.setViewportSize({ width, height: 960 });
    await request.put(`/api/worlds/${s.world}/presentation`, {
      data: { theme_id: skin },
    });
    await page.goto("/");
    await nav(page, "Календарь");
    const area = page.locator(".calendar-screen"),
      detail = area.getByRole("region", { name: "События дня" });
    await area
      .getByRole("button", { name: "Сегодня в игре", exact: true })
      .click();
    await expect(
      detail.getByText("Годовщина первой восстановленной карты", {
        exact: true,
      }),
    ).toBeVisible();
    for (const label of ["Завершено", "Отменено", "срок прошёл"])
      await expect(detail.getByText(label, { exact: false })).toBeVisible();
    await expect(area).not.toContainText("Скрытая личная дата");
    expect(
      await area.evaluate((el) => el.scrollWidth <= el.clientWidth),
    ).toBeTruthy();
    expect(
      await page
        .locator(".save-workspace")
        .evaluate((el) => el.scrollWidth <= el.clientWidth),
    ).toBeTruthy();
    await expect(detail).toContainText("10:00");
    await area.locator(".rdp-day_button[aria-pressed=true]").focus();
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("Enter");
    await expect(
      area.locator(".rdp-day_button[aria-pressed=true]"),
    ).toBeFocused();
    await expect(detail).toContainText("9 октября");
    await area
      .getByRole("button", { name: "Сегодня в игре", exact: true })
      .click();
    await area
      .locator(".rdp-day_button")
      .filter({
        has: page.locator(".calendar-day-number", { hasText: /^10$/ }),
      })
      .click();
    await expect(detail).toContainText("Каникулы Аси.");
    await expect(detail).toContainText(
      "10 октября 2026 года → 17 октября 2026 года",
    );
    await area
      .getByRole("button", { name: "Сегодня в игре", exact: true })
      .click();
    if (
      process.env.CALENDAR_VISUAL &&
      info.project.name === "desktop" &&
      (width === 1440 || width === 360)
    )
      await page.screenshot({ path: `/tmp/issue155-${width}.png` });
    await expect(area.locator(".calendar-event-count").first()).toHaveText(
      /\d+/,
    );
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    await area.getByRole("button", { name: "Год", exact: true }).click();
    await expect(area.locator(".calendar-mini")).toHaveCount(12);
    await expect(
      area
        .locator(".calendar-mini")
        .first()
        .locator(".calendar-mini-grid>small"),
    ).toHaveCount(7);
    if (
      process.env.CALENDAR_VISUAL &&
      info.project.name === "desktop" &&
      width === 360
    )
      await page.screenshot({ path: "/tmp/issue155-year.png" });
    await area
      .locator(".calendar-mini")
      .last()
      .getByRole("button")
      .first()
      .click();
    await expect(area.locator(".calendar-period h3")).toContainText("Декабрь");
    await area
      .getByRole("button", { name: "Следующий месяц", exact: true })
      .click();
    await expect(area.locator(".calendar-period h3")).toContainText(
      "Январь 2027",
    );
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
  }
  const after = await (await request.get(`/api/saves/${s.save}`)).json();
  expect(after.revision).toBe(before.revision);
  expect(after.state).toEqual(before.state);
});
test("155 custom calendar, year boundary, keyboard, navigation and reload preference", async ({
  page,
  request,
}) => {
  await seed(page, request, "ui-calendar-custom");
  await page.goto("/");
  await nav(page, "Календарь");
  const area = page.locator(".calendar-screen");
  await expect(area.locator(".custom-calendar>small")).toHaveCount(5);
  await expect(area.locator(".custom-calendar>button")).toHaveCount(25);
  await area.getByLabel("Следующий месяц", { exact: true }).click();
  await expect(area.locator(".calendar-period h3")).toHaveText("Свет · 43");
  await expect(area.locator(".custom-calendar>button")).toHaveCount(20);
  const day = area.locator(".custom-calendar>button").nth(9);
  await day.focus();
  await page.keyboard.press("Enter");
  await expect(day).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Вернуться в историю" }).click();
  await nav(page, "Календарь");
  await expect(area.locator(".calendar-detail h4")).toContainText("10 Свет");
  await page.reload();
  await nav(page, "Календарь");
  await expect(area.locator(".calendar-detail h4")).toContainText("10 Свет");
  await area.getByRole("button", { name: "Год", exact: true }).click();
  await expect(area.locator(".calendar-mini")).toHaveCount(2);
  await expect(
    area.locator(".calendar-mini").first().getByRole("button"),
  ).toHaveCount(20);
  await expect(
    area.locator(".calendar-mini").last().getByRole("button"),
  ).toHaveCount(25);
  await page.reload();
  await nav(page, "Календарь");
  await expect(area.locator(".calendar-mini")).toHaveCount(2);
  await area.getByLabel("Предыдущий год", { exact: true }).click();
  await expect(area.locator(".calendar-period h3")).toHaveText("42");
  await area
    .getByRole("button", { name: "Сегодня в игре", exact: true })
    .click();
  await expect(area.locator(".calendar-detail h4")).toContainText("25");
});
test("155 loading, failure retry, truncated data and long text at 200% with reduced motion", async ({
  page,
  request,
}) => {
  await seed(page, request);
  let mode = "error";
  let release: () => void = () => {};
  const gate = new Promise<void>((r) => (release = r));
  await page.route("**/calendar?*", async (route) => {
    if (mode === "error")
      return route.fulfill({
        status: 503,
        json: { detail: "Проверка ошибки календаря" },
      });
    if (mode === "wait") await gate;
    const response = await route.fetch();
    const data = await response.json();
    data.scheduled.truncated = true;
    if (data.events[0])
      data.events[0].name = "Длинное название памятного события ".repeat(20);
    await route.fulfill({ json: data });
  });
  await page.goto("/");
  await nav(page, "Календарь");
  const area = page.locator(".calendar-screen");
  await expect(area.getByRole("alert")).toContainText("Не удалось");
  mode = "wait";
  await area.getByRole("button", { name: "Повторить" }).click();
  await expect(area.getByText("Загрузка календаря…")).toBeVisible();
  await expect(area).not.toContainText("Известных событий нет.");
  release();
  await expect(area).toContainText("Список и индикаторы могут быть неполными.");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 720, height: 1000 });
  await page.evaluate(() => (document.documentElement.style.zoom = "2"));
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await area.getByLabel("Следующий месяц", { exact: true }).click();
  await expect(area).toContainText("В загруженной части событий нет.");
});
test("155 late actor response is discarded; revision refreshes projection", async ({
  page,
  request,
}) => {
  const s = await seed(page, request);
  await page.goto("/");
  await nav(page, "Календарь");
  const area = page.locator(".calendar-screen");
  await expect(area.locator(".calendar-detail article").first()).toBeVisible();
  let release: () => void = () => {};
  const gate = new Promise<void>((r) => (release = r));
  let intercepted = false;
  await page.route("**/calendar?*", async (route) => {
    if (intercepted) return route.continue();
    intercepted = true;
    const response = await route.fetch();
    const data = await response.json();
    data.events = [
      {
        id: "stale",
        date: "2026-11-01",
        kind: "observance",
        name: "STALE PRIVATE MARKER",
        character_ids: [],
      },
    ];
    await gate;
    await route.fulfill({ json: data }).catch(() => {});
  });
  await area.getByLabel("Следующий месяц", { exact: true }).click();
  await expect.poll(() => intercepted).toBeTruthy();
  await page.getByRole("button", { name: "Вернуться в историю" }).click();
  await actor(page, "qa_vera", "Вера Ларина");
  release();
  await nav(page, "Календарь");
  await expect(area.locator(".rdp-root")).toBeVisible();
  await expect(area).not.toContainText("STALE PRIVATE MARKER");
  await expect(area).not.toContainText(
    "Годовщина первой восстановленной карты",
  );
  const current = await (await request.get(`/api/saves/${s.save}`)).json();
  expect(current.revision).toBeGreaterThan(0);
});
test("155 Narrative Start Game, turn, calendar, save/reload, next turn", async ({
  page,
  request,
}) => {
  const s = await (await request.post("/test/seed")).json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    s,
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Начать игру", exact: true }).click();
  await expect(page.locator(".choices button")).toHaveCount(6);
  await page.locator(".choices button").first().click();
  await expect(page.locator(".turn")).toHaveCount(2);
  await expect(page.locator(".choices button")).toHaveCount(6);
  await nav(page, "Календарь");
  await expect(page.locator(".calendar-screen,.calendar-empty")).toBeVisible();
  await page.getByRole("button", { name: "Вернуться в историю" }).click();
  await page.reload();
  await expect(page.locator(".turn")).toHaveCount(2);
  await page.locator(".choices button").first().click();
  await expect(page.locator(".turn")).toHaveCount(3);
  await expect(page.locator(".choices button")).toHaveCount(6);
  const saved = await (await request.get(`/api/saves/${s.save}`)).json();
  expect(saved.revision).toBeGreaterThan(1);
});

test("155 Gregorian 28/29/30/31 days and selected leap day", async ({
  page,
  request,
}) => {
  const s = await seed(page, request);
  const saved = await (await request.get(`/api/saves/${s.save}`)).json();
  await page.goto("/");
  const key = `calendar-view:${s.save}:${saved.state.controlled_actor_id || "none"}`;
  for (const [month, day, count] of [
    ["2024-02", "29", 29],
    ["2026-02", "01", 28],
    ["2026-04", "01", 30],
    ["2026-12", "31", 31],
  ] as const) {
    await page.evaluate(
      ({ key, month, day }) =>
        localStorage.setItem(
          key,
          JSON.stringify({ month, selected: month + "-" + day, year: false }),
        ),
      { key, month, day },
    );
    await page.reload();
    await nav(page, "Календарь");
    const area = page.locator(".calendar-screen");
    await expect(area.locator(".rdp-day_button")).toHaveCount(count);
    await expect(
      area.locator(".rdp-day_button[aria-pressed=true] .calendar-day-number"),
    ).toHaveText(String(+day));
  }
});
