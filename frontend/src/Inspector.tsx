import {CharacterView} from './CharacterDossier';
import {dossierText as t,type DossierTab} from './lib/dossier';
import {CharacterAvatar} from "./Portrait";
import {SectionTabs} from "./components/ui/section-tabs";
import {ThemeSelector} from "./ThemeProvider";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Download,
  Maximize2, Minimize2,
} from "lucide-react";
import { toast } from "sonner";
import { api, download } from "./api";
import { type World, type Save, type Scene, active } from "./types";
import {localDate} from "./dates";
import {WorldView,SceneOverview,RelationsView,SecretsView,ThreadsView,MemoryView,Reveal} from "./InspectorViews";
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
  const [dossierTab,setDossierTab]=useState<DossierTab>('overview');
  const [expanded,setExpanded]=useState(()=>sessionStorage.getItem('dossier-expanded')==='yes');
  const scrolls=useRef(new Map<string,number>());
  const dialogRef=useRef<HTMLDivElement>(null);
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
  const cards = (state?.characters||[]).filter(
    (c) =>
      (!query ||
        [c.name, ...(c.aliases ?? [])]
          .join(" ")
          .toLocaleLowerCase()
          .includes(query.toLocaleLowerCase())) &&
      (!near || meta?.present_ids.includes(c.id)),
  );
  const selected = cards.find((c) => c.id === character) ?? cards[0];
  const scrollKey=`${save?.id||world?.id}:${state?.controlled_actor_id}:${selected?.id}:${panel}:${dossierTab}`;
  useLayoutEffect(()=>{const el=dialogRef.current;if(open&&el)el.scrollTop=scrolls.current.get(scrollKey)||0},[open,scrollKey]);
  useEffect(()=>{if(open&&panel==='Персонажи'&&selected&&selected.id!==character)setCharacter(selected.id)},[open,panel,selected?.id,character,setCharacter]);
  if (!world || !state) return null;
  return (
    <Dialog open={open} onOpenChange={(v) => !v && close()}>
      <DialogContent ref={dialogRef} onOpenAutoFocus={e=>{if(panel==='Персонажи'){e.preventDefault();requestAnimationFrame(()=>{const el=dialogRef.current;if(el){el.querySelector<HTMLButtonElement>('.dossier-tabs [aria-selected="true"]')?.focus({preventScroll:true});el.scrollTop=scrolls.current.get(scrollKey)||0}})}}} onScroll={e=>scrolls.current.set(scrollKey,e.currentTarget.scrollTop)} className={`inspector-dialog ${panel==='Персонажи'?'dossier-inspector':''} ${expanded&&panel==='Персонажи'?'dossier-expanded':''}`}>
        {panel==='Персонажи'&&<button className="dossier-width-toggle" aria-label={t(expanded?'collapse':'expand')} aria-pressed={expanded} onClick={()=>{setExpanded(!expanded);sessionStorage.setItem('dossier-expanded',!expanded?'yes':'no')}}>{expanded?<Minimize2 size={18}/>:<Maximize2 size={18}/>}</button>}
        <DialogHeader>
          <DialogTitle title={world.name}>{world.name}</DialogTitle>
          <DialogDescription>
            Основа v{world.version} · {save ? save.name : "Исходный мир"}
          </DialogDescription>
        </DialogHeader>
        <details className="theme-disclosure"><summary>Тема мира</summary><ThemeSelector/></details>
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
        <SectionTabs className="panel-tabs" label="Разделы справочника" value={panel} onChange={setPanel} items={(["Мир","Сцена","Персонажи","Отношения","Тайны","Сюжет","Память"] as Panel[]).map(id=>({id,label:id}))}/>
        {panel === "Мир" && <WorldView saveId={save?.id} state={state} meta={meta}/>}
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
                  <CharacterAvatar subject={selected} saveId={save?.id} size={32}/>
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
                <p className="eyebrow character-index">
                  {cards.indexOf(selected) + 1} / {cards.length} · Карточка
                  ведущего
                </p>
                <CharacterView state={state} card={selected} save={save} refresh={refresh} tab={dossierTab} setTab={setDossierTab} onCharacter={id=>{setQuery('');setNear(false);setCharacter(id)}}/>
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
