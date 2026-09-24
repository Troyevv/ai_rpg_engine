import { useEffect, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Download,
} from "lucide-react";
import { toast } from "sonner";
import { api, download } from "./api";
import { type World, type Save, type Scene, active } from "./types";
import {localDate} from "./dates";
import {WorldView,SceneOverview,CharacterView,RelationsView,SecretsView,ThreadsView,MemoryView,Reveal} from "./InspectorViews";
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
          <p>Мир создан: {localDate(world.created_at)}</p>
          {save && (
            <>
              <p>Прохождение #{save.id}</p>
              <p>Обновлено: {localDate(save.updated_at)}</p>
            </>
          )}
          <Reveal title="Правила повествования / Стиль" text={state.sections.tone} preview={false}/><Reveal title="Особенности и правила истории" text={state.story_notes} preview={false}/>
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
        {panel === "Мир" && <WorldView state={state} meta={meta}/>}
        {panel === "Сцена" && (
          <>
            <SceneOverview state={state} meta={meta}/>
            {save && (
              <details className="inspect-reveal"><summary><span className="inspect-title">Уточнить строку сцены</span></summary><fieldset>
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
              </fieldset></details>
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
                <CharacterView state={state} card={selected} save={save} refresh={refresh}/>
              </>
            ) : (
              <p className="muted">Персонажи не найдены.</p>
            )}
          </>
        )}
        {panel === "Отношения" && <RelationsView state={state} save={save} refresh={refresh}/>}
        {panel === "Тайны" && <SecretsView state={state}/>}
        {panel === "Сюжет" && <ThreadsView state={state}/>}
        {panel === "Память" && <MemoryView state={state}/>}
      </DialogContent>
    </Dialog>
  );
}
