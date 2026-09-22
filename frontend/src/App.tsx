import { useCallback, useEffect, useState, useRef } from "react";
import {
  BookOpen,
  Globe,
  Users,
  Brain,
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
import { Library } from "./Library";
import { Preparation } from "./Preparation";
import { Game } from "./Game";

import {useMobile,useMobileViewport,MobileNavigation} from './mobile';
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from './components/ui/dialog';
export default function App() {
  const mobile=useMobile();useMobileViewport(mobile);
  const [mobileMenu,setMobileMenu]=useState(false);
  const [branches,setBranches]=useState(false);
  const [view, setView] = useState<"game" | "prepare">("game");
  const [library, setLibrary] = useState(false);
  const [settings, setSettings] = useState(false);
  const [inspector, setInspector] = useState(false);
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
    setSelection({ world, save });
    setView("game");
    setInspector(false);
  };
  const inspect = (p: Panel) => {
    setPanel(p);
    setInspector(true);
  };
  const openCharacter = (id: string) => {
    setCharacter(id);
    inspect("Персонажи");
  };
  return (
    <div className={`app-shell ${reading ? "reading" : ""}`}>
      <Toaster theme="dark" richColors position="top-center" />
      {!mobile&&<nav className="nav-rail" aria-label="Главная навигация">
        <button
          className="brand"
          aria-label="AI RPG Engine"
          onClick={() => setView("game")}
        >
          <Feather size={26} />
        </button>
        <div className="nav-links">
          <button
            className={view === "game" ? "current" : ""}
            onClick={() => setView("game")}
          >
            <BookOpen />
            <span>Игра</span>
          </button>
          <button
            className={view === "prepare" ? "current" : ""}
            onClick={() => setView("prepare")}
          >
            <Feather />
            <span>Создать</span>
          </button>
          <div className="nav-divider" />
          <button disabled={!world} onClick={() => inspect("Мир")}>
            <Globe />
            <span>Мир</span>
          </button>
          <button disabled={!world} onClick={() => inspect("Персонажи")}>
            <Users />
            <span>Персонажи</span>
          </button>
          <button disabled={!world} onClick={() => inspect("Память")}>
            <Brain />
            <span>Память</span>
          </button>
        </div>
        <button className="nav-settings" disabled={prefsLoading} onClick={() => setSettings(true)}>
          <Settings2 />
          <span>Настройки</span>
        </button>
      </nav>}
      <div className="app-main">
        <header className="topbar">
          <button className="breadcrumb" onClick={() => setLibrary(true)}>
            <LibraryIcon size={17} />
            <span>
              {view === "prepare"
                ? "Мастерская"
                : world?.name || "Твои истории"}
            </span>
            <span className="muted">⌄</span>
          </button>
          {mobile?<MobileNavigation open={mobileMenu} setOpen={setMobileMenu} world={!!world} go={setView} inspect={inspect} settings={()=>setSettings(true)} reading={reading} toggleReading={()=>setReading(!reading)} branches={()=>setBranches(true)}/>:<div className="topbar-actions">
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
          <Preparation
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
          <Game
            key={`${selection.world}-${selection.save}`}
            world={world}
            save={save}
            refresh={refresh}
            choose={choose}
            openLibrary={() => setLibrary(true)}
            openCharacter={openCharacter}
            prefs={prefs}
            apiKey={apiKey}
          />
        )}
      </div>
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
        world={world}
        save={save}
        open={inspector}
        close={() => setInspector(false)}
        panel={panel}
        setPanel={setPanel}
        character={character}
        setCharacter={setCharacter}
        refresh={refresh}
      />
    </div>
  );
}
