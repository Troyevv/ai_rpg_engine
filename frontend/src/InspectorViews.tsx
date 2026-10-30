import {RelationshipCard} from './RelationshipCard';
import {relationshipRows} from './lib/relationshipRows';
import { useState, type ReactNode } from 'react';
import type { State, Knowledge, Save } from './types';
import {RelationshipEditor} from './RelationshipEditor';
import { Markdown } from './Markdown';
export const brief = (text: string, n = 150) => { const clean = text.replace(/[#*_`>]/g, '').replace(/\s+/g, ' ').trim(); return clean.length > n ? clean.slice(0, n).replace(/\s+\S*$/, '') + '…' : clean; };
const nameOf = (s: State, id: string) => s.characters.find(c => c.id === id)?.name || id;

export function Reveal({ title, text, children, info, preview = true }: {
    info?: ReactNode;
    title: string;
    text?: string;
    children?: ReactNode;
    preview?: boolean;
}) { const [expanded,setExpanded]=useState(false); return <details className="inspect-reveal" onToggle={e=>setExpanded(e.currentTarget.open)}><summary><span className="inspect-title">{title}</span>{info && <span className="muted small">{info}</span>}{preview && text && <span className="inspect-preview">{brief(text)}</span>}</summary>{expanded&&<div className="inspect-detail">{text && <Markdown text={text}/>}{children}</div>}</details>; }
function Items({ items }: {
    items: ReactNode[];
}) { return <>{items.slice(0, 5)}{items.length > 5 && <details className="inspect-more"><summary>Ещё {items.length - 5}</summary>{items.slice(5)}</details>}</>; }
function Empty({ children }: {
    children: ReactNode;
}) { return <p className="muted small">{children}</p>; }
export function KnowledgeRows({state, rows}: {state:State;rows:Knowledge[]}) {
    const labels:Record<string,string>={known:'Знает',suspected:'Подозревает',unknown:'Неизвестно',outdated:'Устарело',refuted:'Опровергнуто',superseded:'Исправлено'};
    const render=(k:Knowledge)=><Reveal key={`${k.actor_id}:${k.fact_id}`} title={labels[k.status] || k.status} text={state.world?.facts?.[k.fact_id]?.text || k.fact_id}>
        {k.evidence&&<p className="small">Основание: {k.evidence}</p>}
        {k.replaced_by&&<p className="small">Новое убеждение: {state.world?.facts?.[k.replaced_by]?.text || k.replaced_by}</p>}
    </Reveal>;
    const current=rows.filter(k=>k.status==='known'||k.status==='suspected');
    const retired=rows.filter(k=>['outdated','refuted','superseded'].includes(k.status));
    return <><Items items={current.map(render)}/>{retired.length>0&&<details><summary>Прежние убеждения · {retired.length}</summary><Items items={retired.map(render)}/></details>}</>;
}
export function RelationsView({
  state,
  actor,
  save,
  refresh,
  onCharacter,
}: {
  state: State;
  actor?: string;
  save?: Save | null;
  refresh?: () => void;
  onCharacter?: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [person, setPerson] = useState("");
  const [direction, setDirection] = useState("both");
  const controlled =
    state.controlled_actor_id === undefined
      ? state.protagonist_id || state.characters.find((c) => c.is_player)?.id
      : state.controlled_actor_id;
  const card =
    save && refresh && (!actor || actor === controlled)
      ? state.characters.find((c) => c.id === controlled)
      : undefined;
  const rows = relationshipRows(state).filter(
    (r) =>
      (!actor || r.source_id === actor || r.target_id === actor) &&
      (!person || r.source_id === person || r.target_id === person) &&
      (!actor ||
        direction === "both" ||
        (direction === "out"
          ? r.source_id === actor
          : r.target_id === actor)) &&
      [nameOf(state, r.source_id), nameOf(state, r.target_id), r.context]
        .join(" ")
        .toLocaleLowerCase()
        .includes(query.trim().toLocaleLowerCase()),
  );
  const render = (
    actions?: (r: (typeof rows)[number]) => ReactNode,
    add?: ReactNode,
  ) => (
    <>
      <div className="relationship-tools">
        <label>
          Поиск
          <input
            aria-label="Поиск отношений"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Имя или описание"
          />
        </label>
        <label>
          Персонаж
          <select
            aria-label="Участник отношений"
            value={person}
            onChange={(e) => setPerson(e.target.value)}
          >
            <option value="">Все персонажи</option>
            {state.characters
              .filter((c) => c.id !== actor)
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
          </select>
        </label>
        {person && onCharacter && (
          <button
            className="inspector-link"
            onClick={() => onCharacter(person)}
          >
            Открыть досье: {nameOf(state, person)}
          </button>
        )}
        {add}
      </div>
      {actor && (
        <div
          className="inspector-segments"
          role="group"
          aria-label="Направление отношений"
        >
          {[
            ["both", "Все направления"],
            ["out", "К другим"],
            ["in", "От других"],
          ].map(([key, label]) => (
            <button
              key={key}
              aria-pressed={direction === key}
              onClick={() => setDirection(key)}
            >
              {label}
            </button>
          ))}
        </div>
      )}
      <p className="muted small">
        Стрелка показывает, кто к кому относится. Обратное направление —
        отдельная запись.
      </p>
      <div className="inspector-stack">
        {rows.map((r, i) => (
          <RelationshipCard
            key={`${r.source_id}:${r.target_id}:${i}`}
            state={state}
            relation={r}
            saveId={save?.id}
            onCharacter={onCharacter}
            change={r.change}
            actions={actions?.(r)}
          />
        ))}
        {!rows.length && (
          <p role="status" className="dossier-empty">
            {query || person
              ? "Отношения не найдены."
              : "Отношения пока не записаны."}
          </p>
        )}
      </div>
    </>
  );
  return card && save && refresh ? (
    <RelationshipEditor
      key={`${save.id}:${card.id}`}
      save={save}
      card={card}
      refresh={refresh}
    >
      {({ actions, add }) => render(actions, add)}
    </RelationshipEditor>
  ) : (
    render()
  );
}
