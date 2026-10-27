import "./styles/current-game.css";
import {ThemeProvider, useTheme} from "./ThemeProvider";
import { lazy, Suspense, useCallback, useEffect, useState, useRef } from "react";
import {
  CalendarDays, GitBranch, ArrowLeft,
  BookOpen,
  Settings2,
  Feather,
  PanelRight,
  Library as LibraryIcon,
  Eye,
  EyeOff,
} from "lucide-react";
import { Toaster, toast } from "sonner";
import { api } from "./api";
import { defaults, type World, type Save, type Preferences } from "./types";
import { Button } from "./components/ui/button";
import { Settings } from "./Settings";
import { Inspector, type Panel } from "./Inspector";
import {inspectorSections,it,panelLabel} from "./lib/inspector";
import { Library } from "./Library";
import { WorldWorkshop } from "./WorldWorkshop";
import { Game } from "./Game";
import { Tabletop } from "./Tabletop";

import {useMobile,useMobileViewport,MobileNavigation} from './mobile';
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from './components/ui/dialog';
const GameCalendar=lazy(()=>import('./GameCalendar').then(m=>({default:m.GameCalendar})));
const Genealogy=lazy(()=>import('./Genealogy').then(m=>({default:m.Genealogy})));
export default function App() {
  const [gameMode,setGameMode]=useState(()=>localStorage.getItem('game-mode')||'narrative');
  const changeMode=(mode:string)=>{setGameMode(mode);localStorage.setItem('game-mode',mode);};
  const mobile=useMobile();useMobileViewport(mobile);
  const [mobileMenu,setMobileMenu]=useState(false);
  const [workspace,setWorkspace]=useState<"calendar"|"family"|null>(null);
  const [familyRoot,setFamilyRoot]=useState<string|undefined>();
  const workspaceTrigger=useRef<HTMLElement|null>(null);
  const closeWorkspace=()=>{setWorkspace(null);requestAnimationFrame(()=>{const target=workspaceTrigger.current?.isConnected?workspaceTrigger.current:document.querySelector<HTMLElement>(".current-game-entry button");target?.focus()})};
  const openWorkspace=(section:"calendar"|"family",root?:string)=>{workspaceTrigger.current=document.activeElement as HTMLElement;closeInspector();setView("game");setFamilyRoot(root);setWorkspace(section);window.dispatchEvent(new Event("save-workspace-opened"))};
  useEffect(()=>{const open=(e:Event)=>{const d=(e as CustomEvent).detail;openWorkspace(d.section,d.root)};window.addEventListener('save-workspace',open);return()=>window.removeEventListener('save-workspace',open)},[]);
  useEffect(()=>{if(!workspace)return;requestAnimationFrame(()=>document.querySelector<HTMLButtonElement>('.save-workspace header button')?.focus());const key=(e:KeyboardEvent)=>{if(e.key==='Escape'&&!e.defaultPrevented&&!document.querySelector('[role="dialog"],.inspector-workspace:not([hidden])')){e.preventDefault();closeWorkspace()}};window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key)},[workspace]);
  const [branches,setBranches]=useState(false);
  const [view, setView] = useState<"game" | "prepare">("game");
  const [library, setLibrary] = useState(false);
  const [settings, setSettings] = useState(false);
  const [inspector, setInspector] = useState(false);
  const [worldInfo,setWorldInfo]=useState(false);
  const inspectorTrigger=useRef<HTMLElement|null>(null);
  const inspectorVisible=useRef(inspector);inspectorVisible.current=inspector;
  useEffect(()=>{const back=()=>{
    if(!inspectorVisible.current)return;
    // Keep one same-document entry while a nested dialog/source owns Back.
    history.pushState({...history.state,inspectorOpen:true},'');
    const dialog=document.querySelector<HTMLButtonElement>('[role="dialog"] .dialog-close');
    if(dialog)dialog.click();else window.dispatchEvent(new Event('inspector-back'));
  };window.addEventListener('popstate',back);return()=>window.removeEventListener('popstate',back)},[]);
  const closeInspector=()=>{inspectorVisible.current=false;setInspector(false);if(history.state?.inspectorOpen)history.back();requestAnimationFrame(()=>{const target=inspectorTrigger.current?.isConnected?inspectorTrigger.current:document.querySelector<HTMLElement>(".nav-links button,.topbar button");target?.focus({preventScroll:true})})};
  const [panel, setPanel] = useState<Panel>("Мир");
  const [character, setCharacter] = useState("");
  const [reading, setReading] = useState(false);
  const [prefsLoading,setPrefsLoading] = useState(true);
  const [prefs, setPrefs] = useState<Preferences>(defaults);
  const [apiKey, setApiKey] = useState("");
  const [world, setWorld] = useState<World | null>(null);
  const [save, setSave] = useState<Save | null>(null);
  const [selection, setSelection] = useState<{ world?: number; save?: number }>(
    () => {
      try {
        return JSON.parse(localStorage.getItem("selection") || "{}");
      } catch {
        return {};
      }
    },
  );
  const [loading, setLoading] = useState(false);
  const [profile] = useState(() => {
    let p = localStorage.getItem("profile");
    if (!p) {
      p =
        crypto.randomUUID?.() ??
        Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) =>
          b.toString(16).padStart(2, "0"),
        ).join("");
      localStorage.setItem("profile", p);
    }
    return p;
  });
  useEffect(() => {
    api<Partial<Preferences>>(`/settings/${profile}`)
      .then((p) => setPrefs({ ...defaults, ...p, idea:{...defaults.idea,...p.idea}, summary:{...defaults.summary,...p.summary}, game:{...defaults.game,...p.game} }))
      .catch((e) => toast.error(e.message))
      .finally(()=>setPrefsLoading(false));
  }, [profile]);
  const selectedRef = useRef(selection);
  selectedRef.current = selection;
  const refresh = useCallback(() => {
    if (!selection.world) return;
    Promise.all([
      api<World>(`/worlds/${selection.world}`),
      selection.save
        ? api<Save>(`/saves/${selection.save}`)
        : Promise.resolve(null),
    ])
      .then(([w, s]) => {
        if (selectedRef.current === selection) {
          setWorld(w);
          setSave(s);
        }
      })
      .catch((e) => toast.error(e.message));
  }, [selection]);
  useEffect(() => {
    localStorage.setItem("selection", JSON.stringify(selection));
    setWorld(null);
    setSave(null);
    if (!selection.world) return;
    setLoading(true);
    const c = new AbortController();
    Promise.all([
      api<World>(`/worlds/${selection.world}`, undefined, "GET", c.signal),
      selection.save
        ? api<Save>(`/saves/${selection.save}`, undefined, "GET", c.signal)
        : Promise.resolve(null),
    ])
      .then(([w, s]) => {
        if (selectedRef.current === selection) {
          setWorld(w);
          setSave(s);
        }
      })
      .catch((e) => {
        if (!c.signal.aborted) toast.error(e.message);
      })
      .finally(() => {
        if (!c.signal.aborted) setLoading(false);
      });
    return () => c.abort();
  }, [selection]);
  const choose = (world: number, save?: number) => {
    setWorkspace(null);
    setSelection({ world, save });
    setView("game");
    closeInspector();
  };
  const inspect = (p: Panel) => {
    if(!inspector){inspectorTrigger.current=document.activeElement as HTMLElement;history.pushState({...history.state,inspectorOpen:true},'')}
    window.dispatchEvent(new Event("save-workspace-opened"));
    setView("game");
    setPanel(p);
    setInspector(true);
  };
  const openCharacter = (id: string) => {
    setCharacter(id);
    inspect("Персонажи");
  };
  if(gameMode==='tabletop')return <ThemeProvider world={null}><ThemedToaster/><Tabletop onBack={()=>changeMode('narrative')} onSettings={()=>setSettings(true)} prefs={prefs} apiKey={apiKey}/><Settings open={settings} onOpenChange={setSettings} value={prefs} save={async p=>{await api(`/settings/${profile}`,p,'PUT');setPrefs(p);}} apiKey={apiKey} setApiKey={setApiKey}/></ThemeProvider>;
  return (
    <ThemeProvider world={world}><div className={`app-shell narrative-shell ${inspector?"inspector-open":""} ${reading&&!inspector ? "reading" : ""}`}>
      <ThemedToaster />
      {!mobile&&<nav className="nav-rail" aria-label="Главная навигация">
        <button
          className="brand"
          aria-label="AI RPG Engine"
          onClick={() => {setView("game");closeWorkspace();closeInspector()}}
        >
          <Feather size={26} /><span>NARRATIVE</span>
        </button>
        {world&&<div className="inspector-world-label"><strong title={world.name}>{world.name}</strong><small>{save?.name||it("original")} · {it("baseline")} v{world.version}</small></div>}
        <div className="nav-links">
          <button
            className={view === "game" && !workspace && !inspector ? "current" : ""}
            onClick={() => {setView("game");closeWorkspace();closeInspector()}}
          >
            <BookOpen />
            <span>Игра</span>
          </button>
          <button
            className={view === "prepare" ? "current" : ""}
            onClick={() => {setWorkspace(null);closeInspector();setView("prepare")}}
          >
            <Feather />
            <span>Создать</span>
          </button>
          {(['worldGroup','storyGroup'] as const).map(group=><div className="inspector-nav-group" key={group}><p>{it(group)}</p>{inspectorSections.filter(s=>s.group===group).map(({id,icon:Icon})=><button key={id} disabled={!world} className={inspector&&panel===id?'current':''} aria-current={inspector&&panel===id?'page':undefined} onClick={()=>inspect(id)}><Icon/><span>{panelLabel(id)}</span></button>)}</div>)}
          <div className="inspector-nav-group"><p>{it('currentGame')}</p>{(['calendar','family'] as const).map(section=><button key={section} disabled={!save} className={workspace===section&&!inspector?'current':''} onClick={()=>openWorkspace(section)}>{section==='calendar'?<CalendarDays/>:<GitBranch/>}<span>{section==='calendar'?'Календарь':'Родословная'}</span></button>)}</div>
          <button disabled={!world} onClick={()=>setWorldInfo(true)}><Settings2/><span>{it('settings')}</span></button>
        </div>
        <button className="nav-settings" disabled={prefsLoading} onClick={() => setSettings(true)}>
          <Settings2 />
          <span>Настройки</span>
        </button>
      </nav>}
      <div className="app-main">
        <header className="topbar" hidden={inspector}>
          <Button variant="outline" size="sm" aria-label="Настольная RPG" onClick={()=>changeMode("tabletop")}>{mobile?"RPG":"Настольная RPG"}</Button>
          <button className="breadcrumb" onClick={() => setLibrary(true)}>
            <LibraryIcon size={17} />
            <span>
              {view === "prepare"
                ? "Мастерская"
                : world?.name || "Твои истории"}
            </span>
            <span className="muted">⌄</span>
          </button>
          {mobile&&!inspector?<MobileNavigation activePanel={inspector?panel:undefined} workspace={openWorkspace} open={mobileMenu} setOpen={setMobileMenu} world={!!world} go={v=>{setWorkspace(null);closeInspector();setView(v)}} inspect={inspect} settings={()=>setSettings(true)} reading={reading} toggleReading={()=>setReading(!reading)} branches={()=>setBranches(true)}/>:<div className="topbar-actions">
            {view === "game" && (
              <Button
                variant="ghost"
                size="icon"
                aria-label={reading ? "Выйти из чтения" : "Режим чтения"}
                onClick={() => {
                  setReading(!reading);
                  setInspector(false);
                }}
              >
                {reading ? <EyeOff size={19} /> : <Eye size={19} />}
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon"
              disabled={prefsLoading}
              aria-label="Настройки"
              onClick={() => setSettings(true)}
            >
              <Settings2 size={18} />
            </Button>
            {world && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => inspect(panel)}
              >
                <PanelRight size={16} />
                <span className="desktop-label">О мире</span>
              </Button>
            )}
          </div>}
        </header>
        {view === "prepare" ? (
          <WorldWorkshop
              onGame={choose}
            prefs={prefs}
            apiKey={apiKey}
            onWorld={(w) => {
              choose(w);
              setLibrary(true);
            }}
          />
        ) : loading || prefsLoading ? (
          <div className="skeleton-page">
            <div />
            <div />
            <div />
            <p className="muted">Открываем историю…</p>
          </div>
        ) : (
          <div className="game-preserved" inert={!!workspace||inspector} aria-hidden={!!workspace||inspector}><Game
            key={`${selection.world}-${selection.save}`}
            world={world}
            save={save}
            refresh={refresh}
            choose={choose}
            openLibrary={() => setLibrary(true)}
            openCharacter={openCharacter}
            prefs={prefs}
            apiKey={apiKey}
          /></div>
        )}
      </div>
      {workspace&&save&&<section className="save-workspace" inert={inspector} aria-label={workspace==='calendar'?'Календарь':'Родословная'}><header><button onClick={closeWorkspace}><ArrowLeft size={18}/>Вернуться в историю</button><h1>{workspace==='calendar'?'Календарь':'Родословная'}</h1></header><Suspense fallback={<p role="status">Загрузка…</p>}>{workspace==='calendar'?<GameCalendar key={`${save.id}:${save.state.controlled_actor_id}`} save={save}/>:<Genealogy key={`${save.id}:${save.state.controlled_actor_id}`} save={save} rootId={familyRoot} onCharacter={openCharacter}/>}</Suspense></section>}
      <Dialog open={branches} onOpenChange={setBranches}><DialogContent className={mobile?'mobile-sheet':''}><DialogHeader><DialogTitle>Ветки истории</DialogTitle><DialogDescription>Варианты ответов доступны под сценами. Смена старого варианта требует отката зависимых ходов. Именованные ветки пока не реализованы.</DialogDescription></DialogHeader></DialogContent></Dialog>
      <Settings
        open={settings}
        onOpenChange={setSettings}
        value={prefs}
        save={async (p) => {
          await api(`/settings/${profile}`, p, "PUT");
          setPrefs(p);
        }}
        apiKey={apiKey}
        setApiKey={setApiKey}
      />
      <Library
        open={library}
        onOpenChange={setLibrary}
        choose={choose}
        prepare={() => setView("prepare")}
      />
      <Inspector
        key={`${selection.world}:${selection.save}:${save?.state.controlled_actor_id}:${save?.state.camera?.pov_actor_id}:${save?.state.camera?.mode}`}
        infoOpen={worldInfo}
        setInfoOpen={setWorldInfo}
        navigation={mobile&&inspector?<MobileNavigation activePanel={inspector?panel:undefined} workspace={openWorkspace} open={mobileMenu} setOpen={setMobileMenu} world={!!world} go={v=>{setWorkspace(null);closeInspector();setView(v)}} inspect={inspect} settings={()=>setSettings(true)} reading={reading} toggleReading={()=>setReading(!reading)} branches={()=>setBranches(true)}/>:undefined}
        world={world}
        save={save}
        open={inspector}
        close={closeInspector}
        onPhone={()=>{closeInspector();requestAnimationFrame(()=>window.dispatchEvent(new Event("phone-open")))}}
        panel={panel}
        setPanel={setPanel}
        character={character}
        setCharacter={setCharacter}
        refresh={refresh}
      />
    </div></ThemeProvider>
  );
}

function ThemedToaster(){const {presentation}=useTheme();return <Toaster theme={presentation.theme_id==='parchment'?'light':'dark'} position="top-center" toastOptions={{className:"story-toast"}}/>}
