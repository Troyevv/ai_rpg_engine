import { test, expect } from "@playwright/test";

test("NPC review: committed identity, draft lifecycle, typed attributes and proposals", async ({
  page,
  request,
}, info) => {
  const selected = await (await request.post("/test/npc-review-seed")).json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    selected,
  );
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByRole("heading", { name: "Лада", exact: true }),
  ).toBeVisible();
  const committed = await (
    await request.get(`/api/saves/${selected.save}`)
  ).json();
  expect(committed.turns).toHaveLength(1);
  expect(
    committed.state.characters.some((c: { id: string }) => c.id === "new_npc"),
  ).toBeTruthy();
  expect(committed.state.npc_reviews.records).toHaveLength(2);
  await expect(
    dialog.getByRole("button", { name: "Подтвердить", exact: true }),
  ).toBeDisabled();
  await expect(dialog.getByLabel("Возраст", { exact: true })).toHaveValue("");
  await dialog.getByLabel("Возраст", { exact: true }).fill("27 лет");
  await dialog.getByRole("tab", { name: /Состояние/ }).click();
  await expect(
    dialog
      .getByRole("group", { name: "Биологический пол" })
      .getByRole("button", { name: "Женский", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await dialog
    .getByRole("group", { name: "Репродуктивная способность" })
    .getByRole("button", { name: "Неизвестно", exact: true })
    .click();
  await dialog
    .getByLabel("Физическое состояние", { exact: true })
    .fill("Отдохнула");
  if (process.env.NPC_REVIEW_SCREENSHOTS)
    await page.screenshot({
      path: `/tmp/npc-review-${info.project.name}-attributes.png`,
    });
  await dialog.getByRole("button", { name: "Отложить", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: /Новые лица в истории/ }),
  ).toBeVisible();
  await page
    .getByLabel("Своё действие или реплика")
    .fill("Продолжаю разговор.");
  await page
    .getByRole("button", { name: "Отправить действие", exact: true })
    .click();
  await expect
    .poll(async () => {
      const s = await (await request.get(`/api/saves/${selected.save}`)).json();
      return s.turns.length;
    })
    .toBe(2);
  await expect(
    page.getByRole("button", { name: /Новые лица в истории/ }),
  ).toBeEnabled();
  await page.getByRole("button", { name: /Новые лица в истории/ }).click();
  await expect(dialog.getByLabel("Возраст", { exact: true })).toHaveValue(
    "27 лет",
  );
  // Switching characters saves dirty fields without losing either draft.
  await dialog
    .getByRole("button", { name: /Александр Константинович/ })
    .click();
  await dialog.getByLabel("Роль", { exact: true }).fill("Архитектор");
  await dialog.getByRole("button", { name: /Лада/ }).click();
  await expect(dialog.getByLabel("Возраст", { exact: true })).toHaveValue(
    "27 лет",
  );
  // A failed provider response leaves the edited field intact and permits retry.
  await dialog.getByRole("tab", { name: /Глубина/ }).click();
  const biography = dialog
    .locator(".npc-review-field")
    .filter({ has: page.getByLabel("Биография", { exact: true }) });
  await biography.getByLabel("Биография", { exact: true }).fill("Мой текст");
  await page.route(
    "**/npc-reviews/new_npc/generate",
    (route) =>
      route.fulfill({
        status: 409,
        json: { detail: "Тестовая ошибка генерации" },
      }),
    { times: 1 },
  );
  await biography
    .getByRole("button", { name: "Предложить текст", exact: true })
    .click();
  await expect(dialog.getByRole("alert")).toContainText("Тестовая ошибка");
  await expect(
    dialog.getByRole("button", { name: "Сверить с сервером", exact: true }),
  ).toHaveCount(0);
  if (process.env.NPC_REVIEW_SCREENSHOTS)
    await page.screenshot({
      path: `/tmp/npc-review-${info.project.name}-generation-error.png`,
    });
  await expect(biography.getByLabel("Биография", { exact: true })).toHaveValue(
    "Мой текст",
  );
  await biography
    .getByRole("button", { name: "Предложить текст", exact: true })
    .click();
  await expect(biography.locator(".npc-review-proposal")).toContainText(
    "Выросла у моря",
  );
  await expect(biography.getByLabel("Биография", { exact: true })).toHaveValue(
    "Мой текст",
  );
  await biography.locator(".npc-review-proposal").scrollIntoViewIfNeeded();
  if (process.env.NPC_REVIEW_SCREENSHOTS)
    await page.screenshot({
      path: `/tmp/npc-review-${info.project.name}-proposal.png`,
    });
  await biography.getByRole("button", { name: "Принять текст" }).click();
  for (const section of ["Образ", "Личность", "Глубина"]) {
    await dialog.getByRole("tab", { name: new RegExp(section) }).click();
    const inputs = dialog.locator(".npc-review-fields textarea");
    for (let i = 0; i < (await inputs.count()); i++)
      if (!(await inputs.nth(i).inputValue()).trim())
        await inputs
          .nth(i)
          .fill("Подробное описание характера и опыта. ".repeat(12));
  }
  for (const skin of ["graphite", "parchment", "cyberpunk"]) {
    await request.put(`/api/worlds/${selected.world}/presentation`, {
      data: { theme_id: skin },
    });
    await dialog
      .getByRole("button", { name: "Сохранить черновик", exact: true })
      .click();
    await expect(
      dialog.getByText("Черновик сохранён", { exact: true }),
    ).toBeVisible();
    await page.reload();
    // pending_review reopens on reload; deferred does not.
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(dialog).toHaveCSS("overflow", "hidden");
    expect(
      await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth + 1),
    ).toBeTruthy();
    if (process.env.NPC_REVIEW_SCREENSHOTS)
      await page.screenshot({
        path: `/tmp/npc-review-${info.project.name}-${skin}.png`,
      });
  }
  await dialog
    .getByRole("button", { name: "Подтвердить", exact: true })
    .click();
  await expect(
    dialog.getByRole("heading", { name: /Александр Константинович/ }),
  ).toBeVisible();
  const after = await (await request.get(`/api/saves/${selected.save}`)).json();
  expect(
    after.state.npc_reviews.records.find(
      (r: { id: string }) => r.id === "new_npc",
    ).status,
  ).toBe("confirmed");
  expect(after.state.world.characters.new_npc.physical_state).toBe("Отдохнула");
  expect(
    after.state.characters.filter((c: { id: string }) => c.id === "new_npc"),
  ).toHaveLength(1);
  expect(errors).toEqual([]);
});

