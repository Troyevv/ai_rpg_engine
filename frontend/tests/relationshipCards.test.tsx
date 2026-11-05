import { act } from "react";
import { createRoot } from "react-dom/client";
import { it, expect, vi, beforeEach, afterEach } from "vitest";
import { RelationshipCard } from "../src/RelationshipCard";
import { relationshipRows } from "../src/lib/relationshipRows";
import type { State, WorldRelation } from "../src/types";
const observers: { notify: (visible: boolean) => void; disconnect: ReturnType<typeof vi.fn> }[] = [];
beforeEach(() => {
  observers.length = 0;
  vi.stubGlobal("IntersectionObserver", class {
    disconnect = vi.fn();
    constructor(private callback: (entries: { isIntersecting: boolean }[]) => void) {
      observers.push({ notify: (visible) => callback([{ isIntersecting: visible }]), disconnect: this.disconnect });
    }
    observe() { this.callback([{ isIntersecting: true }]); }
  });
});
afterEach(() => vi.unstubAllGlobals());
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

it("keeps signed native semantics and exact labels, and never invents unknown metrics", async () => {
  const host = document.createElement("div");
  const root = createRoot(host);
  const dimensions = { fear: -100, trust: -31, respect: 0, affection: 62, attraction: 100,
    jealousy: { direction: "up", reason: "Известно только изменение" } };
  try {
    await act(() => root.render(<RelationshipCard state={state} relation={{ ...a, dimensions }} />));
    const meters = [...host.querySelectorAll("meter")];
    expect(meters.map(m => [m.min, m.value, m.max])).toEqual(
      [-100, -31, 0, 62, 100].map(value => [-100, value, 100]),
    );
    expect([...host.querySelectorAll<HTMLElement>(".relationship-meter-fill")].map(m => m.style.transform))
      .toEqual(["scaleX(0)", "scaleX(0.345)", "scaleX(0.5)", "scaleX(0.81)", "scaleX(1)"]);
    expect(meters[1].getAttribute("aria-label")).toBe("Доверие: -31; от −100 до 100");
    expect(host.querySelector('[data-dimension="jealousy"] meter')).toBeNull();
    expect(host.querySelector('[data-dimension="irritation"]')).toBeNull();
    expect(host.textContent).toContain("Известно только изменение");
  } finally { await act(() => root.unmount()); }
});

it("replays only on opening or selection, preserves entry across data refresh, and cleans observers", async () => {
  const host = document.createElement("div");
  const root = createRoot(host);
  let relation = a, active = true, motionKey = "all";
  const render = () => act(() => root.render(<RelationshipCard state={state} relation={relation} active={active} motionKey={motionKey} />));
  const track = () => host.querySelector(".relationship-meter")!;
  try {
    await render();
    const first = track();
    expect(first.getAttribute("data-entered")).toBe("true");
    relation = { ...a, dimensions: { ...a.dimensions } };
    await render();
    expect(track()).toBe(first);
    expect(observers).toHaveLength(3);
    relation = { ...a, dimensions: { trust: -20 } };
    await render();
    expect(track()).toBe(first);
    expect(track().getAttribute("data-entered")).toBe("true");
    expect(host.querySelector<HTMLElement>(".relationship-meter-fill")!.style.transform).toBe("scaleX(0.4)");
    expect(observers[1].disconnect).toHaveBeenCalledOnce();
    await act(() => observers[0].notify(false));
    expect(track().getAttribute("data-visible")).toBe("false");
    expect(track().getAttribute("data-entered")).toBe("true");
    active = false;
    await render();
    expect(track().getAttribute("data-entered")).toBe("false");
    await act(() => observers[0].notify(true)); // stale callback after disconnect
    expect(track().getAttribute("data-entered")).toBe("false");
    active = true;
    await render();
    expect(track().getAttribute("data-entered")).toBe("true");
    relation = b;
    await render();
    expect(track()).not.toBe(first);
    const second = track();
    motionKey = "incoming";
    await render();
    expect(track()).not.toBe(second);
  } finally { await act(() => root.unmount()); }
  expect(observers.every(o => o.disconnect.mock.calls.length === 1)).toBe(true);
});
