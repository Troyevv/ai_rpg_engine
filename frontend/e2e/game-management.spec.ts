import { test, expect } from "@playwright/test";
import { gameAction, nav } from "./navigation";

test("management tabs, search, keyboard, settings and external destinations survive reload", async ({
  page,
  request,
}, info) => {
  const selected = await (await request.post("/test/family-seed")).json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    selected,
  );
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const skin of ["graphite", "parchment"]) {
    await request.put(`/api/worlds/${selected.world}/presentation`, {
      data: { theme_id: skin },
    });
    await page.goto("/");
    for (const width of info.project.name === "mobile"
      ? [360, 393]
      : [1440, 900, 768]) {
      await page.setViewportSize({ width, height: 900 });
      await page.locator(".current-game-entry button").click();
      const dialog = page.getByRole("dialog");
      const tabs = dialog.getByRole("tablist");
      await expect(tabs.getByRole("tab")).toHaveText([
        "Время",
        "Персонажи",
        "Хронология",
        "Настройки",
      ]);
      await tabs.getByRole("tab", { name: "Время", exact: true }).click();
      await page.keyboard.press("ArrowRight");
      await expect(
        tabs.getByRole("tab", { name: "Персонажи", exact: true }),
      ).toBeFocused();
      await dialog.getByLabel("Поиск персонажей").fill("НЕСУЩЕСТВУЮЩИЙ");
      await expect(
        dialog.getByText("Персонажи не найдены. Попробуй другое имя."),
      ).toBeVisible();
      await dialog.getByRole("button", { name: "Сбросить поиск" }).click();
      await expect(
        dialog.locator(".current-character-list button").first(),
      ).toBeVisible();
      await tabs.getByRole("tab", { name: "Настройки", exact: true }).click();
      await expect(
        dialog.getByText("Настраивается до начала игры."),
      ).toBeVisible();
      const toggle = dialog.getByRole("switch");
      await toggle.uncheck();
      await expect(toggle).not.toBeChecked();
      await page.evaluate(
        () => (document.documentElement.style.fontSize = "32px"),
      );
      expect(
        await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth),
      ).toBe(true);
      expect(
        await page
          .locator(".current-game-content")
          .evaluate((el) => el.scrollWidth <= el.clientWidth),
      ).toBe(true);
      await page.evaluate(() => (document.documentElement.style.fontSize = ""));
      await page.keyboard.press("Escape");
      await expect(page.locator(".current-game-entry button")).toBeFocused();
    }
  }
  for (const name of ["Календарь", "Родословная"]) {
    await page.reload();
    await nav(page, name);
    await expect(page.locator(".save-workspace")).toBeVisible();
    await page.keyboard.press("Escape");
  }
  await page.locator(".current-game-entry button").click();
  await page.getByRole("tab", { name: "Персонажи", exact: true }).click();
  const person = page.locator(".current-character-list button").first();
  await person.click();
  await expect(page.locator(".current-game-panel")).toHaveCount(0);
  await expect(page.locator(".inspector-workspace")).toBeVisible();
  await page.keyboard.press("Escape");
  expect(errors).toEqual([]);
});

test("chronology uses visible projection, handles errors, groups dates and expands text", async ({
  page,
  request,
}) => {
  const selected = await (await request.post("/test/family-seed")).json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    selected,
  );
  let fail = true;
  const text = "Длинное известное событие. ".repeat(15);
  await page.route("**/milestones?*", async (route) => {
    await route.fulfill({
      status: fail ? 503 : 200,
      json: fail
        ? { detail: "Временная ошибка" }
        : [
            {
              id: "visible",
              summary: text,
              minute: 0,
              date: "2026-10-08",
              actor_ids: [],
              category: "marriage",
            },
          ],
    });
  });
  await page.goto("/");
  await page.locator(".current-game-entry button").click();
  await page.getByRole("tab", { name: "Хронология", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Временная ошибка");
  fail = false;
  await page.getByRole("button", { name: "Повторить загрузку" }).click();
  await expect(page.locator(".management-timeline h4")).toHaveText(
    "8 октября 2026 года",
  );
  await page.locator(".management-timeline summary").click();
  await expect(page.locator(".management-timeline article p")).toHaveText(
    text.trim(),
  );
  await page.getByLabel("События персонажа").selectOption({ index: 1 });
  await expect(page.locator(".management-timeline article")).toHaveCount(1);
});

test("advance invalidates stale preview and preserves request after launch error", async ({
  page,
  request,
}) => {
  const selected = await (await request.post("/test/long-term-seed")).json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    selected,
  );
  await page.goto("/");
  await gameAction(page, "Длительный переход");
  const dialog = page.getByRole("dialog");
  const submit = dialog.getByRole("button", {
    name: "Подтвердить длительный переход",
  });
  await expect(submit).toBeEnabled();
  await dialog.getByText(/Подробности симуляции/).click();
  await dialog.getByLabel("Лимит обращений к модели").fill("0");
  await dialog.getByLabel("Единица перехода").selectOption("weeks");
  await dialog.getByLabel("Количество единиц перехода").fill("");
  await expect(submit).toBeDisabled();
  await dialog.getByLabel("Количество единиц перехода").fill("2");
  await dialog.getByLabel("Причина").fill("Долгое ожидание");
  await expect(submit).toBeEnabled();
  await page.route("**/long-term", (r) =>
    r.fulfill({
      status: 503,
      json: { detail: "Не удалось запустить переход" },
    }),
  );
  await submit.click();
  await expect(dialog.getByRole("alert")).toContainText(
    "Не удалось запустить переход",
  );
  await expect(dialog.getByLabel("Причина")).toHaveValue("Долгое ожидание");
  await expect(dialog.getByLabel("Количество единиц перехода")).toHaveValue(
    "2",
  );
  await page.unroute("**/long-term");
  await submit.click();
  await expect(dialog).toHaveCount(0);
  await expect(
    page.locator(".skip-diagnostics").filter({ hasText: "Длительный переход" }),
  ).toBeVisible();
  await page.reload();
  const save = await (await request.get(`/api/saves/${selected.save}`)).json();
  expect(save.state.last_long_term_advance.llm_calls).toBe(0);
});

