import { test, expect } from "@playwright/test";

test("tabletop creation, manual roll, combat, reload and character sheet", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Настольная RPG", exact: true })
    .click();
  await page.getByRole("button", { name: "Создать настольную игру" }).click();
  await page.getByRole("button", { name: "Далее", exact: true }).click();
  await page.getByRole("button", { name: "Далее", exact: true }).click();
  await page.getByLabel("Название кампании").fill("Browser " + Date.now());
  await page.getByRole("button", { name: "Далее", exact: true }).click();
  await page.getByLabel("Имя героя").fill("Александр");
  await page.getByRole("button", { name: "Далее", exact: true }).click();
  await page.getByLabel("Взять Терона в партию").uncheck();
  await page.getByRole("button", { name: "Далее", exact: true }).click();
  await page.getByRole("button", { name: "Далее", exact: true }).click();
  await page.getByRole("button", { name: "Начать приключение" }).click();
  await expect(
    page.getByRole("button", { name: "Осмотреть сундук", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Осмотреть сундук", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Бросить кубик" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Начать бой", exact: true }),
  ).toBeDisabled();
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Бросить кубик" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Бросить кубик" }).click();
  await expect(page.getByRole("button", { name: "Бросить кубик" })).toHaveCount(
    0,
  );
  await page.getByRole("button", { name: "Начать бой", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Инициатива", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Бросить кубик" }).click();
  await expect(page.getByRole("region", { name: "Очередь боя" })).toBeVisible();
  await page.locator(".tt-shell").evaluate((el) => {
    el.scrollTop = 0;
  });
  await page.screenshot({
    path: `test-results/tabletop-${test.info().project.name}.png`,
    fullPage: true,
  });
  // Deterministic mechanics are covered by the API slice. This test uses actual RNG.
  // The initial goblin can deal at most 11 damage, so the 12-HP hero gets a turn.
  await page
    .getByRole("button", { name: "Атаковать: Гоблин-дозорный" })
    .click();
  await expect(
    page.getByRole("button", { name: "Бросить кубик" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Бросить кубик" }).click();
  await expect(
    page.getByRole("button", { name: "Сделать ход" }),
  ).not.toHaveText("Обработка…");
  // A hit requests a separate damage roll; a miss leaves the encounter ready.
  const current = await page.evaluate(async () => {
    const id = localStorage.getItem("tabletop-game");
    return (await fetch("/api/tabletop/games/" + id)).json();
  });
  if (current.state.pending) {
    await expect(
      page.getByRole("heading", { name: "Урон", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Бросить кубик" }).click();
  }
  await page
    .getByRole("navigation", { name: "Разделы настольной игры" })
    .getByRole("button", { name: "Персонаж", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Александр", exact: true, level: 1 }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Инвентарь", exact: true }).click();
  await expect(page.getByText("Кольчуга", { exact: true })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.getByRole("button", { name: "Вернуться к историям" }).click();
  await expect(
    page.getByRole("button", { name: "Настольная RPG", exact: true }),
  ).toBeVisible();
});
