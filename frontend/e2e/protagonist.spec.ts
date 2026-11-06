import {gameAction} from './navigation';
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
  await gameAction(page,'Сменить главного героя');
  const dialog = page.getByRole("dialog").last();
  await dialog.getByLabel("Новый главный герой").selectOption("qa_asya");
  await dialog.getByRole("button", { name: "Проверить и посмотреть" }).click();
  await expect(dialog.getByText("Готово к подтверждению")).toBeVisible();
  await dialog.getByRole("button", { name: "Подтвердить смену" }).click();
  await expect(dialog).toBeHidden();
  let save = await (await request.get(`/api/saves/${selected.save}`)).json();
  expect(save.state.protagonist_id).toBe("qa_asya");
  expect(save.state.controlled_actor_id).toBe("qa_asya");
  const count = save.state.characters.length;
  await gameAction(page,'Сменить главного героя');
  await dialog
    .getByRole("button", { name: "Создать нового", exact: true })
    .click();
  await dialog.getByRole("button", { name: "Отмена", exact: true }).click();
  save = await (await request.get(`/api/saves/${selected.save}`)).json();
  expect(save.state.characters).toHaveLength(count);
  await gameAction(page,'Сменить главного героя');
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
    page.locator(".current-game-entry button"),
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
  await gameAction(page,'Сменить главного героя');
  const dialog = page.getByRole("dialog").last();
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

test('control commit keeps actions locked until the refreshed revision arrives', async ({page,request}) => {
  const selected=await(await request.post('/test/seed')).json();
  await page.addInitScript(s=>localStorage.setItem('selection',JSON.stringify(s)),selected);
  await page.goto('/');
  await page.getByRole('button',{name:'Начать игру',exact:true}).click();
  await expect(page.locator('.turn')).toHaveCount(1);
  const before=await(await request.get(`/api/saves/${selected.save}`)).json();
  const usage=await(await request.get(`/api/saves/${selected.save}/accounting`)).json();
  let release!:()=>void;
  let arrived!:()=>void;
  const gate=new Promise<void>(resolve=>release=resolve);
  const refreshing=new Promise<void>(resolve=>arrived=resolve);
  await page.route(`**/api/saves/${selected.save}`,async route=>{
    const response=await route.fetch();const value=await response.json();
    if(value.revision>before.revision){arrived();await gate;}
    await route.fulfill({response,json:value});
  });
  const committed=page.waitForResponse(r=>r.url().endsWith('/protagonist')&&r.request().method()==='POST');
  if(await page.getByLabel('Управляемый персонаж').isVisible())await page.getByLabel('Управляемый персонаж').selectOption('character_2');
  else{
    await page.locator('.mobile-pov button').first().click();
    await page.getByRole('dialog').last().getByRole('button',{name:before.state.characters.find((c:any)=>c.id==='character_2').name,exact:true}).click();
  }
  try{
    expect((await committed).ok()).toBe(true);
    await refreshing;
    await expect(page.getByRole('button',{name:'Мир без ГГ',exact:true})).toBeDisabled();
    await expect(page.getByRole('button',{name:'Мир без ГГ',exact:true})).toBeDisabled();
  }finally{release();}
  await expect(page.getByRole('button',{name:'Мир без ГГ',exact:true})).toBeEnabled();
  const after=await(await request.get(`/api/saves/${selected.save}`)).json();
  expect(after.state.controlled_actor_id).toBe('character_2');
  expect(after.state.protagonist_id).toBe(before.state.protagonist_id);
  expect(after.turns).toHaveLength(before.turns.length);
  expect((await(await request.get(`/api/saves/${selected.save}/accounting`)).json()).requests).toHaveLength(usage.requests.length);
  await page.getByRole('button',{name:'Мир без ГГ',exact:true}).click();
  await expect(page.locator('.turn')).toHaveCount(2);
});