test("ordinary time skip commits and remains independent of long-term advance", async ({
  page,
  request,
}) => {
  const selected = await (await request.post("/test/seed")).json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    selected,
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Начать игру", exact: true }).click();
  await expect(page.locator(".choices button")).toHaveCount(6);
  const before = await (
    await request.get(`/api/saves/${selected.save}`)
  ).json();
  await gameAction(page, "Пропустить время");
  await page.getByRole("button", { name: "+10 мин", exact: true }).click();
  await page
    .getByRole("button", { name: "Пропустить 0 ч 10 мин", exact: true })
    .click();
  await expect(page.locator(".turn")).toHaveCount(2);
  await page.reload();
  const after = await (await request.get(`/api/saves/${selected.save}`)).json();
  expect(after.state.world_clock.minute - before.state.world_clock.minute).toBe(
    10,
  );
  expect(after.state.last_long_term_advance).toEqual(
    before.state.last_long_term_advance,
  );
  await gameAction(page, "Длительный переход");
  await expect(page.getByRole("alert")).toContainText(
    "Для месяцев и лет нужна установленная дата календаря",
  );
  await page.getByLabel("Единица перехода").selectOption("weeks");
  await expect(page.getByRole("alert")).toContainText(
    "До 7 суток используй обычный пропуск времени",
  );
  await page.getByLabel("Количество единиц перехода").fill("2");
  await expect(
    page.getByRole("button", { name: "Подтвердить длительный переход" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Отмена", exact: true }).click();
  await expect(page.locator(".current-game-entry button")).toBeFocused();
});

test("late advance preview cannot enable confirmation for changed input", async ({
  page,
  request,
}) => {
  const selected = await (await request.post("/test/long-term-seed")).json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    selected,
  );
  let release!: () => void;
  const held = new Promise<void>((r) => (release = r));
  let waiting = false;
  let delivered = false;
  await page.route("**/long-term/preview", async (route) => {
    const body = route.request().postDataJSON();
    if (body.amount === 2) {
      waiting = true;
      await held;
    }
    const response = await route.fetch();
    await route.fulfill({ response });
    if (body.amount === 2) delivered = true;
  });
  await page.goto("/");
  await gameAction(page, "Длительный переход");
  const dialog = page.getByRole("dialog");
  const submit = dialog.getByRole("button", {
    name: "Подтвердить длительный переход",
  });
  await expect(submit).toBeEnabled();
  await dialog.getByLabel("Количество единиц перехода").fill("2");
  await expect.poll(() => waiting).toBe(true);
  await expect(submit).toBeDisabled();
  await dialog.getByLabel("Количество единиц перехода").fill("3");
  await expect(submit).toBeEnabled();
  const current = await dialog.locator(".advance-destination").innerText();
  release();
  await expect.poll(() => delivered).toBe(true);
  await expect(dialog.locator(".advance-destination")).toHaveText(current, {
    useInnerText: true,
  });
  await expect(dialog.getByLabel("Количество единиц перехода")).toHaveValue(
    "3",
  );
  await dialog.getByRole("button", { name: "Отмена", exact: true }).click();
});

test("long character names and weather retry fit mobile and enlarged text", async ({
  page,
  request,
}) => {
  const selected = await (await request.post("/test/family-seed")).json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    selected,
  );
  await page.route(`**/api/saves/${selected.save}`, async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.state.characters[0].name =
      "Александр Александрович Оченьдлиннаяфамилия".repeat(4);
    await route.fulfill({ response, json: body });
  });
  let weatherError = true;
  await page.route("**/weather", (route) =>
    route.fulfill({
      status: weatherError ? 503 : 200,
      json: weatherError ? { detail: "Погода недоступна" } : null,
    }),
  );
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto("/");
  await page.locator(".current-game-entry button").click();
  await page.getByRole("tab", { name: "Персонажи", exact: true }).click();
  await page.evaluate(() => (document.documentElement.style.fontSize = "32px"));
  expect(
    await page
      .locator(".current-game-content")
      .evaluate((el) => el.scrollWidth <= el.clientWidth),
  ).toBe(true);
  await page.getByRole("tab", { name: "Настройки", exact: true }).click();
  await page.getByText("Климат и погода", { exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Погода недоступна");
  weatherError = false;
  await page.getByRole("button", { name: "Повторить загрузку погоды" }).click();
  await expect(page.getByLabel("Регион климата")).toBeVisible();
  expect(
    await page
      .locator(".current-game-content")
      .evaluate((el) => el.scrollWidth <= el.clientWidth),
  ).toBe(true);
});
