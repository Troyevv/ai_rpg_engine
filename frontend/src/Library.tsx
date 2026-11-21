import { Choice } from "@/components/ui/choice";
import { useEffect, useState } from "react";
import { BookOpen, Plus, Upload, X, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { localDate } from "./dates";
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
  open, currentWorld,
  onOpenChange,
  choose,
  prepare,
  chat,
}: {
  open: boolean; currentWorld?:number;
  onOpenChange: (v: boolean) => void;
  choose: (world: number, save?: number) => void;
  prepare: () => void;
  chat?: (source?: {world_id:number}) => void;
}) {
  const [worlds, setWorlds] = useState<WorldItem[]>([]);
  const [selected, setSelected] = useState<number>();
  const selectWorld=(id:number|undefined)=>{
    if(id!==selected)setSaves([]);
    setSelected(id);
  };
  const [saves, setSaves] = useState<SaveItem[]>([]);
  const [mode,setMode]=useState("narrative");
  const [name, setName] = useState("Новое прохождение");
  const [worldName, setWorldName] = useState("");
  const [markdown, setMarkdown] = useState("");
  const [removed,setRemoved] = useState<WorldItem[]>([]);
  const [deleting,setDeleting]=useState<WorldItem|null>(null);
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
  const [refreshKey,setRefreshKey]=useState(0);
  useEffect(() => {
    if (!open)return;
    const controller=new AbortController();
    api<WorldItem[]>("/worlds",undefined,"GET",controller.signal)
      .then(items=>{
        if(controller.signal.aborted)return;
        setWorlds(items);
        setSelected(old=>[old,currentWorld].find(id=>items.some(w=>w.id===id))??items[0]?.id);
      }).catch(e=>{if(!controller.signal.aborted)toast.error(e.message)});
    return ()=>controller.abort();
  }, [open,refreshKey,currentWorld]);
  useEffect(() => {
    if (open && selected) {
      const c = new AbortController();
      api<SaveItem[]>(`/worlds/${selected}/saves`, undefined, "GET", c.signal)
        .then(items=>{if(!c.signal.aborted)setSaves(items)})
        .catch(e=>{if(!c.signal.aborted)toast.error(e.message)});
      return () => c.abort();
    }
  }, [open,selected,refreshKey]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="library-dialog">
        <DialogHeader>
          <DialogTitle>Миры и прохождения</DialogTitle>
          <DialogDescription>
            Выбери мир и продолжи своё прохождение.
          </DialogDescription>
        </DialogHeader>
        <div className="actions library-actions">
          <span>{worlds.length} · Миры</span>
          <Button size="icon" variant="ghost" aria-label="Обновить список" onClick={()=>setRefreshKey(n=>n+1)}><RefreshCw size={16}/></Button>
          {chat&&<Button variant="outline" onClick={()=>chat()}>RP-чат · кампании</Button>}
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
        <div className="library-layout">
        {worlds.length>0&&<label className="library-world-select">Выбрать мир<Choice aria-label="Выбрать мир" value={String(selected??'')} onValueChange={id=>selectWorld(Number(id))}>
          {worlds.map(w=><option key={w.id} value={String(w.id)}>{w.name}</option>)}
        </Choice></label>}
        <div className="world-grid">
          {worlds.map((w) => (
            <article className="world-card-wrap" data-world-id={w.id} key={w.id}><button
              aria-label={`Открыть ${w.name}`}
              onClick={() => selectWorld(w.id)}
              aria-pressed={selected===w.id}
              className={`world-card ${selected === w.id ? "selected" : ""}`}
            >
              <BookOpen size={23} />
              <span className="eyebrow">Мир · версия {w.version}</span>
              <strong>{w.name}</strong>
              <span className="muted small">
                Создана: {localDate(w.created_at)}
              </span>
            </button><button className="world-remove" aria-label={`Удалить ${w.name}`} disabled={busy} onClick={e=>{e.stopPropagation();setDeleting(w)}}><X size={18}/></button></article>
          ))}
        </div>

        {!worlds.length && (
          <p className="muted">
            Пока нет миров. Подготовь сценарий или загрузи готовую выжимку.
          </p>
        )}
        {selected && (
          <section className="save-list">
            <span className="eyebrow">Выбранный мир</span>
            <div className="library-selected"><h3>{worlds.find(w=>w.id===selected)?.name}</h3>
              <button className="library-remove" aria-label="Переместить мир в корзину" onClick={()=>setDeleting(worlds.find(w=>w.id===selected)||null)}><X size={18}/></button>
            </div><h4>Прохождения</h4>

            {saves.map((s) => (
              <button key={s.id}
                onClick={() => {
                  choose(selected, s.id);
                  onOpenChange(false);
                }}
              >
                <span>{s.name} · Narrative</span>
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
            <details><summary>Новое прохождение</summary>
            <label>Режим нового прохождения<Choice aria-label="Режим нового прохождения" value={mode} onValueChange={selectedValue => setMode(selectedValue)}><option value="narrative">Narrative</option><option value="chat">RP-чат</option></Choice></label>
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
                    if(mode==="chat"&&chat){chat({world_id:selected});return;}
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
            </details>
          </section>
        )}
        </div>
        <details><summary>Удалённые выжимки</summary><Button variant="ghost" onClick={()=>void api<WorldItem[]>("/worlds?deleted=true").then(setRemoved).catch(e=>toast.error(e.message))}>Обновить корзину</Button>{removed.map(w=><div data-deleted-world-id={w.id} key={w.id}>{w.name} · v{w.version}<Button size="sm" onClick={()=>void run(async()=>{await api(`/worlds/${w.id}/restore`,{});setWorlds(await api("/worlds"));setRemoved(await api("/worlds?deleted=true"));selectWorld(w.id)})}>Восстановить</Button></div>)}</details>
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
                selectWorld(w.id);
                setMarkdown("");
                toast.success("Мир сохранён");
              })
            }
          >
            Сохранить мир
          </Button>
        </details>
      </DialogContent>
      <Dialog open={!!deleting} onOpenChange={v=>{if(!v&&!busy)setDeleting(null)}}>
        <DialogContent><DialogHeader><DialogTitle>Удалить «{deleting?.name}»?</DialogTitle><DialogDescription>История будет перемещена в удалённые.</DialogDescription></DialogHeader>
        <div className="actions"><Button variant="ghost" disabled={busy} onClick={()=>setDeleting(null)}>Отмена</Button><Button disabled={busy} onClick={()=>void run(async()=>{if(!deleting)return;await api(`/worlds/${deleting.id}`,undefined,"DELETE");setWorlds(await api("/worlds"));setRemoved(await api("/worlds?deleted=true"));if(selected===deleting.id)selectWorld(undefined);setDeleting(null);toast.success("История перемещена в удалённые")})}>Удалить</Button></div></DialogContent>
      </Dialog>
    </Dialog>
  );
}
