import { useEffect, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  ChevronLeft,
  ChevronRight,
  Download,
} from "lucide-react";
import { toast } from "sonner";
import { api, download } from "./api";
import { type World, type Save, type Scene, active } from "./types";
import { Markdown } from "./Markdown";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "./components/ui/dialog";
export type Panel =
  "Мир" | "Сцена" | "Персонажи" | "Отношения" | "Тайны" | "Сюжет" | "Память";
export function Inspector({
  world,
  save,
  open,
  close,
  panel,
  setPanel,
  character,
  setCharacter,
  refresh,
}: {
  world: World | null;
  save: Save | null;
  open: boolean;
  close: () => void;
  panel: Panel;
  setPanel: (v: Panel) => void;
  character: string;
  setCharacter: (v: string) => void;
  refresh: () => void;
}) {
  const [query, setQuery] = useState("");
  const [near, setNear] = useState(false);
  const [scene, setScene] = useState<Scene>({
    time: "",
    location: "",
    present_ids: [],
  });
  const [busy, setBusy] = useState(false);
  const state = save?.state ?? world?.state;
  const meta = save?.scene_meta ?? world?.scene_meta;
  useEffect(() => {
    setScene(meta ?? { time: "", location: "", present_ids: [] });
  }, [meta]);
  useEffect(() => {
    setQuery("");
    setNear(false);
  }, [open, world?.id]);
  if (!world || !state) return null;
  const cards = state.characters.filter(
    (c) =>
      (!query ||
        [c.name, ...(c.aliases ?? [])]
          .join(" ")
          .toLocaleLowerCase()
          .includes(query.toLocaleLowerCase())) &&
      (!near || meta?.present_ids.includes(c.id)),
  );
  const selected = cards.find((c) => c.id === character) ?? cards[0];
  const name = (id: string) =>
    state.characters.find((c) => c.id === id)?.name ?? id;
  const relations = (id?: string) =>
    state.relationships
      .filter((r) => !id || r.source_id === id)
      .map((r, i) => (
        <section className="relation" key={i}>
          <strong>
            {name(r.source_id)} →{" "}
            {r.target_id ? name(r.target_id) : r.target_name}
          </strong>
          <Markdown text={r.text} />
          {r.change && (
            <p
              className={r.change.direction === "up" ? "positive" : "negative"}
            >
              {r.change.direction === "up" ? (
                <ArrowUp size={16} />
              ) : (
                <ArrowDown size={16} />
              )}{" "}
              {r.change.reason}{" "}
              {r.change.turn !== undefined && `· Ход ${r.change.turn}`}
            </p>
          )}
        </section>
      ));
  return (
    <Dialog open={open} onOpenChange={(v) => !v && close()}>
      <DialogContent className="inspector-dialog">
        <DialogHeader>
          <DialogTitle>{world.name}</DialogTitle>
          <DialogDescription>
            Основа v{world.version} · {save ? save.name : "Исходный мир"}
          </DialogDescription>
        </DialogHeader>
        <details className="metadata">
          <summary>О мире и сохранении</summary>
          <p>Мир создан: {world.created_at}</p>
          {save && (
            <>
              <p>Прохождение #{save.id}</p>
              <p>Обновлено: {save.updated_at}</p>
            </>
          )}
          <Button
            size="sm"
            variant="outline"
            onClick={() => download(world.source_md, `world_${world.id}.md`)}
          >
            <Download size={14} />
            Исходная выжимка
          </Button>
        </details>
        <div className="panel-tabs">
          {(
            [
              "Мир",
              "Сцена",
              "Персонажи",
              "Отношения",
              "Тайны",
              "Сюжет",
              "Память",
            ] as Panel[]
          ).map((p) => (
            <button
              key={p}
              className={panel === p ? "selected" : ""}
              onClick={() => setPanel(p)}
            >
              {p}
            </button>
          ))}
        </div>
        {panel === "Мир" && (
          <>
            <Markdown text={state.sections.tone} />
            {state.locations.map((l, i) => (
              <section key={i}>
                <h3>{l.name}</h3>
                <Markdown text={l.text} />
              </section>
            ))}
          </>
        )}
        {panel === "Сцена" && (
          <>
            <Markdown text={state.scene} />
            {save && (
              <fieldset>
                <legend>Уточнить строку сцены</legend>
                <label>
                  Время
                  <Input
                    value={scene.time}
                    onChange={(e) =>
                      setScene((s) => ({ ...s, time: e.target.value }))
                    }
                  />
                </label>
                <label>
                  Место
                  <Input
                    value={scene.location}
                    onChange={(e) =>
                      setScene((s) => ({ ...s, location: e.target.value }))
                    }
                  />
                </label>
                <p className="muted small">Присутствующие, включая ГГ</p>
                {state.characters.map((c) => (
                  <label className="check" key={c.id}>
                    <input
                      type="checkbox"
                      checked={scene.present_ids.includes(c.id)}
                      onChange={(e) =>
                        setScene((s) => ({
                          ...s,
                          present_ids: e.target.checked
                            ? [...s.present_ids, c.id]
                            : s.present_ids.filter((id) => id !== c.id),
                        }))
                      }
                    />
                    {c.name}
                  </label>
                ))}
                <Button
                  disabled={busy || active(save.job)}
                  onClick={async () => {
                    setBusy(true);
                    try {
                      await api(
                        `/saves/${save.id}/scene`,
                        { ...scene, revision: save.revision },
                        "PATCH",
                      );
                      refresh();
                      toast.success("Сцена обновлена");
                    } catch (e) {
                      toast.error((e as Error).message);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  Сохранить строку сцены
                </Button>
              </fieldset>
            )}
          </>
        )}
        {panel === "Персонажи" && (
          <>
            <Input
              aria-label="Найти персонажа"
              placeholder="Имя или прозвище"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <label className="check">
              <input
                type="checkbox"
                checked={near}
                onChange={(e) => setNear(e.target.checked)}
              />
              Только рядом
            </label>
            {selected ? (
              <>
                <div className="character-nav">
                  <Button
                    aria-label="Предыдущий персонаж"
                    variant="ghost"
                    size="icon"
                    onClick={() =>
                      setCharacter(
                        cards[
                          (cards.indexOf(selected) - 1 + cards.length) %
                            cards.length
                        ].id,
                      )
                    }
                  >
                    <ChevronLeft />
                  </Button>
                  <select
                    aria-label="Персонаж"
                    value={selected.id}
                    onChange={(e) => setCharacter(e.target.value)}
                  >
                    {cards.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                  <Button
                    aria-label="Следующий персонаж"
                    variant="ghost"
                    size="icon"
                    onClick={() =>
                      setCharacter(
                        cards[(cards.indexOf(selected) + 1) % cards.length].id,
                      )
                    }
                  >
                    <ChevronRight />
                  </Button>
                </div>
                <p className="eyebrow">
                  {cards.indexOf(selected) + 1} / {cards.length} · Карточка
                  ведущего
                </p>
                <h2>{selected.name}</h2>
                <p className="muted small">
                  Может содержать скрытые намерения.
                </p>
                {Object.entries(selected.fields)
                  .filter(([k]) => !k.startsWith("Отношение к "))
                  .map(([k, v]) => (
                    <section key={k}>
                      <h3>{k}</h3>
                      <Markdown text={v} />
                    </section>
                  ))}
                <h3>Текущие отношения</h3>
                {relations(selected.id)}
              </>
            ) : (
              <p className="muted">Персонажи не найдены.</p>
            )}
          </>
        )}
        {panel === "Отношения" && relations()}
        {panel === "Тайны" && (
          <>
            <p className="eyebrow">Данные ведущего · спойлеры</p>
            <Markdown text={state.sections.knowledge} />
            {state.facts?.map((f, i) => (
              <section key={i}>
                <Markdown text={f.text} />
                <p className="muted small">
                  Знают: {f.known_by.map(name).join(", ")}
                </p>
              </section>
            ))}
          </>
        )}
        {panel === "Сюжет" && (
          <>
            <Markdown text={state.story_notes} />
            {state.plans?.map((p, i) => (
              <section key={i}>
                <Markdown text={p.text} />
                <span className="pill">
                  {{
                    open: "Открыто",
                    done: "Выполнено",
                    cancelled: "Отменено",
                  }[p.status] ?? p.status}
                </span>
              </section>
            ))}
          </>
        )}
        {panel === "Память" && (
          <>
            {state.events?.length ? (
              state.events.map((e, i) => (
                <section key={i}>
                  <p className="eyebrow">Ход {e.turn}</p>
                  <Markdown text={e.text} />
                  <p className="muted small">
                    {e.character_ids.map(name).join(", ")}
                  </p>
                </section>
              ))
            ) : (
              <p className="muted">События появятся после игровых ходов.</p>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
