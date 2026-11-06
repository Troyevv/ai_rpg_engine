import { act } from "react";
import { createRoot } from "react-dom/client";
import { it, expect, vi } from "vitest";
import { GameCalendar } from "../src/GameCalendar";
import { api } from "../src/api";
import type { Save } from "../src/types";
vi.mock("../src/api", () => ({ api: vi.fn() }));
it("revision changes immediately remove old events and ignore a late response", async () => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const resolves: Array<(v: any) => void> = [];
  vi.mocked(api).mockImplementation(
    () => new Promise((resolve) => resolves.push(resolve)),
  );
  let save = {
    id: 155,
    revision: 1,
    state: {
      controlled_actor_id: "actor",
      characters: [],
      world_clock: {
        projection: { date: "2026-10-08" },
        calendar: { profile: { system: "gregorian" } },
      },
    },
  } as unknown as Save;
  const render = () => act(() => root.render(<GameCalendar save={save} />));
  const projection = (name: string) => ({
    profile: { system: "gregorian" },
    days: [
      {
        date: "2026-10-08",
        year: 2026,
        month: 10,
        day: 8,
        weekday: 3,
        weather: {
          condition: "rain",
          temperature: 14,
          unit: "C",
          forecast: true,
        },
      },
    ],
    events: [
      {
        id: "private",
        name,
        date: "2026-10-08",
        kind: "personal",
        character_ids: [],
      },
    ],
    scheduled: { items: [], truncated: false },
    notices: [],
  });
  try {
    await render();
    await act(() => resolves[0](projection("OLD PRIVATE")));
    expect(host.textContent).toContain("OLD PRIVATE");
    save = { ...save, revision: 2 };
    await render();
    expect(host.textContent).not.toContain("OLD PRIVATE");
    save = { ...save, revision: 3 };
    await render();
    await act(() => resolves[1](projection("STALE PRIVATE")));
    expect(host.textContent).not.toContain("STALE PRIVATE");
    await act(() => resolves[2](projection("CURRENT")));
    expect(host.textContent).toContain("CURRENT");
    expect(host.textContent).toContain("Дождь · 14°C");
    expect(host.textContent).toContain("Прогноз погоды");
  } finally {
    await act(() => root.unmount());
    host.remove();
    localStorage.clear();
    vi.restoreAllMocks();
  }
});
