import { act } from "react";
import { createRoot } from "react-dom/client";
import { it, expect, vi } from "vitest";
import { CurrentGame } from "../src/CurrentGame";
import { api } from "../src/api";
import type { Save } from "../src/types";
vi.mock("../src/api", () => ({ api: vi.fn() }));

it("clears chronology immediately on revision changes and ignores late responses", async () => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const resolves: Array<(value: unknown) => void> = [];
  vi.mocked(api).mockImplementation(
    () => new Promise((resolve) => resolves.push(resolve)),
  );
  let save = {
    id: 1,
    revision: 1,
    turns: [],
    state: {
      characters: [],
      locations: [],
      relationships: [],
      sections: {},
      scene: "",
      story_notes: "",
      controlled_actor_id: "a",
    },
  } as unknown as Save;
  const noop = () => {};
  const render = () =>
    act(() =>
      root.render(
        <CurrentGame
          save={save}
          timeSkip={noop}
          longTerm={noop}
          notices
          policy={noop}
          protagonist={noop}
          camera={noop}
          openCharacter={noop}
          onNotices={noop}
          disabled={false}
          refresh={noop}
        />,
      ),
    );
  const row = (summary: string) => [
    {
      id: summary,
      summary,
      date: "2026-10-08",
      minute: 0,
      category: "marriage",
      actor_ids: [],
    },
  ];
  try {
    await render();
    await act(() => host.querySelector("button")!.click());
    await act(() =>
      document
        .querySelector<HTMLButtonElement>("#management-panel-tab-history")!
        .click(),
    );
    await act(() => resolves[0](row("Previously visible")));
    expect(
      document.querySelector(".management-timeline")?.textContent,
    ).toContain("Previously visible");
    save = { ...save, revision: 2 };
    await render();
    expect(document.querySelector(".management-timeline")).toBeNull();
    save = { ...save, revision: 3 };
    await render();
    await act(() => resolves[2](row("Current visible")));
    await act(() => resolves[1](row("Stale response")));
    expect(
      document.querySelector(".management-timeline")?.textContent,
    ).toContain("Current visible");
    expect(document.body.textContent).not.toContain("Stale response");
    save = {
      ...save,
      revision: 4,
      state: { ...save.state, controlled_actor_id: "b" },
    };
    await render();
    expect(document.querySelector(".management-timeline")).toBeNull();
    await act(() => resolves[3]([]));
    expect(document.body.textContent).toContain("Известных вех нет");
  } finally {
    await act(() => root.unmount());
    host.remove();
    vi.mocked(api).mockReset();
  }
});
