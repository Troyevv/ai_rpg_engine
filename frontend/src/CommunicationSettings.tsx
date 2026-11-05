import { useEffect, useState } from "react";
import {MessageCircle,Phone,Mail,Footprints,RadioTower,Radio,PhoneCall,Sparkles,Check,Plus,ChevronDown,Info,NotebookPen,Smartphone} from "lucide-react";
import {AtelierDisclosure} from "./workshop/AtelierDisclosure";
import { api } from "./api";
import { gameLocale } from "./gameDate";
import { Button } from "./components/ui/button";
import { Textarea } from "./components/ui/textarea";
import "./styles/communication-settings.css";
const channelIcons=[MessageCircle,Phone,Mail,Footprints,RadioTower,Radio,PhoneCall,Sparkles,Check,Plus,ChevronDown,Info,NotebookPen,Smartphone];
export const channels = [
  "text_message",
  "voice_call",
  "letter",
  "courier",
  "telegram",
  "landline",
  "magic",
] as const;
type Channel = (typeof channels)[number];
type Policy = "instant" | "delayed" | "live";
export type CommunicationProfile = Partial<Record<Channel, boolean>> & {
  profile_version?: 1;
  preset?: string;
  presentation?: "none" | "phone";
  delivery_policy?: Partial<Record<Channel, Policy>>;
  delivery_minutes?: Partial<Record<"letter" | "courier" | "telegram", number>>;
  author_note?: string;
  region?: string;
  ring_timeout_minutes?: number;
  emergency_numbers?: Record<string, string>;
};
export const communicationNames = [
  "Сообщения и чаты",
  "Мобильные звонки",
  "Письма",
  "Гонцы",
  "Телеграммы",
  "Стационарные звонки",
  "Магическая связь",
];
const en = [
  "Messages and chats",
  "Mobile calls",
  "Letters",
  "Couriers",
  "Telegrams",
  "Landline calls",
  "Magical communication",
];
const presets = {
  none: ["Без удалённой связи", "No remote communication"],
  letters: ["Письма и гонцы", "Letters and couriers"],
  "1939": [
    "1939 · письма, телеграф, телефон",
    "1939 · mail, telegraph, telephone",
  ],
  modern: ["Современность", "Modern"],
  fantastic: ["Футуристическая / магическая", "Futuristic / magical"],
  custom: ["Пользовательский", "Custom"],
};
const policies = {
  instant: ["Мгновенно", "Instant"],
  delayed: ["С задержкой", "Delayed"],
  live: ["В реальном времени", "Live"],
};
const defaultPolicy = (c: Channel): Policy =>
  c === "voice_call" || c === "landline"
    ? "live"
    : c === "text_message" || c === "magic"
      ? "instant"
      : "delayed";
