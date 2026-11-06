import {confirmWorkshopStart} from './workshop-navigation';
import {generateIdea} from './idea-navigation';
import {workshopNav,draftsMenu} from './workshop-navigation';
import { test, expect } from "@playwright/test";
import { nav } from "./navigation";

for (const skin of ["graphite", "parchment"])
  test(`communication profile creation, editor and Narrative lifecycle · ${skin}`, async ({
    page,
    request,
  }) => {
    const workspace = await (
      await request.post("/api/workspaces", {
        data: { name: `Communication ${skin}` },
      })
    ).json();
    await page.addInitScript(
      (id) => localStorage.setItem("draftWorkspace", id),
      workspace.id,
    );
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    await nav(page, "Создать");

    const profile = page.getByRole("region", { name: "Технологии связи" });
    await profile.getByLabel("Набор технологий связи",{exact:true}).selectOption("modern");
    await profile
      .getByRole("checkbox", { name: "Письма", exact: true })
      .check();
    await profile
      .getByRole("checkbox", { name: "Магическая связь", exact: true })
      .check();
    await expect(
      profile.getByLabel("Набор технологий связи",{exact:true}),
    ).toHaveValue("custom");
    await profile.getByText("Правила и особенности",{exact:true}).click();
    await profile
      .getByLabel("Особенности связи в мире")
      .fill("1350 год: смартфоны, письма и магия.");
    await page
      .getByLabel("Описание мира или текст импорта")
      .fill("Соседи разговаривают на кухне.");
    await generateIdea(page);
    await expect(
      page.locator('.ww-hero h1, .fl-result h2'),
    ).toBeVisible();
    await page.getByRole("button", { name: "Открыть вид автора", exact: true }).click();
    await page
      .getByRole("button", { name: "Показать всё", exact: true })
      .click();
    await workshopNav(page,'Сцена и правила');await page.getByRole('button',{name:'Календарь и связь',exact:true}).click();
    const editor = page
      .locator(".workshop-content")
      .getByRole("region", { name: "Технологии связи" });
    await expect(
      editor.getByRole("checkbox", { name: "Магическая связь", exact: true }),
    ).toBeChecked();
    await editor.getByRole("checkbox", { name: "Гонцы", exact: true }).check();
    await page
      .getByRole("button", { name: "Сохранить технологии связи", exact: true })
      .click();
    await expect(
      page.getByRole("button", {
        name: "Сохранить технологии связи",
        exact: true,
      }),
    ).toBeDisabled();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
    ).toBe(false);
    await page.reload();
    await nav(page, "Создать");
    const url = `/api/workspaces/${workspace.id}/draft`;
    const draft = await (await request.get(url + "?author=true")).json();
    expect(draft.state.world.communication).toMatchObject({
      text_message: true,
      voice_call: true,
      letter: true,
      courier: true,
      magic: true,
      preset: "custom",
    });
    await workshopNav(page,'Проверка мира');
    await page
      .getByRole("button", { name: "Повторить проверку", exact: true })
      .click();
    await workshopNav(page,'Обзор мира');
    await expect(page.locator('.ww-hero h1, .fl-result h2')).toBeVisible();
    await page
      .getByRole("button", {
        name: "Подтвердить мир и начать игру",
        exact: true,
      })
      .click();
    const confirmed = page.waitForResponse(
      (r) =>
        r.url().endsWith("/draft/confirm") && r.request().method() === "POST",
    );
    await confirmWorkshopStart(page);
    const selected = await (await confirmed).json();
    await request.put(`/api/worlds/${selected.world}/presentation`, {
      data: { theme_id: skin },
    });
    await page.reload();
    await page
      .getByRole("button", { name: "Начать игру", exact: true })
      .click();
    await expect(page.locator(".choices button").first()).toBeVisible();
    await page.locator(".choices button").first().click();
    await expect
      .poll(
        async () =>
          (await (await request.get(`/api/saves/${selected.save}`)).json())
            .turns.length,
      )
      .toBe(2);
    await page.reload();
    await expect(page.locator(".choices button").first()).toBeVisible();
    await page.locator(".choices button").first().click();
    await expect
      .poll(
        async () =>
          (await (await request.get(`/api/saves/${selected.save}`)).json())
            .turns.length,
      )
      .toBe(3);
    const saved = await (
      await request.get(`/api/saves/${selected.save}`)
    ).json();
    expect(saved.state.communication_profile).toEqual(
      draft.state.world.communication,
    );
    await page.locator(".current-game-entry button").click();
    const settings = page
      .getByRole("dialog")
      .filter({
        has: page.getByRole("heading", { name: "Текущая игра", exact: true }),
      });
    await settings
      .getByRole("tablist", { name: "Разделы текущей игры" })
      .getByRole("tab", { name: "Настройки", exact: true })
      .click();
    const readonly = settings.getByRole("region", { name: "Технологии связи" });
    await expect(readonly).toContainText("Магическая связь");
    await expect(readonly.locator("input,textarea,button")).toHaveCount(0);
  });

test("communication presets, keyboard and English labels", async ({
  page,
  request,
}) => {
  const workspace = await (
    await request.post("/api/workspaces", {
      data: { name: "Communication en" },
    })
  ).json();
  await page.addInitScript(
    (id) => localStorage.setItem("draftWorkspace", id),
    workspace.id,
  );
  await page.goto("/");
  await nav(page, "Создать");
  await page.evaluate(() => (document.documentElement.lang = "en"));
  await page.getByLabel("Описание мира или текст импорта").fill("x");
  // Trigger the parent render after changing the existing locale source.

  const profile = page.locator(".atelier-communication");
  await profile.getByRole("combobox").selectOption("1939");
  await expect(
    profile.getByRole("checkbox", { name: "Letters", exact: true }),
  ).toBeChecked();
  await expect(
    profile.getByRole("checkbox", { name: "Telegrams", exact: true }),
  ).toBeChecked();
  await profile.getByRole("combobox").selectOption("none");
  await expect(profile.locator("input:checked")).toHaveCount(0);
  await page.evaluate(() => (document.documentElement.style.fontSize = "200%"));
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
});
