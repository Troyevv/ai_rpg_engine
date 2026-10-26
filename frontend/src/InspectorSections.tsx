import { useState, type ReactNode } from "react";
import {
  ArrowRight,
  ArrowLeftRight,
  MapPin,
  Clock,
  BookOpen,
  CalendarDays,
  FileText,
  Shield,
  LockKeyhole,
  Search,
  Users,
  History,
  Phone,
  type LucideIcon,
} from "lucide-react";
import type {
  State,
  Scene,
  Save,
  World,
  WorldFact,
  Knowledge,
  Thread,
} from "./types";
import { WeatherBadge } from "./SceneClock";
import { CharacterAvatar } from "./Portrait";
import { Markdown } from "./Markdown";
import { Reveal, brief } from "./InspectorViews";
import { SocialStateView } from "./SocialStateView";
import { RelationshipEditor } from "./RelationshipEditor";
import { relationshipLabel } from "./lib/relationships";
import { worldTime } from "./lib/worldTime";
import { socialLabel } from "./lib/social";
import { gameLocale } from "./gameDate";
import { formatDateLabel } from "./gameDate";
import { it, type InspectorText, type Panel } from "./lib/inspector";

type Props = {
  state: State;
  meta?: Scene;
  save?: Save | null;
  onCharacter: (id: string) => void;
  onPanel: (panel: Panel) => void;
  onPhone?: () => void;
};
const actorOf = (s: State) =>
  s.controlled_actor_id === undefined
    ? s.protagonist_id || s.characters.find((c) => c.is_player)?.id
    : s.controlled_actor_id;
const nameOf = (s: State, id: string) =>
  s.characters.find((c) => c.id === id)?.name || id;
const factHeading = (s: State, f: WorldFact) => {
  const relation = Object.values(s.world?.objective_relations || {}).find(r => r.fact_id === f.id)
    || s.objective_relations?.find(r => f.character_ids.includes(r.source_id) && f.character_ids.includes(r.target_id) && [
      `Установленная связь: ${r.kind}, ${r.source_id}, ${r.target_id}.`,
      `Установленная связь: ${r.kind}, ${r.target_id}, ${r.source_id}.`,
    ].includes(f.text));
  if (!relation) return null;
  const a = s.characters.find(c => c.id === relation.source_id);
  const b = s.characters.find(c => c.id === relation.target_id);
  if (!a || !b) return null;
  const label = gameLocale().startsWith("en") ? relation.kind.replaceAll("_", " ") : socialLabel(relation.kind);
  return `${label}: ${a.name} → ${b.name}`;
};
const allFacts = (s: State): WorldFact[] =>
  s.world?.facts
    ? Object.values(s.world.facts)
    : (s.facts || []).map((f, i) => ({
        id: String(i),
        text: f.text,
        secret: false,
        character_ids: f.known_by,
        evidence: [],
      }));
const matches = (query: string, ...values: (string | undefined)[]) =>
  values
    .join(" ")
    .toLocaleLowerCase()
    .includes(query.trim().toLocaleLowerCase());
const timeLabel = (s: State, minute: number | null | undefined) =>
  minute == null
    ? it("undated")
    : formatDateLabel(worldTime(minute, s.world_clock?.calendar));
const labelStatus = (status: string) =>
  it(
    (
      {
        active: "activeStatus",
        developing: "developing",
        dormant: "dormant",
        paused: "dormant",
        resolved: "resolved",
        cancelled: "cancelled",
        known: "known",
        suspected: "suspected",
        outdated: "outdated",
        refuted: "refuted",
        superseded: "superseded",
        unknown: "unknownKnowledge",
      } as Record<string, InspectorText>
    )[status] || "unknown",
  );

// Parent links are projected by the existing location API. Cycles/unknown parents
// stop the display trail; prose never supplies a missing geographic relationship.
function locationTrail(state: State, location: State["locations"][number]) {
  const names: string[] = [];
  const seen = new Set<string>();
  let id = location.parent_id;
  while (id && !seen.has(id)) {
    seen.add(id);
    const parent = state.locations.find((l) => l.id === id);
    if (!parent) break;
    names.unshift(parent.name);
    id = parent.parent_id;
  }
  return names.join(" › ");
}

