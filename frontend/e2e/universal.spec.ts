import { test, expect } from "@playwright/test";
import { choose } from "./choices";
for (const [width, height] of [
  [360, 800],
  [390, 844],
  [412, 915],
])
  test(`Setting and application choices ${width}`, async ({ page }) => {
    test.setTimeout(120000);
    await page.setViewportSize({ width, height });
    await page.goto("/");
    await page
      .getByRole("button", { name: "Настольная RPG", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Создать кампанию", exact: true })
      .click();

    await page
      .getByLabel("Описание нового мира")
      .fill("Общество живёт внутри стеклянных приливов и собирает голоса.");
    await page
      .getByRole("button", { name: "Создать структуру мира", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Сохранить мир", exact: true }),
    ).toBeVisible({ timeout: 30000 });
    const editor = page.locator(".setting-editor");
    await editor
      .getByLabel("Название", { exact: true })
      .fill(`Приливы ${width}`);
    await editor
      .getByRole("button", { name: "Сохранить мир", exact: true })
      .click();
    await expect(
      editor.getByRole("button", { name: "Сохранить мир", exact: true }),
    ).toBeEnabled();
    await choose(editor.getByLabel("Раздел мира"), "skills");
    await editor.getByLabel("Раздел мира").click();
    await expect(page.locator(".choice-content")).toBeVisible();
    await page.goBack();
    await expect(page.locator(".choice-content")).toHaveCount(0);
    await expect(editor.getByLabel("Раздел мира")).toBeFocused();
    await expect(page.locator("select,datalist")).toHaveCount(0);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await editor
      .getByRole("button", {
        name: "Подтвердить мир и создать кампанию",
        exact: true,
      })
      .click();
    await expect(page.locator(".setting-editor")).toHaveCount(0);
    await page
      .getByLabel("Идея приключения", { exact: true })
      .fill("Найти украденный голос");
    await page
      .getByRole("button", { name: "Сгенерировать мир", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Мир и стартовая сцена", exact: true }),
    ).toBeVisible({ timeout: 30000 });
    await page.getByRole("button", { name: "Далее", exact: true }).click();
    await page
      .getByLabel("Имя героя", { exact: true })
      .fill("Хранитель голоса");
    await page
      .getByRole("button", { name: "5. Характеристики", exact: true })
      .click();
    for (const [name, count] of [
      ["Сила", 10],
      ["Ловкость", 8],
      ["Телосложение", 9],
      ["Интеллект", 5],
      ["Мудрость", 7],
      ["Харизма", 3],
    ] as const) {
      for (let i = 0; i < count; i++)
        await page
          .getByRole("button", { name: `Увеличить: ${name}`, exact: true })
          .click();
    }
    await page
      .getByRole("button", { name: "8. Снаряжение", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Купить: Кинжал", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Надеть: Кинжал", exact: true })
      .click();
    await page.getByRole("button", { name: "Далее", exact: true }).click();
    await page
      .getByRole("button", { name: "Начать приключение", exact: true })
      .click();
    await expect(page.locator(".tt-compose textarea")).toBeEnabled({
      timeout: 30000,
    });
    const gameId = await page.evaluate(() =>
      localStorage.getItem("tabletop-game"),
    );
    const saved = await (
      await page.request.get(`/api/tabletop/games/${gameId}`)
    ).json();
    expect(
      saved.state.characters.traveler.inventory.some(
        (e: { item_id: string; equipped: boolean }) =>
          e.item_id === "dagger" && e.equipped,
      ),
    ).toBe(true);
    await page.reload();
    await expect(page.locator(".tt-compose textarea")).toBeEnabled({
      timeout: 30000,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    const response = await page.request.get("/api/tabletop/settings/worlds");
    expect(
      (await response.json()).some(
        (w: { name: string }) => w.name === `Приливы ${width}`,
      ),
    ).toBe(true);
  });
