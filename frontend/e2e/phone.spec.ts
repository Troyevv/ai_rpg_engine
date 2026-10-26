import {gameAction} from './navigation';
import { test, expect } from "@playwright/test";

test("phone controls, freeform text, reload and physical scene", async ({
  page,
  request,
}) => {
  const seed = await request.post("/test/phone-seed");
  expect(seed.ok()).toBeTruthy();
  const selected = await seed.json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    selected,
  );
  const before = await (
    await request.get(`/api/saves/${selected.save}`)
  ).json();
  await page.goto("/");
  await expect(
    page.locator(".choices button").filter({ hasText: "Посмотреть в окно" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: /^Телефон/ })
    .click();
  const dialog = page.getByRole("region", {name:"Телефон персонажа"});
  await expect(dialog.getByText("Входящий", { exact: false })).toBeVisible();
  await dialog.getByRole("button", { name: "Ответить", exact: true }).click();
  await expect(
    dialog.getByRole("button", { name: "Завершить разговор", exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(
    page.locator(".choices button").filter({ hasText: "Посмотреть в окно" }),
  ).toHaveCount(0);
  await page.getByLabel("Канал действия").selectOption("physical");
  await expect(
    page.locator(".choices button").filter({ hasText: "Посмотреть в окно" }),
  ).toBeVisible();
  await page.getByLabel("Канал действия").selectOption("call");
  await page.reload();
  await page
    .getByRole("button", { name: /^Телефон/ })
    .click();
  await dialog
    .getByRole("button", { name: "Завершить разговор", exact: true })
    .click();
  await expect(
    dialog.getByRole("button", { name: "Завершить разговор", exact: true }),
  ).toHaveCount(0);
  const after = await (await request.get(`/api/saves/${selected.save}`)).json();
  expect(after.state.scene).toEqual(before.state.scene);
  await dialog.getByRole("button", { name: "Вера работа", exact: true }).click();
  await dialog
    .getByRole("button", { name: "Написать", exact: true })
    .first()
    .click();
  await dialog
    .getByLabel("Сообщение в телефоне")
    .fill("Привет! Это мой точный текст.");
  await dialog
    .getByRole("button", { name: "Отправить сообщение", exact: true })
    .click();
  await expect(
    dialog.getByText("Привет! Это мой точный текст.", { exact: true }),
  ).toBeVisible();
  await expect(dialog.locator(".choice")).toHaveCount(0);
  await page.reload();
  await page.getByRole("button", { name: "Телефон", exact: true }).click();
  await dialog.getByRole("button", { name: "Переписки", exact: true }).click();
  await dialog.getByRole("button").filter({ hasText: "Вера работа" }).click();
  await expect(
    dialog.getByText("Привет! Это мой точный текст.", { exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
});

test("decline and configured in-game emergency log", async ({
  page,
  request,
}) => {
  const selected = await (await request.post("/test/phone-seed")).json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    selected,
  );
  await page.goto("/");
  await page
    .getByRole("button", { name: /^Телефон/ })
    .click();
  const dialog = page.getByRole("region", {name:"Телефон персонажа"});
  await dialog.getByRole("button", { name: "Отклонить", exact: true }).click();
  await dialog.getByRole("button", { name: "Звонки", exact: true }).click();
  await expect(dialog.getByText(/Входящий · Отклонён/)).toBeVisible();
  await dialog.getByRole("button", {name:"Контакты",exact:true}).click();
  await dialog
    .getByRole("button", { name: "Позвонить: Скорая помощь", exact: true })
    .click();
  await expect(dialog.getByText(/Исходящий · Пропущен/)).toBeVisible();
  await expect(dialog.locator('a[href^="tel:"]')).toHaveCount(0);
});

test("group membership and protagonist-owned contacts", async ({
  page,
  request,
}) => {
  const selected = await (await request.post("/test/phone-seed")).json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    selected,
  );
  await page.goto("/");
  await page
    .getByRole("button", { name: /^Телефон/ })
    .click();
  const dialog = page.getByRole("region", {name:"Телефон персонажа"});
  await dialog
    .getByRole("button", { name: "Игнорировать", exact: true })
    .click();
  await dialog.getByRole("button", { name: "Переписки", exact: true }).click();
  await dialog
    .getByRole("button", { name: "Создать группу", exact: true })
    .click();
  await dialog.getByLabel("Название группы").fill("Планы на завтра");
  await dialog.getByLabel("Вера работа", { exact: true }).check();
  await dialog
    .getByRole("button", { name: "Создать переписку", exact: true })
    .click();
  await dialog
    .getByRole("button")
    .filter({ hasText: "Планы на завтра" })
    .click();
  await dialog
    .getByLabel("Сообщение в телефоне")
    .fill("Только участникам группы.");
  await dialog
    .getByRole("button", { name: "Отправить сообщение", exact: true })
    .click();
  await expect(
    dialog.getByText("Только участникам группы.", { exact: true }),
  ).toBeVisible();
  await dialog.locator("details summary").filter({hasText:"Управление участниками"}).click();
  await dialog
    .getByRole("button", { name: "Удалить: Вера работа", exact: true })
    .click();
  await expect(
    dialog.getByRole("button", { name: "Добавить: Вера работа", exact: true }),
  ).toBeVisible();
  await dialog
    .getByRole("button", { name: "Добавить: Вера работа", exact: true })
    .click();
  await expect(
    dialog.getByRole("button", { name: "Удалить: Вера работа", exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await gameAction(page,'Сменить главного героя');
  await page.getByRole("dialog").getByLabel("Новый главный герой").selectOption("qa_vera");
  await page.getByRole("dialog").getByRole("button", { name: "Проверить и посмотреть" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Подтвердить смену" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
  await page.getByRole("button", { name: /^Телефон/ }).click();
  await expect(dialog.getByText("Кирилл", { exact: true })).toBeVisible();
  await expect(dialog.getByText("Мастерская", { exact: true })).toHaveCount(0);
  await expect(dialog.getByText("Новый знакомый", { exact: true })).toHaveCount(
    0,
  );
  const save = await (await request.get(`/api/saves/${selected.save}`)).json();
  expect(save.state.phone.actor_id).toBe("qa_vera");
  expect(save.state.phone.contacts).toHaveLength(1);
});

test("unread text and shared portrait projection", async ({
  page,
  request,
}) => {
  const selected = await (
    await request.post("/test/phone-seed?unread=true")
  ).json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    selected,
  );
  await page.goto("/");
  await expect(
    page.getByText("Прочти, когда будет удобно.", { exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: /^Телефон/ }).click();
  const dialog = page.getByRole("region", {name:"Телефон персонажа"});
  const contact = dialog
    .locator("article.phone-row")
    .filter({ hasText: "Вера работа" });
  await expect(contact.locator("svg[data-silhouette]")).toBeVisible();
  await page.screenshot({
    path: test.info().outputPath("phone-unread.png"),
    animations: "disabled",
  });
  const png = await page.evaluate(() => {
    const c = document.createElement("canvas");
    c.width = 256;
    c.height = 384;
    const ctx = c.getContext("2d")!;
    ctx.fillStyle = "#916744";
    ctx.fillRect(0, 0, 256, 384);
    return c.toDataURL("image/png").split(",")[1];
  });
  const save = await (await request.get(`/api/saves/${selected.save}`)).json();
  const settings = JSON.stringify({
    crop: { x: 0.3, y: 0.7, zoom: 1.5 },
    make_current: true,
  });
  const uploaded = await request.post(
    `/api/saves/${selected.save}/characters/qa_vera/portraits`,
    {
      params: { revision: save.revision, settings },
      headers: { "Content-Type": "image/png" },
      data: Buffer.from(png, "base64"),
    },
  );
  expect(uploaded.ok()).toBeTruthy();
  await page.reload();
  await page.getByRole("button", { name: /^Телефон/ }).click();
  await expect(contact.locator("img")).toBeVisible();
  const portrait = await contact.locator("img").getAttribute("src");
  await expect(
    dialog.getByLabel("Текущий звонок").locator("img"),
  ).toHaveAttribute("src", portrait!);
  await contact.getByRole("button", { name: "Вера работа", exact: true }).click();
  await contact.getByRole("button", { name: "Написать", exact: true }).click();
  await expect(
    dialog.getByText("Прочти, когда будет удобно.", { exact: true }),
  ).toBeVisible();
  await expect(
    dialog.getByLabel("Участники переписки").locator("img"),
  ).toHaveAttribute("src", portrait!);
  const after = await (await request.get(`/api/saves/${selected.save}`)).json();
  expect(
    after.state.phone.events.find((e: any) => e.channel === "TEXT_MESSAGE")
      .unread,
  ).toBe(false);
  await page.screenshot({
    path: test.info().outputPath("phone-chat-portrait.png"),
    animations: "disabled",
  });
});
