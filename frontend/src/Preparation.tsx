import {Versions} from "./Versions";
import {Diagnostics} from "./Diagnostics";
import { useEffect, useState } from "react";
import { Download, Send, Plus, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { api, download } from "./api";
import { useJob } from "./hooks";
import {
  active,
  type Workspace,
  type Job,
  type Preferences,
  type World,
} from "./types";
import { Markdown } from "./Markdown";
import { JobView } from "./JobView";
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
export function Preparation({
  prefs,
  apiKey,
  onWorld,
  onDraft,
}: {
  prefs: Preferences;
  apiKey: string;
  onWorld: (id: number) => void;
  onDraft?: (id: string) => void;
}) {
  const [list, setList] = useState<{ id: string; name: string }[]>([]);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [id, setId] = useState(localStorage.getItem("workspace") || "");
  const [text, setText] = useState("");
  const [name, setName] = useState("Новая история");
  const [saveName, setSaveName] = useState("");
  const [versionKind,setVersionKind] = useState<"idea"|"summary"|null>(null);
  const [removed,setRemoved] = useState<{id:string;name:string;revision:number}[]>([]);
  const [diagnostics,setDiagnostics] = useState(false);
  const [saveOpen, setSaveOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const refresh = () => {
    if (id)
      api<Workspace>(`/workspaces/${id}`)
        .then(setWorkspace)
        .catch((e) => toast.error(e.message));
  };
  useEffect(() => {
    api<{ id: string; name: string }[]>("/workspaces")
      .then(setList)
      .catch((e) => toast.error(e.message));
  }, []);
  useEffect(() => {
    setWorkspace(null);
    if (id) {
      localStorage.setItem("workspace", id);
      const c = new AbortController();
      api<Workspace>(`/workspaces/${id}`, undefined, "GET", c.signal)
        .then(setWorkspace)
        .catch(() => {});
      return () => c.abort();
    }
  }, [id]);
  const { job, reconnecting } = useJob(workspace?.job, refresh);
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
  const generate = (kind: "idea" | "summary") =>
    run(async () => {
      if (!workspace) return;
      const j = await api<Job>(`/workspaces/${id}/generate`, {
        kind,
        text,
        revision: workspace.revision,
        config: prefs[kind],
        api_key: apiKey,
      });
      setWorkspace((w) => (w ? { ...w, job: j } : w));
      if (kind === "idea") setText("");
    });
  return (
    <main className="preparation">
      {workspace&&<><Diagnostics workspaceId={workspace.id} open={diagnostics} onOpenChange={setDiagnostics}/><Button variant="ghost" onClick={()=>setDiagnostics(true)}>Запросы и расходы мастерской</Button></>}
      <div className="page-heading">
        <div>
          <p className="eyebrow">Мастерская историй</p>
          <h1>Сначала — искра.</h1>
          <p className="muted">Опиши мир, который хочется прожить.</p>
        </div>
        <Sparkles size={30} className="accent" />
      </div>
      <div className="workspace-bar">
        <select
          aria-label="Подготовка"
          value={id}
          onChange={(e) => setId(e.target.value)}
        >
          <option value="">Выбрать сценарий</option>
          {list.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </select>
        <Input
          aria-label="Название сценария"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <Button
          variant="outline"
          disabled={busy || !name.trim()}
          onClick={() =>
            run(async () => {
              const w = await api<Workspace>("/workspaces", { name });
              setList((items) => [{ id: w.id, name: w.name }, ...items]);
              setId(w.id);
            })
          }
        >
          <Plus size={16} />
          Новый сценарий
        </Button>
      </div>
      {workspace&&<Versions kind={versionKind||"summary"} owner={workspace.id} open={!!versionKind} close={()=>setVersionKind(null)} changed={refresh}/>}
      <details><summary>Удалённые сценарии</summary><Button variant="ghost" onClick={()=>void api<typeof removed>("/workspaces?deleted=true").then(setRemoved).catch(e=>toast.error(e.message))}>Обновить корзину</Button>{removed.map(w=><div key={w.id}>{w.name}<Button size="sm" onClick={()=>void run(async()=>{await api(`/workspaces/${w.id}/restore`,{revision:w.revision});setList(await api("/workspaces"));setRemoved(await api("/workspaces?deleted=true"));setId(w.id)})}>Восстановить</Button></div>)}</details>
      {workspace && onDraft && <Button disabled={busy || active(job) || !workspace.idea} onClick={()=>onDraft(workspace.id)}>Продолжить в редакторе мира</Button>}
      {workspace ? (
        <>
          <div className="preparation-grid">
            <section className="document">
              <p className="eyebrow">01 · Сценарист</p>
              <h2>Замысел</h2>
              <Button variant="ghost" size="sm" onClick={()=>setVersionKind("idea")}>Версии сценария</Button>
              {workspace.idea ? (
                <details open>
                  <summary>Сценарий готов</summary>
                  <Markdown text={workspace.idea} />
                </details>
              ) : (
                <p className="empty-copy">
                  Персонажи, атмосфера, место встречи. Нескольких предложений
                  достаточно для начала.
                </p>
              )}
              {job?.kind === "idea" && (
                <JobView
                  job={job}
                  reconnecting={reconnecting}
                  stop={() =>
                    run(async () => {
                      await api(`/jobs/${job.id}/stop`, {});
                      refresh();
                    })
                  }
                />
              )}
              <div className="actions">
                {workspace.idea && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => download(workspace.idea, "idea.md")}
                  >
                    <Download size={14} />
                    Скачать сценарий
                  </Button>
                )}
              </div>
              {workspace.messages.length > 0 && (
                <details>
                  <summary>История требований</summary>
                  {workspace.messages.map((m, i) => (
                    <p className="requirement" key={i}>
                      {m.content}
                    </p>
                  ))}
                </details>
              )}
              <Textarea
                aria-label="Идея или правки сценария"
                placeholder="Современный город, компания друзей, юмор и немного романтики…"
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
              <Button
                disabled={busy || active(job) || !text.trim()}
                onClick={() => generate("idea")}
              >
                <Send size={15} />
                {workspace.idea ? "Доработать сценарий" : "Написать сценарий"}
              </Button>
            </section>
            <section className="document">
              <p className="eyebrow">02 · Генератор выжимки</p>
              <h2>Основа мира</h2>
              <Button variant="ghost" size="sm" onClick={()=>setVersionKind("summary")}>Версии выжимки</Button>
              {workspace.summary&&<Button variant="ghost" size="sm" disabled={busy||active(job)} onClick={()=>{if(window.confirm("Удалить текущую выжимку? Её версии и сохранённые миры останутся."))void run(async()=>{const h=await api<{active_id:number}>(`/documents/summary/${id}`);await api(`/documents/summary/${id}`,{content:"",expected_head:h.active_id});refresh()})}}>Удалить выжимку</Button>}
              {workspace.summary ? (
                <details open>
                  <summary>
                    {workspace.summary_complete
                      ? "Выжимка готова"
                      : "Черновик выжимки"}
                  </summary>
                  <Markdown text={workspace.summary} />
                </details>
              ) : (
                <p className="empty-copy">
                  Когда замысел сложится, преврати его в подробный мир:
                  характеры, отношения, тайны и стартовую сцену.
                </p>
              )}
              {job?.kind === "summary" && (
                <JobView
                  job={job}
                  reconnecting={reconnecting}
                  stop={() =>
                    run(async () => {
                      await api(`/jobs/${job.id}/stop`, {});
                      refresh();
                    })
                  }
                />
              )}
              <div className="actions">
                <Button
                  disabled={busy || active(job) || !workspace.idea}
                  onClick={() => generate("summary")}
                >
                  Создать выжимку
                </Button>
                {workspace.summary_complete && (
                  <Button
                    variant="outline"
                    disabled={active(job)}
                    onClick={() => {
                      setSaveName(workspace.name);
                      setSaveOpen(true);
                    }}
                  >
                    Сохранить выжимку
                  </Button>
                )}
              </div>
              {workspace.summary && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => download(workspace.summary, "summary.md")}
                >
                  <Download size={14} />
                  Скачать выжимку
                </Button>
              )}
              {job?.status === "error" && job.narrative && (
                <Button
                  variant="ghost"
                  onClick={() => download(job.narrative, "draft.md")}
                >
                  Скачать черновик ответа
                </Button>
              )}
            </section>
          </div>
          <Button variant="ghost" disabled={busy||active(job)} onClick={()=>{if(window.confirm("Удалить сценарий вместе с рабочей выжимкой? Сохранённые миры и история версий останутся."))void run(async()=>{await api(`/workspaces/${id}`,{revision:workspace.revision},"DELETE");setId("");setWorkspace(null);setList(await api("/workspaces"))})}}>Удалить сценарий</Button>
          <Button
            className="reset-button"
            variant="ghost"
            disabled={busy || active(job)}
            onClick={() => {
              if (
                window.confirm(
                  "Очистить сценарий и выжимку? Сохранённые миры останутся.",
                )
              )
                run(async () => {
                  await api(`/workspaces/${id}/reset`, {
                    revision: workspace.revision,
                  });
                  refresh();
                });
            }}
          >
            Очистить сценарий и выжимку
          </Button>
        </>
      ) : (
        <div className="empty-state">
          <Sparkles size={40} />
          <h2>У каждой истории есть начало</h2>
          <p>Создай сценарий кнопкой выше или выбери существующий.</p>
        </div>
      )}
      <Dialog open={saveOpen} onOpenChange={setSaveOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Сохранить мир</DialogTitle>
            <DialogDescription>
              Выжимка станет основой новых прохождений. То же имя с изменённым
              текстом создаст новую версию.
            </DialogDescription>
          </DialogHeader>
          <Input
            aria-label="Название мира"
            value={saveName}
            onChange={(e) => setSaveName(e.target.value)}
          />
          <Button
            disabled={busy || !saveName.trim()}
            onClick={() =>
              run(async () => {
                const w = await api<World>(`/workspaces/${id}/world`, {
                  name: saveName,
                });
                setSaveOpen(false);
                toast.success("Мир сохранён");
                onWorld(w.id);
              })
            }
          >
            Сохранить мир
          </Button>
        </DialogContent>
      </Dialog>
    </main>
  );
}
