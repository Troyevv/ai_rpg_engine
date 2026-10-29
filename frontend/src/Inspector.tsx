import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Download,
  Maximize2,
  Minimize2,
  Settings2,
  MapPin,
  Pencil,
} from "lucide-react";
import { toast } from "sonner";
import { api, download } from "./api";
import { type World, type Save, type State, type Scene, active } from "./types";
import { localDate } from "./dates";
import { ThemeSelector } from "./ThemeProvider";
import { CharacterView } from "./CharacterDossier";
import { CharacterAvatar } from "./Portrait";
import { dossierText, type DossierTab } from "./lib/dossier";
import { it, panelLabel, inspectorSections, type Panel } from "./lib/inspector";
import { Reveal } from "./InspectorViews";
import {
  WorldSection,
  SceneSection,
  RelationsSection,
  SecretsSection,
  ThreadsSection,
  MemorySection,
  InspectorCard,
} from "./InspectorSections";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "./components/ui/dialog";
import "./styles/inspector-workspace.css";
export type { Panel } from "./lib/inspector";

export function CharacterPicker({
  state,
  meta,
  save,
  character,
  setCharacter,
  query,
  setQuery,
  near,
  setNear,
}: {
  state: State;
  meta?: Scene;
  save: Save | null;
  character: string;
  setCharacter: (v: string) => void;
  query: string;
  setQuery: (v: string) => void;
  near: boolean;
  setNear: (v: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const cards = state.characters.filter(
    (c) =>
      (!near || meta?.present_ids.includes(c.id) || meta?.observed_ids?.includes(c.id)) &&
      [c.name, ...(c.aliases || [])]
        .join(" ")
        .toLocaleLowerCase()
        .includes(query.toLocaleLowerCase()),
  );
  const selected = state.characters.find((c) => c.id === character);
  const index = cards.findIndex((c) => c.id === character);
  useEffect(() => {
    if (open) {
      setCursor(Math.max(0, index));
      input.current?.focus();
    }
  }, [open]);
  useEffect(() => {
    setCursor(0);
  }, [query, near]);
  useEffect(() => {
    const click = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", click);
    return () => document.removeEventListener("pointerdown", click);
  }, []);
  const choose = (id: string) => {
    setCharacter(id);
    setOpen(false);
    button.current?.focus({ preventScroll: true });
  };
  return (
    <div
      className="inspector-character-toolbar"
      ref={root}
      onKeyDown={(e) => {
        if (e.key === "Escape" && open) {
          e.preventDefault();
          e.stopPropagation();
          setOpen(false);
          button.current?.focus();
        }
      }}
    >
      <Button
        variant="ghost"
        size="icon"
        aria-label={it("previous")}
        disabled={!cards.length}
        onClick={() =>
          setCharacter(cards[(index - 1 + cards.length) % cards.length].id)
        }
      >
        <ChevronLeft />
      </Button>
      <div className="inspector-combo-wrap">
        <button
          ref={button}
          className="inspector-combo"
          role="combobox"
          data-value={character}
          aria-label={it("selector")}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={open ? "inspector-character-options" : undefined}
          onClick={() => setOpen(!open)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown" || e.key === "ArrowUp") {
              e.preventDefault();
              setOpen(true);
            }
          }}
        >
          {selected && (
            <CharacterAvatar subject={selected} saveId={save?.id} size={30} />
          )}
          <span>{selected?.name || it("noCharacters")}</span>
          <ChevronDown size={15} />
        </button>
        {open && (
          <div className="inspector-combo-popup">
            <Input
              ref={input}
              aria-label={it("searchCharacters")}
              placeholder={it("nameAlias")}
              role="combobox"
              aria-autocomplete="list"
              aria-expanded="true"
              aria-controls="inspector-character-options"
              aria-activedescendant={
                cards[cursor] ? `inspector-option-${cursor}` : undefined
              }
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                  e.preventDefault();
                  const next = Math.max(
                    0,
                    Math.min(
                      cards.length - 1,
                      cursor + (e.key === "ArrowDown" ? 1 : -1),
                    ),
                  );
                  setCursor(next);
                  document
                    .getElementById(`inspector-option-${next}`)
                    ?.scrollIntoView({ block: "nearest" });
                }
                if (e.key === "Enter" && cards[cursor]) {
                  e.preventDefault();
                  choose(cards[cursor].id);
                }
              }}
            />
            <div
              id="inspector-character-options"
              role="listbox"
              aria-label={it("selector")}
            >
              {cards.map((c, i) => (
                <button
                  id={`inspector-option-${i}`}
                  role="option"
                  data-character-id={c.id}
                  aria-selected={character === c.id}
                  className={cursor === i ? "focused" : ""}
                  key={c.id}
                  tabIndex={-1}
                  onClick={() => choose(c.id)}
                >
                  <CharacterAvatar subject={c} saveId={save?.id} size={32} />
                  <span>{c.name}</span>
                </button>
              ))}
            </div>
            {!cards.length && <p role="status">{it("noMatch")}</p>}
          </div>
        )}
      </div>
      <Button
        variant="ghost"
        size="icon"
        aria-label={it("next")}
        disabled={!cards.length}
        onClick={() => setCharacter(cards[(index + 1) % cards.length].id)}
      >
        <ChevronRight />
      </Button>
      <label className="inspector-near">
        <input
          type="checkbox"
          checked={near}
          onChange={(e) => setNear(e.target.checked)}
        />
        <MapPin size={14} />
        {it("near")}
      </label>
      <span className="inspector-counter" aria-live="polite">
        {index < 0 ? 0 : index + 1} / {cards.length}
      </span>
    </div>
  );
}

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
  onPhone,
  navigation,
  infoOpen,
  setInfoOpen,
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
  onPhone: () => void;
  navigation?: ReactNode;
  infoOpen: boolean;
  setInfoOpen: (v: boolean) => void;
}) {
  const state = save?.state ?? world?.state;
  const meta = save?.scene_meta ?? world?.scene_meta;
  const [dossierTab, setDossierTab] = useState<DossierTab>("overview");
  const [expanded, setExpanded] = useState(
    () => sessionStorage.getItem("dossier-expanded") !== "no",
  );
  const [query, setQuery] = useState("");
  const [near, setNear] = useState(false);
  const [sceneEditing, setSceneEditing] = useState(false);
  const [visited, setVisited] = useState<Set<Panel>>(new Set([panel]));
  const [origin, setOrigin] = useState<{
    panel: Panel;
    focus: HTMLElement | null;
  } | null>(null);
  const [characterHistory, setCharacterHistory] = useState<{
    id: string; tab: DossierTab; query: string; near: boolean; scroll: number;
    partnerId?: string;
  }[]>([]);
  const focusOnCharacter = useRef(false);
  const pendingReturn = useRef<{scroll: number; partnerId?: string} | null>(null);
  const scrolls = useRef(new Map<string, number>());
  const scrollRef = useRef<HTMLDivElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const key = `${panel}:${panel === "Персонажи" ? `${character}:${dossierTab}` : ""}`;
  useLayoutEffect(() => {
    if (open && scrollRef.current) {
      const returning = pendingReturn.current;
      scrollRef.current.scrollTop = returning?.scroll ?? scrolls.current.get(key) ?? 0;
      if (returning) {
        pendingReturn.current = null;
        focusOnCharacter.current = false;
        const link = [...scrollRef.current.querySelectorAll<HTMLButtonElement>('[data-partner-id]')]
          .find(el => el.dataset.partnerId === returning.partnerId);
        (link || heading.current)?.focus({preventScroll: true});
      } else if (focusOnCharacter.current) {
        focusOnCharacter.current = false;
        heading.current?.focus({preventScroll: true});
      }
    }
  }, [open, key]);
  useEffect(() => {
    if (open) heading.current?.focus({ preventScroll: true });
  }, [open, panel]);
  useEffect(() => {
    if (open) setVisited((v) => new Set([...v, panel]));
  }, [open, panel]);
  useEffect(() => {
    if (panel !== "Персонажи" || !open) {
      setOrigin(null);
      setCharacterHistory([]);
    }
  }, [panel, open]);
  const cards = (state?.characters || []).filter(
    (c) =>
      (!near || meta?.present_ids.includes(c.id) || meta?.observed_ids?.includes(c.id)) &&
      [c.name, ...(c.aliases || [])]
        .join(" ")
        .toLocaleLowerCase()
        .includes(query.toLocaleLowerCase()),
  );
  const knownSelection = !character || state?.characters.some(c => c.id === character);
  const selected = cards.find(c => c.id === character) || (knownSelection ? cards[0] : undefined);
  useEffect(() => {
    if (open && panel === "Персонажи" && selected && selected.id !== character)
      setCharacter(selected.id);
  }, [open, panel, selected?.id, character, setCharacter]);
  const openCharacter = (id: string) => {
    if (!state?.characters.some(c => c.id === id)) return;
    if (panel === "Персонажи" && selected?.id === id) return;
    if (scrollRef.current) scrolls.current.set(key, scrollRef.current.scrollTop);
    if (panel !== "Персонажи") {
      setOrigin({ panel, focus: document.activeElement as HTMLElement });
    } else if (selected) {
      setCharacterHistory(rows => [...rows, {
        id: selected.id, tab: dossierTab, query, near,
        scroll: scrollRef.current?.scrollTop || 0,
        partnerId: (document.activeElement as HTMLElement)?.dataset.partnerId,
      }]);
    }
    focusOnCharacter.current = true;
    setQuery("");
    setNear(false);
    setDossierTab("overview");
    setCharacter(id);
    setPanel("Персонажи");
  };
  const back = () => {
    // A scroll event can still be queued when Escape/Back hides the surface.
    // Capture the current DOM position before that event loses its open owner.
    if (scrollRef.current) scrolls.current.set(key, scrollRef.current.scrollTop);
    const history = characterHistory.filter(row => state?.characters.some(c => c.id === row.id));
    const previous = history.at(-1);
    if (previous) {
      setCharacterHistory(history.slice(0, -1));
      pendingReturn.current = previous;
      setQuery(previous.query);
      setNear(previous.near);
      setDossierTab(previous.tab);
      setCharacter(previous.id);
    } else if (origin) {
      setCharacterHistory([]);
      const from = origin;
      setOrigin(null);
      setPanel(from.panel);
      requestAnimationFrame(
        () =>
          from.focus?.isConnected && from.focus.focus({ preventScroll: true }),
      );
    } else close();
  };
  const backRef = useRef(back);
  backRef.current = back;
  useEffect(() => {
    if (!open) return;
    const back = () => backRef.current();
    window.addEventListener("inspector-back", back);
    return () => window.removeEventListener("inspector-back", back);
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const escape = (e: KeyboardEvent) => {
      if (
        e.key === "Escape" &&
        !e.defaultPrevented &&
        !document.querySelector('[role="dialog"]')
      ) {
        e.preventDefault();
        backRef.current();
      }
    };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [open]);
  if (!world || !state) return null;
  const previousCharacter = [...characterHistory].reverse().map(row => state.characters.find(c => c.id === row.id)).find(Boolean);
  const props = {
    state,
    meta,
    save,
    onCharacter: openCharacter,
    onPanel: setPanel,
    onPhone,
  };
  const section = inspectorSections.find((s) => s.id === panel)!;
  return (
    <>
      <section
        className="inspector-workspace"
        hidden={!open}
        aria-label={panelLabel(panel)}
      >
        <header className="inspector-topbar">
          {navigation}
          <div className="inspector-breadcrumb">
            <span title={world.name}>{world.name}</span>
            <span>/</span>
            <strong>{panelLabel(panel)}</strong>
          </div>
          <span className="inspector-scope">{it("gm")}</span>
          <Button
            variant="ghost"
            size="icon"
            className="inspector-width"
            aria-label={it(expanded ? "collapse" : "expand")}
            aria-pressed={expanded}
            onClick={() => {
              setExpanded(!expanded);
              sessionStorage.setItem(
                "dossier-expanded",
                expanded ? "no" : "yes",
              );
            }}
          >
            {expanded ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
          </Button>
          <Button
            size="icon"
            variant="ghost"
            aria-label={it("settings")}
            onClick={() => setInfoOpen(true)}
          >
            <Settings2 size={18} />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            aria-label={previousCharacter ? `${dossierText("returnDossier")}: ${previousCharacter.name}` : it("close")}
            onClick={back}
          >
            <ArrowLeft size={17} />
            <span>
              {previousCharacter ? dossierText("backDossier") : origin ? it("backTo") + panelLabel(origin.panel) : it("back")}
            </span>
          </Button>
        </header>
        <div
          ref={scrollRef}
          className={`inspector-scroll ${expanded ? "dossier-expanded" : "inspector-compact"}`}
          onScroll={(e) => {
            if (open) scrolls.current.set(key, e.currentTarget.scrollTop);
          }}
        >
          <div className="inspector-page">
            {panel !== "Персонажи" ? (
              <div className="inspector-page-heading">
                <div>
                  <span className="eyebrow">
                    {it(panel === "Мир" ? "overview" : section.group)}
                  </span>
                  <h1 ref={heading} tabIndex={-1}>
                    {it(
                      panel === "Сцена"
                        ? "sceneTitle"
                        : panel === "Сюжет"
                          ? "threadsTitle"
                          : section.key,
                    )}
                  </h1>
                  <p>{it(`${section.key}Sub` as "worldSub")}</p>
                </div>
                {panel === "Сцена" && save && (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={active(save.job) || sceneEditing}
                    aria-expanded={sceneEditing}
                    onClick={() => setSceneEditing(true)}
                  >
                    <Pencil size={15} />
                    {it("editScene")}
                  </Button>
                )}
              </div>
            ) : (
              <h1 ref={heading} tabIndex={-1} className="sr-only">
                {it("characters")}
              </h1>
            )}
            {inspectorSections
              .filter((s) => visited.has(s.id) || s.id === panel)
              .map(({ id }) => (
                <div key={id} hidden={id !== panel}>
                  {id === "Мир" && <WorldSection {...props} world={world} />}
                  {id === "Сцена" && (
                    <SceneSection
                      {...props}
                      editor={
                        save && (
                          <SceneEditor
                            key={save.id}
                            save={save}
                            edit={sceneEditing}
                            setEdit={setSceneEditing}
                            meta={meta}
                            refresh={refresh}
                          />
                        )
                      }
                    />
                  )}
                  {id === "Персонажи" && (
                    <>
                      <CharacterPicker
                        {...{
                          state,
                          meta,
                          save,
                          character,
                          setCharacter: (id: string) => {setCharacterHistory([]);setCharacter(id)},
                          query,
                          setQuery,
                          near,
                          setNear,
                        }}
                      />
                      {selected ? (
                        <CharacterView
                          state={state}
                          card={selected}
                          save={save}
                          refresh={refresh}
                          tab={dossierTab}
                          setTab={setDossierTab}
                          onCharacter={openCharacter}
                        />
                      ) : (
                        <p role="status" className="inspector-empty">
                          {it("noCharacters")}
                        </p>
                      )}
                    </>
                  )}
                  {id === "Отношения" && (
                    <RelationsSection {...props} refresh={refresh} />
                  )}
                  {id === "Тайны" && <SecretsSection {...props} />}
                  {id === "Сюжет" && <ThreadsSection {...props} />}
                  {id === "Память" && <MemorySection {...props} />}
                </div>
              ))}
          </div>
        </div>
      </section>
      <Dialog open={infoOpen} onOpenChange={setInfoOpen}>
        <DialogContent className="inspector-settings">
          <DialogHeader>
            <DialogTitle>{it("settings")}</DialogTitle>
            <DialogDescription>
              {world.name} · {it("baseline")} v{world.version} ·{" "}
              {save?.name || it("original")}
            </DialogDescription>
          </DialogHeader>
          <ThemeSelector />
          <div className="metadata">
            <p>
              {it("created")}: {localDate(world.created_at)}
            </p>
            {save && (
              <>
                <p>
                  {it("save")} #{save.id}
                </p>
                <p>
                  {it("updated")}: {localDate(save.updated_at)}
                </p>
              </>
            )}
            <Reveal
              title={it("tone")}
              text={state.sections.tone}
              preview={false}
            />
            <Reveal
              title={it("rules")}
              text={state.story_notes}
              preview={false}
            />
            <Button
              size="sm"
              variant="outline"
              onClick={() => download(world.source_md, `world_${world.id}.md`)}
            >
              <Download size={14} />
              {it("export")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
function SceneEditor({
  edit,
  setEdit,
  save,
  meta,
  refresh,
}: {
  save: Save;
  meta?: Scene;
  refresh: () => void;
  edit: boolean;
  setEdit: (value: boolean) => void;
}) {
  const [scene, setScene] = useState<Scene>(
    meta ?? { time: "", location: "", present_ids: [] },
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!edit) setScene(meta ?? { time: "", location: "", present_ids: [] });
  }, [meta, edit]);
  const blocked = busy || active(save.job);
  if (!edit) return null;
  return (
    <InspectorCard title={it("editScene")}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (blocked) return;
          setBusy(true);
          setError("");
          try {
            await api(
              `/saves/${save.id}/scene`,
              {
                // Empty time tells the existing API to retain the canonical minute.
                // Display labels may be campaign-relative; do not re-parse an unchanged label.
                time: scene.time === meta?.time ? "" : scene.time,
                location: scene.location,
                present_ids: scene.present_ids,
                revision: save.revision,
              },
              "PATCH",
            );
            refresh();
            setEdit(false);
            toast.success(it("sceneSaved"));
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <fieldset disabled={blocked}>
          <label>
            {it("time")}
            <Input
              value={scene.time}
              onChange={(e) =>
                setScene((s) => ({ ...s, time: e.target.value }))
              }
            />
          </label>
          <label>
            {it("location")}
            <Input
              value={scene.location}
              onChange={(e) =>
                setScene((s) => ({ ...s, location: e.target.value }))
              }
            />
          </label>
          <p className="muted small">{it("presentLabel")}</p>
          {save.state.characters.map((c) => (
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
          {error && <p role="alert">{error}</p>}
          <div className="actions">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setEdit(false)}
            >
              {it("cancel")}
            </Button>
            <Button type="submit">{it("saveScene")}</Button>
          </div>
        </fieldset>
      </form>
    </InspectorCard>
  );
}
