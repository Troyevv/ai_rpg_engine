import { expect, type Locator } from "@playwright/test";
export async function choose(control: Locator, value: string) {
  if ((await control.getAttribute("role")) === "group") {
    await control.locator(`[data-value=${JSON.stringify(value)}]`).click();
    return;
  }
  await control.click();
  const dialog = control.page().locator(".choice-content");
  const option = dialog.locator(
    `[role=option][data-value=${JSON.stringify(value)}]`,
  );
  if (await option.count()) await option.click();
  else {
    await dialog.getByLabel("Поиск вариантов").fill(value);
    await dialog
      .getByRole("option", { name: `Использовать «${value}»` })
      .click();
  }
  await expect(dialog).toHaveCount(0);
}
export async function choiceValues(control: Locator) {
  await control.click();
  const dialog = control.page().locator(".choice-content");
  const values = await dialog
    .getByRole("option")
    .evaluateAll((nodes) =>
      nodes.map((n) => n.getAttribute("data-value") || ""),
    );
  await dialog.getByLabel("Закрыть выбор").click();
  await expect(dialog).toHaveCount(0);
  return values;
}
