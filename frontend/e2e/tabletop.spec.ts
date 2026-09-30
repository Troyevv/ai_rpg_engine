import { test, expect } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

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
    await page
      .getByRole("button", { name: "Настольная RPG", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Создать кампанию", exact: true })
      .click();
    await page
      .getByLabel("Идея приключения", { exact: true })
      .fill("Город архивов, исчезнувшая рукопись");
    await page
      .getByRole("button", { name: "Сгенерировать мир", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Исчезнувшая рукопись", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Далее", exact: true }).click();
    await page.getByLabel("Имя героя", { exact: true }).fill("Александр");
    await page.getByLabel("Внешность", { exact: true }).fill("Серый плащ");
    await page.getByRole("button", { name: "Далее", exact: true }).click();
    await page
      .getByRole("button", { name: "Начать приключение", exact: true })
      .click();
    const click = async (name: string) => {
      await page.getByRole("button", { name, exact: true }).click();
      await expect(
        page.getByRole("button", { name: "Осмотреться", exact: true }),
      ).toBeEnabled();
    };
    await click("Осмотреться");
    await click("Поговорить: Архивариус");
    await click("Перейти: Хранилище");
    await page
      .getByRole("button", { name: "Обыскать место", exact: true })
      .click();
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
    await page
      .getByRole("button", { name: "Начать бой: Страж архива", exact: true })
      .click();
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
    await page.getByRole("button", { name: "Инвентарь", exact: true }).click();
    await page
      .getByRole("button", { name: "Использовать на Александр", exact: true })
      .click();
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
    await page.getByRole("button", { name: "Игра", exact: true }).click();
    await click("Закончить ход");
    await page.getByRole("button", { name: /^Атаковать Страж:/ }).click();
    await page
      .getByRole("button", { name: "Бросить кубик", exact: true })
      .click();
    await expect(page.getByRole("status")).toContainText("Урон");
    await click("Бросить кубик");
    await click("Открыть: Сумка стража");
    await click("Взять: Старинная монета ×3");
    await click("Перейти: Площадь");
    await click("Поговорить: Архивариус");
    await page.getByRole("button", { name: "Журнал", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Вернуть рукопись · Выполнено" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Инвентарь", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Старинная монета ×8", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Персонаж", exact: true }).click();
    await expect(page.getByText("Серый плащ", { exact: false })).toBeVisible();
    await page.getByRole("button", { name: "Игра", exact: true }).click();
    await page.getByLabel("Твоё действие").fill("Найти обсерваторию");
    await page.getByText("Расширить мир", { exact: true }).click();
    await click("Создать новое место");
    await expect(
      page.getByRole("button", { name: "Перейти: Обсерватория", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Карта", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Обсерватория", exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: `test-results/tabletop-v2-${info.project.name}.png`,
      fullPage: true,
    });
    await page.getByRole("button", { name: "DM", exact: true }).click();
    await page
      .getByRole("button", { name: "Показать публичный контекст", exact: true })
      .click();
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
  await page
    .getByRole("button", { name: "Настольная RPG", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Создать кампанию", exact: true })
    .click();
  await page
    .getByLabel("Идея приключения", { exact: true })
    .fill("invalid references");
  await page
    .getByRole("button", { name: "Сгенерировать мир", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("missing_secret");
  await expect(page.getByRole("alert")).toContainText("missing_actor");
  await page.getByText("Диагностика проверки (2)", { exact: true }).click();
  await expect(page.locator(".tt-diagnostics")).toContainText(
    "unknown_reference · character:archivist · knowledge",
  );
  await page
    .getByRole("button", { name: "Открыть невалидный черновик" })
    .click();
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
  await page
    .getByRole("button", { name: "Создать кампанию", exact: true })
    .click();
  await page.getByLabel("Продолжить черновик").selectOption(invalid.id);
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
  await page.getByRole("button", { name: "Далее", exact: true }).click();
  await expect(page.getByLabel("Имя героя", { exact: true })).toBeVisible();
});
