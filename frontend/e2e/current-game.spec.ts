import { test, expect } from "@playwright/test";
import { calendarDate } from "../src/gameDate";

test("date-only formatting is independent of timezone", () => {
  for (const [iso, label] of [
    ["2026-10-08", "8 октября 2026 года"],
    ["2026-10-09", "9 октября 2026 года"],
    ["2024-02-29", "29 февраля 2024 года"],
  ])
    expect(calendarDate(iso, "long", "ru-RU")).toBe(label);
});

test("calendar, genealogy, policy and weather stay save-scoped and responsive", async ({
  page,
  request,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const selected = await (await request.post("/test/family-seed")).json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    selected,
  );
  if (info.project.name === "mobile")
    await page.setViewportSize({ width: 360, height: 800 });
  for (const skin of ["graphite", "parchment"]) {
    await request.put(`/api/worlds/${selected.world}/presentation`, {
      data: { theme_id: skin },
    });
    await page.goto("/");
    await page.locator(".current-game-entry button").click();
    const menu = page.getByRole("dialog");
    const tabs = menu.getByRole("navigation", { name: "Разделы текущей игры" });
    await tabs
      .getByRole("button", { name: "Родословная", exact: true })
      .click();
    const family=page.locator(".save-workspace");
    await expect(family.locator(".react-flow__node").first()).toBeVisible();
    // PR #120 makes all canonical families public, independent of Knowledge.
    await expect(family.getByLabel("Семья персонажа").locator('option[value="qa_zoya"]')).toContainText("Зоя");
    await family.getByLabel("Семья персонажа").selectOption("qa_zoya");
    await expect(family.locator(".family-node").filter({hasText:"Зоя"})).toBeVisible();
    await family.getByRole("button", { name: "Вся семья", exact: true }).click();
    await page.screenshot({
      path: info.outputPath(`family-${skin}.png`),
      animations: "disabled",
    });
    await page.keyboard.press("Escape");
    await page.locator(".current-game-entry button").click();
    await tabs.getByRole("button", { name: "Настройки", exact: true }).click();
    await menu.getByLabel("Показывать изменения отношений").uncheck();
    expect(
      await page.evaluate(() => localStorage.getItem("relationship-notices")),
    ).toBe("off");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  }
  const calendar = selected;
  const before = await (
    await request.get(`/api/saves/${calendar.save}`)
  ).json();
  await page.locator(".current-game-entry button").click();
  const menu = page.getByRole("dialog");
  const tabs = menu.getByRole("navigation", { name: "Разделы текущей игры" });
  await tabs.getByRole("button", { name: "Календарь", exact: true }).click();
  const calendarArea=page.locator(".save-workspace");
  await expect(calendarArea.locator(".rdp-root")).toBeVisible();
  await expect(calendarArea).toContainText("Октябрь 2026");
  await page.screenshot({
    path: info.outputPath("calendar.png"),
    animations: "disabled",
  });
  await calendarArea.getByLabel("Следующий месяц", { exact: true }).click();
  await expect(calendarArea).toContainText("Ноябрь 2026");
  await calendarArea.getByRole("button", { name: "Год", exact: true }).click();
  await expect(calendarArea.locator(".calendar-mini")).toHaveCount(12);
  const after = await (await request.get(`/api/saves/${calendar.save}`)).json();
  expect(after.revision).toBe(before.revision);
  expect(after.state.world_clock.minute).toBe(before.state.world_clock.minute);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});

test("one phone device preserves unsent chat drafts across collapse and modal", async ({
  page,
  request,
}, info) => {
  const selected = await (
    await request.post("/test/phone-seed?unread=true")
  ).json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    selected,
  );
  await page.emulateMedia({ reducedMotion: "reduce" });
  if (info.project.name === "mobile")
    await page.setViewportSize({ width: 393, height: 850 });
  await page.goto("/");
  await expect(page.locator(".phone-led")).toBeVisible();
  const device = page.getByTestId("phone-device");
  await device.evaluate(
    (el) => ((el as HTMLElement).dataset.identity = "same"),
  );
  await page.screenshot({
    path: info.outputPath("phone-resting.png"),
    animations: "disabled",
  });
  await page.getByRole("button", { name: /^Телефон/ }).click();
  const phone = page.getByRole("region", { name: "Телефон персонажа" });
  await phone.getByRole("button",{name:"Вера работа",exact:true}).click();
  await phone
    .locator(".phone-row")
    .filter({ hasText: "Вера работа" })
    .getByRole("button", { name: "Написать", exact: true })
    .click();
  await phone.getByLabel("Сообщение в телефоне").fill("Несохранённый ответ");
  await page.screenshot({
    path: info.outputPath("phone-expanded.png"),
    animations: "disabled",
  });
  await phone
    .getByRole("button", { name: "К перепискам", exact: true })
    .click();
  await phone.locator(".phone-row").filter({ hasText: "Вера работа" }).click();
  await expect(phone.getByLabel("Сообщение в телефоне")).toHaveValue(
    "Несохранённый ответ",
  );
  await page.keyboard.press("Escape");
  await expect(device).toHaveAttribute("data-identity", "same");
  await page.getByRole("button", { name: /^Телефон/ }).click();
  await expect(phone.getByLabel("Сообщение в телефоне")).toHaveValue(
    "Несохранённый ответ",
  );
  await page.locator(".current-game-entry button").click();
  await expect(device).not.toHaveClass(/is-open/);
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: /^Телефон/ }).click();
  await expect(phone.getByLabel("Сообщение в телефоне")).toHaveValue(
    "Несохранённый ответ",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("incapacitation blocks keyboard and submit while observation remains available", async ({
  page,
  request,
}) => {
  const selected = await (
    await request.post("/test/family-seed?checkpoint=family-incapacitated")
  ).json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    selected,
  );
  await page.goto("/");
  const before = await (
    await request.get(`/api/saves/${selected.save}`)
  ).json();
  const input = page.getByLabel("Своё действие или реплика");
  await expect(input).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Отправить действие", exact: true }),
  ).toBeDisabled();
  await input.dispatchEvent("keydown", { key: "Enter", ctrlKey: true });
  expect(
    (await (await request.get(`/api/saves/${selected.save}`)).json()).turns,
  ).toHaveLength(before.turns.length);
  await page
    .getByRole("button", {
      name: "Продолжить наблюдать за героем",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("button", { name: "Продолжить наблюдать", exact: true }),
  ).toBeVisible();
  const after = await (await request.get(`/api/saves/${selected.save}`)).json();
  expect(after.state.controlled_actor_id).toBeNull();
  expect(after.state.protagonist_id).toBe(before.state.protagonist_id);
});

