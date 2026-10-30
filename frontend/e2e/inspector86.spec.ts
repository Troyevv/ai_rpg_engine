import { test, expect } from "@playwright/test";
import { nav } from "./navigation";
const sections = [
  "Мир",
  "Сцена",
  "Персонажи",
  "Отношения",
  "Сюжет",
  "Память",
  "Тайны",
];
const out = process.env.INSPECTOR_EVIDENCE_DIR || "../docs/manual_qa/narrative_v4/issue86-evidence";
const capture=process.env.UI_EVIDENCE==='1';
test.use({ video:capture?'on':'off' });
for (const width of [1440, 768, 393, 360])
  test(`seven sections, skins, widths ${width}`, async ({
    page,
    request,
  }, info) => {
    test.skip(info.project.name !== "desktop");
    test.setTimeout(120000);
    await page.setViewportSize({ width, height: 900 });
    const s = await (
      await request.post("/test/ui-completion-seed?checkpoint=ui-inspector")
    ).json();
    await page.addInitScript(
      (s) => localStorage.setItem("selection", JSON.stringify(s)),
      s,
    );
    const original = await (await request.get(`/api/saves/${s.save}`)).json();
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    for (const skin of ["graphite", "parchment"]) {
      await request.put(`/api/worlds/${s.world}/presentation`, {
        data: { theme_id: skin },
      });
      await page.goto("/");
      for (const section of sections) {
        await nav(page, section);
        const area = page.locator(".inspector-workspace");
        await expect(area).toBeVisible();
        await expect(area).toHaveAttribute("aria-label", section);
        await expect(area.getByRole("heading", { level: 1 })).toBeVisible();
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        ).toBe(true);
        expect(
          await area.evaluate((e) => e.scrollWidth <= e.clientWidth + 1),
        ).toBe(true);
        for (const input of await area
          .locator('input[type="search"]:visible')
          .all()) {
          expect((await input.boundingBox())!.width).toBeGreaterThan(100);
        }
        if(capture)await page.screenshot({
          path: `${out}/after-${width}-${skin}-${section}-expanded.png`,
          animations: "disabled",
        });
        {
          if (width < 768)
            await page.setViewportSize({ width: 768, height: 900 });
          await page
            .getByRole("button", { name: "Компактная панель", exact: true })
            .click();
          if (width < 768) await page.setViewportSize({ width, height: 900 });
          for (const input of await area
            .locator('input[type="search"]:visible')
            .all()) {
            expect((await input.boundingBox())!.width).toBeGreaterThan(100);
          }
          if(capture)await page.screenshot({
            path: `${out}/after-${width}-${skin}-${section}-compact.png`,
            animations: "disabled",
          });
          if (width < 768)
            await page.setViewportSize({ width: 768, height: 900 });
          await page
            .getByRole("button", { name: "Расширить панель", exact: true })
            .click();
          if (width < 768) await page.setViewportSize({ width, height: 900 });
        }
      }
      await nav(page, "Персонажи");
      await expect(page.getByRole("tab")).toHaveCount(5);
      await expect(
        page.locator(".character-profile .portrait-control"),
      ).toBeVisible();
      await page.getByRole("tab", { name: "Личность", exact: true }).click();
      await nav(page, "Мир");
      await nav(page, "Персонажи");
      await expect(
        page.getByRole("tab", { name: "Личность", exact: true }),
      ).toHaveAttribute("aria-selected", "true");
    }
    expect(errors).toEqual([]);
    const after = await (await request.get(`/api/saves/${s.save}`)).json();
    expect(after.revision).toBe(original.revision);
    expect(after.state.world).toEqual(original.state.world);
  });
