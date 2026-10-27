import {relationshipLabel} from './lib/relationships';
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
export function RelationsView({ state, actor, save, refresh, excludeSource }: {
    state: State;
    actor?: string;
    excludeSource?:string;
    save?:Save|null;
    refresh?:()=>void;
}) { const controlled=state.controlled_actor_id===undefined ? state.protagonist_id || state.characters.find(c=>c.is_player)?.id : state.controlled_actor_id; const card=save&&refresh ? state.characters.find(c=>c.id===controlled) : undefined; const structured = Object.values(state.world?.relationships || {}); const rows = structured.map(r => ({ source: r.source_id, target: r.target_id, text: r.context, dimensions: r.dimensions, change: state.relationships.find(old => old.source_id === r.source_id && old.target_id === r.target_id)?.change })); for (const r of state.relationships) {
    if (!structured.some(x => x.source_id === r.source_id && (x.target_id === r.target_id || nameOf(state, x.target_id) === r.target_name)))
        rows.push({ source: r.source_id, target: r.target_id || r.target_name || 'Неизвестно', text: r.text, dimensions: {}, change: r.change });
} return <div className="inspector-content">{card&&save&&refresh&&<RelationshipEditor key={`${save.id}-${card.id}`} save={save} card={card} refresh={refresh}/>}<Items items={rows.filter(r => (!actor || r.source === actor || r.target === actor) && (!card || r.source!==card.id) && r.source!==excludeSource).map((r, i) => <Reveal key={i} info={Object.entries(r.dimensions).map(([k, v]) => `${relationshipLabel(k)}: ${typeof v === 'number' ? v : v.direction === 'up' ? '↑' : v.direction === 'down' ? '↓' : '→'}`).join(' · ')} title={`${nameOf(state, r.source)} → ${nameOf(state, r.target)}`} text={r.text}><div className="inspect-chips">{Object.entries(r.dimensions).map(([key, value]) => <span className="pill" key={key}>{relationshipLabel(key)}: {typeof value === 'number' ? value : <span className={value.direction === 'up' ? 'positive' : value.direction === 'down' ? 'negative' : ''}>{value.direction === 'up' ? '↑' : value.direction === 'down' ? '↓' : '→'} {value.reason}</span>}</span>)}</div>{r.change && <p className={r.change.direction === 'up' ? 'positive' : 'negative'}>{r.change.direction === 'up' ? '↑' : '↓'} {r.change.reason}</p>}</Reveal>)}/>{!rows.length && <Empty>Отношения пока не записаны.</Empty>}</div>; }
