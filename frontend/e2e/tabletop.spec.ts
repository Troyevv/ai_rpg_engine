import { choose, choiceValues } from "./choices";
import { test, expect, type Page } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

// Both layouts use their visible navigation, including the mobile action drawer.
async function press(page: Page, name: string | RegExp) {
  const target = page.getByRole("button", {
    name,
    exact: true,
    includeHidden: true,
  });
  await target.waitFor({ state: "attached" });
  const details = target.locator("xpath=ancestor::details[1]");
  if (!(await target.isVisible()) && (await details.count()))
    await details.locator("summary").click();
  const actions = page.getByRole("button", { name: "Действия", exact: true });
  if (
    !(await target.isVisible()) &&
    (await actions.isVisible()) &&
    (await target.evaluate((el) => !!el.closest(".tt-action-panel")))
  )
    await actions.click();
  await target.click();
}

async function legacyDraft(page: Page, idea: string) {
  const response = await page.request.post(
    new URL("/test/tabletop-draft", page.url()).href,
    { data: { idea } },
  );
  const result = await response.json();
  const id = result.id || result.draft_id;
  expect(id, JSON.stringify(result)).toBeTruthy();
  await press(page, "Создать кампанию");
  await choose(page.getByLabel("Продолжить черновик"), id);
}