export function CommunicationSettings({
  value,
  onChange,
  disabled = false,
  compact = false,
}: {
  value: CommunicationProfile | null;
  onChange?: (v: CommunicationProfile) => void;
  disabled?: boolean;
  compact?: boolean;
}) {
  const english = gameLocale().startsWith("en"),
    names = english ? en : communicationNames,
    index = english ? 1 : 0;
  const [catalog, setCatalog] = useState<Record<string, CommunicationProfile>>(
      {},
    ),
    [error, setError] = useState("");
  useEffect(() => {
    if (!onChange) return;
    let live = true;
    api<Record<string, CommunicationProfile>>("/communication/presets")
      .then((v) => {
        if (live) setCatalog(v);
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [!!onChange]);
  const v = value || {};
  const enabled = channels.filter((c) => v[c]);
  const change = (patch: Partial<CommunicationProfile>) =>
    onChange?.({ ...v, ...patch, preset: "custom" });
  const selectPreset = (id:string) => onChange?.(id === 'custom' ? {...v,preset:id} : {...catalog[id],author_note:v.author_note||''});
  const toggle = (c:Channel,checked:boolean) => {
    const next={...v,[c]:checked};
    change({[c]:checked,presentation:next.text_message||next.voice_call?'phone':'none',
      delivery_policy:{...v.delivery_policy,[c]:v.delivery_policy?.[c]||defaultPolicy(c)}});
  };
  if(compact&&onChange)return <section className="paper comm-card atelier-communication" aria-label="Технологии связи">
    <header className="card-head comm-head"><div className="title-line"><Radio className="section-icon"/><h2>Технологии связи</h2></div><span className="count-badge" aria-live="polite">{enabled.length} из 7</span></header>
    <fieldset disabled={disabled} className="comm-body"><div className="era"><label htmlFor="atelier-communication-preset">Набор технологий</label>
      <div className="select-wrap"><select id="atelier-communication-preset" aria-label="Набор технологий связи" value={v.preset||'none'} onChange={e=>selectPreset(e.target.value)}>
        {Object.entries(presets).map(([id,label])=><option key={id} value={id} disabled={!catalog[id]}>{id==='custom'&&!english?'Свой набор':label[index]}</option>)}
      </select><ChevronDown size={15}/></div><p>Выберите основу. Эпоху мира задаёт замысел.</p></div>
      <fieldset className="channel-set"><legend>Доступные каналы</legend><div className="chips">{channels.map((c,i)=>{const Icon=channelIcons[i];return <label key={c} className="channel" data-selected={!!v[c]} title={names[i]+' · '+policies[v.delivery_policy?.[c]||defaultPolicy(c)][index]}>
        <input type="checkbox" checked={!!v[c]} onChange={e=>toggle(c,e.target.checked)}/><Icon size={14}/><span>{names[i]}</span>{v[c]?<Check className="on selection-mark" size={13}/>:<Plus className="off" size={12}/>}
      </label>})}</div></fieldset>
    </fieldset>
    <div className="comm-bottom"><span><Info size={14}/>Личные разговоры доступны всегда</span></div>
    <AtelierDisclosure className="comm-disclosure" title={<><NotebookPen size={14}/>Правила и особенности</>}>
     <div className="comm-extra"><div><strong>Доставка</strong>{enabled.length?<ul>{enabled.map(c=><li key={c}>{names[channels.indexOf(c)]}<span>{policies[v.delivery_policy?.[c]||defaultPolicy(c)][index]}</span></li>)}</ul>:<p>Удалённые каналы выключены.</p>}
     {v.presentation==='phone'&&<p className="horiz"><Smartphone size={15}/>В игре доступен телефон.</p>}</div>
     <label>Особенности связи в мире<Textarea disabled={disabled} value={v.author_note||''} maxLength={2000} placeholder="Например, мобильные телефоны есть только у городских гильдий…" onChange={e=>change({author_note:e.target.value})}/><small>Описание уточняет обычаи. Каналы включаются отдельно.</small></label></div>
    </AtelierDisclosure>{error&&<p className="sp-error" role="alert">{error}</p>}
  </section>;
  return (
    <section
      className="communication-settings"
      aria-label={english ? "Communication technologies" : "Технологии связи"}
    >
      <h4>{english ? "Communication technologies" : "Технологии связи"}</h4>
      <p>
        {english
          ? "Choose any combination, regardless of year or genre. In-person dialogue remains available."
          : "Любое сочетание независимо от года и жанра. Личные разговоры доступны всегда."}
      </p>
      {!onChange ? (
        <>
          <p>
            {enabled.length
              ? enabled.map((c) => names[channels.indexOf(c)]).join(" · ")
              : english
                ? "No active remote channels"
                : "Нет активных каналов удалённой связи"}
          </p>
          {enabled.map((c) => (
            <p key={c}>
              {names[channels.indexOf(c)]}:{" "}
              {policies[v.delivery_policy?.[c] || defaultPolicy(c)][index]}
            </p>
          ))}
          {v.author_note && <p>{v.author_note}</p>}
          <small>
            {english
              ? "Set before starting the game."
              : "Настраивается до начала игры."}
          </small>
        </>
      ) : (
        <fieldset disabled={disabled}>
          <legend className="sr-only">
            {english ? "Channel configuration" : "Настройка каналов"}
          </legend>
          <div
            className="communication-presets"
            role="group"
            aria-label={
              english ? "Communication preset" : "Набор технологий связи"
            }
          >
            {(
              [
                "none",
                "letters",
                "1939",
                "modern",
                "fantastic",
                "custom",
              ] as const
            ).map((id) => (
              <button
                type="button"
                key={id}
                aria-pressed={v.preset === id}
                disabled={!catalog[id]}
                onClick={() => selectPreset(id)}
              >
                {presets[id][index]}
              </button>
            ))}
          </div>
          <div className="communication-channels">
            {channels.map((c, i) => (
              <div className="communication-channel" key={c}>
                <label>
                  <input
                    type="checkbox"
                    checked={!!v[c]}
                    onChange={e => toggle(c,e.target.checked)}
                  />
                  {names[i]}
                </label>
                {v[c] && (
                  <span>
                    {
                      policies[v.delivery_policy?.[c] || defaultPolicy(c)][
                        index
                      ]
                    }
                  </span>
                )}
              </div>
            ))}
          </div>
          <label>
            {english ? "World-specific details" : "Особенности связи в мире"}
            <Textarea
              value={v.author_note || ""}
              maxLength={2000}
              placeholder={
                english
                  ? "Appearance, customs, atmosphere…"
                  : "Внешний вид, обычаи, атмосфера…"
              }
              onChange={(e) => change({ author_note: e.target.value })}
            />
          </label>
          <small>
            {english
              ? "This description does not enable channels or change delivery rules. A recipient may choose not to reply."
              : "Описание не включает каналы и не меняет правила доставки. Адресат может не ответить."}
          </small>
          {error && <p role="alert">{error}</p>}
        </fieldset>
      )}
    </section>
  );
}
export function CommunicationEditor({
  wid,
  revision,
  profile,
  disabled,
  refresh,
}: {
  wid: string;
  revision: number;
  profile: CommunicationProfile;
  disabled: boolean;
  refresh: () => Promise<unknown>;
}) {
  const [value, setValue] = useState(profile),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const english = gameLocale().startsWith("en");
  useEffect(() => {
    setValue(profile);
    setError("");
  }, [wid, revision]);
  return (
    <>
      <CommunicationSettings
        value={value}
        onChange={setValue}
        disabled={disabled || busy}
      />
      <Button
        disabled={
          disabled || busy || JSON.stringify(value) === JSON.stringify(profile)
        }
        onClick={async () => {
          setBusy(true);
          setError("");
          try {
            await api(`/workspaces/${wid}/draft/communication`, {
              revision,
              profile: value,
            });
            await refresh();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {english ? "Save communication settings" : "Сохранить технологии связи"}
      </Button>
      {error && <p role="alert">{error}</p>}
    </>
  );
}