export function InspectorCard({
  title,
  icon: Icon,
  aside,
  children,
  className = "",
}: {
  title?: string;
  icon?: LucideIcon;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`inspector-card ${className}`}>
      {title && (
        <header className="inspector-card-heading">
          <h2>{title}</h2>
          {aside || (Icon && <Icon size={17} aria-hidden />)}
        </header>
      )}
      {children}
    </section>
  );
}
export function InspectorEmpty({ search = false }: { search?: boolean }) {
  return (
    <p className="inspector-empty" role="status">
      {it(search ? "noMatch" : "empty")}
    </p>
  );
}
export function InspectorSearch({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="inspector-search">
      <Search size={16} aria-hidden />
      <input
        aria-label={label}
        placeholder={label + "…"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}
function PersonFilter({
  state,
  value,
  onChange,
}: {
  state: State;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <select
      className="inspector-filter"
      aria-label={it("participant")}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">{it("allPeople")}</option>
      {state.characters.map((c) => (
        <option key={c.id} value={c.id}>
          {c.name}
        </option>
      ))}
    </select>
  );
}
function Segments<T extends string>({
  label,
  value,
  items,
  onChange,
}: {
  label: string;
  value: T;
  items: { id: T; label: string; disabled?: boolean }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="inspector-segments" role="group" aria-label={label}>
      {items.map((i) => (
        <button
          key={i.id}
          aria-pressed={value === i.id}
          disabled={i.disabled}
          onClick={() => onChange(i.id)}
        >
          {i.label}
        </button>
      ))}
    </div>
  );
}
/** Limit mounted records, not the searchable projection. No hidden off-page record DOM. */
function Bounded<T>({
  rows,
  render,
  initial = 12,
}: {
  rows: T[];
  render: (r: T, i: number) => ReactNode;
  initial?: number;
}) {
  const [limit, setLimit] = useState(initial);
  return (
    <>
      {rows.slice(0, limit).map(render)}
      {rows.length > limit && (
        <button
          className="inspector-more"
          onClick={() => setLimit((n) => n + initial)}
        >
          {it("more")} · {it("shown")} {Math.min(limit, rows.length)} {it("of")}{" "}
          {rows.length}
        </button>
      )}
    </>
  );
}
function People({
  ids,
  state,
  save,
  onCharacter,
}: {
  ids: string[];
  state: State;
  save?: Save | null;
  onCharacter: (id: string) => void;
}) {
  return (
    <div className="inspector-people">
      {ids.map((id) => {
        const c = state.characters.find((c) => c.id === id);
        return c ? (
          <button
            className="inspector-person-chip"
            key={id}
            onClick={() => onCharacter(id)}
          >
            <CharacterAvatar subject={c} saveId={save?.id} size={26} />
            <span>{c.name}</span>
          </button>
        ) : (
          <span className="muted small" key={id}>
            {it("unknown")}
          </span>
        );
      })}
    </div>
  );
}
function Facts({
  values,
  state,
  save,
  onCharacter,
  secret = false,
}: { values: WorldFact[]; secret?: boolean } & Pick<
  Props,
  "state" | "save" | "onCharacter"
>) {
  const knowledge = Object.values(state.world?.knowledge || {});
  return (
    <Bounded
      rows={values}
      render={(f) => (
        <article
          key={f.id}
          className={
            secret ? "inspector-card inspector-secret" : "inspector-fact"
          }
        >
          {secret && (
            <div className="inspector-row">
              <span className="pill">{it("fact")}</span>
              <LockKeyhole size={18} className="inspector-purple" aria-hidden />
            </div>
          )}
          {secret ? (
            <>
              <h2>{factHeading(state, f) || brief(f.text, 85)}</h2>
              {!factHeading(state, f) && brief(f.text, 85) !== f.text && <Markdown text={f.text} />}
            </>
          ) : (
            <>
              <span className="pill">{it("fact")}</span>
              <p className="inspector-fact-text">{brief(f.text, 220)}</p>
              {brief(f.text, 220).endsWith("…") && (
                <Reveal title={it("details")} text={f.text} preview={false} />
              )}
            </>
          )}
          {secret && (
            <div className="inspector-knowledge">
              {(["known", "suspected"] as const).map((status) => {
                const ids = state.world?.knowledge
                  ? knowledge
                      .filter((k) => k.fact_id === f.id && k.status === status)
                      .map((k) => k.actor_id)
                  : status === "known"
                    ? f.character_ids
                    : [];
                return (
                  <div key={status}>
                    <span>{labelStatus(status)}</span>
                    {ids.length ? (
                      <People {...{ state, save, onCharacter }} ids={ids} />
                    ) : (
                      <small>{it("unknown")}</small>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          <Reveal title={it("evidence")} preview={false}>
            {factHeading(state, f) && <Markdown text={f.text} />}
            {!secret && (
              <>
                <People
                  {...{ state, save, onCharacter }}
                  ids={f.character_ids}
                />
                {["known", "suspected"].map((status) => (
                  <p key={status}>
                    {labelStatus(status)}:{" "}
                    {knowledge
                      .filter((k) => k.fact_id === f.id && k.status === status)
                      .map((k) => nameOf(state, k.actor_id))
                      .join(", ") || it("unknown")}
                  </p>
                ))}
              </>
            )}
            {f.evidence?.map((text, i) => (
              <Markdown key={i} text={text} />
            ))}
            {!f.evidence?.length && (
              <p className="muted small">{it("unknown")}</p>
            )}
          </Reveal>
        </article>
      )}
    />
  );
}
function Commitments({
  state,
  save,
  onCharacter,
}: Pick<Props, "state" | "save" | "onCharacter">) {
  const priority: Record<string, number> = {
    "CURRENT STATE": 0,
    "OVERDUE PLAN": 1,
    PLAN: 2,
    FACT: 3,
    "CANCELLED PLAN": 4,
  };
  const events = Object.values(state.world?.scheduled_events || {}).sort(
    (a, b) =>
      (priority[a.context_category] ?? 5) -
        (priority[b.context_category] ?? 5) ||
      (a.temporal_projection.start_minute ?? Infinity) -
        (b.temporal_projection.start_minute ?? Infinity),
  );
  if (!events.length) return null;
  const labels: Record<string, InspectorText> = {
    PLAN: "plan",
    "OVERDUE PLAN": "overdue",
    "CURRENT STATE": "period",
    FACT: "completed",
    "CANCELLED PLAN": "cancelledPlan",
  };
  return (
    <InspectorCard title={it("commitments")} icon={CalendarDays}>
      <Bounded
        initial={4}
        rows={events}
        render={(e) => (
          <article key={e.id} className="inspector-commitment">
            <CalendarDays size={28} aria-hidden />
            <div>
              <strong>{e.description}</strong>
              <p className="small muted">
                {e.start_label
                  ? formatDateLabel(
                      e.temporal_projection.precision === "exact" &&
                        !e.interval_state
                        ? e.start_label
                        : `${it("window")}: ${e.start_label} — ${e.end_label || it("unknown")}`,
                    )
                  : it("noDeadline")}
              </p>
              <span className={`pill commitment-${e.status}`}>
                {it(
                  e.outcome === "missed"
                    ? "missed"
                    : labels[e.context_category] ||
                        (
                          {
                            pending: "plan",
                            resolved: "completed",
                            cancelled: "cancelledPlan",
                          } as const
                        )[e.status],
                )}
              </span>
              <Reveal title={it("details")} preview={false}>
                <People
                  {...{ state, save, onCharacter }}
                  ids={e.character_ids}
                />
                {e.condition && (
                  <p>
                    {it("condition")}: {e.condition}
                  </p>
                )}
                {e.outcome === "blocked" && <p>{it("blocked")}</p>}
                {e.outcome === "dependency_cancelled" && (
                  <p>{it("dependencyCancelled")}</p>
                )}
                {!!e.depends_on?.length && (
                  <p>
                    {it("depends")}:{" "}
                    {e.depends_on
                      .map(
                        (id) =>
                          state.world?.scheduled_events?.[id]?.description ||
                          it("unknown"),
                      )
                      .join(", ")}
                  </p>
                )}
                {e.evidence && <Markdown text={e.evidence} />}
              </Reveal>
            </div>
          </article>
        )}
      />
      <p className="inspector-note">{it("commitmentNotice")}</p>
      {save && (
        <button
          className="inspector-link"
          onClick={() =>
            window.dispatchEvent(
              new CustomEvent("save-workspace", {
                detail: { section: "calendar" },
              }),
            )
          }
        >
          {it("calendar")}
          <ArrowRight size={15} />
        </button>
      )}
    </InspectorCard>
  );
}

export function WorldSection(props: Props & { world: World }) {
  const { world, state, meta, save, onCharacter, onPanel } = props;
  const [query, setQuery] = useState("");
  const locations = state.locations.filter((l) =>
    matches(query, l.name, l.text),
  );
  const projection = state.world_clock?.projection;
  return (
    <div className="inspector-content">
      <section className="inspector-card inspector-world-hero">
        <div>
          <div className="inspector-people">
            {[state.campaign?.era, state.campaign?.genre]
              .filter(Boolean)
              .map((v) => (
                <span className="pill" key={v}>
                  {v}
                </span>
              ))}
            <span className="pill">
              {it("baseline")} v{world.version}
            </span>
          </div>
          <h2>{world.name}</h2>
          {(state.campaign?.description ||
            state.world_summary ||
            state.summary ||
            state.sections.world) && (
            <Markdown
              text={
                state.campaign?.description ||
                state.world_summary ||
                state.summary ||
                state.sections.world
              }
            />
          )}
        </div>
        <div className="inspector-hero-time">
          <strong>{projection?.time || meta?.time || it("unknown")}</strong>
          <span>
            {projection?.date
              ? formatDateLabel(projection.date)
              : state.world_clock?.last_event_time || ""}
          </span>
          <WeatherBadge weather={state.scene_meta?.weather ?? meta?.weather} />
        </div>
      </section>
      <div className="inspector-columns">
        <div className="inspector-stack">
          <InspectorCard
            title={it("now")}
            aside={
              <span className="pill">{meta?.location || it("unknown")}</span>
            }
          >
            <Markdown text={state.scene} />
            <footer className="inspector-card-footer">
              <People {...props} ids={meta?.present_ids || []} />
              <button
                className="inspector-link"
                onClick={() => onPanel("Сцена")}
              >
                {it("toScene")}
                <ArrowRight size={15} />
              </button>
            </footer>
          </InspectorCard>
          <InspectorCard title={it("locations")} icon={MapPin}>
            <InspectorSearch
              label={it("findLocation")}
              value={query}
              onChange={setQuery}
            />
            {locations.length ? (
              <Bounded
                rows={locations}
                render={(l, i) => (
                  <div className="inspector-location" key={l.id || i}>
                    <MapPin size={20} aria-hidden />
                    <div className="inspector-location-detail">
                      {l.parent_id && (
                        <small className="muted">
                          {locationTrail(state, l)}
                        </small>
                      )}
                      <Reveal title={l.name} text={l.text} />
                    </div>
                  </div>
                )}
              />
            ) : (
              <InspectorEmpty search={!!query} />
            )}
          </InspectorCard>
          <InspectorCard title={it("social")} icon={Users}>
            <SocialStateView state={state} saveId={save?.id} />
          </InspectorCard>
        </div>
        <div className="inspector-stack">
          <Commitments {...{ state, save, onCharacter }} />
          <InspectorCard title={it("facts")} icon={FileText}>
            {allFacts(state).some((f) => !f.secret) ? (
              <Facts
                values={allFacts(state).filter((f) => !f.secret)}
                {...props}
              />
            ) : (
              <InspectorEmpty />
            )}
          </InspectorCard>
        </div>
      </div>
    </div>
  );
}

export function SceneSection(props: Props & { editor: ReactNode }) {
  const { state, meta, save, onCharacter, onPanel, onPhone, editor } = props;
  const actor = actorOf(state);
  const calls =
    state.phone?.events.filter(
      (e) =>
        e.channel === "VOICE_CALL" &&
        ["answered", "ringing"].includes(e.status),
    ) || [];
  const present = state.characters.filter((c) =>
    meta?.present_ids.includes(c.id),
  );
  return (
    <div className="inspector-columns">
      <div className="inspector-stack">
        <InspectorCard
          title={meta?.location || it("unknown")}
          aside={<span className="pill">{it("currentLocation")}</span>}
        >
          <div className="inspector-scene-meta">
            <span>
              <Clock size={14} />
              {state.world_clock?.projection?.date
                ? `${formatDateLabel(state.world_clock.projection.date)} · ${state.world_clock.projection.time}`
                : meta?.time || it("unknown")}
            </span>
            <span>
              {it("pov")}:{" "}
              {state.camera?.pov_actor_id
                ? nameOf(state, state.camera.pov_actor_id)
                : state.camera?.mode === "actor" && actor
                  ? nameOf(state, actor)
                  : it("observer")}
            </span>
          </div>
          <div className="inspector-scene-prose">
            <Markdown text={state.scene} />
          </div>
          <footer className="inspector-card-footer">
            <button
              className="inspector-link"
              onClick={() => onPanel("Память")}
            >
              {it("toMemory")}
              <ArrowRight size={15} />
            </button>
          </footer>
        </InspectorCard>
        <InspectorCard
          title={it("present")}
          aside={<span className="pill">{present.length}</span>}
        >
          {present.map((c) => (
            <button
              className="inspector-person-row"
              key={c.id}
              onClick={() => onCharacter(c.id)}
            >
              <CharacterAvatar subject={c} saveId={save?.id} size={44} />
              <span>
                <strong>{c.name}</strong>
                <small>
                  {c.id === actor
                    ? it("controlled")
                    : c.id === state.camera?.subject_id
                      ? it("pov")
                      : meta?.location || it("unknown")}
                </small>
              </span>
              <ArrowRight size={18} />
            </button>
          ))}
          {!present.length && <InspectorEmpty />}
        </InspectorCard>
      </div>
      <div className="inspector-stack">
        {!!calls.length && (
          <InspectorCard title={it("remote")} icon={Phone}>
            {calls.map((call) => (
              <div className="inspector-remote" key={call.id}>
                <div className="inspector-person-row">
                  <CharacterAvatar
                    subject={call.subject}
                    saveId={save?.id}
                    size={40}
                  />
                  <span>
                    <strong>{call.subject.name}</strong>
                    <small>
                      {it(
                        call.status === "answered"
                          ? "callActive"
                          : "callRinging",
                      )}
                    </small>
                  </span>
                </div>
                <p className="inspector-note">{it("remoteNote")}</p>
              </div>
            ))}
            {onPhone && (
              <button className="inspector-link" onClick={onPhone}>
                {it("toPhone")}
                <ArrowRight size={15} />
              </button>
            )}
          </InspectorCard>
        )}
        {(state.scene_meta?.weather ?? meta?.weather) && (
          <InspectorCard title={it("environment")}>
            <WeatherBadge
              weather={state.scene_meta?.weather ?? meta?.weather}
            />
            <p className="inspector-note">{it("weatherNote")}</p>
          </InspectorCard>
        )}
        <InspectorCard title={it("context")} icon={Clock}>
          <dl className="inspect-kv">
            <dt>{it("location")}</dt>
            <dd>{meta?.location || it("unknown")}</dd>
            <dt>{it("time")}</dt>
            <dd>
              {formatDateLabel(
                meta?.time ||
                  state.world_clock?.last_event_time ||
                  it("unknown"),
              )}
            </dd>
            <dt>{it("controlled")}</dt>
            <dd>{actor ? nameOf(state, actor) : it("noActor")}</dd>
          </dl>
          <button className="inspector-link" onClick={() => onPanel("Сюжет")}>
            {it("toThreads")}
            <ArrowRight size={15} />
          </button>
        </InspectorCard>
        {editor}
      </div>
    </div>
  );
}

export function RelationsSection(props: Props & { refresh: () => void }) {
  const { state, save, refresh } = props;
  const controlled = actorOf(state);
  const [person, setPerson] = useState(controlled || "");
  const [query, setQuery] = useState("");
  const [direction, setDirection] = useState("out");
  const structured = Object.values(state.world?.relationships || {});
  const rows = structured.map((r) => ({
    source: r.source_id,
    target: r.target_id,
    text: r.context,
    dimensions: r.dimensions,
    change: state.relationships.find(
      (v) => v.source_id === r.source_id && v.target_id === r.target_id,
    )?.change,
  }));
  for (const r of state.relationships)
    if (
      !structured.some(
        (x) =>
          x.source_id === r.source_id &&
          (x.target_id === r.target_id ||
            nameOf(state, x.target_id) === r.target_name),
      )
    )
      rows.push({
        source: r.source_id,
        target: r.target_id || r.target_name || it("unknown"),
        text: r.text,
        dimensions: {},
        change: r.change,
      });
  const filtered = rows.filter(
    (r) =>
      (!person ||
        (direction === "out"
          ? r.source === person
          : direction === "in"
            ? r.target === person
            : r.source === person || r.target === person)) &&
      matches(query, nameOf(state, r.source), nameOf(state, r.target), r.text),
  );
  const card = state.characters.find((c) => c.id === controlled);
  return (
    <>
      <div className="inspector-tools">
        <PersonFilter state={state} value={person} onChange={setPerson} />
        <Segments
          label={it("direction")}
          value={direction}
          onChange={setDirection}
          items={[
            { id: "out", label: it("outgoing") },
            { id: "in", label: it("incoming") },
            { id: "both", label: it("both") },
          ]}
        />
        <InspectorSearch
          label={it("findRelations")}
          value={query}
          onChange={setQuery}
        />
      </div>
      <div className="inspector-direction">
        <div>
          <strong>{person ? nameOf(state, person) : it("allPeople")}</strong>
          <p>{it("directionNote")}</p>
        </div>
        <ArrowLeftRight size={22} />
      </div>
      <div className="inspector-stack">
        {!filtered.length && <InspectorEmpty search={!!query} />}
        <Bounded
          rows={filtered}
          render={(r, i) => (
            <article
              key={`${r.source}:${r.target}:${i}`}
              className="inspector-card inspector-relation"
            >
              <div>
                <div className="inspector-pair">
                  <People {...props} ids={[r.source]} />
                  <ArrowRight size={15} />
                  <People {...props} ids={[r.target]} />
                </div>
                <h2>
                  {nameOf(state, direction === "in" ? r.source : r.target)}
                </h2>
                <Markdown text={r.text} />
              </div>
              <div className="inspector-metrics">
                {Object.entries(r.dimensions).map(([key, value]) => (
                  <div key={key} data-dimension={key} className="inspector-metric">
                    <div>
                      <span>{relationshipLabel(key)}</span>
                      <strong>
                        {typeof value === "number" ? value : it("change")}
                      </strong>
                    </div>
                    {typeof value === "number" ? (
                      <meter
                        min={-100}
                        max={100}
                        value={value}
                        aria-label={`${relationshipLabel(key)}: ${value}; ${it("range")}`}
                      />
                    ) : (
                      <p>
                        {value.direction === "up"
                          ? "↑"
                          : value.direction === "down"
                            ? "↓"
                            : "→"}{" "}
                        {value.reason}
                      </p>
                    )}
                  </div>
                ))}
                {Object.values(r.dimensions).some(
                  (v) => typeof v === "number",
                ) && <small className="muted">{it("range")}</small>}
              </div>
              {r.change && (
                <footer className="inspector-card-footer">
                  {r.change.direction === "up" ? "↑" : "↓"} {r.change.reason}
                </footer>
              )}
            </article>
          )}
        />
      </div>
      {card && save && (
        <details className="inspector-editor-disclosure">
          <summary>
            {it("editRelations")} · {card.name}
          </summary>
          <RelationshipEditor
            key={`${save.id}:${card.id}`}
            save={save}
            card={card}
            refresh={refresh}
          />
        </details>
      )}
    </>
  );
}

export function SecretsSection(props: Props) {
  const [query, setQuery] = useState("");
  const values = allFacts(props.state).filter(
    (f) =>
      f.secret &&
      matches(
        query,
        f.text,
        ...f.character_ids.map((id) => nameOf(props.state, id)),
      ),
  );
  return (
    <>
      <p className="inspector-notice">
        <Shield size={20} />
        {it("gmNotice")}
      </p>
      <div className="inspector-tools">
        <InspectorSearch
          label={it("findSecrets")}
          value={query}
          onChange={setQuery}
        />
        <small className="muted">{values.length}</small>
      </div>
      <div className="inspector-secret-grid">
        <Facts {...props} values={values} secret />
      </div>
      {!values.length && <InspectorEmpty search={!!query} />}
      <Reveal
        title={it("originalSecrets")}
        text={props.state.sections.knowledge}
        preview={false}
      />
      <p className="inspector-note">{it("publicFamily")}</p>
    </>
  );
}

export function ThreadsSection(props: Props) {
  const { state } = props;
  const [status, setStatus] = useState("active");
  const [person, setPerson] = useState("");
  const rows: Thread[] = state.world?.threads
    ? Object.values(state.world.threads)
    : (state.plans || []).map((p, i) => ({
        id: String(i),
        description: p.text,
        state: p.text,
        status:
          p.status === "open"
            ? "active"
            : p.status === "done"
              ? "resolved"
              : p.status,
        character_ids: [],
        relevance: 0,
        last_event_id: null,
      }));
  const filtered = rows
    .filter(
      (r) =>
        (!person || r.character_ids.includes(person)) &&
        (status === "all" ||
          (status === "active"
            ? ["active", "developing"].includes(r.status)
            : status === "paused"
              ? ["dormant", "paused"].includes(r.status)
              : ["resolved", "cancelled"].includes(r.status))),
    )
    .sort((a, b) => b.relevance - a.relevance);
  return (
    <>
      <div className="inspector-tools">
        <Segments
          label={it("status")}
          value={status}
          onChange={setStatus}
          items={(["active", "paused", "finished", "all"] as const).map(
            (id) => ({ id, label: it(id) }),
          )}
        />
        <PersonFilter state={state} value={person} onChange={setPerson} />
        <small className="muted">{filtered.length}</small>
      </div>
      <div className="inspector-stack">
        <Bounded
          rows={filtered}
          render={(r) => {
            const eventId = r.last_event_id || r.source_event_id;
            const event = eventId ? state.world?.events?.[eventId] : undefined;
            return (
              <article
                className={`inspector-card inspector-thread thread-${r.status}`}
                key={r.id}
              >
                <div className="inspector-row">
                  <span className="pill">{labelStatus(r.status)}</span>
                  {event && (
                    <small className="muted">
                      {timeLabel(state, event.minute)} · {it("turn")}{" "}
                      {event.source_sequence}
                    </small>
                  )}
                </div>
                <h2>{brief(r.description, 100)}</h2>
                {brief(r.description, 100) !== r.description && <Markdown text={r.description} />}
                <People {...props} ids={r.character_ids} />
                <Reveal
                  title={it("development")}
                  text={r.state}
                  preview={false}
                />
              </article>
            );
          }}
        />
        {!filtered.length && <InspectorEmpty />}
      </div>
      <Reveal
        title={it("originalThreads")}
        text={state.story_notes}
        preview={false}
      />
    </>
  );
}
function KnowledgeCards({ rows, ...props }: { rows: Knowledge[] } & Props) {
  return (
    <Bounded
      rows={rows}
      render={(k, i) => (
        <article
          className="inspector-knowledge-card"
          key={`${k.actor_id}:${k.fact_id}:${i}`}
        >
          <span className={`pill knowledge-${k.status}`}>
            {labelStatus(k.status)}
          </span>
          <Markdown
            text={props.state.world?.facts?.[k.fact_id]?.text || it("unknown")}
          />
          {k.evidence && (
            <Reveal title={it("evidence")} text={k.evidence} preview={false} />
          )}
          <People {...props} ids={[k.actor_id]} />
          {k.replaced_by && (
            <Reveal
              title={it("replaced")}
              text={
                props.state.world?.facts?.[k.replaced_by]?.text || it("unknown")
              }
              preview={false}
            />
          )}
        </article>
      )}
    />
  );
}
export function MemorySection(props: Props) {
  const { state } = props;
  const [scope, setScope] = useState("player");
  const [kind, setKind] = useState("all");
  const [query, setQuery] = useState("");
  const [person, setPerson] = useState("");
  const actor = actorOf(state);
  const knowledge = Object.values(state.world?.knowledge || {}).filter(
    (k) => k.actor_id === actor && k.status !== "unknown",
  );
  const events = state.world?.events
    ? Object.values(state.world.events)
        .filter((e) =>
          scope === "player"
            ? e.player_observed
            : e.witnesses.includes(actor || "") ||
              knowledge.some(
                (k) => k.status === "known" && k.source_event_id === e.id,
              ),
        )
        .sort(
          (a, b) =>
            (b.minute ?? -1) - (a.minute ?? -1) ||
            b.source_sequence - a.source_sequence,
        )
    : (state.events || [])
        .filter(
          (e) => scope === "player" || e.character_ids.includes(actor || ""),
        )
        .slice()
        .reverse()
        .map((e, i) => ({
          id: String(i),
          text: e.text,
          participants: e.character_ids,
          minute: null,
          source_sequence: e.turn,
        }));
  const filtered = events.filter(
    (e) =>
      (!person || e.participants.includes(person)) &&
      matches(query, e.text, ...e.participants.map((id) => nameOf(state, id))),
  );
  const facts = allFacts(state).filter(
    (f) =>
      !f.secret &&
      (!person || f.character_ids.includes(person)) &&
      (scope === "player" ||
        knowledge.some((k) => k.fact_id === f.id && k.status === "known")) &&
      matches(query, f.text, ...f.character_ids.map((id) => nameOf(state, id))),
  );
  const known = knowledge.filter(
    (k) =>
      (!person ||
        k.actor_id === person ||
        state.world?.facts?.[k.fact_id]?.character_ids.includes(person)) &&
      matches(query, state.world?.facts?.[k.fact_id]?.text, k.evidence),
  );
  const current = known.filter((k) =>
    ["known", "suspected"].includes(k.status),
  );
  const retired = known.filter((k) =>
    ["outdated", "refuted", "superseded"].includes(k.status),
  );
  return (
    <>
      <div className="inspector-tools">
        <Segments
          label={it("visibility")}
          value={scope}
          onChange={setScope}
          items={[
            { id: "player", label: it("player") },
            { id: "actor", label: it("actor"), disabled: !actor },
          ]}
        />
        <InspectorSearch
          label={it("findMemory")}
          value={query}
          onChange={setQuery}
        />
        <PersonFilter state={state} value={person} onChange={setPerson} />
      </div>
      <div className="inspector-memory-kinds">
        <Segments
          label={it("memory")}
          value={kind}
          onChange={setKind}
          items={(["all", "events", "facts", "knowledge"] as const).map(
            (id) => ({ id, label: it(id) }),
          )}
        />
      </div>
      <p className="sr-only">{it("searchCoverage")}</p>
      <div
        className={`inspector-memory-columns ${kind !== "all" ? "inspector-single" : ""}`}
      >
        {(kind === "all" || kind === "events") && (
          <div className="inspector-timeline">
            {!filtered.length && <InspectorEmpty search={!!query} />}
            <Bounded
              rows={filtered}
              render={(e, i) => {
                const group =
                  e.minute == null
                    ? `${it("turn")} ${e.source_sequence}`
                    : timeLabel(state, e.minute).replace(/ · \d{2}:\d{2}$/, "");
                const previous = filtered[i - 1];
                const groupKey =
                  e.minute == null
                    ? `turn:${e.source_sequence}`
                    : Math.floor(e.minute / 1440);
                const prevKey =
                  previous?.minute == null
                    ? `turn:${previous?.source_sequence}`
                    : Math.floor(previous.minute / 1440);
                return (
                  <div key={e.id}>
                    {(i === 0 || groupKey !== prevKey) && (
                      <h3 className="inspector-day">{group}</h3>
                    )}
                    <article className="inspector-timeline-event">
                      <span className="inspector-timeline-time">
                        {e.minute == null ? (
                          <History size={13} />
                        ) : (
                          String(Math.floor((e.minute % 1440) / 60)).padStart(
                            2,
                            "0",
                          ) +
                          ":" +
                          String(e.minute % 60).padStart(2, "0")
                        )}
                      </span>
                      <div className="inspector-card">
                        <h2>{brief(e.text, 85)}</h2>
                        {brief(e.text, 85) !== e.text && <Markdown text={e.text} />}
                        <footer className="inspector-card-footer">
                          <People {...props} ids={e.participants} />
                          <small>
                            {timeLabel(state, e.minute)} · {it("turn")}{" "}
                            {e.source_sequence}
                          </small>
                        </footer>
                      </div>
                    </article>
                  </div>
                );
              }}
            />
          </div>
        )}
        {kind !== "events" && (
          <div className="inspector-stack">
            {(kind === "all" || kind === "facts") && (
              <InspectorCard title={it("importantFacts")} icon={FileText}>
                {facts.length ? (
                  <Facts {...props} values={facts} />
                ) : (
                  <InspectorEmpty search={!!query} />
                )}
              </InspectorCard>
            )}
            {(kind === "all" || kind === "knowledge") && (
              <InspectorCard title={it("knowledge")} icon={BookOpen}>
                {!actor ? (
                  <p className="muted">{it("noActor")}</p>
                ) : (
                  <>
                    <KnowledgeCards {...props} rows={current} />
                    {!current.length && <InspectorEmpty search={!!query} />}
                    <details>
                      <summary>
                        {it("retired")} · {retired.length}
                      </summary>
                      <KnowledgeCards {...props} rows={retired} />
                    </details>
                  </>
                )}
              </InspectorCard>
            )}
          </div>
        )}
      </div>
      <Reveal title={it("archive")} preview={false}>
        <h3>{it("gmMemory")}</h3>
        <Markdown text={state.memory?.summary || it("noMemory")} />
        {Object.entries(state.memory?.per_actor || {}).map(([id, m]) => (
          <Reveal
            key={id}
            title={nameOf(state, id)}
            text={m.summary}
            preview={false}
          />
        ))}
      </Reveal>
    </>
  );
}
