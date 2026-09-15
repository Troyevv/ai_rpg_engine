import { useEffect, useState } from "react";
import { BookOpen, Plus, Upload } from "lucide-react";
import { toast } from "sonner";
import { api } from "./api";
import type { WorldItem, SaveItem, World, Save } from "./types";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { Textarea } from "./components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "./components/ui/dialog";
export function Library({
  open,
  onOpenChange,
  choose,
  prepare,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  choose: (world: number, save?: number) => void;
  prepare: () => void;
}) {
  const [worlds, setWorlds] = useState<WorldItem[]>([]);
  const [selected, setSelected] = useState<number>();
  const [saves, setSaves] = useState<SaveItem[]>([]);
  const [name, setName] = useState("Новое прохождение");
  const [worldName, setWorldName] = useState("");
  const [markdown, setMarkdown] = useState("");
  const [removed,setRemoved] = useState<WorldItem[]>([]);
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    if (open)
      api<WorldItem[]>("/worlds")
        .then(setWorlds)
        .catch((e) => toast.error(e.message));
  }, [open]);
  useEffect(() => {
    setSaves([]);
    if (selected) {
      const c = new AbortController();
      api<SaveItem[]>(`/worlds/${selected}/saves`, undefined, "GET", c.signal)
        .then(setSaves)
        .catch(() => {});
      return () => c.abort();
    }
  }, [selected]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="library-dialog">
        <DialogHeader>
          <DialogTitle>Твои истории</DialogTitle>
          <DialogDescription>
            Выбери мир и продолжи своё прохождение.
          </DialogDescription>
        </DialogHeader>
        <div className="actions">
          <Button
            onClick={() => {
              onOpenChange(false);
              prepare();
            }}
          >
            <Plus size={16} />
            Создать историю
          </Button>
        </div>
        <div className="world-grid">
          {worlds.map((w) => (
            <button
              key={w.id}
              onClick={() => setSelected(w.id)}
              className={`world-card ${selected === w.id ? "selected" : ""}`}
            >
              <BookOpen size={23} />
              <span className="eyebrow">Мир · версия {w.version}</span>
              <strong>{w.name}</strong>
              <span className="muted small">
                {new Date(w.created_at + "Z").toLocaleDateString()}
              </span>
            </button>
          ))}
        </div>
        {!worlds.length && (
          <p className="muted">
            Пока нет миров. Подготовь сценарий или загрузи готовую выжимку.
          </p>
        )}
        {selected && (
          <section className="save-list">
            <h3>Прохождения</h3>
            <Button variant="ghost" disabled={busy} onClick={()=>{if(window.confirm("Удалить эту версию выжимки из библиотеки? Сейвы сохранятся; выжимку можно восстановить."))void run(async()=>{await api(`/worlds/${selected}`,undefined,"DELETE");setWorlds(await api("/worlds"));setSelected(undefined)})}}>Удалить версию выжимки</Button>
            {saves.map((s) => (
              <button
                key={s.id}
                onClick={() => {
                  choose(selected, s.id);
                  onOpenChange(false);
                }}
              >
                <span>{s.name}</span>
                <span>Продолжить →</span>
              </button>
            ))}
            <Button
              variant="ghost"
              onClick={() => {
                choose(selected);
                onOpenChange(false);
              }}
            >
              Посмотреть исходный мир
            </Button>
            <div className="actions">
              <Input
                aria-label="Название прохождения"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <Button
                disabled={busy || !name.trim()}
                onClick={() =>
                  run(async () => {
                    const s = await api<Save>(`/worlds/${selected}/saves`, {
                      name,
                    });
                    choose(selected, s.id);
                    onOpenChange(false);
                  })
                }
              >
                Создать прохождение
              </Button>
            </div>
          </section>
        )}
        <details><summary>Удалённые выжимки</summary><Button variant="ghost" onClick={()=>void api<WorldItem[]>("/worlds?deleted=true").then(setRemoved).catch(e=>toast.error(e.message))}>Обновить корзину</Button>{removed.map(w=><div key={w.id}>{w.name} · v{w.version}<Button size="sm" onClick={()=>void run(async()=>{await api(`/worlds/${w.id}/restore`,{});setWorlds(await api("/worlds"));setRemoved(await api("/worlds?deleted=true"));setSelected(w.id)})}>Восстановить</Button></div>)}</details>
        <details>
          <summary>
            <Upload size={16} />
            Загрузить готовую выжимку
          </summary>
          <label>
            Название мира
            <Input
              value={worldName}
              onChange={(e) => setWorldName(e.target.value)}
            />
          </label>
          <label>
            Markdown-файл (UTF-8)
            <Input
              type="file"
              accept=".md"
              onChange={async (e) => {
                const f = e.target.files?.[0];
                if (f) {
                  try {
                    const text = new TextDecoder("utf-8", {
                      fatal: true,
                    }).decode(await f.arrayBuffer());
                    setMarkdown(text);
                  } catch {
                    toast.error("Файл должен быть в UTF-8");
                  }
                }
              }}
            />
          </label>
          <Textarea
            aria-label="Текст выжимки"
            value={markdown}
            placeholder="Или вставь Markdown"
            onChange={(e) => setMarkdown(e.target.value)}
          />
          <Button
            disabled={busy || !worldName.trim() || !markdown.trim()}
            onClick={() =>
              run(async () => {
                const w = await api<World>("/worlds", {
                  name: worldName,
                  markdown,
                });
                setWorlds(await api("/worlds"));
                setSelected(w.id);
                setMarkdown("");
                toast.success("Мир сохранён");
              })
            }
          >
            Сохранить мир
          </Button>
        </details>
      </DialogContent>
    </Dialog>
  );
}