test("generated campaign, quest, combat, loot, expansion and real server restart", async ({
  page,
}, info) => {
  test.setTimeout(120000);
  const dir = mkdtempSync(join(tmpdir(), "tabletop-e2e-"));
  const port = 8012;
  const base = `http://127.0.0.1:${port}`;
  let child: ChildProcess | undefined;
  let logs = "";
  const start = async () => {
    child = spawn(
      process.env.E2E_PYTHON || "python",
      [resolve("../tests/e2e_server.py")],
      {
        env: {
          ...process.env,
          E2E_PORT: String(port),
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
  };
  const stop = async () => {
    if (child && child.exitCode === null) {
      const done = new Promise<void>((resolve) =>
        child!.once("exit", () => resolve()),
      );
      child.kill("SIGTERM");
      await done;
    }
  };
  try {
    await start();
    await page.goto(base);
    await press(page, "Настольная RPG");
    await legacyDraft(page, "Город архивов, исчезнувшая рукопись");
    await expect(
      page.getByRole("heading", { name: "Исчезнувшая рукопись", exact: true }),
    ).toBeVisible();
    await press(page, "Далее");
    await page.getByLabel("Имя героя", { exact: true }).fill("Александр");
    await press(page, "10. Внешность");
    await page.getByLabel("Внешность", { exact: true }).fill("Серый плащ");
    await press(page, "Далее");
    await press(page, "Начать приключение");
    const click = async (name: string) => {
      await press(page, name);
      await expect(
        page.getByRole("button", {
          name: "Осмотреться",
          exact: true,
          includeHidden: true,
        }),
      ).toBeEnabled();
    };
    await click("Осмотреться");
    await click("Поговорить: Архивариус");
    await click("Перейти: Хранилище");
    await press(page, "Обыскать место");
    await expect(
      page.getByRole("button", { name: "Бросить кубик", exact: true }),
    ).toBeVisible();
    const saved = await page.evaluate(async () => {
      const id = localStorage.getItem("tabletop-game");
      return (await fetch("/api/tabletop/games/" + id)).json();
    });
    expect(JSON.stringify(saved)).not.toContain("NEVER_DISCLOSE");
    expect(JSON.stringify(saved)).not.toContain("REMOTE_SECRET");
    expect(saved.state.pending).not.toHaveProperty("dc");
    await stop();
    await start();
    await page.reload();
    await expect(
      page.getByRole("button", { name: "Бросить кубик", exact: true }),
    ).toBeVisible();
    const restored = await page.evaluate(async () => {
      const id = localStorage.getItem("tabletop-game");
      return (await fetch("/api/tabletop/games/" + id)).json();
    });
    expect(restored.state).toEqual(saved.state);
    expect(restored.revision).toBe(saved.revision);
    await click("Бросить кубик");
    await click("Открыть: Тайный ящик");
    await click("Взять: Рукопись ×1");
    await press(page, "Начать бой: Страж архива");
    await click("Бросить кубик");
    await click("Движение +5");
    await click("Закончить ход");
    let snapshot = await page.evaluate(async () =>
      (
        await fetch(
          "/api/tabletop/games/" + localStorage.getItem("tabletop-game"),
        )
      ).json(),
    );
    expect(snapshot.state.characters.traveler.hp).toBeLessThan(
      snapshot.state.characters.traveler.max_hp,
    );
    await click("Второе дыхание");
    await expect(
      page.getByRole("button", {
        name: "Второе дыхание",
        exact: true,
        includeHidden: true,
      }),
    ).toBeDisabled();
    const afterFeature = await page.evaluate(async () =>
      (
        await fetch(
          "/api/tabletop/games/" + localStorage.getItem("tabletop-game"),
        )
      ).json(),
    );
    expect(afterFeature.state.characters.traveler.hp).toBeGreaterThan(
      snapshot.state.characters.traveler.hp,
    );
    expect(afterFeature.state.characters.traveler.resources.SECOND_WIND).toBe(
      0,
    );
    expect(afterFeature.state.encounter.action).toBe(true);
    expect(afterFeature.state.encounter.bonus_action).toBe(false);
    await press(page, "Инвентарь");
    await press(page, "Использовать на Александр");
    await expect(
      page.getByRole("button", {
        name: "Использовать на Александр",
        exact: true,
      }),
    ).toHaveCount(0);
    snapshot = await page.evaluate(async () =>
      (
        await fetch(
          "/api/tabletop/games/" + localStorage.getItem("tabletop-game"),
        )
      ).json(),
    );
    expect(snapshot.state.characters.traveler.hp).toBe(
      snapshot.state.characters.traveler.max_hp,
    );
    await press(page, "Игра");
    await click("Закончить ход");
    await press(page, /^Атаковать Страж:/);
    await press(page, "Бросить кубик");
    await expect(page.locator(".tt-roll-card")).toContainText("Урон");
    await click("Бросить кубик");
    await click("Открыть: Сумка стража");
    await click("Взять: Старинная монета ×3");
    await click("Перейти: Площадь");
    await click("Поговорить: Архивариус");
    await press(page, "Новый уровень: 2");
    await expect(
      page.getByRole("dialog", { name: "Повышение уровня" }),
    ).toContainText("Уровень 1 → 2");
    await press(page, "Подтвердить уровень");
    await expect(
      page.getByRole("button", { name: "Новый уровень: 2", exact: true }),
    ).toHaveCount(0);
    await press(page, "Журнал");
    await expect(
      page.getByRole("heading", { name: "Вернуть рукопись · Выполнено" }),
    ).toBeVisible();
    await press(page, "Инвентарь");
    await expect(
      page.getByRole("heading", { name: "Старинная монета ×8", exact: true }),
    ).toBeVisible();
    await press(page, "Персонаж");
    await expect(page.getByText("Серый плащ", { exact: false })).toBeVisible();
    await press(page, "Игра");
    await page.getByLabel("Твоё действие").fill("Найти обсерваторию");
    if (
      await page
        .getByRole("button", { name: "Действия", exact: true })
        .isVisible()
    )
      await press(page, "Действия");
    await page.getByText("Расширить мир", { exact: true }).click();
    await click("Создать новое место");
    await expect(
      page.getByRole("button", {
        name: "Перейти: Обсерватория",
        exact: true,
        includeHidden: true,
      }),
    ).toBeAttached();
    const leveled = await page.evaluate(async () =>
      (
        await fetch(
          "/api/tabletop/games/" + localStorage.getItem("tabletop-game"),
        )
      ).json(),
    );
    expect(leveled.state.characters.traveler.level).toBe(2);
    await stop();
    await start();
    await page.reload();
    const resumed = await page.evaluate(async () =>
      (
        await fetch(
          "/api/tabletop/games/" + localStorage.getItem("tabletop-game"),
        )
      ).json(),
    );
    expect(resumed.state).toEqual(leveled.state);
    await press(page, "Перейти: Обсерватория");
    await expect(page.locator(".tt-header")).toContainText("Обсерватория");
    await page.screenshot({
      path: `test-results/tabletop-game-${info.project.name}.png`,
      fullPage: true,
    });

    await press(page, "Карта");
    await expect(
      page.getByRole("heading", {
        name: "Обсерватория · ты здесь",
        exact: true,
      }),
    ).toBeVisible();
    await page.screenshot({
      path: `test-results/tabletop-v2-${info.project.name}.png`,
      fullPage: true,
    });
    await press(page, "DM");
    await press(page, "Показать публичный контекст");
    await expect(page.locator(".tt-json")).toBeVisible();
    expect(await page.locator(".tt-shell").innerText()).not.toContain(
      "NEVER_DISCLOSE",
    );
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
  } finally {
    await stop();
    rmSync(dir, { recursive: true, force: true });
  }
});

test("invalid generated draft shows all diagnostics and requires explicit correction", async ({
  page,
}) => {
  await page.goto("/");
  await press(page, "Настольная RPG");
  await legacyDraft(page, "invalid references");

  await page.getByText("Диагностика проверки (2)", { exact: true }).click();
  await expect(page.locator(".tt-diagnostics")).toContainText(
    "unknown_reference · character:archivist · knowledge",
  );

  await expect(
    page.getByRole("button", { name: "Далее", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByLabel("Определение кампании", { exact: true }),
  ).toHaveCount(0);
  const invalid = await page.evaluate(async () => {
    const drafts = await (await fetch("/api/tabletop/drafts")).json();
    return drafts.find(
      (d: { generation_status: string }) => d.generation_status === "INVALID",
    );
  });
  await page.reload();
  await press(page, "Создать кампанию");
  await choose(page.getByLabel("Продолжить черновик"), invalid.id);
  await expect(
    page.getByRole("button", { name: "Далее", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByText("Диагностика проверки (2)", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Режим автора: редактирование со спойлерами").check();
  const editor = page.getByLabel("Определение кампании", { exact: true });
  const definition = JSON.parse(await editor.inputValue());
  definition.characters[1].knowledge = ["sealed_truth", "rumor"];
  definition.characters[1].relationships = { traveler: 10 };
  await editor.fill(JSON.stringify(definition));
  await page.getByRole("button", { name: "Проверить и сохранить мир" }).click();
  await expect(
    page.getByRole("button", { name: "Далее", exact: true }),
  ).toBeEnabled();
  await expect(page.locator(".tt-diagnostics")).toHaveCount(0);
  await press(page, "Далее");
  await expect(page.getByLabel("Имя героя", { exact: true })).toBeVisible();
});

test("AI DM check and choice have durable mechanical controls", async ({
  page,
}) => {
  await page.goto("/");
  await press(page, "Настольная RPG");
  await expect(page.getByLabel("LLM DM", { exact: true })).toHaveCount(0);
  await legacyDraft(page, "Протокол ведущего");
  await press(page, "Далее");
  await press(page, "Далее");
  await press(page, "Начать приключение");
  await expect(page.locator(".tt-playing")).toBeVisible();
  await press(page, "Настройки DM");
  await choose(page.getByLabel("Стиль", { exact: true }), "dark");
  await choose(
    page.getByLabel("Сложность проверок", { exact: true }),
    "always",
  );
  await Promise.all([
    page.waitForResponse(
      (r) => r.url().endsWith("/settings") && r.request().method() === "POST",
    ),
    press(page, "Сохранить настройки ведущего"),
  ]);
  await page.reload();
  await expect(page.locator(".tt-playing")).toBeVisible();
  await press(page, "Настройки DM");
  await expect(page.getByLabel("Стиль", { exact: true })).toHaveAttribute(
    "data-value",
    "dark",
  );
  await expect(
    page.getByLabel("Сложность проверок", { exact: true }),
  ).toHaveAttribute("data-value", "always");
  await press(page, "Игра");
  const input = page.getByLabel("Твоё действие", { exact: true });
  await input.fill("Пробираюсь через затопленный тоннель");
  await press(page, "Отправить DM");
  await expect(page.getByRole("status")).toContainText("Сильное течение");
  await expect(page.getByRole("status")).toContainText("Сложность: 15");
  await page.screenshot({
    path: `test-results/tabletop-roll-${test.info().project.name}.png`,
    fullPage: true,
  });
  await expect(input).toBeDisabled();
  await page.reload();
  await expect(input).toBeDisabled();
  await press(page, "Бросить кубик");
  await expect(input).toBeEnabled();
  await input.fill("Уточнить путь");
  await press(page, "Отправить DM");
  await expect(page.getByRole("status")).toContainText(
    "Как обследуешь проход?",
  );
  await expect(input).toBeDisabled();
  await page.reload();
  await press(page, "Проверить течение");
  await expect(
    page.getByRole("button", { name: "Бросить кубик", exact: true }),
  ).toBeVisible();
  await expect(input).toBeDisabled();
  await press(page, "Бросить кубик");
  await expect(input).toBeEnabled();
});

test("point buy and AI portrait are reviewed before character creation", async ({
  page,
}, testInfo) => {
  await page.goto("/");
  await press(page, "Настольная RPG");
  await legacyDraft(page, "Герой с характером");
  await press(page, "Далее");
  await page
    .getByLabel("Концепция героя", { exact: true })
    .fill("Бывший городской стражник");
  await press(page, "✨ Сгенерировать персонажа");
  await expect(
    page.getByLabel("Предложение ведущего", { exact: true }),
  ).toContainText("Бывший городской стражник");
  await press(page, "Принять портрет");
  await expect(page.getByLabel("Имя героя", { exact: true })).toHaveValue(
    "Александр",
  );
  await press(page, "5. Характеристики");
  await choose(
    page.getByLabel("Метод характеристик", { exact: true }),
    "point_buy",
  );
  await expect(
    page.getByRole("status", { name: "Бюджет характеристик" }),
  ).toContainText("Осталось очков: 27");
  await press(page, "Увеличить: Сила");
  await expect(
    page.getByRole("status", { name: "Бюджет характеристик" }),
  ).toContainText("Осталось очков: 26");
  await expect(
    page.getByLabel("Предварительный лист персонажа", { exact: true }),
  ).toContainText("Сила -1");
  await press(page, "Уменьшить: Сила");
  await expect(
    page.getByRole("status", { name: "Бюджет характеристик" }),
  ).toContainText("Осталось очков: 27");
  await page.screenshot({
    path: `test-results/creator-${testInfo.project.name}.png`,
    fullPage: true,
  });
  await press(page, "Далее");
  await press(page, "Начать приключение");
  await press(page, "Персонаж");
  await press(page, "Биография");
  await expect(
    page.getByText("Бывший городской стражник.", { exact: false }),
  ).toBeVisible();
});

test("wizard creator and spellbook keep casting pending across reload", async ({
  page,
}) => {
  await page.goto("/");
  await press(page, "Настольная RPG");
  await legacyDraft(page, "Маг в библиотеке");
  await press(page, "Далее");
  await press(page, "3. Класс");
  await page.getByRole("button", { name: /^Маг Кость здоровья/ }).click();
  await press(page, "9. Заклинания");
  await expect(
    page.getByLabel("Знать Огненная стрела", { exact: true }),
  ).toBeChecked();
  await press(page, "Далее");
  await press(page, "Начать приключение");
  await press(page, "Перейти: Хранилище");
  await press(page, "Начать бой: Страж архива");
  let releaseRoll!: () => void;
  const rollResponse = new Promise<void>((resolve) => {
    releaseRoll = resolve;
  });
  await page.route(
    "**/api/tabletop/games/*/roll",
    async (route) => {
      const response = await route.fetch();
      await rollResponse;
      await route.fulfill({ response });
    },
    { times: 1 },
  );
  await press(page, "Бросить кубик");
  await press(page, "Заклинания");
  releaseRoll();
  await expect(page.getByRole("region", { name: "Боевой HUD" })).toContainText(
    "Ход: Искатель",
  );
  await choose(page.getByLabel("Цель заклинания", { exact: true }), "sentinel");
  await press(page, "Сотворить: Огненная стрела");
  const snapshot = () =>
    page.evaluate(async () =>
      (
        await fetch(
          "/api/tabletop/games/" + localStorage.getItem("tabletop-game"),
        )
      ).json(),
    );
  await expect
    .poll(async () => (await snapshot()).state.pending?.purpose)
    .toBe("spell_attack");
  await page.reload();
  await press(page, "Бросить кубик");
  await expect
    .poll(async () => (await snapshot()).state.pending?.purpose)
    .toBe("spell_damage");
  await press(page, "Бросить кубик");
  await expect.poll(async () => (await snapshot()).state.pending).toBeNull();
  expect(
    (await snapshot()).state.characters.traveler.spell_slots["1"].remaining,
  ).toBe(2);
});
