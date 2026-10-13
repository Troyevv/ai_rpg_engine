import { test, expect } from "@playwright/test";
test("permanent transition and manual creation preview cancel commit", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const selected = await (await request.post("/test/protagonist-seed")).json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    selected,
  );
  await page.goto("/");
  await page
    .getByRole("button", { name: "Сменить главного героя", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Новый главный герой").selectOption("qa_asya");
  await dialog.getByRole("button", { name: "Проверить и посмотреть" }).click();
  await expect(dialog.getByText("Готово к подтверждению")).toBeVisible();
  await dialog.getByRole("button", { name: "Подтвердить смену" }).click();
  await expect(dialog).toBeHidden();
  let save = await (await request.get(`/api/saves/${selected.save}`)).json();
  expect(save.state.protagonist_id).toBe("qa_asya");
  expect(save.state.controlled_actor_id).toBe("qa_asya");
  const count = save.state.characters.length;
  await page
    .getByRole("button", { name: "Сменить главного героя", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Создать нового", exact: true })
    .click();
  await dialog.getByRole("button", { name: "Отмена", exact: true }).click();
  save = await (await request.get(`/api/saves/${selected.save}`)).json();
  expect(save.state.characters).toHaveLength(count);
  await page
    .getByRole("button", { name: "Сменить главного героя", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Создать нового", exact: true })
    .click();
  await dialog.getByLabel("Имя", { exact: true }).fill("Новая героиня");
  await dialog.getByText("Каноническое состояние", { exact: true }).click();
  await dialog
    .getByLabel("Начальное место", { exact: true })
    .selectOption({ label: "Озёрск — библиотека" });
  await dialog
    .getByLabel("Стартовая сцена / Обстоятельства появления", { exact: true })
    .fill("У дверей библиотеки, рядом с посетителями.");
  await dialog.getByRole("button", { name: "Проверить и посмотреть" }).click();
  await expect(dialog.getByText("Готово к подтверждению")).toBeVisible();
  await dialog.getByRole("button", { name: "Подтвердить смену" }).click();
  await expect(dialog).toBeHidden();
  save = await (await request.get(`/api/saves/${selected.save}`)).json();
  expect(save.state.characters).toHaveLength(count + 1);
  expect(
    save.state.characters.find((c: any) => c.id === save.state.protagonist_id)
      .name,
  ).toBe("Новая героиня");
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Сменить главного героя", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
  expect(errors).toEqual([]);
});

test("generated full draft remains editable and one field regeneration preserves the rest", async ({
  page,
  request,
}) => {
  const selected = await (await request.post("/test/protagonist-seed")).json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    selected,
  );
  await page.goto("/");
  await page
    .getByRole("button", { name: "Сменить главного героя", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByRole("button", { name: "Создать нового", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Создать полный черновик моделью" })
    .click();
  await expect(dialog.getByLabel("Имя", { exact: true })).toHaveValue(
    "Сгенерированная героиня",
  );
  await dialog.getByLabel("Имя", { exact: true }).fill("Отредактированное имя");
  const scene = dialog
    .locator(".protagonist-field")
    .filter({
      has: page.getByLabel("Стартовая сцена / Обстоятельства появления", {
        exact: true,
      }),
    });
  await scene.getByRole("button", { name: "Предложить", exact: true }).click();
  await expect(
    dialog.getByLabel("Стартовая сцена / Обстоятельства появления", {
      exact: true,
    }),
  ).toHaveValue("Новая сцена у двери.");
  await expect(dialog.getByLabel("Имя", { exact: true })).toHaveValue(
    "Отредактированное имя",
  );
  await dialog.getByRole("button", { name: "Проверить и посмотреть" }).click();
  await dialog.getByRole("button", { name: "Подтвердить смену" }).click();
  await expect(dialog).toBeHidden();
  const save = await (await request.get(`/api/saves/${selected.save}`)).json();
  expect(
    save.state.characters.find((c: any) => c.id === save.state.protagonist_id)
      .name,
  ).toBe("Отредактированное имя");
});