test("NPC review resolves parallel edits without overwriting either version", async ({
  page,
  request,
}) => {
  const selected = await (await request.post("/test/npc-review-seed")).json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    selected,
  );
  await page.goto("/");
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Возраст", { exact: true }).fill("Мои 27 лет");
  await dialog.getByRole("tab", { name: /Состояние/ }).click();
  await dialog
    .getByRole("group", { name: "Биологический пол" })
    .getByRole("button", { name: "Неизвестно", exact: true })
    .click();
  const before = await (
    await request.get(`/api/saves/${selected.save}`)
  ).json();
  const record = before.state.npc_reviews.records.find(
    (r: { id: string }) => r.id === "new_npc",
  );
  const response = await request.post(
    `/api/saves/${selected.save}/npc-reviews/new_npc`,
    {
      data: {
        revision: before.revision,
        review_revision: record.revision,
        operation_id: "parallel-browser-edit",
        fields: { ...record.card.fields, Возраст: "Серверные 35 лет" },
        character: { biological_sex: "male" },
        action: "save",
      },
    },
  );
  expect(response.ok()).toBeTruthy();
  await dialog
    .getByRole("button", { name: "Сохранить черновик", exact: true })
    .click();
  await expect(dialog.getByRole("alert")).toContainText("изменились");
  await dialog
    .getByRole("button", { name: "Сверить с сервером", exact: true })
    .click();
  await expect(dialog.locator(".npc-review-conflict")).toHaveCount(2);
  await page.reload();
  await expect(dialog.locator(".npc-review-conflict")).toHaveCount(2);
  const age = dialog
    .locator(".npc-review-conflict")
    .filter({ hasText: "Возраст: параллельные правки" });
  await expect(age).toContainText("Мои 27 лет");
  await expect(age).toContainText("Серверные 35 лет");
  await age
    .getByRole("button", { name: "Принять серверную", exact: true })
    .click();
  const sex = dialog
    .locator(".npc-review-conflict")
    .filter({ hasText: "Биологический пол: параллельные правки" });
  await expect(sex).toContainText("Неизвестно");
  await expect(sex).toContainText("Мужской");
  await sex.getByRole("button", { name: "Оставить мою", exact: true }).click();
  await dialog
    .getByRole("button", { name: "Сохранить черновик", exact: true })
    .click();
  await expect(
    dialog.getByText("Черновик сохранён", { exact: true }),
  ).toBeVisible();
  const after = await (await request.get(`/api/saves/${selected.save}`)).json();
  const updated = after.state.npc_reviews.records.find(
    (r: { id: string }) => r.id === "new_npc",
  );
  expect(updated.card.fields["Возраст"]).toBe("Серверные 35 лет");
  expect(updated.character.biological_sex).toBeNull();
  expect(updated.current.biological_sex).toBe("female");
  // Wait for the parent to adopt the committed revision before using controls.
  await expect(dialog.getByRole("button", {name:"Отложить", exact:true})).toBeEnabled();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
});
