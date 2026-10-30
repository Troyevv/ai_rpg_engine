import { act } from "react";
import { createRoot } from "react-dom/client";
import { it, expect, vi } from "vitest";
import { RelationshipCard } from "../src/RelationshipCard";
import { relationshipRows } from "../src/lib/relationshipRows";
import type { State, WorldRelation } from "../src/types";
const a: WorldRelation = {
  source_id: "a",
  target_id: "b",
  context: "Доверяет",
  dimensions: { trust: 0, fear: -100, respect: 100 },
};
const b: WorldRelation = {
  source_id: "b",
  target_id: "a",
  context: "Сомневается",
  dimensions: { trust: -31 },
};
const state = {
  characters: [
    { id: "a", name: "Анна", fields: {} },
    { id: "b", name: "Борис", fields: {} },
  ],
  relationships: [{ source_id: "a", target_id: "b", text: "старое описание" }],
  world: { relationships: { a, b } },
} as unknown as State;
it("preserves directions, zero and absent dimensions without duplicating legacy projections", () => {
  const rows = relationshipRows(state);
  expect(rows).toHaveLength(2);
  expect(rows[0].context).toBe("Доверяет");
  expect(rows[0].dimensions).toEqual(a.dimensions);
  expect(rows[1].dimensions.trust).toBe(-31);
  expect(rows[0].dimensions.affection).toBeUndefined();
  const updated = {
    ...state,
    world: { ...state.world!, relationships: { b } },
  };
  expect(relationshipRows({ ...updated, relationships: [] })).toEqual([b]);
});
it("renders actual metrics, portraits, full context, links and reactive updates", async () => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const navigate = vi.fn();
  try {
    await act(() =>
      root.render(
        <RelationshipCard state={state} relation={a} onCharacter={navigate} />,
      ),
    );
    expect(host.querySelectorAll("meter")).toHaveLength(3);
    expect(host.querySelector("meter")?.value).toBe(0);
    expect(host.querySelectorAll(".character-avatar")).toHaveLength(2);
    await act(() =>
      host
        .querySelector<HTMLButtonElement>(
          '[aria-label="Открыть досье: Борис"]',
        )!
        .click(),
    );
    expect(navigate).toHaveBeenCalledWith("b");
    await act(() =>
      root.render(
        <RelationshipCard
          state={state}
          relation={{ ...a, context: "Новое описание", dimensions: {} }}
        />,
      ),
    );
    expect(host.textContent).toContain("Новое описание");
    expect(host.querySelector("meter")).toBeNull();
    expect(host.textContent).toContain("Показатели не заданы");
  } finally {
    await act(() => root.unmount());
    host.remove();
  }
});

it("clears an open editor when controlled actor or save changes, without writes", async () => {
  const { RelationshipEditor } = await import("../src/RelationshipEditor");
  const fetcher = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue({ ok: true, json: async () => ["trust"] } as Response);
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  let save = {
    id: 1,
    revision: 1,
    state: {
      ...state,
      controlled_actor_id: "a",
      world: { ...state.world, characters: { a: { life_status: "alive" } } },
    },
  } as unknown as import("../src/types").Save;
  const render = () =>
    act(() =>
      root.render(
        <RelationshipEditor
          save={save}
          card={state.characters[0]}
          refresh={() => {}}
        />,
      ),
    );
  try {
    await render();
    await act(() => {
      host.querySelector("summary")!.click();
    });
    await act(() => {
      Array.from(host.querySelectorAll("button"))
        .find((b) => b.textContent === "Редактировать")!
        .click();
    });
    expect(document.querySelector(".relationship-dialog")).not.toBeNull();
    save = { ...save, state: { ...save.state, controlled_actor_id: "b" } };
    await render();
    expect(document.querySelector(".relationship-dialog")).toBeNull();
    expect(host.textContent).not.toContain("+ Добавить отношение");
    save = {
      ...save,
      id: 2,
      state: { ...save.state, controlled_actor_id: "a" },
    };
    await render();
    expect(document.querySelector(".relationship-dialog")).toBeNull();
    expect(fetcher.mock.calls.every(([url, options]) => String(url)==="/api/markdown" || options?.method==="GET")).toBe(
      true,
    );
  } finally {
    await act(() => root.unmount());
    host.remove();
    fetcher.mockRestore();
  }
});
