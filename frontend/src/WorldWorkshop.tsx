import {RuntimeValue, resolver, recordTitle, runtimeLabels, enumLabels} from './runtimePresentation';
import {WorldCreationSettings, defaultCreation, type Creation} from './WorldCreationSettings';
import {SectionTabs} from "./components/ui/section-tabs";
import { useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { toast } from 'sonner';
import { api, download } from './api';
import { detectWorldImport } from './worldImport';
import { initialWorkshopIdentity, workshopIdentityReducer } from './workshopIdentity';
import { useJob } from './hooks';
import { active, type Job, type Preferences, type Workspace } from './types';
import { Preparation } from './Preparation';
import { Button } from './components/ui/button';
import { Input } from './components/ui/input';
import { Textarea } from './components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './components/ui/dialog';
import { Markdown } from './Markdown';
import { Trash2 } from 'lucide-react';
type Item = Record<string, unknown>;
type WorkspacePick = { id: string; name: string; revision: number };
type DraftState = {
    campaign: Item;
    characters: (Item & {
        id: string;
        name: string;
        fields: Record<string, string>;
    })[];
    locations: (Item & {
        id: string;
        name: string;
    })[];
    world: Record<string, Record<string, Item>>;
    protagonist_id: string;
    controlled_actor_id: string;
    camera: {
        scene_id: string;
    };
    world_clock: {
        minute: number;
    };
};
type Draft = {
    editor?:{fields:Record<string,string[]>;enums:Record<string,Record<string,string[]>>;schemas:Record<string,Record<string,Item>>} | null;
    creation_settings?: Partial<Creation>;
    presentation?: {clock:{label:string;effective?:{month_names:string[];weekday_names:string[];month_lengths:(number|null)[];year:number|null;seasons:{name:string;month:number;day:number}[];observances:{name:string;month:number;day:number}[]}};notices?:string[]} | null;
    id: string;
    name: string;
    revision: number;
    version_id: number | null;
    candidate?: Record<string,unknown> | null;
    relation_merges?: {ids:string[];paths:string[];differences:string[];safe:boolean;records:Item[]}[];
    review?: {status:string;reason?:string;issues?:{message:string;severity:string;protocol_warnings?:unknown[]}[]} | null;
    start_block_reason?: string | null;
    state: DraftState | null;
    validation: {
        diagnostics?: {path:string;message:string}[];
        errors: string[];
        warnings: string[];
    };
    import_warnings: string[];
    source_text: string;
    outline: string;
    history: {
        id: number;
        reason: string;
        created_at: string;
    }[];
    job: Job | null;
};
type Target = {
    kind: string;
    id: string;
    field: string;
    value: unknown;
    label: string;
};
const motivationFields = ['goals', 'intentions', 'obligations'];
const motivationStatuses: Record<string,string> = {active:'активно',completed:'выполнено',cancelled:'отменено',failed:'не выполнено',superseded:'заменено',expired:'срок истёк',blocked:'заблокировано'};
const motivationText = (value: unknown, activeOnly=false): string => !Array.isArray(value) ? '' : value
    .filter(v=>!activeOnly || typeof v==='string' || (v && v.status==='active' && !v.review_required?.length))
    .map(v=>typeof v==='string' ? v : v && typeof v.text==='string' ? v.text+(activeOnly ? '' : ` [${motivationStatuses[v.status] || v.status}]`) : 'Некорректная запись')
    .join(' · ');
const structuredField = (field:string,value:unknown,schema?:Item) => !!schema && [schema,...(schema.anyOf as Item[] || [])].some(s=>s.type==='object' || '$ref' in s || s.type==='array' && ((s.items as Item)?.type==='object' || !!(s.items as Item)?.['$ref'])) || motivationFields.includes(field) || !!(value && typeof value==='object' && field!=='dimensions' && (!Array.isArray(value) || value.some(x=>typeof x==='object')));
const labels: Record<string, string> = { public_description: 'Аннотация для игрока', title: 'Название', setting: 'Обстановка', era: 'Эпоха', genre: 'Жанр', tone: 'Тон', description: 'Описание', rules: 'Правила повествования', name: 'Имя / название', aliases: 'Другие имена', location: 'Местоположение', situation: 'Сейчас', goals: 'Цели', intentions: 'Намерения', emotion: 'Эмоциональное состояние', obligations: 'Обязательства', source_id: 'От кого', target_id: 'К кому', context: 'Динамика отношений', dimensions: 'Показатели отношений', visible_to_ids: 'Кому известна информация', text: 'Описание', secret: 'Секрет', owner_id: 'Чья тайна', character_ids: 'Связанные персонажи', evidence: 'Основания', actor_id: 'Кто знает', fact_id: 'Факт', status: 'Статус', source_event_id: 'Источник знания', state: 'Текущее развитие', public_state: 'Известное герою состояние', relevance: 'Значимость', participants: 'Участники', start_minute: 'Начало · минуты недели', end_minute: 'Конец · минуты недели', protagonist_id: 'Основной герой', controlled_actor_id: 'Управляемый персонаж', scene_id: 'Стартовая сцена', minute: 'Игровое время · минуты недели', witnesses: 'Свидетели', fact_ids: 'Факты', player_observed: 'Известно игроку' };
Object.assign(labels,{parent_id:'Родительская локация',location_id:'Локация',organization_id:'Организация',kind:'Тип',since:'Начало периода',until:'Конец периода',physical_state:'Физическое состояние',life_status:'Жизненный статус',birth_date:'Дата рождения',calendar:'Календарь',appearance:'Внешность',personality:'Характер',values:'Ценности',capabilities:'Возможности',developmental_stage:'Этап жизни',claim:'Структурированный факт',holder_id:'У кого находится'});
Object.assign(labels,runtimeLabels);
const fields: Record<string, string[]> = { campaign: ['title', 'setting', 'era', 'genre', 'tone', 'description', 'rules'], actor: ['location', 'situation', 'goals', 'intentions', 'emotion', 'obligations'], relationship: ['source_id', 'target_id', 'context', 'dimensions', 'visible_to_ids'], location: ['name', 'text'], fact: ['text', 'secret', 'owner_id', 'character_ids', 'evidence'], knowledge: ['actor_id', 'fact_id', 'status', 'source_event_id'], thread: ['description', 'state', 'public_state', 'status', 'character_ids', 'relevance', 'visible_to_ids'], scene: ['location', 'participants', 'text', 'start_minute', 'end_minute', 'status'], event: ['text', 'participants', 'witnesses', 'minute', 'fact_ids', 'player_observed'], start: ['protagonist_id', 'controlled_actor_id', 'scene_id', 'minute'] };
const extensionGroups: Record<string,string> = {objective_relations:'Родство и социальные связи',organizations:'Организации',residences:'Проживание',roles:'Профессии и роли',possessions:'Значимое имущество',conditions:'Обстоятельства',pregnancies:'Беременности',contacts:'Контакты',reproductive_events:'Репродуктивные события',naming_decisions:'Выбор имён',scheduled_events:'Будущие события и договорённости'};
const groups = [['Персонажи', 'character', 'characters'], ['Отношения', 'relationship', 'relationships'], ['Места', 'location', 'locations'], ['Факты и тайны', 'fact', 'facts'], ['Знания персонажей', 'knowledge', 'knowledge'], ['Сюжетные линии', 'thread', 'threads'], ['Сцены', 'scene', 'scenes'], ['События', 'event', 'events']];
const short = (value: unknown, max = 180) => { const s = String(value || '').replace(/\s+/g, ' ').trim(); return s.length > max ? s.slice(0, max).trimEnd() + '…' : s; };
const dimensions: Record<string,string> = {trust:'Доверие',affection:'Привязанность',attraction:'Влечение',irritation:'Раздражение',fear:'Страх',jealousy:'Ревность',respect:'Уважение'};
const strength = (n: number) => Math.abs(n) < 25 ? 'слабое' : Math.abs(n) < 60 ? 'заметное' : 'сильное';
export function WorldWorkshop({ prefs, apiKey, onWorld, onGame }: {
    prefs: Preferences;
    apiKey: string;
    onWorld: (id: number) => void;
    onGame: (world: number, save: number) => void;
}) {
    const [creation, setCreation] = useState<Creation>(()=>{try{return {...defaultCreation,...JSON.parse(localStorage.getItem('worldCreationSettings')||'{}')}}catch{return defaultCreation}});
    useEffect(()=>{localStorage.setItem('worldCreationSettings',JSON.stringify(creation));},[creation]);
    const [candidatePath,setCandidatePath] = useState('');
    const [candidateValue,setCandidateValue] = useState('');
    const [residenceGrouping,setResidenceGrouping] = useState('actor');
    const [structuredEdit, setStructuredEdit] = useState('');
    const [mode, setMode] = useState('quick');
    const [section, setSection] = useState<'overview'|'characters'|'world'|'relations'|'story'|'start'|'more'>('overview');
    const [selectedCharacter, setSelectedCharacter] = useState('');
    const [editingIdea, setEditingIdea] = useState(false);
    const [workspace, dispatchWorkspace] = useReducer(workshopIdentityReducer<Draft>, localStorage.getItem('draftWorkspace') || '', initialWorkshopIdentity<Draft>);
    const {id, draft, loading} = workspace;
    const requestSequence = useRef(0);
    const loadController = useRef<AbortController | null>(null);
    const [list, setList] = useState<WorkspacePick[]>([]);
    const [removed, setRemoved] = useState<WorkspacePick[]>([]);
    const [deleteDraft, setDeleteDraft] = useState<WorkspacePick | null>(null);
    const [author, setAuthor] = useState(false);
    const [authorAsk, setAuthorAsk] = useState(false);
    const [authorAcknowledged, setAuthorAcknowledged] = useState(false);
    const [text, setText] = useState('');
    const [importFormat, setImportFormat] = useState<'text'|'json'>('text');
    const [importFile, setImportFile] = useState('');
    const detectedImport = useMemo(() => detectWorldImport(text, importFile ? importFormat : undefined), [text, importFile, importFormat]);
    const [name, setName] = useState('Новая история');
    const [useIdea, setUseIdea] = useState(false);
    const [busy, setBusy] = useState(false);
    const [edit, setEdit] = useState<Target | null>(null);
    const [value, setValue] = useState<unknown>('');
    const [instruction, setInstruction] = useState('');
    const [ack, setAck] = useState(false);
    const [confirmStart, setConfirmStart] = useState(false);
    const [related, setRelated] = useState<{
        kind: string;
        id: string;
    }[]>([]);
    const [removal, setRemoval] = useState<{
        kind: string;
        id: string;
        deps: {
            kind: string;
            id: string;
        }[];
    } | null>(null);
    const selectWorkspace = (wid: string, nextDraft: Draft | null = null) => {
        if (nextDraft && String(nextDraft.id) !== String(wid)) throw new Error('Workspace identity mismatch');
        loadController.current?.abort();
        if (wid) localStorage.setItem('draftWorkspace', wid);
        else localStorage.removeItem('draftWorkspace');
        dispatchWorkspace({type: 'select', id: wid, draft: nextDraft, request: ++requestSequence.current});
        setEdit(null); setRemoval(null); setConfirmStart(false);
    };
    const refresh = async () => {
        if (!id) return;
        loadController.current?.abort();
        const controller = new AbortController();
        loadController.current = controller;
        const request = ++requestSequence.current;
        dispatchWorkspace({type: 'load', id, request});
        try {
            const next = await api<Draft>(`/workspaces/${id}/draft?author=${author}`, undefined, 'GET', controller.signal);
            if (!controller.signal.aborted) dispatchWorkspace({type: 'loaded', id, draft: next, request});
        } catch (e) {
            if (!controller.signal.aborted) toast.error((e as Error).message);
            dispatchWorkspace({type: 'failed', id, request});
        }
    };
    useEffect(() => { setImportFormat('text'); setImportFile(''); }, [id]);
    useEffect(() => { if (mode !== 'import' && importFormat === 'json') {
        setText(''); setImportFormat('text'); setImportFile('');
    } }, [mode, importFormat]);
    useEffect(() => { void api<typeof list>('/workspaces').then(setList).catch(e => toast.error(e.message)); }, []);
    useEffect(() => {
        void refresh();
        return () => loadController.current?.abort();
    }, [id, author]);
    const savedCreation=JSON.stringify(draft?.creation_settings||{});
    useEffect(()=>{const saved=JSON.parse(savedCreation);if(Object.keys(saved).length)setCreation({...defaultCreation,...saved});},[id,savedCreation]);
    const { job, reconnecting } = useJob(draft?.job, refresh);
    const locked = busy || loading || active(job);
    const phaseStatus: Record<string, [string,string]> = {
        continuing: ['Продолжаем ответ…', 'Полученная часть сохранена. Модель дописывает тот же мир.'],
        world: ['Собираем игровой мир…', 'Модель развивает идею и сразу создаёт готовый World State.'],
        retrying: ['Исправляем найденные ошибки…', 'Модель предлагает локальные изменения; остальные данные сохраняются.'],
        improving: ['Дополняем карточки…', 'Заполняем разрешённые незаданные детали; сохраняем авторские ограничения.'],
        validating: ['Проверяем структуру мира…', 'Локальная проверка типов и ссылок.'],
        reviewing: ['Проверяем смысловую согласованность…', 'Модель проверяет сохранённый мир.'],
        review_format_repair: ['Исправляем отчёт проверки…', 'Мир сохранён. Исправляется формат ответа проверяющего.'],
        saving: ['Сохраняем версию…', 'Проверенный мир записывается в SQLite.'],
        editing: ['Обновляем выбранное поле…', 'Модель подготавливает новую версию поля.'],
    };
    const status = phaseStatus[job?.phase || ''] || ['Ожидаем запуска генерации…', 'Задание создано и ожидает запуска модели.'];
    const run = async (fn: () => Promise<void>) => { setBusy(true); try {
        await fn();
    }
    catch (e) {
        toast.error((e as Error).message);
    }
    finally {
        setBusy(false);
    } };
    const change = (body: Item) => run(async () => { await api(`/workspaces/${id}/draft`, { revision: draft?.revision, ...body }, 'PATCH'); refresh(); });
    const generate = (body: Item) => run(async () => { const j = await api<Job>(`/workspaces/${id}/draft/generate`, { revision: draft?.revision, config: prefs.summary, api_key: apiKey, ...body }); dispatchWorkspace({type:'update',id,update:d => d ? {...d,job:j} : d}); setEdit(null); });
    const openEdit = (target: Target) => { setEdit(target); setValue(target.value); setStructuredEdit(JSON.stringify(target.value ?? null,null,2)); setInstruction(''); setAck(false); };
    const state = draft?.state;
    const editSchema=edit ? draft?.editor?.schemas?.[edit.kind]?.[edit.field] : undefined;
    const editTypes=[editSchema,...(editSchema?.anyOf as Item[] || [])].filter(Boolean).map(s=>s?.type);
    const nullableEdit=editTypes.includes('null');
    const previousWorld = !!state && !!(job as Job & {transport_incomplete?:boolean})?.transport_incomplete;
    const characters = state?.characters || [];
    const actor = state?.controlled_actor_id;
    const resolve = resolver(state || {characters:[],locations:[],world:{}});
    const person = (cid: unknown) => resolve('actor_id',cid) || 'Неизвестно';
    const place = (lid: unknown) => resolve('location',lid) || 'Место не указано';
    const calendarNotices=draft?.presentation?.notices||[];
    const weekTime = () => draft?.presentation?.clock.label || 'Время не указано';
    const actorCard = characters.find(c => c.id === actor);
    const beginning = state?.world.scenes?.[state.camera.scene_id];
    const relations = Object.entries(state?.world.relationships || {});
    const facts = Object.entries(state?.world.facts || {});
    const threads = Object.entries(state?.world.threads || {});
    const actorState = actor ? state?.world.characters?.[actor] : undefined;
    const named = (title: string, value: unknown) => value ? <div className="workshop-meta"><span>{title}</span><strong>{title==='Место'?place(value):String(value)}</strong></div> : null;
    const relation = ([key,r]: [string,Item]) => <details className="workshop-detail workshop-relation" key={key}><summary><strong>{person(r.source_id)} → {person(r.target_id)}</strong><span>{short(r.context,100)}</span></summary>
      {Boolean(r.dimensions) && Object.keys(r.dimensions as Item).length > 0 && <div className="workshop-chips">{Object.entries(r.dimensions as Item).map(([k,v])=><span key={k}>{dimensions[k] || k} · {strength(Number(v))}{Number(v) < 0 ? ' (−)' : ''}</span>)}</div>}
      {Boolean(r.context) && <p className="workshop-literary">{String(r.context)}</p>}{author && entity('relationship',key,r)}</details>;
    const options = (field: string): [
        string,
        string
    ][] | null => {
        const typed=edit && draft?.editor?.enums[edit.kind]?.[field];
        if(typed)return typed.map(v=>[v,enumLabels[v] || v]);
        if (['protagonist_id', 'controlled_actor_id', 'source_id', 'target_id', 'owner_id', 'actor_id', 'character_ids', 'visible_to_ids', 'participants', 'witnesses'].includes(field))
            return characters.map(c => [c.id, c.name]);
        const group = field === 'scene_id' ? 'scenes' : field === 'fact_id' || field === 'fact_ids' ? 'facts' : field === 'source_event_id' ? 'events' : null;
        if (group)
            return Object.entries(state?.world[group] || {}).map(([k, v]) => [k, String(v.text || v.location || k)]);
        if (['location','location_id','parent_id','location_ids'].includes(field)) return (state?.locations || []).map(p=>[p.id,p.name]);
        if (field === 'organization_id') return Object.entries(state?.world.organizations || {}).map(([id,v])=>[id,String(v.name || id)]);
        if (field === 'status')
            return (edit?.kind === 'knowledge' ? ['known', 'suspected', 'unknown', 'outdated', 'refuted', 'superseded'] : edit?.kind === 'thread' ? ['active', 'developing', 'dormant', 'resolved'] : ['active', 'closed']).map(x => [x, enumLabels[x] || x]);
        return null;
    };
    const row = (kind: string, eid: string, field: string, v: unknown, editable=true) => <div className="draft-field" key={field}><div className="draft-field-heading"><span>{labels[field] || field.replace('fields.', '')}</span>{author && editable && (field.startsWith('fields.') || draft?.editor?.fields[kind]?.includes(field)) && <Button variant="ghost" size="sm" disabled={locked} aria-label={`Изменить ${labels[field] || field}`} onClick={() => {setStructuredEdit(JSON.stringify(v,null,2));openEdit({ kind, id: eid, field, value: v, label: labels[field] || field.replace('fields.', '') });}}>Изменить</Button>}</div>{v && typeof v==='object' && field!=='capabilities' ? <details><summary>{field==='calendar' ? enumLabels[String(((v as Item).profile as Item)?.system || 'gregorian')] : `Сведения · ${Array.isArray(v)?v.length:Object.keys(v).length}`}</summary><RuntimeValue field={field} value={v} resolve={resolve} author={author}/></details> : <RuntimeValue field={field} value={v} resolve={resolve} author={author}/>}</div>;
    const extension = (key:string,title:string) => {
        const records=Object.entries(state?.world[key] || {});
        const render=([eid,item]:[string,Item])=><details className="workshop-detail" key={eid}><summary>{recordTitle(key,item,resolve,author)}{item.status?' · '+(enumLabels[String(item.status)] || String(item.status)):''}</summary>{Object.entries(item).filter(([field])=>!['id','revision','source_turn','turn_id','provenance','applied'].includes(field)).map(([field,v])=>row(key,eid,field,v))}<details><summary>Технические сведения</summary><pre>{JSON.stringify(item,null,2)}</pre></details></details>;
        return <details className="workshop-detail" key={key}><summary>{title} · {records.length}</summary>{!records.length && <p>Нет записей</p>}{key==='residences' && records.length>0 ? <><label>Группировать по <select aria-label="Группировка проживания" value={residenceGrouping} onChange={e=>setResidenceGrouping(e.target.value)}><option value="actor">персонажам</option><option value="location">местам</option></select></label>{Array.from(new Set(records.map(([,v])=>String(v[residenceGrouping==='actor'?'actor_id':'location_id'])))).map(id=><section key={id}><h5>{resolve(residenceGrouping==='actor'?'actor_id':'location_id',id)}</h5>{records.filter(([,v])=>v[residenceGrouping==='actor'?'actor_id':'location_id']===id).map(render)}</section>)}</>:records.map(render)}</details>;
    };
    const entity = (kind: string, eid: string, item: Item) => <div className="draft-entity" key={eid}>
 {kind === 'character' ? <>{row(kind, eid, 'name', item.name)}{Array.isArray(item.aliases) && item.aliases.length > 0 ? row(kind, eid, 'aliases', item.aliases) : null}{Object.entries(item.fields as Record<string, string>).filter(([k]) => !['Сейчас', 'Чего хочет', 'Намерения'].includes(k)).map(([k, v]) => row(kind, eid, 'fields.' + k, v))}<details><summary>Состояние, цели и намерения</summary>{[...fields.actor,...Object.keys(state?.world.characters[eid] || {}).filter(f=>!fields.actor.includes(f) && !!draft?.editor?.fields.actor?.includes(f))].map(f => row('actor', eid, f, state?.world.characters[eid]?.[f] ?? null))}<details><summary>Технические сведения состояния</summary><pre>{JSON.stringify(state?.world.characters[eid],null,2)}</pre></details></details></> : [...fields[kind],...Object.keys(item).filter(f=>!fields[kind].includes(f) && !['id','revision','source_turn','time_semantics'].includes(f))].map(f => row(kind, eid, f, item[f] ?? (['character_ids', 'visible_to_ids', 'participants', 'witnesses', 'fact_ids', 'evidence'].includes(f) ? [] : '')))}
 {author && <div className="actions">{kind === 'character' && <Button variant="outline" disabled={locked} onClick={() => { setEdit({ kind, id: eid, field: '__character', value: '', label: 'Перегенерировать персонажа целиком' }); setInstruction(''); setAck(false); setRelated([]); void api<{
        kind: string;
        id: string;
    }[]>(`/workspaces/${id}/draft/dependencies?kind=character&entity_id=${eid}`).then(setRelated).catch(e => toast.error(e.message)); }}>Новая версия персонажа</Button>}<Button variant="ghost" disabled={locked} onClick={() => void run(async () => { const deps = await api<{
        kind: string;
        id: string;
    }[]>(`/workspaces/${id}/draft/dependencies?kind=${kind}&entity_id=${eid}`); setRemoval({ kind, id: eid, deps }); })}>Удалить</Button></div>}
 </div>;
    if (mode === 'scenario')
        return <><Button className="workshop-back" variant="ghost" onClick={() => setMode('quick')}>← Генератор мира</Button><Preparation prefs={prefs} apiKey={apiKey} onWorld={onWorld} onDraft={wid => { selectWorkspace(wid); setUseIdea(true); setMode('quick'); }}/></>;
    return <main className="preparation world-workshop" aria-busy={loading} data-workspace-id={id} data-draft-workspace-id={draft?.id || ''}>
      <header className="workshop-heading">
        <p className="eyebrow">Мастерская историй</p>
        <h1>{state ? String(state.campaign.title || draft?.name) : 'Придумай свою историю'}</h1>
        <p>Расскажи, во что хочется играть. Генератор разовьёт идею: придумает мир, персонажей и начальную ситуацию.</p>
      </header>
      <nav className="workshop-paths" aria-label="Способ создания">
        <button className={mode === 'quick' ? 'selected' : ''} onClick={() => setMode('quick')}>По моей идее</button>
        <button onClick={() => setMode('scenario')}>Со Сценаристом</button>
        <button className={mode === 'import' ? 'selected' : ''} onClick={() => setMode('import')}>Импортировать</button>
      </nav>
      <details className="workshop-continue"><summary>Мои черновики {draft ? `· ${draft.name}` : ''}</summary>
        <div className="workshop-draft-list">
          <button disabled={locked} className={!id ? 'selected' : ''} onClick={() => { selectWorkspace(''); setAuthor(false); setUseIdea(false); setText(''); }}>+ Новая история</button>
          {list.map(w => <div className="workshop-draft-row" data-workspace-id={w.id} key={w.id}>
            <button disabled={locked} className={id === w.id ? 'selected' : ''} onClick={() => { selectWorkspace(w.id); setAuthor(false); setUseIdea(false); setText(''); }}>{w.name}</button>
            <Button variant="ghost" size="sm" aria-label={`Удалить черновик «${w.name}»`} disabled={locked} onClick={() => setDeleteDraft(w)}><Trash2 size={16}/></Button>
          </div>)}
        </div>
        <details className="workshop-trash" onToggle={e => { if (e.currentTarget.open) void api<WorkspacePick[]>('/workspaces?deleted=true').then(setRemoved).catch(err => toast.error(err.message)); }}><summary>Удалённые черновики</summary>
          {removed.length === 0 ? <p>Корзина пуста.</p> : removed.map(w => <div className="workshop-draft-row" data-workspace-id={w.id} key={w.id}><span>{w.name}</span><Button variant="ghost" size="sm" disabled={locked} onClick={() => void run(async () => { await api(`/workspaces/${w.id}/restore`,{revision:w.revision}); setList(await api<WorkspacePick[]>('/workspaces')); setRemoved(await api<WorkspacePick[]>('/workspaces?deleted=true')); selectWorkspace(w.id); toast.success('Черновик восстановлен'); })}>Восстановить</Button></div>)}
        </details>
      </details>
      {job?.status==='error' && (job as Job & {transport_incomplete?:boolean}).transport_incomplete && <section role="status"><h3>Восстановление ответа</h3><p>Полученный ответ сохранён. Продолжение проверит сборку, запросит недостающий конец при необходимости и завершит проверку мира. Полный проверенный мир ещё не готов.</p></section>}
      {((job?.resumable && !(job as Job & {fragment_recovery?:boolean;transport_blocked?:boolean}).fragment_recovery && !(job as Job & {transport_blocked?:boolean}).transport_blocked) || (draft?.review?.status==='stale' && job?.status==='saved')) && <Button disabled={locked} onClick={()=>void run(async()=>{await api(`/workspaces/${id}/draft/resume`,{api_key:apiKey,revision:draft?.revision,max_tokens:prefs.summary.max_tokens,context_length:prefs.summary.context_length});await refresh();})}>{draft?.review && !(job as Job & {transport_incomplete?:boolean})?.transport_incomplete ? 'Повторить проверку' : 'Продолжить сохранённую генерацию'}</Button>}
      {job?.resumable && <p className="workshop-hint">При продолжении сохраняются модель и режим thinking задания. Из текущих настроек применятся только контекст и лимит ответа; общий бюджет не сбрасывается.</p>}
      {(job as Job & {transport_blocked?:boolean})?.transport_blocked && <p role="alert">Сборка остановлена: повреждены исходные данные или нет безопасной границы для повтора. Скачайте диагностику; автоматическая замена сохранённых частей запрещена.</p>}
      {(job as Job & {fragment_recovery?:boolean})?.fragment_recovery && <details><summary>Повторить проблемное продолжение</summary><p>Предыдущие части останутся неизменными. Отклонённая часть сохранится в диагностике; новый запрос может быть оплачен.</p><Button disabled={locked} onClick={()=>void run(async()=>{await api(`/workspaces/${id}/draft/resume`,{api_key:apiKey,revision:draft?.revision,max_tokens:prefs.summary.max_tokens,context_length:prefs.summary.context_length,retry_last_fragment:true});await refresh();})}>Запросить только последнее продолжение</Button></details>}
      {(job?.status === 'error' || job?.status === 'stopped') && <div><Button variant="outline" onClick={()=>void run(async()=>{download(JSON.stringify(await api(`/workspaces/${id}/draft/raw`),null,2),'generation-response.json');})}>Скачать исходный ответ и диагностику</Button>
      {(job as Job & {unknown_outcome?:boolean}).unknown_outcome && <details><summary>Восстановить запрос с неизвестным исходом</summary><p>Провайдер мог списать оплату. Повтор может быть оплачен ещё раз; полученный текст останется в истории.</p><Button disabled={locked} onClick={()=>void run(async()=>{await api(`/workspaces/${id}/draft/resume`,{api_key:apiKey,revision:draft?.revision,max_tokens:prefs.summary.max_tokens,context_length:prefs.summary.context_length,acknowledge_unknown:true});await refresh();})}>Повторить с возможной повторной оплатой</Button></details>}</div>}
      {draft?.review && ['failed','running','not_started','stale'].includes(draft.review.status) && <section className="workshop-review" role="status"><h3>Смысловая проверка не завершена</h3><p>Мир сохранён. Автоматическая проверка не завершилась. Это не установленная ошибка поля мира.</p><p>{draft.review.reason || 'Для запуска игры требуется проверить актуальную версию мира.'}</p></section>}
      {author && draft?.review?.issues && draft.review.issues.length>0 && <details className="workshop-detail"><summary>Замечания смысловой проверки · {draft.review.issues.length}</summary>{draft.review.issues.map((issue,i)=><div key={i}><p>{issue.severity==='blocker'?'Противоречие':'Рекомендация'}: {issue.message}</p>{issue.protocol_warnings && <details><summary>Диагностика ссылок отчёта</summary><pre>{JSON.stringify(issue.protocol_warnings,null,2)}</pre></details>}</div>)}</details>}
      {draft?.start_block_reason && <p role="alert">Запуск заблокирован: {draft.start_block_reason}</p>}
      {!state && draft?.version_id && !(job as Job & {transport_incomplete?:boolean})?.transport_incomplete && job && <Button variant="outline" onClick={()=>authorAcknowledged ? setAuthor(true) : setAuthorAsk(true)}>Открыть результат в редакторе автора</Button>}
      {author && draft?.relation_merges?.map((merge,i)=><section className="workshop-review" key={i}>
        <h3>Две записи одной связи</h3>
        <p>{merge.safe?'Структурированные данные совпадают. Объединение сохранит оба описания и ссылки. Смысловая проверка проверит согласованность текста.':'Записи различаются: повторите проверку для локального исправления противоречия.'}</p>
        <p>Различающиеся поля: {merge.differences.join(', ') || 'только ID и порядок участников'}</p>
        {merge.records.map((record,j)=><details key={j} open><summary>{merge.paths[j]}</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify(record,null,2)}</pre></details>)}
        {merge.safe && <Button disabled={locked} onClick={()=>void run(async()=>{await api(`/workspaces/${id}/draft/merge-relations`,{revision:draft.revision,ids:merge.ids});await refresh();})}>Объединить связи</Button>}
      </section>)}
      {author && draft?.candidate && <section className="workshop-review"><h3>Восстановление черновика</h3><p>Результат сохранён целиком. Поля с установленными ошибками можно выбрать ниже. Доступное действие восстановления показано выше; технические подробности сохранены в журнале.</p>
        {draft.validation.diagnostics?.filter(d=>d.path && d.path!=='/').map((d,i)=><div key={i}><p role="alert">{d.path}: {d.message}</p><Button variant="outline" disabled={d.path==='/'} onClick={()=>{setCandidatePath(d.path);let v:unknown=draft.candidate;try{for(const key of d.path.slice(1).split('/'))v=(v as Record<string,unknown>)[key.replace(/~1/g,'/').replace(/~0/g,'~')];}catch{v=null;}setCandidateValue(JSON.stringify(v??null,null,2));}}>Исправить поле</Button></div>)}
        {candidatePath && <><Input aria-label="Путь поля кандидата" value={candidatePath} onChange={e=>setCandidatePath(e.target.value)}/>
        <Textarea aria-label="Значение поля кандидата JSON" value={candidateValue} onChange={e=>setCandidateValue(e.target.value)}/>
        <Button disabled={locked || !candidatePath || candidatePath==='/'} onClick={()=>void run(async()=>{await api(`/workspaces/${id}/draft/candidate`,{revision:draft.revision,path:candidatePath,value:JSON.parse(candidateValue)},'PATCH');await refresh();})}>Сохранить исправление</Button></>}
        <Button variant="outline" onClick={()=>void refresh()}>Проверить структуру локально</Button>
        <details><summary>Полный кандидат (включая тайны)</summary><pre style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{JSON.stringify(draft.candidate,null,2)}</pre></details>
      </section>}
      {(!state || editingIdea) && <section className="workshop-inspiration">
        <div className="workshop-inspiration-head"><span className="workshop-step">01 · ЗАМЫСЕЛ</span><h2>{mode === 'import' ? 'Загрузи готовую выжимку' : 'С чего начинается история?'}</h2></div>
        <p>{mode === 'import' ? 'Подойдёт .md, .txt или готовый .json мира. Можно вставить текст выжимки ниже.' : 'Пиши свободно, как Сценаристу: персонажи, атмосфера, отношения, важные события. Пробелы генератор заполнит сам.'}</p>
        {mode === 'quick' && !useIdea && <p className="workshop-footnote">Генератор сразу превратит замысел в готовый мир и выжимку. Сценарист доступен отдельно.</p>}
        {mode === 'import' && <Input type="file" accept=".md,.txt,.json" disabled={locked} aria-label="Файл мира" onChange={e => { const f = e.target.files?.[0]; if (f) void run(async () => {const content = await f.text(); setText(content); setImportFormat(f.name.toLowerCase().endsWith('.json') ? 'json' : 'text'); setImportFile(f.name);}); }}/ >}
        {mode === 'import' && <p role="status">Распознано: {detectedImport.format === 'json' ? detectedImport.error ? 'JSON (ошибка)' : 'JSON World State' : 'текстовая выжимка'}{importFile && ` · ${importFile}`}{importFile && importFormat === 'json' && <> · Будет импортирован готовый World State. <Button variant="ghost" disabled={locked} onClick={() => {setText(''); setImportFormat('text'); setImportFile('');}}>Вставить текст выжимки</Button></>}</p>}
        {mode === 'import' && detectedImport.error && <p className="workshop-error" role="alert">{detectedImport.error}</p>}
        {!id && <Input aria-label="Название черновика" value={name} onChange={e => setName(e.target.value)} placeholder="Название истории (можно изменить позже)" />}
        {mode !== 'import' && <WorldCreationSettings value={creation} onChange={setCreation} disabled={locked}/>}
        {!(mode === 'import' && importFile && importFormat === 'json') && <Textarea className="workshop-idea-input" value={text} onChange={e => {setText(e.target.value); setImportFile(''); setImportFormat('text');}} aria-label="Описание мира или текст импорта" placeholder={mode === 'import' ? 'Вставь здесь текст выжимки или JSON мира…' : 'Например: современная клиника. Я играю за врача. Придумай важных коллег и напряжённые, но живые отношения. Сейчас четверг, 14:00…'} />}
        {mode === 'quick' && draft && <label className="workshop-scenario-option"><input type="checkbox" checked={useIdea} onChange={e => setUseIdea(e.target.checked)}/> Взять за основу сценарий этого черновика</label>}
        <div className="workshop-create-actions">
          <Button disabled={locked || (!text.trim() && !useIdea) || (mode === 'import' && !!detectedImport.error)} onClick={() => void run(async () => {
            if (mode === 'import' && detectedImport.error) throw new Error(detectedImport.error);
            let current = draft; let wid = id;
            if (!current) {
              const w = await api<Workspace>('/workspaces', {name: name.trim() || 'Новая история'});
              wid = w.id; current = {id: wid, name: w.name, revision: w.revision, version_id: null, state: null,
                validation: {errors: [], warnings: []}, import_warnings: [], source_text: '', outline: '', history: [], job: null};
              setList(items => [w, ...items]);
            }
            if (mode === 'import') {
              const imported = await api<Draft>(`/workspaces/${wid}/draft/import`, {text, format: detectedImport.format, revision: current.revision});
              const opened = author ? await api<Draft>(`/workspaces/${wid}/draft?author=true`) : imported;
              selectWorkspace(wid, opened);
            }
            else {
              const j = await api<Job>(`/workspaces/${wid}/draft/generate`, {revision: current.revision, task: 'world', text, use_idea: useIdea, creation_settings: creation, config: prefs.summary, api_key: apiKey});
              selectWorkspace(wid, {...current, job: j});
            }
            setEditingIdea(false);
            if (mode === 'import' && detectedImport.format === 'json') {setText(''); setImportFormat('text'); setImportFile('');}
          })}>{mode === 'import' ? 'Открыть в редакторе' : state ? 'Создать новую версию мира' : 'Развить идею и создать мир'}</Button>
          {state && <Button variant="ghost" onClick={() => setEditingIdea(false)}>Вернуться к миру</Button>}
        </div>
      </section>}
      {active(job) && <section className="workshop-generating" role="status">
        <span className="workshop-pulse"/><div><strong>{reconnecting ? 'Восстанавливаем соединение…' : status[0]}</strong><p>{reconnecting ? 'Ожидаем связь с сервером. Генерация продолжает выполняться.' : status[1]}</p>{!reconnecting && !!job?.progress_chars && !['validating','saving'].includes(job.phase || '') && <small>Получено {job.progress_chars.toLocaleString('ru-RU')} символов ответа</small>}</div>
        <Button variant="ghost" onClick={() => void run(async () => {await api(`/jobs/${job!.id}/stop`, {}); refresh();})}>Остановить</Button>
      </section>}
      <Dialog open={!!deleteDraft} onOpenChange={open => { if (!open) setDeleteDraft(null); }}><DialogContent><DialogHeader><DialogTitle>Удалить «{deleteDraft?.name}»?</DialogTitle><DialogDescription>Черновик переместится в удалённые. Готовые игровые сохранения не затрагиваются.</DialogDescription></DialogHeader><div className="workshop-dialog-actions"><Button variant="ghost" onClick={() => setDeleteDraft(null)}>Отмена</Button><Button disabled={busy} onClick={() => void run(async () => { if (!deleteDraft) return; await api(`/workspaces/${deleteDraft.id}`,{revision:deleteDraft.revision},'DELETE'); setList(await api<WorkspacePick[]>('/workspaces')); setRemoved(await api<WorkspacePick[]>('/workspaces?deleted=true')); if (id === deleteDraft.id) { selectWorkspace(''); } setDeleteDraft(null); toast.success('Черновик перемещён в удалённые'); })}>Удалить</Button></div></DialogContent></Dialog>
      {job?.error && <p className="workshop-error" role="alert">{job.error}</p>}
      {calendarNotices.map((notice,i)=><p key={i} role="status">{notice}</p>)}
      {state && <section className="workshop-result">
        {job?.status === 'saved' && !!draft?.validation.warnings.length && <p className="workshop-hint">Мир сохранён. Некоторые творческие детали модель оставила неполными — они перечислены в «Проверке мира» и доступны для редактирования.</p>}
        <div className="workshop-result-heading"><div><span className="workshop-step">{previousWorld ? 'ПРЕДЫДУЩИЙ МИР' : '02 · МИР ГОТОВ'}</span><h2>{previousWorld ? 'Ранее сохранённый мир' : 'Посмотри, что получилось'}</h2></div>
          <Button variant="ghost" disabled={locked} onClick={() => {setEditingIdea(true); setText(draft?.source_text || text);}}>Изменить замысел</Button></div>
        <div className="workshop-result-toolbar">
          <div className="workshop-view"><span>Вид:</span><button className={!author ? 'selected' : ''} aria-pressed={!author} onClick={() => setAuthor(false)}>Игрок</button><button className={author ? 'selected' : ''} aria-pressed={author} onClick={() => authorAcknowledged ? setAuthor(true) : setAuthorAsk(true)}>Автор мира</button></div>
          <span className="workshop-hint">{author ? 'Полное состояние: секреты и намерения NPC доступны для редактирования.' : `То, что доступно персонажу ${person(actor)}.`}</span>
        </div>
        {(draft?.validation.errors.length || draft?.validation.warnings.length || draft?.import_warnings.length) ? <details className="workshop-review" open={!!draft?.validation.errors.length}>
          <summary>Проверка мира · {draft?.validation.errors.length || 0} ошибок · {(draft?.validation.warnings.length || 0) + (draft?.import_warnings.length || 0)} замечаний</summary>
          {[...(draft?.validation.errors || []), ...(draft?.validation.warnings || []), ...(draft?.import_warnings || [])].map((x,i)=><p key={i}>{x}</p>)}
        </details> : null}
        <SectionTabs className="workshop-tabs" label="Разделы мира" value={section} onChange={setSection} items={([['overview','Обзор'],['characters','Персонажи'],['world','Места и факты'],['relations','Отношения'],['story','Сюжет'],['start','Начало'],['more','Ещё']] as const).map(([id,label])=>({id,label}))}/>

        <div className="workshop-content" key={section}>
          {section === 'overview' && <>
            <p className="workshop-kicker">Твой мир</p><h3>{String(state.campaign.title || draft?.name)}</h3>
            {state.campaign.description && <p className="workshop-literary">{short(state.campaign.description,340)}</p>}
            <div className="workshop-overview-grid"><section><h4>О мире</h4>{named('Жанр',state.campaign.genre)}{named('Тон',state.campaign.tone)}{named('Место',state.campaign.setting)}{named('Время',state.campaign.era)}</section>
              <section><h4>Главный герой</h4><button className="workshop-text-link" onClick={() => {setSelectedCharacter(state.protagonist_id);setSection('characters');}}>{person(state.protagonist_id)} →</button>{named('Возраст',actorCard?.fields['Возраст'])}{named('Роль',actorCard?.fields['Роль'])}{actorCard?.fields['Характер'] && <p>{short(actorCard.fields['Характер'],170)}</p>}</section></div>
            <section className="workshop-overview-section"><h4>Стартовая точка</h4><p>{weekTime()} · {place(beginning?.location || actorState?.location)}</p>{Boolean(beginning?.text) && <p className="workshop-literary">{short(beginning?.text,240)}</p>}<button className="workshop-text-link" onClick={() => setSection('start')}>Начало игры →</button></section>
            <section className="workshop-overview-section"><h4>Ключевые персонажи · {characters.length}</h4><div className="workshop-mini-list">{characters.filter(c=>c.id!==state.protagonist_id).slice(0,7).map(c=><button key={c.id} onClick={() => {setSelectedCharacter(c.id);setSection('characters');}}><strong>{c.name}</strong><span>{short(c.fields['Роль'],95)}</span></button>)}</div><button className="workshop-text-link" onClick={() => setSection('characters')}>Все персонажи →</button></section>
            {relations.some(([,r])=>r.source_id===actor) && <section className="workshop-overview-section"><h4>Связи героя</h4><div className="workshop-mini-list">{relations.filter(([,r])=>r.source_id===actor).slice(0,5).map(([k,r])=><button key={k} onClick={() => setSection('relations')}><strong>{person(r.target_id)}</strong><span>{short(r.context,110)}</span></button>)}</div></section>}
            {facts.length>0 && <section className="workshop-overview-section"><h4>Известные обстоятельства</h4><ul>{facts.slice(0,5).map(([k,f])=><li key={k}>{short(f.text,180)}</li>)}</ul><button className="workshop-text-link" onClick={() => setSection('world')}>Все доступные факты →</button></section>}
            {threads.length>0 && <section className="workshop-overview-section"><h4>Открытые линии</h4><ul>{threads.slice(0,3).map(([k,t])=><li key={k}>{short(t.description,170)}</li>)}</ul><button className="workshop-text-link" onClick={() => setSection('story')}>Сюжет →</button></section>}
          </>}
          {section === 'characters' && <>
            <h3>Персонажи</h3><p className="workshop-hint">Выбери человека, чтобы посмотреть его историю и состояние.</p>
            <div className="workshop-character-list">{characters.map(c => <button key={c.id} className={(selectedCharacter || characters[0]?.id) === c.id ? 'selected' : ''} onClick={() => setSelectedCharacter(c.id)}><span>{c.name}</span>{c.id === state.protagonist_id && <small>ГГ</small>}</button>)}</div>
            {characters.filter(c => c.id === (selectedCharacter && characters.some(x=>x.id===selectedCharacter) ? selectedCharacter : characters[0]?.id)).map(c => <article className="workshop-person" key={c.id}>
              <h4>{c.name}{c.id === state.protagonist_id && <span className="workshop-badge">ГГ</span>}</h4>
              <p className="workshop-person-role">{[c.fields['Возраст'],c.fields['Роль']].filter(Boolean).join(' · ')}</p>
              {author ? entity('character', c.id, c) : <>
                {c.fields['Характер'] && <section className="workshop-person-section"><h5>Характер</h5><p className="workshop-literary">{short(c.fields['Характер'],230)}</p><details><summary>Полное описание</summary><p>{c.fields['Характер']}</p></details></section>}
                {c.fields['Внешность'] && <section className="workshop-person-section"><h5>Внешность</h5><p>{short(c.fields['Внешность'],170)}</p><details><summary>Подробнее</summary><p>{c.fields['Внешность']}</p></details></section>}
                {(['Стиль общения','Привычки','Сильные стороны','Слабости','Страхи и уязвимости'] as const).filter(key => !!c.fields[key]).map(key => <details className="workshop-detail" key={key}><summary>{key}</summary><p>{c.fields[key]}</p></details>)}
                {c.id===actor && actorState && <section className="workshop-person-section"><h5>Сейчас</h5>{named('Место',actorState.location)}{named('Занятие',actorState.situation)}{named('Состояние',actorState.emotion)}{!!motivationText(actorState.goals,true) && <p>Цели: {motivationText(actorState.goals,true)}</p>}{!!motivationText(actorState.intentions,true) && <p>Намерения: {motivationText(actorState.intentions,true)}</p>}</section>}
                {relations.some(([,r])=>r.source_id===c.id) && <section className="workshop-person-section"><h5>Отношения</h5>{relations.filter(([,r])=>r.source_id===c.id).map(([k,r])=><button key={k} className="workshop-text-link" onClick={()=>setSection('relations')}>{person(r.target_id)} · {short(r.context,100)} →</button>)}</section>}
                {c.id===actor && facts.length>0 && <section className="workshop-person-section"><h5>Известные факты</h5><ul>{facts.filter(([,f])=>(f.character_ids as string[] || []).includes(c.id)).slice(0,5).map(([k,f])=><li key={k}>{short(f.text,150)}</li>)}</ul></section>}
                {c.fields['Биография'] && <details className="workshop-detail"><summary>Биография и прошлое</summary><p>{c.fields['Биография']}</p></details>}
                {c.id===actor && c.fields['Статус'] && <details className="workshop-detail"><summary>Подробный статус</summary><p>{c.fields['Статус']}</p></details>}
              </>}
            </article>)}
            {author && <Button variant="outline" disabled={locked} onClick={() => void change({operation:'add',kind:'character'})}>+ Добавить персонажа</Button>}
          </>}
          {section === 'world' && <><h3>Места и факты</h3>
            {author && Object.entries(extensionGroups).filter(([key])=>key!=='objective_relations').map(([key,title])=>extension(key,title))}
            <h4>Места · {state.locations.length}</h4>{state.locations.length ? state.locations.map(loc => <details className="workshop-detail" key={loc.id}><summary><strong>{loc.name}</strong><span>{short(loc.text,130)}</span></summary>{author ? entity('location',loc.id,loc) : <p>{String(loc.text || '')}</p>}</details>) : <p className="workshop-hint">Нет доступной информации.</p>}
            {author && <Button variant="outline" disabled={locked} onClick={() => void change({operation:'add',kind:'location'})}>+ Добавить место</Button>}
            <div className="workshop-subsection"><h4>{author ? 'Факты и тайны' : 'Известные факты'} · {facts.length}</h4>{facts.length ? facts.map(([key,item])=><details className="workshop-detail" key={key}><summary><strong>{short(item.text,140)}</strong>{author && item.secret ? <span>Тайна</span> : null}</summary>{author ? entity('fact',key,item) : <p>{String(item.text || '')}</p>}</details>) : <p className="workshop-hint">Нет доступной информации.</p>}{author && <Button variant="outline" disabled={locked} onClick={() => void change({operation:'add',kind:'fact'})}>+ Добавить факт</Button>}
              {author && <>
              <details className="workshop-detail"><summary>Кто что знает</summary>{Object.entries(state.world.knowledge || {}).map(([key,item])=><details className="workshop-detail" key={key}><summary>{recordTitle('knowledge',item,resolve,author)} · {enumLabels[String(item.status)] || String(item.status)}</summary>{entity('knowledge',key,item)}</details>)}<Button variant="outline" disabled={locked} onClick={() => void change({operation:'add',kind:'knowledge'})}>+ Добавить знание</Button></details>
              </>}
            </div>
          </>}
          {section === 'relations' && <><h3>Отношения · {relations.length}</h3>{author && extension('objective_relations',extensionGroups.objective_relations)}<h4>Направленные чувства</h4>{relations.length ? relations.map(relation) : <p className="workshop-hint">Нет доступной информации.</p>}{author && <Button variant="outline" disabled={locked} onClick={() => void change({operation:'add',kind:'relationship'})}>+ Добавить отношение</Button>}</>}
          {section === 'story' && <><h3>{author ? 'Сюжетные линии' : 'Известные предпосылки'} · {threads.length}</h3>{threads.length ? threads.map(([key,item])=><details className="workshop-detail" key={key}><summary><strong>{short(item.description,150)}</strong><span>{String(item.status || '')}</span></summary><p>{String(item.description || '')}</p>{Boolean(item.state) && <p>{String(item.state)}</p>}{author && entity('thread',key,item)}</details>) : <p className="workshop-hint">Нет доступной информации.</p>}{author && <><Button variant="outline" disabled={locked} onClick={() => void change({operation:'add',kind:'thread'})}>+ Добавить линию</Button><details className="workshop-detail"><summary>Уже произошедшие события</summary>{Object.entries(state.world.events || {}).map(([key,item])=><details className="workshop-detail" key={key}><summary>{String(item.text || key)}</summary>{entity('event',key,item)}</details>)}<Button variant="outline" disabled={locked} onClick={() => void change({operation:'add',kind:'event'})}>+ Добавить событие</Button></details></>}</>}
            {section === 'start' && <><h3>Начало игры</h3>{draft?.presentation?.clock.effective && <section aria-label="Действующий календарь"><h4>Действующий календарь</h4><p>{draft.presentation.clock.effective.weekday_names.join(' · ')}</p><p>{draft.presentation.clock.effective.month_names.map((name,i)=>`${name}: ${draft.presentation!.clock.effective!.month_lengths[i] ?? '28–29 (год неизвестен)'}`).join(' · ')}</p><p>Сезоны: {draft.presentation.clock.effective.seasons.length ? draft.presentation.clock.effective.seasons.map(s=>`${s.name} — ${s.day}.${s.month}`).join(' · ') : 'Не заданы'}. Праздники: {draft.presentation.clock.effective.observances.length ? draft.presentation.clock.effective.observances.map(o=>`${o.name} — ${o.day}.${o.month}`).join(' · ') : 'Не заданы'}.</p></section>}{author && row('clock','clock','calendar',(state.world_clock as unknown as Item).calendar || {})}<div className="workshop-start"><div><span>Когда</span><strong>{weekTime()}</strong></div><div><span>Где</span><strong>{place(beginning?.location || actorState?.location)}</strong></div><div><span>Управление</span><strong>{person(actor)}</strong></div><div><span>Рядом</span><strong>{(beginning?.participants as string[] || []).filter(cid=>cid!==actor).map(person).join(' · ') || 'Пока никто'}</strong></div></div>
              {actorState?.situation && <p className="workshop-literary">{String(actorState.situation)}</p>}{beginning?.text && <section className="workshop-overview-section"><h4>Текущая ситуация</h4><p className="workshop-literary">{String(beginning.text)}</p></section>}
              {author && <>{Object.entries(state.world.scenes || {}).map(([key,item])=><details className="workshop-detail" key={key}><summary>{place(item.location)}</summary>{entity('scene',key,item)}</details>)}<Button variant="outline" disabled={locked} onClick={() => void change({operation:'add',kind:'scene'})}>+ Добавить сцену</Button><details className="workshop-detail"><summary>Изменить стартовых участников и время</summary>{fields.start.map(f=>row('start','',f,f==='scene_id'?state.camera.scene_id:f==='minute'?state.world_clock.minute:state[f as 'protagonist_id'|'controlled_actor_id']))}</details></>}
            </>}
          {section === 'more' && <><h3>Дополнительно</h3><details className="workshop-detail"><summary>Стиль и правила повествования</summary>{author ? fields.campaign.map(f=>row('campaign','',f,state.campaign[f] || '')) : <p>{String(state.campaign.genre || '')} · {String(state.campaign.tone || '')}</p>}</details>
            <details className="workshop-detail"><summary>История версий · {draft?.history.length}</summary>{draft?.history.map((v,i)=><div className="workshop-version" key={v.id}><span>Версия {draft.history.length-i} · {v.reason}</span>{author && <Button disabled={locked||v.id===draft.version_id} variant="outline" onClick={() => void change({operation:'restore',source_id:v.id})}>Восстановить</Button>}</div>)}</details>
            {author && <>{Object.entries(state.world).filter(([key])=>!['version','characters','relationships','facts','knowledge','threads','scenes','events',...Object.keys(extensionGroups)].includes(key)).map(([key,v])=><details className="workshop-detail" key={key}><summary>{runtimeLabels[key] || key} · просмотр</summary><RuntimeValue field={key} value={v} resolve={resolve} author/></details>)}<details className="workshop-detail"><summary>Исходный замысел или импорт</summary><Markdown text={draft?.source_text || 'Исходный текст не сохранён.'}/></details>{draft?.outline && <details className="workshop-detail"><summary>Как сценарист развил идею</summary><Markdown text={draft.outline}/></details>}<div className="workshop-export">{['md','txt','json'].map(format=><Button key={format} variant="outline" onClick={()=>void run(async()=>{const response=await fetch(`/api/workspaces/${id}/draft/export?version_id=${draft?.version_id}&format=${format}`);if(!response.ok)throw new Error('Не удалось экспортировать мир');download(await response.text(),`world.${format}`)})}>{format === 'json' ? 'Экспорт JSON' : `Скачать .${format}`}</Button>)}</div></>}
          </>}
        </div>
        <div className="workshop-finish"><p>{previousWorld ? 'Новая генерация ещё не завершена. Здесь доступен предыдущий мир, а не её результат.' : 'Всё готово? Начни игру в этом мире. Его можно будет редактировать до подтверждения.'}</p><Button disabled={locked || !!draft?.validation.errors.length} onClick={() => setConfirmStart(true)}>{previousWorld ? 'Начать игру в предыдущем мире' : 'Подтвердить мир и начать игру'}</Button></div>
      </section>}
 <Dialog open={authorAsk} onOpenChange={setAuthorAsk}><DialogContent><DialogHeader><DialogTitle>Открыть вид автора?</DialogTitle><DialogDescription>Ты увидишь тайны, неизвестные персонажам факты и скрытые намерения. Это может раскрыть будущие события.</DialogDescription></DialogHeader><Button onClick={() => { setAuthorAsk(false); setAuthorAcknowledged(true); setAuthor(true); }}>Показать всё</Button></DialogContent></Dialog>
 <Dialog open={!!edit} onOpenChange={o => { if (!o)
        setEdit(null); }}><DialogContent><DialogHeader><DialogTitle>{edit?.label}</DialogTitle><DialogDescription>Меняется только выбранное поле. Остальные сущности сохраняются.</DialogDescription></DialogHeader>{edit && edit.field !== '__character' && <>{options(edit.field) ? Array.isArray(value) ? <div className="draft-options">{options(edit.field)!.map(([k, n]) => <label key={k}><input type="checkbox" checked={value.includes(k)} onChange={e => setValue(e.target.checked ? [...value, k] : value.filter(x => x !== k))}/>{n}</label>)}</div> : <select aria-label={edit.label} value={String(value ?? '')} onChange={e => setValue(e.target.value || null)}><option value="">Не указано</option>{options(edit.field)!.map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select> : editTypes.includes('boolean') && nullableEdit ? <select aria-label={edit.label} value={value==null?'unknown':String(value)} onChange={e=>setValue(e.target.value==='unknown'?null:e.target.value==='true')}><option value="unknown">Неизвестно</option><option value="true">Да</option><option value="false">Нет</option></select> : typeof value === 'boolean' ? <label><input type="checkbox" checked={value} onChange={e => setValue(e.target.checked)}/>Да</label> : typeof value === 'number' || editTypes.includes('integer') || editTypes.includes('number') ? <Input type="number" aria-label={edit.label} value={value==null?'':String(value)} onChange={e => setValue(e.target.value==='' && nullableEdit?null:Number(e.target.value))}/> : structuredField(edit.field,value,editSchema) ? <Textarea aria-label={edit.label} value={structuredEdit} onChange={e=>setStructuredEdit(e.target.value)}/> : value && typeof value === 'object' && !Array.isArray(value) ? <div>{['trust', 'affection', 'attraction', 'irritation', 'fear', 'jealousy', 'respect', ...Object.keys(value)].filter((v, i, a) => a.indexOf(v) === i).map(k => <label key={k}>{k}<Input type="number" value={String((value as Item)[k] ?? '')} onChange={e => { const next = { ...value } as Item; if (e.target.value === '')
        delete next[k];
    else
        next[k] = Number(e.target.value); setValue(next); }}/></label>)}</div> : <Textarea aria-label={edit.label} value={Array.isArray(value) ? value.join('\n') : String(value ?? '')} onChange={e => setValue(Array.isArray(value) ? e.target.value.split('\n') : e.target.value)}/>}{nullableEdit && <Button variant="outline" onClick={()=>{setValue(null);setStructuredEdit('null');}}>Оставить неизвестным</Button>}<Button disabled={locked} onClick={() => void run(async () => { await api(`/workspaces/${id}/draft`, { revision: draft?.revision, operation: 'patch', kind: edit.kind, entity_id: edit.id, field: edit.field, value: structuredField(edit.field,value,editSchema) ? JSON.parse(structuredEdit) : value, warnings_ack: ack }, 'PATCH'); setEdit(null); refresh(); })}>Сохранить поле</Button></>}
 {edit?.field === '__character' && <div><p>Связанные записи останутся неизменными; проверь их после изменения биографии:</p>{related.map(d => <p key={d.kind + d.id}>{d.kind} · {d.id}</p>)}</div>}<Textarea aria-label="Указание генератору" placeholder="Как изменить? Например: сделать характер мягче, сохранив биографию." value={instruction} onChange={e => setInstruction(e.target.value)}/><label><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)}/> Изменить всё равно при семантических замечаниях</label><Button variant="outline" disabled={locked} onClick={() => edit && void generate({ task: edit.field === '__character' ? 'character' : 'field', kind: edit.kind, entity_id: edit.id, field: edit.field, text: instruction, warnings_ack: ack })}>Перегенерировать {edit?.field === '__character' ? 'персонажа' : 'поле'}</Button></DialogContent></Dialog>
 <Dialog open={!!removal} onOpenChange={o => { if (!o)
        setRemoval(null); }}><DialogContent><DialogHeader><DialogTitle>Удалить запись?</DialogTitle><DialogDescription>{removal?.deps.length ? 'Сначала измени связанные записи. Автоматически удалять их нельзя.' : 'Будет создана новая версия. Предыдущую можно восстановить из истории.'}</DialogDescription></DialogHeader>{removal?.deps.map(d => <p key={d.kind + d.id}>{d.kind} · {characters.find(c => c.id === d.id)?.name || d.id}</p>)}<Button disabled={locked || !!removal?.deps.length} onClick={() => void run(async () => { await api(`/workspaces/${id}/draft`, { revision: draft?.revision, operation: 'remove', kind: removal?.kind, entity_id: removal?.id }, 'PATCH'); setRemoval(null); refresh(); })}>Удалить</Button></DialogContent></Dialog>
 <Dialog open={confirmStart} onOpenChange={setConfirmStart}><DialogContent><DialogHeader><DialogTitle>Начать эту историю?</DialogTitle><DialogDescription>Будет сохранена текущая версия мира. Повторной генерации или разбора текста не будет.</DialogDescription></DialogHeader>{draft?.validation.warnings.map(x => <p key={x}>{x}</p>)}<Button disabled={locked} onClick={() => void run(async () => { const result = await api<{
        world: number;
        save: number;
    }>(`/workspaces/${id}/draft/confirm`, { revision: draft?.revision, version_id: draft?.version_id }); setConfirmStart(false); onGame(result.world, result.save); })}>Подтвердить и открыть игру</Button></DialogContent></Dialog>
 </main>;
}
