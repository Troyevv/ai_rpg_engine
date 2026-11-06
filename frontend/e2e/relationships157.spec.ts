import { test, expect, type Page } from "@playwright/test";
import { nav, pickCharacter } from "./navigation";
const dialog = (page: Page) => page.locator(".relationship-dialog");
async function open(page: Page) {
  await nav(page, "Мир");
  await nav(page, "Персонажи");
  await page.getByRole("tab", { name: "Отношения", exact: true }).click();
}
async function edit(page: Page, target: string) {
  await page.getByLabel(`Действия с отношением к ${target}`).click();
  await page
    .getByRole("button", { name: "Редактировать", exact: true })
    .click();
}
test("dossier directions, errors, draft protection, exact dimensions and reload", async ({
  page,
  request,
}, info) => {
  const selection = await (await request.post("/test/seed")).json();
  let save = await (await request.get(`/api/saves/${selection.save}`)).json();
  const a = save.state.controlled_actor_id,
    b = save.state.characters.find((c: any) => c.id !== a).id;
  const target = save.state.characters.find((c: any) => c.id === b).name;
  const path = `/api/saves/${selection.save}/characters/${a}/relationships`;
  save = await (
    await request.patch(path, {
      data: {
        revision: save.revision,
        target_id: b,
        context: "Исходная связь",
        dimensions: { trust: 0, fear: -100, respect: 100 },
      },
    })
  ).json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    selection,
  );
  if (info.project.name === "mobile")
    await page.setViewportSize({ width: 360, height: 800 });
  await page.goto("/");
  await open(page);
  const card = page.locator(
    `.relationship-card[data-source="${a}"][data-target="${b}"]`,
  );
  await expect(card).toHaveCount(1);
  await expect(card.locator("meter")).toHaveCount(3);
  await expect(card.locator('[data-dimension="trust"] meter')).toHaveAttribute(
    "value",
    "0",
  );
  await edit(page, target);
  const form = dialog(page);
  await expect(form.getByLabel("Доверие", { exact: true })).toHaveValue("0");
  await form.getByRole("button", { name: "Отмена", exact: true }).click();
  await expect(
    page.getByLabel(`Действия с отношением к ${target}`),
  ).toBeFocused();
  await edit(page, target);
  await expect(form.getByLabel("Привязанность", { exact: true })).toHaveValue(
    "",
  );
  await form.getByLabel("Доверие", { exact: true }).fill("101");
  await expect(
    form.getByRole("button", { name: "Сохранить", exact: true }),
  ).toBeDisabled();
  await form.getByLabel("Доверие", { exact: true }).fill("-100");
  await form.getByLabel("Страх", { exact: true }).fill("");
  await form.getByLabel("Контекст отношения").fill("Черновик не теряется");
  await page.keyboard.press("Escape");
  await expect(form).toContainText("Отбросить несохранённые изменения?");
  await form.getByRole("button", { name: "Продолжить редактирование" }).click();
  await page.goBack();
  await expect(form).toContainText("Отбросить несохранённые изменения?");
  await form.getByRole("button", { name: "Продолжить редактирование" }).click();
  // A real concurrent API edit produces the existing revision conflict.
  await request.patch(path, {
    data: {
      revision: save.revision,
      target_id: b,
      context: "Параллельная запись",
      dimensions: { trust: 12 },
    },
  });
  await form.getByRole("button", { name: "Сохранить", exact: true }).click();
  await expect(form).toContainText("Сейв изменился");
  await expect(form.getByLabel("Контекст отношения")).toHaveValue(
    "Черновик не теряется",
  );
  await form
    .getByRole("button", { name: "Обновить ревизию, сохранив черновик" })
    .click();
  await expect(form).toContainText("Ревизия обновлена");
  let attempts = 0;
  await page.route("**" + path, async (route) => {
    if (route.request().method() === "PATCH") {
      attempts++;
      await route.abort("failed");
    } else await route.continue();
  });
  await form.getByRole("button", { name: "Сохранить", exact: true }).click();
  await expect(form.getByRole("alert")).toContainText(/fetch|Failed|запрос/i);
  await expect(form.getByLabel("Контекст отношения")).toHaveValue(
    "Черновик не теряется",
  );
  await page.unroute("**" + path);
  let release!: () => void;
  const gate = new Promise<void>((resolve) => (release = resolve));
  let writes = 0;
  await page.route("**" + path, async (route) => {
    if (route.request().method() === "PATCH") {
      writes++;
      await gate;
    }
    await route.continue();
  });
  await form
    .getByRole("button", { name: "Сохранить", exact: true })
    .evaluate((button: HTMLButtonElement) => {
      button.click();
      button.click();
    });
  await expect(
    form.getByRole("button", { name: "Сохранение…" }),
  ).toBeDisabled();
  release();

  await expect(form).toHaveCount(0);
  expect(attempts).toBe(1);
  expect(writes).toBe(1);
  await page.unroute("**" + path);
  await expect(card).toContainText("Черновик не теряется");
  save = await (await request.get(`/api/saves/${selection.save}`)).json();
  expect(save.state.world.relationships[`${a}:${b}`].dimensions).toEqual({
    trust: -100,
    respect: 100,
  });
  expect(
    save.state.relationships.find(
      (r: any) => r.source_id === a && r.target_id === b,
    ).text,
  ).toBe("Черновик не теряется");
  await edit(page, target);
  await form.getByLabel("Контекст отношения").fill("Отменить");
  await form.getByRole("button", { name: "Отмена", exact: true }).click();
  await form.getByRole("button", { name: "Отбросить изменения" }).click();
  await expect(form).toHaveCount(0);
  await expect(card).not.toContainText("Отменить");
  await page.reload();
  await open(page);
  await expect(card).toContainText("Черновик не теряется");
  await page.getByLabel("Поиск отношений").fill("нет такого");
  await expect(
    page.getByRole("status").filter({ hasText: "Отношения не найдены" }),
  ).toBeVisible();
  await page.getByLabel("Поиск отношений").fill("");
  await card.getByRole("button", { name: `Открыть досье: ${target}` }).click();
  await expect(page.locator(".character-header")).toContainText(target);
  await expect(
    page.getByRole("button", { name: "+ Добавить отношение", exact: true }),
  ).toHaveCount(0);
  await pickCharacter(page, a);
  await page.getByRole("tab", { name: "Отношения", exact: true }).click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
test("responsive cards and editor, skins, focus, long text, unchanged reads", async ({
  page,
  request,
}, info) => {
  const s = await (
    await request.post("/test/ui-completion-seed?checkpoint=ui-dossier")
  ).json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    s,
  );
  const before = await (await request.get(`/api/saves/${s.save}`)).json();
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const skin of ["graphite", "parchment"]) {
    await request.put(`/api/worlds/${s.world}/presentation`, {
      data: { theme_id: skin },
    });
    await page.setViewportSize({
      width:
        info.project.name === "mobile"
          ? skin === "graphite"
            ? 360
            : 393
          : skin === "graphite"
            ? 1440
            : 768,
      height: 900,
    });
    await page.goto("/");
    await open(page);
    const outgoing = page.locator(
      '.relationship-card[data-source="qa_kirill"][data-target="qa_vera"]',
    );
    const incoming = page.locator(
      '.relationship-card[data-source="qa_vera"][data-target="qa_kirill"]',
    );
    await expect(outgoing).toHaveCount(1);
    await expect(incoming).toHaveCount(1);
    await expect(
      outgoing.locator('[data-dimension="trust"] meter'),
    ).toHaveAttribute("value", "70");
    await expect(
      incoming.locator('[data-dimension="trust"] meter'),
    ).toHaveAttribute("value", "60");
    await expect(page.locator(".character-profile")).not.toContainText(
      "PRIVATE",
    );
    if (process.env.RELATIONSHIP_EVIDENCE === "1" && skin === "graphite") {
      await outgoing.scrollIntoViewIfNeeded();
      await page.screenshot({
        path: `/tmp/157-cards-${info.project.name}.png`,
      });
    }
    await page
      .getByRole("button", { name: "+ Добавить отношение", exact: true })
      .click();
    const form = dialog(page);
    await expect(form.locator(".relationship-dimension").first()).toBeVisible();
    expect(
      await form
        .locator(".relationship-dimension")
        .first()
        .evaluate((el) => getComputedStyle(el).display),
    ).toBe("grid");
    if (info.project.name === "desktop" && skin === "graphite")
      expect((await form.boundingBox())!.width).toBeGreaterThan(700);

    await form
      .getByLabel("Контекст отношения")
      .fill("Очень длинное русское описание с подробностями. ".repeat(40));
    if (process.env.RELATIONSHIP_EVIDENCE === "1" && skin === "graphite")
      await page.screenshot({
        path: `/tmp/157-editor-${info.project.name}.png`,
      });
    await page.evaluate(
      () => (document.documentElement.style.fontSize = "200%"),
    );
    expect(
      await form.evaluate((el) => el.scrollWidth <= el.clientWidth + 1),
    ).toBe(true);
    await form.getByRole("button", { name: "Сохранить", exact: true }).focus();
    await page.keyboard.press("Tab");
    expect(
      await page.evaluate(
        () => !!document.activeElement?.closest(".relationship-dialog"),
      ),
    ).toBe(true);
    await page.keyboard.press("Escape");
    await form.getByRole("button", { name: "Отбросить изменения" }).click();
    await expect(form).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "+ Добавить отношение", exact: true }),
    ).toBeFocused();
    await page.evaluate(() => (document.documentElement.style.fontSize = ""));
  }
  const after = await (await request.get(`/api/saves/${s.save}`)).json();
  expect(after.state.world.relationships).toEqual(
    before.state.world.relationships,
  );
});
