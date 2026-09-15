import { test, expect } from "@playwright/test";

test("scenario → summary → world → save → start → action → regenerate → rollback", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page
    .getByRole("button", { name: "Настройки", exact: true })
    .last()
    .click();
  for (const key of ["idea", "summary", "game"])
    await page.getByLabel("Провайдер " + key).selectOption("deepseek");
  await page.getByLabel("API-ключ DeepSeek").fill("fixture-key");
  await page.getByRole("button", { name: "Сохранить настройки" }).click();
  await page.getByRole("button", { name: "Создать", exact: true }).click();
  await page.getByLabel("Название сценария").fill("Вечер в общем доме");
  await page
    .getByRole("button", { name: "Новый сценарий", exact: true })
    .click();
  await page
    .getByLabel("Идея или правки сценария")
    .fill("Современный город, компания друзей, драмеди.");
  await page
    .getByRole("button", { name: "Написать сценарий", exact: true })
    .click();
  await expect(page.getByText("Сценарий готов", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Создать выжимку", exact: true })
    .click();
  await expect(page.getByText("Выжимка готова", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Сохранить выжимку", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Сохранить мир", exact: true })
    .click();
  await page
    .locator(".world-card")
    .filter({ hasText: "Вечер в общем доме" })
    .first()
    .click();
  await page.getByLabel("Название прохождения").fill("Первый вечер");
  await page
    .getByRole("button", { name: "Создать прохождение", exact: true })
    .click();
  await page.getByRole("button", { name: "Начать игру", exact: true }).click();
  await expect(page.locator(".choices button")).toHaveCount(6);
  await expect(page.locator(".turn")).toHaveCount(1);
  await page.locator(".story .npc-link").first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(
    page.getByText("Карточка ведущего", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Закрыть", exact: true }).click();
  await page
    .getByLabel("Своё действие или реплика")
    .fill("Сесть рядом и улыбнуться");
  await page
    .getByRole("button", { name: "Отправить действие", exact: true })
    .click();
  await page
    .getByLabel("Своё действие или реплика")
    .fill("Черновик следующего действия");
  await expect(page.locator(".turn")).toHaveCount(2);
  await expect(page.locator(".choices button")).toHaveCount(6);
  await expect(page.getByLabel("Своё действие или реплика")).toHaveValue(
    "Черновик следующего действия",
  );
  await page
    .getByRole("button", { name: "Перегенерировать последний ход" })
    .click();
  await expect(page.locator(".choices button")).toHaveCount(6);
  await expect(page.locator(".turn")).toHaveCount(2);
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Откатить", exact: true }).click();
  await expect(page.locator(".turn")).toHaveCount(1);
  await page.reload();
  await expect(page.locator(".turn")).toHaveCount(1);
  await page.getByRole("button", { name: "Режим чтения", exact: true }).click();
  await expect(page.locator(".nav-rail")).toBeHidden();
  await page
    .getByRole("button", { name: "Выйти из чтения", exact: true })
    .click();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > innerWidth,
  );
  expect(overflow).toBe(false);
  await page.locator(".story-scroll").evaluate((el) => (el.scrollTop = 0));
  await page.screenshot({
    path: `test-results/game-${test.info().project.name}.png`,
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("streaming survives disconnect; stop keeps a draft and cannot save it as a world", async ({
  page,
  request,
}) => {
  const w = await (
    await request.post("/api/workspaces", { data: { name: "Остановка" } })
  ).json();
  await page.addInitScript((id) => localStorage.setItem("workspace", id), w.id);
  await page.goto("/");
  await page.getByRole("button", { name: "Создать", exact: true }).click();
  await page.getByLabel("Идея или правки сценария").fill("Друзья");
  await page
    .getByRole("button", { name: "Написать сценарий", exact: true })
    .click();
  await expect(page.getByText("Сценарий готов", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Создать выжимку", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Остановить генерацию", exact: true }),
  ).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Создать", exact: true }).click();
  await page
    .getByRole("button", { name: "Остановить генерацию", exact: true })
    .click();
  await expect(
    page.getByText("Генерация остановлена", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Сохранить выжимку", exact: true }),
  ).toHaveCount(0);
});