test("death automatically opens mandatory continuation and Escape cannot dismiss it", async ({
  page,
  request,
}) => {
  const response = await request.post("/test/family-seed?dead=true");
  expect(response.ok()).toBeTruthy();
  const selected = await response.json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    selected,
  );
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Смена главного героя", exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("heading", { name: "Смена главного героя", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Отмена", exact: true }),
  ).toBeDisabled();
  await page.getByLabel("Новый главный герой").selectOption("qa_vera");
  await page.getByRole("button", { name: "Проверить и посмотреть" }).click();
  await page.getByRole("button", { name: "Подтвердить смену" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(
    (await (await request.get(`/api/saves/${selected.save}`)).json()).state
      .protagonist_id,
  ).toBe("qa_vera");
});

test("explicit climate survives reload and matches the canonical calendar", async ({
  page,
  request,
}) => {
  const selected = await (await request.post("/test/family-seed")).json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    selected,
  );
  await page.goto("/");
  await page.locator(".current-game-entry button").click();
  const menu = page.getByRole("dialog");
  await menu.getByRole("button", { name: "Настройки", exact: true }).click();
  await menu.getByText("Климат и погода", { exact: true }).click();
  const before = await (
    await request.get(`/api/saves/${selected.save}`)
  ).json();
  const location =
    before.state.locations.find(
      (l: any) => l.name === before.state.scene_meta.location,
    )?.id || before.state.locations[0].id;
  await menu.getByLabel("Регион климата").selectOption(location);
  await menu
    .getByRole("button", { name: "Установить климат", exact: true })
    .click();
  await expect(menu.getByText(/Климат установлен/)).toBeVisible();
  await page.keyboard.press("Escape");
  const configured = await (
    await request.get(`/api/saves/${selected.save}`)
  ).json();
  await page.reload();
  expect(
    (await (await request.get(`/api/saves/${selected.save}`)).json()).state
      .scene_meta.weather,
  ).toEqual(configured.state.scene_meta.weather);
  await page.locator(".current-game-entry button").click();
  await menu.getByRole("button", { name: "Календарь", exact: true }).click();
  await expect(page.locator(".save-workspace .weather-badge").first()).toBeVisible();
});

test('phone leaves composer reachable with keyboard-sized viewport and enlarged text',async({page,request},info)=>{
 const selected=await(await request.post('/test/phone-seed?unread=true')).json();
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selected);
 await page.emulateMedia({reducedMotion:'reduce'});
 await page.setViewportSize({width:393,height:500});await page.goto('/');
 await page.getByRole('button',{name:/^Телефон/}).click();
 await expect(page.getByRole('region',{name:'Телефон персонажа'})).toBeVisible();
 await expect.poll(async()=>{const device=await page.getByTestId('phone-device').boundingBox();const composer=await page.locator('.composer').boundingBox();return !!device&&!!composer&&device.y>=0&&device.y+device.height<=composer.y;}).toBe(true);
 await page.screenshot({path:info.outputPath('phone-short-viewport.png'),animations:'disabled'});
 await page.keyboard.press('Escape');await expect(page.getByRole('button',{name:/^Телефон/})).toBeFocused();
 await page.setViewportSize({width:820,height:1000});
 await page.locator('.current-game-entry button').click();
 await page.getByRole('dialog').getByRole('button',{name:'Календарь',exact:true}).click();
 await expect(page.locator('.rdp-root')).toBeVisible();
 await page.evaluate(()=>document.documentElement.style.fontSize='20px');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:info.outputPath('calendar-tablet-large-text.png'),animations:'disabled'});
 await page.keyboard.press('Escape');await expect(page.locator('.current-game-entry button')).toBeFocused();
});
