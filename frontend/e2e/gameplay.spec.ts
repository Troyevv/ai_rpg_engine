import { choose } from "./choices";
import { test, expect, type Page } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

test("Gameplay 1.0: builder, five check domains, combat and equipment restart", async ({
  page,
}, info) => {
  test.setTimeout(180000);
  page.setDefaultTimeout(15000);
  const dir = mkdtempSync(join(tmpdir(), "gameplay-"));
  const base = "http://127.0.0.1:8014";
  let child: ChildProcess | undefined;
  let logs = "";
  async function start() {
    child = spawn(
      process.env.E2E_PYTHON || "python",
      [resolve("../tests/e2e_server.py")],
      {
        env: {
          ...process.env,
          E2E_PORT: "8014",
          E2E_DB_PATH: join(dir, "game.db"),
        },
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    child.stderr!.on("data", (b) => (logs += b.toString()));
    await expect
      .poll(
        async () => {
          try {
            return (await fetch(base + "/api/health")).status;
          } catch {
            return 0;
          }
        },
        { timeout: 20000, message: logs },
      )
      .toBe(200);
  }
  async function stop() {
    if (child && child.exitCode === null) {
      const done = new Promise<void>((r) => child!.once("exit", () => r()));
      child.kill();
      await done;
    }
  }
  async function click(name: string) {
    const b = page.getByRole("button", {
      name,
      exact: true,
      includeHidden: true,
    });
    await b.waitFor({ state: "attached" });
    if (
      !(await b.isVisible()) &&
      (await b.evaluate((el) => !!el.closest(".tt-action-panel")))
    ) {
      const drawer = page.getByRole("button", {
        name: "Действия",
        exact: true,
      });
      if (await drawer.isVisible()) await drawer.click();
    }
    await b.click();
  }
  const state = () =>
    page.evaluate(async () => {
      const id = localStorage.getItem("tabletop-game");
      return (await fetch("/api/tabletop/games/" + id)).json();
    });
  async function ready() {
    await expect(page.locator(".tt-compose textarea")).toBeEnabled();
  }
  async function textAction(text: string) {
    await page.locator(".tt-compose textarea").fill(text);
    await click("Отправить DM");
    await expect(
      page.getByRole("button", { name: "Бросить кубик", exact: true }),
    ).toBeVisible();
    const card = page.locator(".tt-roll-card");
    await expect(card).toBeVisible();
    expect(await card.evaluate((el) => !!el.closest(".tt-story-panel"))).toBe(
      true,
    );
    await click("Бросить кубик");
    await ready();
  }
  try {
    await start();
    await page.goto(base);
    await click("Настольная RPG");
    // This scenario checks the existing runtime. Semantic authoring is covered in universal.spec.ts.
    const draft = await (await page.request.post(`${base}/test/tabletop-draft`, { data: { idea: "gameplay acceptance" } })).json();
    await click("Создать кампанию");
    await choose(page.getByLabel("Продолжить черновик"), draft.id);
    await expect(
      page.getByRole("heading", { name: "Исчезнувшая рукопись", exact: true }),
    ).toBeVisible();
    await click("Далее");
    await page.getByLabel("Имя героя", { exact: true }).fill("Александр");
    await click("5. Характеристики");
    await expect(page.locator(".tt-score output")).toHaveText([
      "5",
      "5",
      "5",
      "5",
      "5",
      "5",
    ]);
    await expect(page.getByLabel("Бюджет характеристик")).toContainText("42");
    await click("Увеличить: Сила");
    await expect(page.getByLabel("Бюджет характеристик")).toContainText("41");
    await click("Уменьшить: Сила");
    await expect(page.getByLabel("Бюджет характеристик")).toContainText("42");
    for (const [name, count] of [
      ["Сила", 10],
      ["Ловкость", 8],
      ["Телосложение", 9],
      ["Интеллект", 5],
      ["Мудрость", 7],
      ["Харизма", 3],
    ] as const) {
      for (let i = 0; i < count; i++) await click(`Увеличить: ${name}`);
    }
    await expect(page.getByLabel("Бюджет характеристик")).toContainText("0");
    await expect(
      page.getByRole("button", { name: "Далее", exact: true }),
    ).toBeEnabled();
    await click("2. Вид");
    await page.getByRole("button", { name: /Эльф.*Скорость/ }).click();
    await expect(page.getByLabel("Влияние выбора")).toBeVisible();
    await click("3. Класс");
    await page.getByRole("button", { name: /Воин.*Кость здоровья/ }).click();
    await click("4. Происхождение");
    await page.getByRole("button", { name: /Солдат/ }).click();
    await click("8. Снаряжение");
    await click("Купить: Кожаная броня");
    await click("Купить: Кинжал");
    await click("Купить: Лечебное зелье");
    await click("Купить: Кольчуга");
    await click("Надеть: Кинжал");
    await click("Надеть: Кожаная броня");
    await expect(page.getByLabel("Бюджет снаряжения")).toContainText(
      "Осталось: 35",
    );
    await page.screenshot({
      path: info.outputPath("starting-shop.png"),
      fullPage: true,
    });
    await click("Далее");
    await click("Начать приключение");
    await ready();
    let g = await state();
    expect(g.state.characters.traveler.gold).toBe(35);
    expect(
      g.state.characters.traveler.inventory.find(
        (e: any) => e.item_id === "leather",
      ).slot,
    ).toBe("TORSO");
    await textAction("Ищу следы");
    g = await state();
    expect(g.state.knowledge.room_clue).toBeTruthy();
    await textAction("Я от капитана");
    g = await state();
    expect(
      g.history
        .at(-1)
        .events.some(
          (e: any) => e.kind === "attitude" && e.after === "friendly",
        ),
    ).toBe(true);
    await textAction("Изучаю руну");
    g = await state();
    expect(g.state.knowledge.rune_clue).toBeTruthy();
    const before = g.state.characters.traveler.hp;
    await textAction("Карабкаюсь по стене");
    g = await state();
    expect(g.state.characters.traveler.hp).toBe(before - 3);
    await click("Перейти: Хранилище");
    await ready();
    await textAction("Прокрадываюсь мимо стража");
    g = await state();
    expect(g.history.at(-1).events.some((e: any) => e.kind === "alert")).toBe(
      true,
    );
    await click("Начать бой: Страж архива");
    await click("Бросить кубик");
    await ready();
    await expect(page.getByLabel("Боевые действия")).toBeVisible();
    await expect(page.getByLabel("Предпросмотр атаки")).toContainText(
      "% попадания",
    );
    const bar = page.getByLabel("Боевые действия");
    await bar.getByRole("button", { name: "Другое", exact: true }).click();
    await bar
      .getByRole("button", { name: "Закончить ход", exact: true })
      .click();
    await ready();
    await bar.getByRole("button", { name: "Атака", exact: true }).click();
    await bar
      .getByRole("button", { name: "Атаковать: Страж", exact: true })
      .click();
    await click("Бросить кубик");
    await click("Бросить кубик");
    await ready();
    g = await state();
    expect(
      g.history
        .at(-1)
        .events.some(
          (e: any) => e.kind === "damage" && e.hp_before > e.hp_after,
        ),
    ).toBe(true);
    if (g.state.encounter) {
      await bar
        .getByRole("button", { name: "Способности", exact: true })
        .click();
      await bar
        .getByRole("button", {
          name: "Использовать: Второе дыхание",
          exact: true,
        })
        .click();
      await click("Бросить кубик");
      await ready();
      g = await state();
      expect(g.state.characters.traveler.resources.SECOND_WIND).toBe(0);
    }
    for (let round = 0; round < 4 && (await state()).state.encounter; round++) {
      await bar.getByRole("button", { name: "Другое", exact: true }).click();
      await bar
        .getByRole("button", { name: "Закончить ход", exact: true })
        .click();
      await ready();
      await bar.getByRole("button", { name: "Атака", exact: true }).click();
      await bar
        .getByRole("button", { name: "Атаковать: Страж", exact: true })
        .click();
      await click("Бросить кубик");
      await click("Бросить кубик");
      await ready();
    }
    expect((await state()).state.encounter).toBeNull();
    await click("Открыть: Сумка стража");
    await ready();
    await click("Взять: Старинная монета ×3");
    await ready();
    await page.screenshot({
      path: info.outputPath("combat-feed.png"),
      fullPage: true,
    });
    await click("Инвентарь");
    const armor = page
      .locator(".tt-inventory-grid article")
      .filter({ has: page.getByRole("heading", { name: /Кожаная броня/ }) });
    await armor.locator("summary").click();
    await armor.getByRole("button", { name: "Снять", exact: true }).click();
    await expect(
      armor.getByRole("button", { name: "Экипировать", exact: true }),
    ).toBeVisible();
    await armor
      .getByRole("button", { name: "Экипировать", exact: true })
      .click();
    await expect(
      armor.getByRole("button", { name: "Снять", exact: true }),
    ).toBeVisible();
    const chain = page
      .locator(".tt-inventory-grid article")
      .filter({ has: page.getByRole("heading", { name: /Кольчуга/ }) });
    await chain.locator("summary").click();
    await chain
      .getByRole("button", { name: "Экипировать", exact: true })
      .click();
    await expect(
      chain.getByRole("button", { name: "Снять", exact: true }),
    ).toBeVisible();
    g = await state();
    expect(g.state.characters.traveler.armor_class).toBe(17);
    expect(
      g.state.characters.traveler.inventory.find(
        (e: any) => e.item_id === "leather",
      ).equipped,
    ).toBe(false);
    expect(
      g.state.characters.traveler.equipment_bonuses.stealth_disadvantage,
    ).toBe(1);
    const saved = g.state;
    await stop();
    await start();
    await page.reload();
    await expect.poll(async () => (await state()).revision).toBe(g.revision);
    expect((await state()).state).toEqual(saved);
  } finally {
    await stop();
    rmSync(dir, { recursive: true, force: true });
  }
});