test("selector keyboard, filters, section return, scene editor and metadata", async ({
  page,
  request,
}, info) => {
  const s = await (
    await request.post("/test/ui-completion-seed?checkpoint=ui-inspector")
  ).json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    s,
  );
  await page.goto("/");
  await page.getByLabel("Своё действие или реплика").fill("Черновик #86");
  await nav(page, "Персонажи");
  await page.getByRole("combobox", { name: "Персонаж", exact: true }).click();
  await page.getByLabel("Найти персонажа").fill("Вера");
  await page.getByLabel("Найти персонажа").press("Enter");
  await expect(page.locator(".dossier-header")).toContainText("Вера");
  await page.getByRole("combobox", { name: "Персонаж", exact: true }).click();
  await page.getByLabel("Найти персонажа").fill("НЕТ-ИМЕНИ");
  await expect(page.getByRole("option")).toHaveCount(0);
  await page.getByLabel("Найти персонажа").press("Escape");
  await expect(page.locator(".inspector-workspace")).toBeVisible();
  await page.getByRole("combobox", { name: "Персонаж", exact: true }).click();
  await page.getByLabel("Найти персонажа").fill("");
  await page.getByLabel("Найти персонажа").press("Escape");
  await page.getByLabel("Только рядом").check();
  await expect(page.locator(".inspector-counter")).not.toHaveText("0 / 0");
  await page.getByLabel("Только рядом").uncheck();
  await nav(page, "Сцена");
  const area = page.locator(".inspector-workspace");
  await area.locator(".inspector-person-row").first().click();
  await expect(area).toHaveAttribute("aria-label", "Персонажи");
  await area.getByRole("button", { name: "Закрыть", exact: true }).click();
  await expect(area).toHaveAttribute("aria-label", "Сцена");
  await area
    .getByRole("button", { name: "Уточнить сцену", exact: true })
    .click();
  await area.getByLabel("Место", { exact: true }).fill("Архив — уточнение");
  await nav(page, "Память");
  await nav(page, "Сцена");
  await expect(area.getByLabel("Место", { exact: true })).toHaveValue(
    "Архив — уточнение",
  );
  await area.getByRole("button", { name: "Отмена", exact: true }).click();
  await expect(
    area.getByRole("button", { name: "Уточнить сцену", exact: true }),
  ).toBeVisible();
  await area
    .getByRole("button", { name: "Настройки и сведения о мире", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText("Основа v");
  await expect(
    page.getByRole("dialog").getByRole("button", { name: "Исходная выжимка" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await area.getByRole("button", { name: "Закрыть", exact: true }).click();
  await expect(page.getByLabel("Своё действие или реплика")).toHaveValue(
    "Черновик #86",
  );
});

test("real directed filters, thread statuses, memory search and scene save retry", async ({
  page,
  request,
}) => {
  const response = await request.post(
    "/test/ui-completion-seed?checkpoint=ui-inspector",
  );
  expect(response.ok()).toBe(true);
  const s = await response.json();
  const before = await (await request.get(`/api/saves/${s.save}`)).json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    s,
  );
  await page.goto("/");
  await nav(page, "Отношения");
  const area = page.locator(".inspector-workspace");
  // The shared card also exists in the collapsed editor. Only the main
  // projection belongs to the direction/search filter under test.
  const relations = area.locator(".inspector-stack > .inspector-relation");
  const editor = area.locator(".inspector-editor-disclosure");
  const actor = before.state.controlled_actor_id;
  const canonical = Object.values(before.state.world.relationships) as {
    source_id: string; target_id: string;
  }[];
  const pairs = (rows: typeof canonical) => rows.map(r => `${r.source_id}->${r.target_id}`).sort();
  const outgoing = pairs(canonical.filter(r => r.source_id === actor));
  const incoming = pairs(canonical.filter(r => r.target_id === actor));
  const renderedPairs = () => relations.evaluateAll(rows => rows.map(r =>
    `${r.getAttribute("data-source")}->${r.getAttribute("data-target")}`).sort());
  expect(outgoing).toEqual(["qa_kirill->qa_timur", "qa_kirill->qa_vera"]);
  expect(incoming).toEqual(["qa_oleg->qa_kirill", "qa_vera->qa_kirill"]);
  await expect(relations).toHaveCount(2);
  await expect.poll(renderedPairs).toEqual(outgoing);
  // Explain the former broad selector's extra matches: two non-visible editor
  // representations of these same API records, not additional logical edges.
  await expect(editor).not.toHaveAttribute("open");
  const editorRelations = editor.locator(".inspector-relation");
  await expect(editorRelations).toHaveCount(2);
  await expect(editorRelations.first()).toBeHidden();
  expect(await editorRelations.evaluateAll(rows => rows.map(r =>
    `${r.getAttribute("data-source")}->${r.getAttribute("data-target")}`).sort())).toEqual(outgoing);
  await expect(area.locator(".inspector-relation:visible")).toHaveCount(2);
  await area.getByRole("button", { name: "От других", exact: true }).click();
  await expect(relations).toHaveCount(2);
  await expect.poll(renderedPairs).toEqual(incoming);
  const reverse = relations.filter({has: page.locator('[data-dimension="respect"]')}).filter({hasText:"не согласна"});
  await expect(reverse).toHaveCount(1);
  await expect(reverse).toHaveAttribute("data-source", "qa_vera");
  await expect(reverse).toHaveAttribute("data-target", "qa_kirill");
  await expect(reverse.locator('[data-dimension="trust"] meter')).toHaveAttribute("value", "-20");
  await expect(reverse.locator('[data-dimension="respect"] meter')).toHaveAttribute("value", "45");
  await nav(page, "Сюжет");
  await area.getByRole("button", { name: "На паузе", exact: true }).click();
  await expect(area.locator(".inspector-thread")).toHaveCount(1);
  await expect(area.locator(".inspector-thread")).toContainText(
    "Возвращение на пристань",
  );
  await area.getByText("Развитие линии", { exact: true }).click();
  await expect(area.locator(".inspect-detail:visible")).toContainText(
    "Записанное состояние",
  );
  await area.getByRole("button", { name: "Завершённые", exact: true }).click();
  await expect(area.locator(".inspector-thread")).toContainText(
    "Завершённая реставрация",
  );
  await nav(page, "Память");
  await area
    .getByRole("button", { name: "Известно персонажу", exact: true })
    .click();
  await nav(page, "Мир");
  await nav(page, "Память");
  await expect(
    area.getByRole("button", { name: "Известно персонажу", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await area
    .getByRole("button", { name: "Известно игроку", exact: true })
    .click();
  await area.getByLabel("Поиск в памяти").fill("Библиотека");
  await expect(area.locator(".inspector-timeline-event")).toHaveCount(1);
  await area.getByLabel("Поиск в памяти").fill("ничего-не-найдено");
  await expect(area.locator(".inspector-timeline-event")).toHaveCount(0);
  await nav(page, "Мир");
  await nav(page, "Память");
  await expect(area.getByLabel("Поиск в памяти")).toHaveValue(
    "ничего-не-найдено",
  );
  await nav(page, "Сцена");
  await area
    .getByRole("button", { name: "Уточнить сцену", exact: true })
    .click();
  await area.getByLabel("Место", { exact: true }).fill("Озёрск — мастерская");
  let fail = true;
  await page.route(`**/api/saves/${s.save}/scene`, async (route) => {
    if (fail) {
      fail = false;
      await route.fulfill({
        status: 503,
        json: { detail: "QA temporary failure" },
      });
    } else await route.continue();
  });
  await area
    .getByRole("button", { name: "Сохранить строку сцены", exact: true })
    .click();
  await expect(area.getByRole("alert")).toContainText("QA temporary failure");
  await expect(area.getByLabel("Место", { exact: true })).toHaveValue(
    "Озёрск — мастерская",
  );
  await area
    .getByRole("button", { name: "Сохранить строку сцены", exact: true })
    .click();
  await expect(
    area.getByRole("button", { name: "Уточнить сцену", exact: true }),
  ).toBeVisible();
  await expect
    .poll(
      async () =>
        (await (await request.get(`/api/saves/${s.save}`)).json()).scene_meta
          .location,
    )
    .toBe("Озёрск — мастерская");
  expect(
    (await (await request.get(`/api/saves/${s.save}`)).json()).state.world_clock
      .minute,
  ).toBe(before.state.world_clock.minute);
});

test("phone projection stays remote and returns to the existing device", async ({
  page,
  request,
}) => {
  const s = await (
    await request.post("/test/phone-seed?incoming=false&decision=answer")
  ).json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    s,
  );
  await page.goto("/");
  await page.getByLabel("Своё действие или реплика").fill("Черновик разговора");
  const phone = page.getByRole("region", { name: "Телефон персонажа" });
  await page.getByRole("button", { name: /^Телефон/ }).click();
  await phone.getByRole("button", { name: "Контакты", exact: true }).click();
  await phone.getByRole("button", { name: "Вера работа", exact: true }).click();
  await phone.getByRole("button", { name: "Позвонить", exact: true }).click();
  const call=page.getByRole("dialog", { name: "Сцена звонка" });
  await expect(call).toBeVisible();
  await call.getByRole("button", { name: "Свернуть звонок" }).click();
  await nav(page, "Сцена");
  await expect(phone).not.toBeVisible();
  await expect(page.locator(".inspector-remote")).toContainText("Вера");
  await expect(page.locator(".inspector-remote")).toContainText(
    "не означает физического присутствия",
  );
  await page
    .getByRole("button", { name: "Перейти к телефону", exact: true })
    .click();
  await expect(phone).toBeVisible();
  await expect(
    phone.getByRole("button", { name: "Завершить разговор", exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByLabel("Своё действие или реплика")).toHaveValue(
    "Черновик разговора",
  );
});

test("browser Back closes settings, source dossier, then workspace without losing draft", async ({
  page,
  request,
}) => {
  const s = await (
    await request.post("/test/ui-completion-seed?checkpoint=ui-inspector")
  ).json();
  await page.addInitScript(
    (s) => localStorage.setItem("selection", JSON.stringify(s)),
    s,
  );
  await page.goto("/");
  await page.getByLabel("Своё действие или реплика").fill("Android Back");
  await nav(page, "Сцена");
  const area = page.locator(".inspector-workspace");
  await area.locator(".inspector-person-row").first().click();
  await area
    .getByRole("button", { name: "Настройки и сведения о мире", exact: true })
    .click();
  await page.goBack();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(area).toHaveAttribute("aria-label", "Персонажи");
  await page.goBack();
  await expect(area).toHaveAttribute("aria-label", "Сцена");
  await page.goBack();
  await expect(area).not.toBeVisible();
  await expect(page.getByLabel("Своё действие или реплика")).toHaveValue(
    "Android Back",
  );
});

test('approved Graphite tonal roles stay scoped to Inspector', async ({page,request},info)=>{
 test.skip(info.project.name!=='desktop');
 const s=await(await request.post('/test/ui-completion-seed?checkpoint=ui-inspector')).json();
 await request.put(`/api/worlds/${s.world}/presentation`, {data:{theme_id:'graphite'}});
 await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),s);
 await page.goto('/');
 const rootBefore=await page.evaluate(()=>getComputedStyle(document.documentElement).getPropertyValue('--bg'));
 await nav(page,'Мир');
 const colors=await page.evaluate(()=>{
  const css=(q:string)=>getComputedStyle(document.querySelector(q)!);
  return {background:css('.inspector-workspace').backgroundColor,nav:css('.nav-rail').backgroundColor,hero:css('.inspector-world-hero').backgroundColor,card:css('.inspector-columns .inspector-card').backgroundColor,border:css('.inspector-columns .inspector-card').borderTopColor,prose:css('.inspector-card .prose').color,secondary:css('.inspector-page-heading p').color,selected:css('.nav-links button.current').backgroundColor};
 });
 expect(colors).toEqual({background:'rgb(28, 30, 33)',nav:'rgb(23, 25, 28)',hero:'rgb(37, 39, 43)',card:'rgb(32, 34, 38)',border:'rgb(58, 60, 64)',prose:'rgb(238, 237, 233)',secondary:'rgb(170, 173, 178)',selected:'rgb(59, 52, 41)'});
 expect(await page.evaluate(()=>getComputedStyle(document.documentElement).getPropertyValue('--bg'))).toBe(rootBefore);
 await nav(page,'Тайны');
 await expect(page.getByRole('heading', {name: /Брак:.*Кирилл/})).toBeVisible();
});
