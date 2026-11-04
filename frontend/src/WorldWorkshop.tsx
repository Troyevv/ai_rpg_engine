import {ReadableText} from './workshop/ReadableText';
import {RecordCollection} from './workshop/RecordCollection';
import {WorkshopShell,type WorkshopSection} from './workshop/WorkshopShell';
import {CharacterCollection,CharacterCard,emptyCollection,type CollectionView,type WorkshopCharacter} from './workshop/CharacterCollection';
import {CharacterDossier} from './workshop/CharacterDossier';
import {StructuredValueEditor} from './workshop/StructuredValueEditor';
import {Home,Users,MapPin,Link,BookOpen,ShieldCheck,ArrowRight,Search,Plus,Clock} from 'lucide-react';
import './styles/world-workshop.css';
import {WorldAIEditor} from './WorldAIEditor';
import {CommunicationEditor,CommunicationSettings,type CommunicationProfile} from './CommunicationSettings';
import {CalendarProfileEditor} from './CalendarProfileEditor';
import {RuntimeValue, resolver, recordTitle, runtimeLabels, enumLabels, characterRefs} from './runtimePresentation';
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
    author?:boolean;
    portraits?:Record<string,Partial<WorkshopCharacter>>;
    editor?:{fields:Record<string,string[]>;definitions?:Record<string,Item>;enums:Record<string,Record<string,string[]>>;schemas:Record<string,Record<string,Item>>} | null;
    creation_settings?: Partial<Creation>;
    presentation?: {clock:{label:string;effective?:{month_names:string[];weekday_names:string[];month_lengths:(number|null)[];year:number|null;regional?:{country:string;subdivision:string|null}|null;seasons:{name:string;month:number;day:number}[];observances:{name:string;month:number;day:number}[]}};notices?:string[]} | null;
    id: string;
    name: string;
    revision: number;
    version_id: number | null;
    candidate?: Record<string,unknown> | null;
    relation_merges?: {ids:string[];paths:string[];differences:string[];safe:boolean;records:Item[]}[];
    review?: {status:string;reason?:string;issues?:{message:string;severity:string;path?:string|null;patch_paths?:string[];related_paths?:string[];protocol_warnings?:unknown[]}[]} | null;
    pending_editor?: boolean;
    creative_status?: 'running' | 'applied' | 'rejected' | 'cancelled' | 'interrupted' | null;
    quality_status?: 'running' | 'accepted' | 'partial' | 'rejected' | 'cancelled' | null;
    start_block_reason?: string | null;
    start_warning?: string | null;
    technical_valid?: boolean;
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
const labels: Record<string, string> = { public_description: 'Аннотация для игрока', title: 'Название', setting: 'Обстановка', era: 'Эпоха', genre: 'Жанр', tone: 'Тон', description: 'Описание', rules: 'Правила повествования', name: 'Имя / название', aliases: 'Другие имена', location: 'Местоположение', situation: 'Сейчас', goals: 'Цели', intentions: 'Намерения', emotion: 'Эмоциональное состояние', obligations: 'Обязательства', source_id: 'От кого', target_id: 'К кому', context: 'Динамика отношений', dimensions: 'Показатели отношений', visible_to_ids: 'Кому известна информация', text: 'Описание', secret: 'Приватный факт', story_secret: 'Сюжетная тайна', secret_subject_ids: 'О ком тайна', secret_existence: 'Показывать существование', owner_id: 'Чья тайна', character_ids: 'Связанные персонажи', evidence: 'Основания', actor_id: 'Кто знает', fact_id: 'Факт', status: 'Статус', source_event_id: 'Источник знания', state: 'Текущее развитие', public_state: 'Известное герою состояние', relevance: 'Значимость', participants: 'Участники', start_minute: 'Начало · минуты недели', end_minute: 'Конец · минуты недели', protagonist_id: 'Основной герой', controlled_actor_id: 'Управляемый персонаж', scene_id: 'Стартовая сцена', minute: 'Игровое время · минуты недели', witnesses: 'Свидетели', fact_ids: 'Факты', player_observed: 'Известно игроку' };
Object.assign(labels,{parent_id:'Родительская локация',location_id:'Локация',organization_id:'Организация',kind:'Тип',since:'Начало периода',until:'Конец периода',physical_state:'Физическое состояние',life_status:'Жизненный статус',birth_date:'Дата рождения',calendar:'Календарь',appearance:'Внешность',personality:'Характер',values:'Ценности',capabilities:'Возможности',developmental_stage:'Этап жизни',claim:'Структурированный факт',holder_id:'У кого находится'});
Object.assign(labels,runtimeLabels);
const fields: Record<string, string[]> = { campaign: ['title', 'setting', 'era', 'genre', 'tone', 'description', 'rules'], actor: ['location', 'situation', 'goals', 'intentions', 'emotion', 'obligations'], relationship: ['source_id', 'target_id', 'context', 'dimensions', 'visible_to_ids'], location: ['name', 'text'], fact: ['text', 'secret', 'story_secret', 'secret_subject_ids', 'secret_existence', 'character_ids', 'evidence'], knowledge: ['actor_id', 'fact_id', 'status', 'source_event_id'], thread: ['description', 'state', 'public_state', 'status', 'character_ids', 'relevance', 'visible_to_ids'], scene: ['location', 'participants', 'text', 'start_minute', 'end_minute', 'status'], event: ['text', 'participants', 'witnesses', 'minute', 'fact_ids', 'player_observed'], start: ['protagonist_id', 'controlled_actor_id', 'scene_id', 'minute'] };
const extensionGroups: Record<string,string> = {objective_relations:'Родство и социальные связи',organizations:'Организации',residences:'Проживание',roles:'Профессии и роли',possessions:'Значимое имущество',conditions:'Обстоятельства',pregnancies:'Беременности',contacts:'Контакты',reproductive_events:'Репродуктивные события',naming_decisions:'Выбор имён',scheduled_events:'Будущие события и договорённости'};
const groups = [['Персонажи', 'character', 'characters'], ['Отношения', 'relationship', 'relationships'], ['Места', 'location', 'locations'], ['Факты и тайны', 'fact', 'facts'], ['Знания персонажей', 'knowledge', 'knowledge'], ['Сюжетные линии', 'thread', 'threads'], ['Сцены', 'scene', 'scenes'], ['События', 'event', 'events']];
const short = (value: unknown, max = 180) => { const s = String(value || '').replace(/\s+/g, ' ').trim(); return s.length > max ? s.slice(0, max).trimEnd() + '…' : s; };
const dimensions: Record<string,string> = {trust:'Доверие',affection:'Привязанность',attraction:'Влечение',irritation:'Раздражение',fear:'Страх',jealousy:'Ревность',respect:'Уважение'};
const strength = (n: number) => Math.abs(n) < 25 ? 'слабое' : Math.abs(n) < 60 ? 'заметное' : 'сильное';
type WorkshopView={section:WorkshopSection;collection:CollectionView;selected:string;subsection:Record<string,string>};
function storedView(wid:string):Partial<WorkshopView>{try{return JSON.parse(sessionStorage.getItem('workshop-view:'+wid)||'{}')}catch{return {}}}
export function WorldWorkshop({ prefs, apiKey, onWorld, onGame, onBack, onSettings }: {
    onBack?:()=>void;
    onSettings?:()=>void;
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
    const initialView=useRef(storedView(localStorage.getItem('draftWorkspace')||'')).current;
    const [section, setSection] = useState<WorkshopSection>(initialView.section||'overview');
    const [collection,setCollection]=useState<CollectionView>(initialView.collection||emptyCollection);
    const [subsection,setSubsection]=useState<Record<string,string>>(initialView.subsection||{});
    const [draftsOpen,setDraftsOpen]=useState(false);
    const [dossierOpen,setDossierOpen]=useState(false);
    const [searchOpen,setSearchOpen]=useState(false);
    const [search,setSearch]=useState('');
    const [recordTarget,setRecordTarget]=useState<{kind:string;id:string}|null>(null);
    const [editError,setEditError]=useState('');
    const [editRevision,setEditRevision]=useState(0);
    const dossierTrigger=useRef<HTMLElement|null>(null);
    const openPerson=(cid:string)=>{dossierTrigger.current=document.activeElement as HTMLElement;setSelectedCharacter(cid);setDossierOpen(true)};
    const viewBuffers=useRef(new Map<string,{section:WorkshopSection;collection:CollectionView;selected:string;subsection:Record<string,string>}>());
    const [selectedCharacter, setSelectedCharacter] = useState(initialView.selected||'');
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
    const [text, setText] = useState(()=>sessionStorage.getItem('workshop-idea:'+ (localStorage.getItem('draftWorkspace')||''))||'');
    const [importFormat, setImportFormat] = useState<'text'|'json'>('text');
    const [importFile, setImportFile] = useState('');
    const detectedImport = useMemo(() => detectWorldImport(text, importFile ? importFormat : undefined), [text, importFile, importFormat]);
    const [name, setName] = useState('Новая история');
    const [useIdea, setUseIdea] = useState(false);
    const [busy, setBusy] = useState(false);
    const [resuming, setResuming] = useState(false);
    const resumeGuard = useRef(false);
    const [emptyRetry, setEmptyRetry] = useState<{token:string;epoch:number}|null>(null);
    const [edit, setEdit] = useState<Target | null>(null);
    const fieldTrigger=useRef<HTMLElement|null>(null);
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
        viewBuffers.current.set(id,{section,collection,selected:selectedCharacter,subsection});
        sessionStorage.setItem('workshop-idea:'+id,text);
        const view=viewBuffers.current.get(wid)||storedView(wid);
        setSection(view?.section||'overview');setCollection(view?.collection||emptyCollection);setSubsection(view?.subsection||{});setSelectedCharacter(view?.selected||'');setDossierOpen(false);
        setText(sessionStorage.getItem('workshop-idea:'+wid)||'');
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
        world: ['Создание мира…', 'Модель создаёт исходный кандидат по вашей идее.'],
        retrying: ['Исправляем найденные ошибки…', 'Модель предлагает локальные изменения; остальные данные сохраняются.'],
        developing: ['Творческое развитие мира…', 'Модель раскрывает неописанные стороны идеи и связывает новые детали с миром. Кандидат сохранён.'],
        improving: ['Дополняем карточки…', 'Заполняем разрешённые незаданные детали; сохраняем авторские ограничения.'],
        validating: ['Проверяем структуру мира…', 'Локальная проверка типов и ссылок.'],
        reviewing: ['Проверяем смысловую согласованность…', 'Модель проверяет сохранённый мир.'],
        review_format_repair: ['Исправляем отчёт проверки…', 'Мир сохранён. Исправляется формат ответа проверяющего.'],
        saving: ['Сохраняем версию…', 'Проверенный мир записывается в SQLite.'],
        proposing: ['Готовим предложение изменений…', 'Текущий мир сохранён. После проверки будет доступен предпросмотр.'],
        preview: ['Предложение готово', 'Откройте AI-редактор в виде автора.'],
        editing: ['Обновляем выбранное поле…', 'Модель подготавливает новую версию поля.'],
    };
    const status = phaseStatus[job?.phase || ''] || ['Ожидаем запуска генерации…', 'Задание создано и ожидает запуска модели.'];
    const operationGuard=useRef(false);
    const run = async (fn: () => Promise<void>) => { if(operationGuard.current)return;operationGuard.current=true;setBusy(true); try {
        await fn();
    }
    catch (e) {
        toast.error((e as Error).message);
    }
    finally {
        operationGuard.current=false;setBusy(false);
    } };
    const resume = async (options: Item = {}) => {
        if (resumeGuard.current || active(job)) return;
        resumeGuard.current = true; setResuming(true);
        await run(async () => {
            const next = await api<Job>(`/workspaces/${id}/draft/resume`, {api_key:apiKey, revision:draft?.revision,
                max_tokens:prefs.summary.max_tokens, context_length:prefs.summary.context_length, ...options});
            dispatchWorkspace({type:'update', id, update:current=>current ? {...current, job:next} : current});
            await refresh();
        });
        resumeGuard.current = false; setResuming(false);
    };
    const change = (body: Item) => run(async () => { await api(`/workspaces/${id}/draft`, { revision: draft?.revision, ...body }, 'PATCH'); refresh(); });
    const generate = (body: Item) => run(async () => { const j = await api<Job>(`/workspaces/${id}/draft/generate`, { revision: draft?.revision, config: prefs.summary, api_key: apiKey, ...body }); dispatchWorkspace({type:'update',id,update:d => d ? {...d,job:j} : d}); setEdit(null); });
    const editBufferKey=(target:Target)=>`workshop-field:${id}:${target.kind}:${target.id}:${target.field}`;
    const openEdit = (target: Target) => {
        let saved:{value:unknown;structured:string;revision:number}|null=null;
        try{saved=JSON.parse(sessionStorage.getItem(editBufferKey(target))||'null')}catch{/* isolated invalid UI buffer */}
        fieldTrigger.current=document.activeElement instanceof HTMLElement?document.activeElement:null;
        setEdit(target);setValue(saved?saved.value:target.value);setStructuredEdit(saved?saved.structured:JSON.stringify(target.value??null,null,2));setEditRevision(saved?.revision??draft?.revision??0);setEditError(saved&&saved.revision!==draft?.revision?'Мир изменился с момента ввода. Проверьте значение и явно разрешите сохранение в текущую версию.':'');setInstruction('');setAck(false);setRelated([]);if(target.field==='__character')void api<{kind:string;id:string}[]>(`/workspaces/${id}/draft/dependencies?kind=character&entity_id=${target.id}`).then(setRelated).catch(e=>toast.error(e.message));
    };
    useEffect(()=>{sessionStorage.setItem('workshop-idea:'+id,text)},[id,text]);
    useEffect(()=>{sessionStorage.setItem('workshop-view:'+id,JSON.stringify({section,collection,selected:selectedCharacter,subsection}))},[id,section,collection,selectedCharacter,subsection]);
    useEffect(()=>{if(edit&&edit.field!=='__character')sessionStorage.setItem(editBufferKey(edit),JSON.stringify({value,structured:structuredEdit,revision:editRevision}))},[edit,value,structuredEdit,editRevision]);
    const state = !!draft?.author===author ? draft?.state : null;
    const editSchema=edit ? draft?.editor?.schemas?.[edit.kind]?.[edit.field] : undefined;
    const editTypes=[editSchema,...(editSchema?.anyOf as Item[] || [])].filter(Boolean).map(s=>s?.type);
    const nullableEdit=editTypes.includes('null');
    const previousWorld = !!state && !!(job as Job & {transport_incomplete?:boolean})?.transport_incomplete;
    const characters = (state?.characters || []).map(c=>({...c,...draft?.portraits?.[c.id]}));
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
        if (characterRefs.has(field)||field==='secret_subject_ids')
            return characters.map(c => [c.id, c.name]);
        const group = field === 'scene_id' ? 'scenes' : field === 'fact_id' || field === 'fact_ids' ? 'facts' : field === 'source_event_id' ? 'events' : null;
        if (group)
            return Object.entries(state?.world[group] || {}).map(([k, v]) => [k, String(v.text || v.location || k)]);
        if (['location','location_id','location_ids'].includes(field)||field==='parent_id'&&edit?.kind!=='organizations') return (state?.locations || []).map(p=>[p.id,p.name]);
        if (field === 'organization_id'||field==='parent_id'&&edit?.kind==='organizations') return Object.entries(state?.world.organizations || {}).map(([id,v])=>[id,String(v.name || id)]);
        const linked=field==='pregnancy_id'?'pregnancies':field==='condition_id'?'conditions':field==='depends_on'?'scheduled_events':field==='replaced_by'||field==='life_fact_id'||field==='parentage_complete_fact_id'?'facts':field==='contact_id'?'contacts':null;
        if(linked)return Object.entries(state?.world[linked]||{}).map(([key,item])=>[key,recordTitle(linked,item,resolve,author)]);
        if (field === 'secret_existence') return [['hidden','Скрыть существование'],['discoverable','Показывать безымянный слот']];
        if (field === 'status')
            return (edit?.kind === 'knowledge' ? ['known', 'suspected', 'unknown', 'outdated', 'refuted', 'superseded'] : edit?.kind === 'thread' ? ['active', 'developing', 'dormant', 'resolved'] : ['active', 'closed']).map(x => [x, enumLabels[x] || x]);
        return null;
    };
    const row = (kind: string, eid: string, field: string, v: unknown, editable=true) => <div className="draft-field" key={field}><div className="draft-field-heading"><span>{labels[field] || field.replace('fields.', '')}</span>{author && editable && (field.startsWith('fields.') || draft?.editor?.fields[kind]?.includes(field)) && <Button variant="ghost" size="sm" disabled={locked} aria-label={`Изменить ${labels[field] || field}`} onClick={() => {setStructuredEdit(JSON.stringify(v,null,2));openEdit({ kind, id: eid, field, value: v, label: labels[field] || field.replace('fields.', '') });}}>Изменить</Button>}</div>{v && typeof v==='object' && field!=='capabilities' ? <details><summary>{field==='calendar' ? enumLabels[String(((v as Item).profile as Item)?.system || 'gregorian')] : `Сведения · ${Array.isArray(v)?v.length:Object.keys(v).length}`}</summary><RuntimeValue field={field} value={v} resolve={resolve} author={author}/></details> : <RuntimeValue field={field} value={v} resolve={resolve} author={author}/>}</div>;
    const extension = (key:string,title:string,filter?:(item:Item)=>boolean) => <RecordCollection key={id+key+author} entries={Object.entries(state?.world[key]||{}).filter(([,item])=>!filter||filter(item))} initialSelected={recordTarget?.kind===key?recordTarget.id:undefined} groupBy={key==='residences'?item=>resolve(residenceGrouping==='actor'?'actor_id':'location_id',item[residenceGrouping==='actor'?'actor_id':'location_id'])||'Не указано':undefined} tools={key==='residences'?<label>Группировать по <select aria-label="Группировка проживания" value={residenceGrouping} onChange={e=>setResidenceGrouping(e.target.value)}><option value="actor">персонажам</option><option value="location">местам</option></select></label>:undefined} title={title} kind={key} storageKey={`workshop:${id}:${key}:${author}`} disabled={locked} describe={item=>recordTitle(key,item,resolve,author)} render={(eid,item)=><>{Object.entries(item).filter(([field])=>!['id','revision','source_turn','turn_id','provenance','applied'].includes(field)).map(([field,v])=>row(key,eid,field,v))}<details><summary>Технические сведения</summary><pre>{JSON.stringify(item,null,2)}</pre></details></>}/>;
    const entity = (kind: string, eid: string, item: Item) => <div className="draft-entity" key={eid}>
 {kind === 'character' ? <>{row(kind, eid, 'name', item.name)}{Array.isArray(item.aliases) && item.aliases.length > 0 ? row(kind, eid, 'aliases', item.aliases) : null}{Object.entries(item.fields as Record<string, string>).filter(([k]) => !['Сейчас', 'Чего хочет', 'Намерения'].includes(k)).map(([k, v]) => row(kind, eid, 'fields.' + k, v))}<details><summary>Состояние, цели и намерения</summary>{[...fields.actor,...Object.keys(state?.world.characters[eid] || {}).filter(f=>!fields.actor.includes(f) && !!draft?.editor?.fields.actor?.includes(f))].map(f => row('actor', eid, f, state?.world.characters[eid]?.[f] ?? null))}<details><summary>Технические сведения состояния</summary><pre>{JSON.stringify(state?.world.characters[eid],null,2)}</pre></details></details></> : [...fields[kind],...Object.keys(item).filter(f=>!fields[kind].includes(f) && !['id','revision','source_turn','time_semantics'].includes(f))].map(f => row(kind, eid, f, (f in item ? item[f] : (['secret','story_secret'].includes(f) ? false : f==='secret_existence' ? 'hidden' : ['secret_subject_ids','character_ids', 'visible_to_ids', 'participants', 'witnesses', 'fact_ids', 'evidence'].includes(f) ? [] : ''))))}
 {author && <div className="actions">{kind === 'character' && <Button variant="outline" disabled={locked} onClick={() => { setEdit({ kind, id: eid, field: '__character', value: '', label: 'Перегенерировать персонажа целиком' }); setInstruction(''); setAck(false); setRelated([]); void api<{
        kind: string;
        id: string;
    }[]>(`/workspaces/${id}/draft/dependencies?kind=character&entity_id=${eid}`).then(setRelated).catch(e => toast.error(e.message)); }}>Новая версия персонажа</Button>}<Button variant="ghost" disabled={locked} onClick={() => void run(async () => { const deps = await api<{
        kind: string;
        id: string;
    }[]>(`/workspaces/${id}/draft/dependencies?kind=${kind}&entity_id=${eid}`); setRemoval({ kind, id: eid, deps }); })}>Удалить</Button></div>}
 </div>;
    const collectionRecords=(kind:string,title:string,entries:[string,Item][],describe:(item:Item)=>string)=> <RecordCollection initialSelected={recordTarget?.kind===kind?recordTarget.id:undefined} key={id+kind+author} {...{entries,title,kind,describe}} disabled={locked} storageKey={`workshop:${id}:${kind}:${author}`} onAdd={author?()=>void change({operation:'add',kind}):undefined} render={(eid,item)=>author?entity(kind,eid,item):<div className="workshop-literary">{String(item.text||item.description||item.context||'')}</div>}/>;
    if (mode === 'scenario')
        return <><Button className="workshop-back" variant="ghost" onClick={() => setMode('quick')}>← Генератор мира</Button><Preparation worldSettings={<WorldCreationSettings value={creation} onChange={setCreation} disabled={locked}/>} prefs={prefs} apiKey={apiKey} onWorld={onWorld} onDraft={wid => { selectWorkspace(wid); setUseIdea(true); setMode('quick'); }}/></>;
    const selectedCard=characters.find(c=>c.id===selectedCharacter) as WorkshopCharacter|undefined;
    const navigate=(next:WorkshopSection)=>{setRecordTarget(null);setSection(next);if(next==='idea')setEditingIdea(true)};
    const pageHeader=(title:string,description:string)=><header className="ww-page-head"><div><p className="ww-eyebrow">Мастерская миров</p><h1>{title}</h1><p>{description}</p></div></header>;
    const tab=(key:string,items:[string,string][])=>{const value=subsection[key]||items[0][0];return <SectionTabs label={key} value={value} onChange={value=>setSubsection({...subsection,[key]:value})} items={items.map(([id,label])=>({id,label}))}/>};
    const currentSub=(key:string,fallback:string)=>subsection[key]||fallback;
    const reviewLink=(path:string)=>{
        const parts=path.split('/').slice(1).map(v=>v.replace(/~1/g,'/').replace(/~0/g,'~'));
        const root=parts[0];const group=root==='world'?parts[1]:root;
        const eid=root==='world'?parts[2]:group==='characters'?state?.characters[Number(parts[1])]?.id:group==='locations'?state?.locations[Number(parts[1])]?.id:undefined;
        const field=root==='world'?parts[3]:parts[2];
        if(group==='characters'&&eid&&characters.some(c=>c.id===eid))return {label:person(eid)+(field?' · '+(labels[field]||field):''),open:()=>openPerson(eid)};
        const routes:Record<string,[WorkshopSection,string,string,string]>={locations:['world','Места','locations','location'],organizations:['world','Места','organizations','organizations'],residences:['world','Места','residences','residences'],roles:['world','Места','roles','roles'],conditions:['world','Места','conditions','conditions'],possessions:['world','Места','possessions','possessions'],contacts:['world','Места','contacts','contacts'],relationships:['relations','Связи','feelings','relationship'],objective_relations:['relations','Связи','objective_relations','objective_relations'],pregnancies:['relations','Связи','pregnancies','pregnancies'],facts:['knowledge','Знания','facts','fact'],knowledge:['knowledge','Знания','knowledge','knowledge'],threads:['story','','','thread'],events:['timeline','Хронология','events','event'],scheduled_events:['timeline','Хронология','scheduled_events','scheduled_events'],reproductive_events:['timeline','Хронология','reproductive_events','reproductive_events'],naming_decisions:['timeline','Хронология','naming_decisions','naming_decisions']};
        const route=routes[group];
        const item=group==='locations'?state?.locations.find(l=>l.id===eid):eid?state?.world[group]?.[eid]:null;
        if(route&&item&&eid)return {label:short(group==='locations'?String(item.name):recordTitle(group,item,resolve,author),100)+(field?' · '+(labels[field]||field):''),open:()=>{setSection(route[0]);if(route[1])setSubsection({...subsection,[route[1]]:route[2]});setRecordTarget({kind:route[3],id:eid})}};
        if(['campaign','world_clock','camera','protagonist_id','controlled_actor_id'].includes(root)||group==='scenes')return {label:'Сцена и правила',open:()=>navigate('start')};
        return null;
    };
    const reviewLinks=(paths:(string|null|undefined)[])=><div className="ww-review-links">{[...new Set(paths.filter((v):v is string=>!!v))].map(path=>{const link=reviewLink(path);return link?<button key={path} onClick={link.open}>{link.label} →</button>:null})}</div>;
    const allIssues=[...new Set([...(draft?.validation.errors||[]),...(draft?.validation.warnings||[]),...(draft?.import_warnings||[]),...(draft?.review?.issues||[]).map(issue=>issue.message)])];
    const viewChanging=!!draft?.state&&!!draft.author!==author;
    const showIdea=(!state&&!viewChanging)||section==='idea';
    const workspaceTitle=String(state?.campaign.title||draft?.name||'Новая история');
    return <main className="world-workshop" aria-busy={loading} data-workspace-id={id} data-draft-workspace-id={draft?.id || ''}>
    <WorkshopShell workspaceId={id} section={showIdea?'idea':section} onSection={navigate} title={workspaceTitle} revision={draft?.revision} loading={loading} busy={busy} author={author} onAuthor={()=>author?setAuthor(false):authorAcknowledged?setAuthor(true):setAuthorAsk(true)} onStart={()=>setConfirmStart(true)} startLabel={active(job)?'Остановить проверку и начать':draft?.start_warning?'Начать с предупреждениями':previousWorld?'Начать игру в предыдущем мире':'Подтвердить мир и начать игру'} canStart={!!state&&!busy&&!loading&&!!draft?.technical_valid} counts={{characters:characters.length,world:state?.locations.length,relations:relations.length,story:threads.length,knowledge:facts.length,review:allIssues.length}} onDrafts={()=>setDraftsOpen(true)} onBack={onBack} onSettings={onSettings} onSearch={()=>setSearchOpen(true)}>
    {previousWorld&&<section className="ww-panel" role="status"><h2>Ранее сохранённый мир</h2><p>Новая генерация не завершена. Сейчас показана предыдущая сохранённая версия; она не заменена неполным ответом.</p><button className="ww-text-button" onClick={()=>navigate('review')}>Продолжить генерацию →</button></section>}
    {!previousWorld&&job?.status==='error'&&section!=='review'&&section!=='idea'&&section!=='ai'&&<section className="ww-panel" role="status"><h2>Задание требует внимания</h2><p>Полученный результат сохранён. Откройте проверку, чтобы увидеть причину и доступные способы продолжения.</p><button className="ww-text-button" onClick={()=>navigate('review')}>Открыть проверку →</button></section>}
    {viewChanging&&<p role="status">Загружаем выбранный вид мира…</p>}
    {showIdea&&<>{pageHeader('Придумай свою историю','Свободный замысел станет миром, который можно прочитать, изменить и проверить перед началом игры.')}
      <nav className="workshop-paths" aria-label="Способ создания">
        <button className={mode === 'quick' ? 'selected' : ''} onClick={() => setMode('quick')}>По моей идее</button>
        <button onClick={() => setMode('scenario')}>Со Сценаристом</button>
        <button className={mode === 'import' ? 'selected' : ''} onClick={() => setMode('import')}>Импортировать</button>
      </nav>
      </>}
      <Dialog open={draftsOpen} onOpenChange={setDraftsOpen}><DialogContent><DialogHeader><DialogTitle>Мои черновики</DialogTitle><DialogDescription>Выберите мир, создайте новый или восстановите удалённый.</DialogDescription></DialogHeader>
      <details className="workshop-continue" open><summary>Мои черновики {draft ? `· ${draft.name}` : ''}</summary>
        <div className="workshop-draft-list">
          <button disabled={locked} className={!id ? 'selected' : ''} onClick={() => { selectWorkspace(''); setAuthor(false); setUseIdea(false); setDraftsOpen(false); }}>+ Новая история</button>
          {list.map(w => <div className="workshop-draft-row" data-workspace-id={w.id} key={w.id}>
            <button disabled={locked} className={id === w.id ? 'selected' : ''} onClick={() => { selectWorkspace(w.id); setAuthor(false); setUseIdea(false); setDraftsOpen(false); }}>{w.name}</button>
            <Button variant="ghost" size="sm" aria-label={`Удалить черновик «${w.name}»`} disabled={locked} onClick={() => setDeleteDraft(w)}><Trash2 size={16}/></Button>
          </div>)}
        </div>
        <details className="workshop-trash" onToggle={e => { if (e.currentTarget.open) void api<WorkspacePick[]>('/workspaces?deleted=true').then(setRemoved).catch(err => toast.error(err.message)); }}><summary>Удалённые черновики</summary>
          {removed.length === 0 ? <p>Корзина пуста.</p> : removed.map(w => <div className="workshop-draft-row" data-workspace-id={w.id} key={w.id}><span>{w.name}</span><Button variant="ghost" size="sm" disabled={locked} onClick={() => void run(async () => { await api(`/workspaces/${w.id}/restore`,{revision:w.revision}); setList(await api<WorkspacePick[]>('/workspaces')); setRemoved(await api<WorkspacePick[]>('/workspaces?deleted=true')); selectWorkspace(w.id); toast.success('Черновик восстановлен'); })}>Восстановить</Button></div>)}
        </details>
      </details>
      </DialogContent></Dialog>
      {(showIdea||section==='review'||section==='ai'&&job?.kind==='draft_editor')&&<>
      {job?.status==='error' && (job as Job & {transport_incomplete?:boolean}).transport_incomplete && <section role="status"><h3>Восстановление ответа</h3><p>Полученный ответ сохранён. Продолжение проверит сборку, запросит недостающий конец при необходимости и завершит проверку мира. Полный проверенный мир ещё не готов.</p></section>}
      {((job?.resumable && !(job as Job & {fragment_recovery?:boolean;transport_blocked?:boolean}).fragment_recovery && !(job as Job & {transport_blocked?:boolean}).transport_blocked) || (draft?.review?.status==='stale' && job?.status==='saved' && job.kind!=='draft_editor')) && <Button disabled={locked} onClick={()=>void resume({})}>{job?.kind==='draft_editor' ? 'Продолжить AI-редактирование' : draft?.creative_status && draft.creative_status !== 'applied' ? 'Продолжить творческое развитие' : draft?.review && !(job as Job & {transport_incomplete?:boolean})?.transport_incomplete ? 'Повторить проверку' : 'Продолжить сохранённую генерацию'}</Button>}
      {draft?.creative_status && ['rejected','cancelled','interrupted'].includes(draft.creative_status) && !active(job) && <p role="status">Творческое развитие не завершено. Последний кандидат сохранён; его можно открыть в редакторе.</p>}
      {job?.response_diagnostic?.code === 'provider_http_rejection' && !active(job) && <p className="workshop-hint">HTTP-отказ не применён к миру. Перед продолжением проверь причину: для ошибки параметров нужно исправить настройки или сборку запроса. Неизменённый запрос с известной причиной HTTP 400 повторно не отправляется.</p>}
      {job?.empty_retry_token && <Button disabled={locked} onClick={()=>setEmptyRetry({token:job.empty_retry_token!,epoch:job.attempt_epoch || 0})}>Повторить после сбоя провайдера</Button>}
      <Dialog open={!!emptyRetry} onOpenChange={open=>{if(!open)setEmptyRetry(null)}}><DialogContent><DialogHeader><DialogTitle>Повторная проверка после сбоя</DialogTitle><DialogDescription>Провайдер завершил запрос без текста. Если временный сбой устранён, можно подтвердить одну новую проверку сохранённого мира. Это новый запрос, который может быть оплачен. Предыдущие ответы и расходы сохранятся, общий бюджет не сбрасывается. Каждому повтору нужно новое подтверждение; автоматических повторов не будет.</DialogDescription></DialogHeader><div className="workshop-dialog-actions"><Button variant="ghost" onClick={()=>setEmptyRetry(null)}>Отмена</Button><Button disabled={locked} onClick={()=>{if(!emptyRetry)return;const retry=emptyRetry;setEmptyRetry(null);void resume({retry_empty_response:retry.token,expected_epoch:retry.epoch})}}>Подтвердить одну повторную проверку</Button></div></DialogContent></Dialog>
      {job?.resumable && <p className="workshop-hint">Модель и Thinking генерации закреплены за заданием. Смысловая проверка выполняется с Thinking Off; из текущих настроек применяются контекст и потолок ответа. Общий бюджет не сбрасывается.</p>}
      {(job as Job & {transport_blocked?:boolean})?.transport_blocked && <p role="alert">Сборка остановлена: повреждены исходные данные или нет безопасной границы для повтора. Скачайте диагностику; автоматическая замена сохранённых частей запрещена.</p>}
      {(job as Job & {fragment_recovery?:boolean})?.fragment_recovery && <details><summary>Повторить проблемное продолжение</summary><p>Предыдущие части останутся неизменными. Отклонённая часть сохранится в диагностике; новый запрос может быть оплачен.</p><Button disabled={locked} onClick={()=>void resume({retry_last_fragment:true})}>Запросить только последнее продолжение</Button></details>}
      {(job?.status === 'error' || job?.status === 'stopped') && <div>{author && <Button variant="outline" onClick={()=>void run(async()=>{download(JSON.stringify(await api(`/workspaces/${id}/draft/raw`),null,2),'generation-response.json');})}>Скачать исходный ответ и диагностику</Button>}
      {(job as Job & {unknown_outcome?:boolean}).unknown_outcome && <details><summary>Восстановить запрос с неизвестным исходом</summary><p>Провайдер мог списать оплату. Повтор может быть оплачен ещё раз; полученный текст останется в истории.</p><Button disabled={locked} onClick={()=>void resume({acknowledge_unknown:true})}>Повторить с возможной повторной оплатой</Button></details>}</div>}
      {!resuming && !active(job) && draft?.review && ['failed','running','not_started','stale'].includes(draft.review.status) && <section className="workshop-review" role="status"><h3>Смысловая проверка не завершена</h3><p>Мир сохранён. Автоматическая проверка не завершилась. Это не установленная ошибка поля мира.</p><p>{draft.review.reason || 'При технической готовности можно начать с предупреждениями без повторной проверки.'}</p></section>}
      {author && draft?.review?.issues && draft.review.issues.length>0 && <details className="workshop-detail"><summary>Замечания смысловой проверки · {draft.review.issues.length}</summary>{draft.review.issues.map((issue,i)=><div key={i}><p>{issue.severity==='blocker'?'Противоречие':'Рекомендация'}: {issue.message}</p>{reviewLinks([issue.path,...issue.patch_paths||[],...issue.related_paths||[]])}{issue.protocol_warnings && <details><summary>Диагностика ссылок отчёта</summary><pre>{JSON.stringify(issue.protocol_warnings,null,2)}</pre></details>}</div>)}</details>}
      {draft?.start_warning && <p role="status">{draft.start_warning} Можно начать с предупреждениями.</p>}
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
      </>}
      {showIdea && <section className="workshop-inspiration">
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
            setEditingIdea(false);setSection('overview');
            if (mode === 'import' && detectedImport.format === 'json') {setText(''); setImportFormat('text'); setImportFile('');}
          })}>{mode === 'import' ? 'Открыть в редакторе' : state ? 'Создать новую версию мира' : 'Развить идею и создать мир'}</Button>
          {state && <Button variant="ghost" onClick={() => {setEditingIdea(false);setSection('overview')}}>Вернуться к миру</Button>}
        </div>
      </section>}
      {(resuming || active(job)) && <section className="workshop-generating" role="status" aria-live="polite" aria-label="Ход проверки мира">
        <span className="workshop-pulse"/><div><strong>{resuming ? 'Запускаем повторную проверку…' : reconnecting ? 'Восстанавливаем соединение…' : status[0]}</strong><p>{resuming ? 'Отправляем запрос на продолжение сохранённого задания.' : reconnecting ? 'Ожидаем связь с сервером. Генерация продолжает выполняться.' : status[1]}</p>{!reconnecting && !!job?.progress_chars && !['validating','saving'].includes(job.phase || '') && <small>Получено {job.progress_chars.toLocaleString('ru-RU')} символов ответа</small>}</div>
        <Button variant="ghost" disabled={resuming || busy} onClick={() => void run(async () => {await api(`/jobs/${job!.id}/stop`, {}); refresh();})}>Остановить</Button>
      </section>}
      <Dialog open={!!deleteDraft} onOpenChange={open => { if (!open) setDeleteDraft(null); }}><DialogContent><DialogHeader><DialogTitle>Удалить «{deleteDraft?.name}»?</DialogTitle><DialogDescription>Черновик переместится в удалённые. Готовые игровые сохранения не затрагиваются.</DialogDescription></DialogHeader><div className="workshop-dialog-actions"><Button variant="ghost" onClick={() => setDeleteDraft(null)}>Отмена</Button><Button disabled={busy} onClick={() => void run(async () => { if (!deleteDraft) return; await api(`/workspaces/${deleteDraft.id}`,{revision:deleteDraft.revision},'DELETE'); setList(await api<WorkspacePick[]>('/workspaces')); setRemoved(await api<WorkspacePick[]>('/workspaces?deleted=true')); if (id === deleteDraft.id) { selectWorkspace(''); } setDeleteDraft(null); toast.success('Черновик перемещён в удалённые'); })}>Удалить</Button></div></DialogContent></Dialog>
      {!resuming && !active(job) && (job?.response_diagnostic?.message || job?.error) && <p className="workshop-error" role="alert">{job?.response_diagnostic?.message || job?.error}</p>}
      {(showIdea||section==='review'||section==='ai'&&job?.kind==='draft_editor')&&<>
      {job?.pinned_config && <p className="workshop-hint">Модель задания: {job.pinned_config.provider} / {job.pinned_config.model} · Thinking генерации: {job.pinned_config.thinking || 'off'} · Thinking проверки: off</p>}
      {job?.effective_config && <p className="workshop-hint" aria-label="Фактические параметры запроса">Последний запрос: {job.effective_config.provider} / {job.effective_config.model} · Thinking: {job.effective_config.thinking} · Контекст: {job.effective_config.context_length} · Лимит ответа: {job.effective_config.max_tokens} · Попытка: {(job.attempt_epoch || 0)+1}</p>}
      {job?.status==='saved' && draft?.review?.status==='completed' && <p role="status">Смысловая проверка завершена. Результат сохранён.</p>}
      {calendarNotices.map((notice,i)=><p key={i} role="status">{notice}</p>)}
      </>}
      {state && !showIdea && <section className="workshop-result">
        {job?.status === 'saved' && ['partial','rejected'].includes(draft?.quality_status || '') && <p className="workshop-hint" role="status">Мир сохранён. {draft?.quality_status === 'partial' ? 'Некоторые творческие детали модель оставила неполными.' : 'Необязательное дополнение не было принято; проверенные данные сохранены.'} Проверить и дополнить детали можно в режиме «Автор мира».</p>}
        <div className="workshop-result-toolbar">
          <div className="workshop-view"><span>Вид:</span><button className={!author ? 'selected' : ''} aria-pressed={!author} onClick={() => setAuthor(false)}>Игрок</button><button className={author ? 'selected' : ''} aria-pressed={author} onClick={() => authorAcknowledged ? setAuthor(true) : setAuthorAsk(true)}>Автор мира</button></div>
          <span className="workshop-hint">{author ? 'Полное состояние: секреты и намерения NPC доступны для редактирования.' : `То, что доступно персонажу ${person(actor)}.`}</span>
        </div>
        {section==='ai'&&!author&&<div className="ww-empty"><h2>Изменения с ИИ</h2><p>Редактор работает с полным авторским миром, включая тайны и знания персонажей.</p><button onClick={()=>authorAcknowledged?setAuthor(true):setAuthorAsk(true)}>Открыть авторский редактор</button></div>}
        {section==='ai' && author && draft && <WorldAIEditor wid={id} revision={draft.revision} job={job} locked={locked} prefs={prefs} apiKey={apiKey} refresh={refresh} resolve={resolve} onJob={next=>dispatchWorkspace({type:'update',id,update:d=>d?{...d,job:next}:d})}/>}
        {section==='review' && (draft?.validation.errors.length || draft?.validation.warnings.length || draft?.import_warnings.length) ? <details className="workshop-review" open={!!draft?.validation.errors.length}>
          <summary>Проверка мира · {draft?.validation.errors.length || 0} ошибок · {(draft?.validation.warnings.length || 0) + (draft?.import_warnings.length || 0)} замечаний</summary>
          {[...(draft?.validation.errors || []), ...(draft?.validation.warnings || []), ...(draft?.import_warnings || [])].map((x,i)=><p key={i}>{x}</p>)}
        </details> : null}
        <div className="workshop-content" key={section}>
          {section === 'overview' && <>
            <section className="ww-hero"><div className="ww-eyebrow">Ваш мир. Ваши истории.</div><h1>{workspaceTitle}</h1><ReadableText text={String(state.campaign.description||state.campaign.public_description||'Начните с персонажей и первой сцены — все детали мира можно раскрыть и изменить.')}/><div className="ww-hero-meta"><span>{String(state.campaign.setting||'Место не задано')}</span><span>{String(state.campaign.genre||'Жанр не задан')}</span><span>{weekTime()}</span></div>{author&&<button className="ww-text-button" onClick={()=>navigate('start')}>Изменить описание и правила →</button>}</section>
            <div className="ww-stats">{([['characters',characters.length,'Персонажей',Users],['world',state.locations.length,'Локаций',MapPin],['relations',relations.length,'Отношений',Link],['story',threads.length,'Сюжетных линий',BookOpen]] as const).map(([key,count,label,Icon])=><button key={key} onClick={()=>navigate(key)}><Icon/><div><strong>{count}</strong><span>{label}</span></div></button>)}</div>
            <div className="ww-overview-grid"><div><header className="ww-section-head"><h2>Те, кто оживляет историю</h2><button onClick={()=>navigate('characters')}>Все персонажи <ArrowRight size={16}/></button></header><div className="ww-characters-grid is-overview">{characters.slice(0,4).map(c=><CharacterCard key={c.id} card={c as WorkshopCharacter} wid={id} author={author} protagonist={state.protagonist_id} onOpen={openPerson}/>)}</div><section className="ww-panel ww-opening"><p className="ww-eyebrow">Первая сцена</p><h2>{place(beginning?.location||actorState?.location)}</h2><p className="workshop-literary">{String(beginning?.text||actorState?.situation||'Стартовая ситуация пока не описана.')}</p><p>{weekTime()}</p><button className="ww-text-button" onClick={()=>navigate('start')}>Открыть начало истории →</button></section></div><aside className="ww-overview-aside"><section className="ww-panel"><h3><ShieldCheck size={20}/>{allIssues.length?'Миру нужно немного внимания':'Готовность мира'}</h3><p>{draft?.technical_valid?'Структура мира корректна.':'Проверьте ошибки перед запуском.'}</p>{allIssues.slice(0,3).map((message,i)=><p className="ww-issue-summary" key={i}>{message}</p>)}<button className="ww-soft" onClick={()=>navigate('review')}>Перейти к проверке <ArrowRight size={16}/></button></section><section className="ww-panel"><h3>У истории есть продолжение</h3><p>Опишите, что изменить. Сначала появится предложение — решение останется за вами.</p><button className="ww-text-button" onClick={()=>navigate('ai')}>Изменить с ИИ →</button></section></aside></div>
          </>}
          {section==='characters'&&<CharacterCollection characters={characters as WorkshopCharacter[]} wid={id} author={author} protagonist={state.protagonist_id} view={collection} setView={setCollection} onOpen={openPerson} onAdd={()=>void change({operation:'add',kind:'character'})} disabled={locked}/>}
          {section==='world'&&<>{pageHeader('Места и сообщества','Где проходит жизнь и что объединяет людей.')}{tab('Места',[['locations','Локации'],['organizations','Сообщества'],['residences','Проживание'],['roles','Роли'],['conditions','Обстоятельства'],['possessions','Имущество'],['contacts','Контакты']])}{currentSub('Места','locations')==='locations'?collectionRecords('location','Места',state.locations.map(l=>[l.id,l]),l=>String(l.name||l.text||'Место')):author?extension(currentSub('Места','locations'),extensionGroups[currentSub('Места','locations')]):<p className="ww-empty">В этой проекции нет доступных записей.</p>}</>}
          {section==='knowledge'&&<>{pageHeader('Факты и знания','Что известно, что скрыто и кто владеет информацией.')}{tab('Знания',[['facts','Факты и тайны'],['knowledge','Кто что знает']])}{currentSub('Знания','facts')==='facts'?collectionRecords('fact',author?'Факты и тайны':'Известные факты',facts,f=>String(f.text||'Факт')):collectionRecords('knowledge','Знания персонажей',Object.entries(state.world.knowledge||{}),k=>recordTitle('knowledge',k,resolve,author))}</>}
          {section==='relations'&&<>{pageHeader('Связи и семьи','Объективные связи и направленные чувства — разные записи мира.')}{tab('Связи',[['feelings','Направленные чувства'],['objective_relations','Семья и связи'],['pregnancies','Беременности']])}{currentSub('Связи','feelings')==='feelings'?collectionRecords('relationship','Направленные чувства',relations,r=>`${person(r.source_id)} → ${person(r.target_id)} · ${String(r.context||'')}`):author?extension(currentSub('Связи','feelings'),extensionGroups[currentSub('Связи','feelings')]):<p className="ww-empty">В этой проекции нет доступных записей.</p>}</>}
          {section==='story'&&<>{pageHeader('Нити вашей истории','Открытые возможности и развивающиеся линии. Они не принимают решения за героя.')}{collectionRecords('thread','Сюжетные линии',threads,t=>String(t.description||'Сюжетная линия'))}</>}
          {section==='timeline'&&<>{pageHeader('Хронология','Предыстория отдельно от планов и будущих договорённостей.')}{tab('Хронология',[['events','Прошедшие события'],['scheduled_events','Будущие события'],['reproductive_events','Семейные события'],['naming_decisions','Выбор имён']])}{currentSub('Хронология','events')==='events'?collectionRecords('event','Уже произошедшие события',Object.entries(state.world.events||{}).sort(([,a],[,b])=>Number(a.minute)-Number(b.minute)),e=>String(e.text||'Событие')):author?extension(currentSub('Хронология','events'),extensionGroups[currentSub('Хронология','events')]):<p className="ww-empty">В этой проекции нет доступных записей.</p>}</>}
            {section === 'start' && <>{pageHeader('Сцена и правила','Герой, камера, время и правила вашей истории.')}<details className="workshop-detail"><summary>Описание и правила мира</summary>{author?fields.campaign.concat('public_description').map(f=>row('campaign','',f,state.campaign[f]??'')):<p>{String(state.campaign.public_description||'')}</p>}</details>{author&&draft?<CommunicationEditor wid={id} revision={draft.revision} profile={(state.world.communication||{}) as CommunicationProfile} disabled={locked} refresh={refresh}/>:<CommunicationSettings value={(state.world.communication||{}) as CommunicationProfile}/>} {author&&draft&&<CalendarProfileEditor wid={id} revision={draft.revision} profile={((state.world_clock as unknown as {calendar?:{profile?:Record<string,unknown>}}).calendar?.profile||{})} selection={draft.creation_settings?.calendar_start?.presets} disabled={locked} refresh={refresh}/>}{draft?.presentation?.clock.effective && <section aria-label="Действующий календарь"><h4>Действующий календарь</h4><p>{draft.presentation.clock.effective.weekday_names.join(' · ')}</p><p>{draft.presentation.clock.effective.month_names.map((name,i)=>`${name}: ${draft.presentation!.clock.effective!.month_lengths[i] ?? '28–29 (год неизвестен)'}`).join(' · ')}</p><p>Сезоны: {draft.presentation.clock.effective.seasons.length ? draft.presentation.clock.effective.seasons.map(s=>`${s.name} — ${s.day}.${s.month}`).join(' · ') : 'Не заданы'}. Праздники: {draft.presentation.clock.effective.regional ? `${draft.presentation.clock.effective.regional.country} · годозависимый набор; ближайшие даты — в предпросмотре` : draft.presentation.clock.effective.observances.length ? draft.presentation.clock.effective.observances.map(o=>`${o.name} — ${o.day}.${o.month}`).join(' · ') : 'Не заданы'}.</p></section>}{author && row('clock','clock','calendar',(state.world_clock as unknown as Item).calendar || {})}<div className="workshop-start"><div><span>Когда</span><strong>{weekTime()}</strong></div><div><span>Где</span><strong>{place(beginning?.location || actorState?.location)}</strong></div><div><span>Управление</span><strong>{person(actor)}</strong></div><div><span>Рядом</span><strong>{(beginning?.participants as string[] || []).filter(cid=>cid!==actor).map(person).join(' · ') || 'Пока никто'}</strong></div></div>
              {actorState?.situation && <p className="workshop-literary">{String(actorState.situation)}</p>}{beginning?.text && <section className="workshop-overview-section"><h4>Текущая ситуация</h4><p className="workshop-literary">{String(beginning.text)}</p></section>}
              {author && <>{Object.entries(state.world.scenes || {}).map(([key,item])=><details className="workshop-detail" key={key}><summary>{place(item.location)}</summary>{entity('scene',key,item)}</details>)}<Button variant="outline" disabled={locked} onClick={() => void change({operation:'add',kind:'scene'})}>+ Добавить сцену</Button><details className="workshop-detail"><summary>Изменить стартовых участников и время</summary>{fields.start.map(f=>row('start','',f,f==='scene_id'?state.camera.scene_id:f==='minute'?state.world_clock.minute:state[f as 'protagonist_id'|'controlled_actor_id']))}</details></>}
            </>}
          {section === 'more' && <>{pageHeader('Можно вернуться назад','История версий, исходные материалы и экспорт мира.')}<button className="ww-soft" onClick={()=>setDraftsOpen(true)}>Мои черновики и корзина</button><details className="workshop-detail"><summary>Стиль и правила повествования</summary>{author ? fields.campaign.map(f=>row('campaign','',f,state.campaign[f] || '')) : <p>{String(state.campaign.genre || '')} · {String(state.campaign.tone || '')}</p>}</details>
            <details className="workshop-detail"><summary>История версий · {draft?.history.length}</summary>{draft?.history.map((v,i)=><div className="workshop-version" key={v.id}><span>Версия {draft.history.length-i} · {v.reason}</span>{author && <Button disabled={locked||v.id===draft.version_id} variant="outline" onClick={() => void change({operation:'restore',source_id:v.id})}>Восстановить</Button>}</div>)}</details>
            {author && <>{Object.entries(state.world).filter(([key])=>!['version','characters','relationships','facts','knowledge','threads','scenes','events',...Object.keys(extensionGroups)].includes(key)).map(([key,v])=><details className="workshop-detail" key={key}><summary>{runtimeLabels[key] || key} · просмотр</summary><RuntimeValue field={key} value={v} resolve={resolve} author/></details>)}<details className="workshop-detail"><summary>Исходный замысел или импорт</summary><Markdown text={draft?.source_text || 'Исходный текст не сохранён.'}/></details>{draft?.outline && <details className="workshop-detail"><summary>Как сценарист развил идею</summary><Markdown text={draft.outline}/></details>}<div className="workshop-export">{['md','txt','json'].map(format=><Button key={format} variant="outline" onClick={()=>void run(async()=>{const response=await fetch(`/api/workspaces/${id}/draft/export?version_id=${draft?.version_id}&format=${format}`);if(!response.ok)throw new Error('Не удалось экспортировать мир');download(await response.text(),`world.${format}`)})}>{format === 'json' ? 'Экспорт JSON' : `Скачать .${format}`}</Button>)}</div></>}
          </>}
        </div>
        {section==='review'&&!author&&<section className="ww-empty"><ShieldCheck/><h2>Этот раздел доступен автору</h2><p>Здесь могут быть скрытые сведения о мире.</p><button className="ww-primary" onClick={()=>authorAcknowledged?setAuthor(true):setAuthorAsk(true)}>Открыть авторский взгляд</button></section>}
        {section==='review'&&author&&<>{pageHeader('Проверка мира','Ошибки структуры, смысловые замечания и состояние проверки.')}<section className="ww-panel"><h3>{draft?.technical_valid?'Структура корректна':'Структура требует исправления'}</h3><p>Смысловая проверка: {({completed:'завершена',stale:'устарела',running:'выполняется',failed:'прервана'} as Record<string,string>)[draft?.review?.status||'']||'не выполнялась'}</p><p>{draft?.review?.reason}</p>{draft?.review?.issues?.map((issue,i)=><article key={i} className="ww-issue-summary"><strong>{issue.severity==='blocker'?'Противоречие':'Замечание'}</strong><p>{issue.message}</p>{reviewLinks([issue.path,...issue.patch_paths||[],...issue.related_paths||[]])}</article>)}{!allIssues.length&&!draft?.review?.issues?.length&&<p>Замечаний в текущем отчёте нет.</p>}</section>{draft?.validation.diagnostics?.map((issue,i)=><article className="ww-panel" key={i}><p>{issue.message}</p>{reviewLinks([issue.path])}<details><summary>Путь диагностики</summary><code>{issue.path}</code></details></article>)}</>}
        {(section==='review'||section==='start')&&<div className="workshop-finish"><p>{previousWorld?'Новая генерация не завершена. Доступен предыдущий мир.':'Запуск сохранит выбранную версию и откроет настоящую игру.'}</p><Button disabled={busy||loading||!draft?.technical_valid} onClick={()=>setConfirmStart(true)}>Перейти к запуску</Button></div>}
      </section>}
    </WorkshopShell>
    <CharacterDossier open={dossierOpen} onClose={()=>setDossierOpen(false)} card={selectedCard} characters={characters as WorkshopCharacter[]} wid={id} author={author} locked={locked} actor={state?.world.characters?.[selectedCharacter]||{}} actorFields={author?Array.from(new Set([...fields.actor,...draft?.editor?.fields.actor||[]])):selectedCharacter===actor?fields.actor:[]} row={row} life={author?<>{extension('conditions',extensionGroups.conditions,item=>item.actor_id===selectedCharacter||(Array.isArray(item.character_ids)&&item.character_ids.includes(selectedCharacter)))}{extension('roles',extensionGroups.roles,item=>item.actor_id===selectedCharacter)}{extension('residences',extensionGroups.residences,item=>item.actor_id===selectedCharacter)}</>:null} refresh={refresh} onSelect={setSelectedCharacter} returnFocus={()=>dossierTrigger.current?.isConnected&&dossierTrigger.current.focus()} connections={<>{relations.filter(([,r])=>r.source_id===selectedCharacter||r.target_id===selectedCharacter).map(relation)}{author&&extension('objective_relations',extensionGroups.objective_relations,item=>[item.source_id,item.target_id,...(Array.isArray(item.actor_ids)?item.actor_ids:[])].includes(selectedCharacter))}</>} knowledge={<>{facts.filter(([,f])=>(f.character_ids as string[]||[]).includes(selectedCharacter)||(f.secret_subject_ids as string[]||[]).includes(selectedCharacter)||Object.values(state?.world.knowledge||{}).some(k=>k.actor_id===selectedCharacter&&k.fact_id===f.id&&k.status==='known')).map(([key,f])=><details className="workshop-detail" key={key}><summary>{short(f.text,150)}</summary>{author?entity('fact',key,f):<p>{String(f.text)}</p>}</details>)}{author&&Object.entries(state?.world.knowledge||{}).filter(([,k])=>k.actor_id===selectedCharacter).map(([key,k])=>entity('knowledge',key,k))}</>} onRegenerate={()=>{if(selectedCard)openEdit({kind:'character',id:selectedCard.id,field:'__character',value:'',label:'Перегенерировать персонажа целиком'})}} onDelete={()=>void run(async()=>{const deps=await api<{kind:string;id:string}[]>(`/workspaces/${id}/draft/dependencies?kind=character&entity_id=${selectedCharacter}`);setRemoval({kind:'character',id:selectedCharacter,deps})})}/>
    <Dialog open={searchOpen} onOpenChange={setSearchOpen}><DialogContent><DialogTitle>Поиск по миру</DialogTitle><DialogDescription>Поиск только по данным текущего взгляда.</DialogDescription><Input autoFocus aria-label="Поиск по миру" value={search} onChange={e=>setSearch(e.target.value)}/><div className="ww-search-results">{search.trim()&&characters.filter(c=>[c.name,...Object.values(c.fields)].join(' ').toLowerCase().includes(search.toLowerCase())).slice(0,30).map(c=><button key={c.id} onClick={()=>{setSearchOpen(false);openPerson(c.id)}}>{c.name}<small>Персонаж</small></button>)}{search.trim()&&[...facts.map(([key,f])=>({key,text:String(f.text),section:'knowledge' as const})),...(state?.locations||[]).map(l=>({key:l.id,text:l.name,section:'world' as const}))].filter(r=>r.text.toLowerCase().includes(search.toLowerCase())).slice(0,30).map(r=><button key={r.key} onClick={()=>{navigate(r.section);setSubsection(prev=>({...prev,[r.section==='world'?'Места':'Знания']:r.section==='world'?'locations':'facts'}));setRecordTarget({kind:r.section==='world'?'location':'fact',id:r.key});setSearchOpen(false)}}>{r.text}</button>)}</div></DialogContent></Dialog>
 <Dialog open={authorAsk} onOpenChange={setAuthorAsk}><DialogContent><DialogHeader><DialogTitle>Открыть вид автора?</DialogTitle><DialogDescription>Ты увидишь тайны, неизвестные персонажам факты и скрытые намерения. Это может раскрыть будущие события.</DialogDescription></DialogHeader><Button onClick={() => { setAuthorAsk(false); setAuthorAcknowledged(true); setAuthor(true); }}>Показать всё</Button></DialogContent></Dialog>
 <Dialog open={!!edit} onOpenChange={o => { if (!o)
        setEdit(null); }}><DialogContent className="ww-field-dialog" onCloseAutoFocus={e=>{if(fieldTrigger.current?.isConnected){e.preventDefault();fieldTrigger.current.focus()}}}><DialogHeader><DialogTitle>{edit?.label}</DialogTitle><DialogDescription>Меняется только выбранное поле. Остальные сущности сохраняются.</DialogDescription></DialogHeader>{editError&&<p role="alert">{editError}</p>}{edit&&editRevision!==draft?.revision&&<Button variant="outline" onClick={()=>{setEditRevision(draft?.revision||0);setEditError('')}}>Использовать ввод для текущей версии</Button>}{edit && edit.field !== '__character' && <>{options(edit.field) ? Array.isArray(value) ? <div className="draft-options">{options(edit.field)!.map(([k, n]) => <label key={k}><input type="checkbox" checked={value.includes(k)} onChange={e => setValue(e.target.checked ? [...value, k] : value.filter(x => x !== k))}/>{n}</label>)}</div> : <select aria-label={edit.label} value={String(value ?? '')} onChange={e => setValue(e.target.value || null)}><option value="">Не указано</option>{options(edit.field)!.map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select> : editTypes.includes('boolean') && nullableEdit ? <select aria-label={edit.label} value={value==null?'unknown':String(value)} onChange={e=>setValue(e.target.value==='unknown'?null:e.target.value==='true')}><option value="unknown">Неизвестно</option><option value="true">Да</option><option value="false">Нет</option></select> : typeof value === 'boolean' ? <label><input type="checkbox" checked={value} onChange={e => setValue(e.target.checked)}/>Да</label> : typeof value === 'number' || editTypes.includes('integer') || editTypes.includes('number') ? <Input type="number" aria-label={edit.label} value={value==null?'':String(value)} onChange={e => setValue(e.target.value==='' && nullableEdit?null:Number(e.target.value))}/> : structuredField(edit.field,value,editSchema) ? <StructuredValueEditor label={edit.label} field={edit.field} value={value} schema={editSchema} definitions={draft?.editor?.definitions} references={options} onChange={v=>{setValue(v);setStructuredEdit(JSON.stringify(v,null,2))}}/> : value && typeof value === 'object' && !Array.isArray(value) ? <div>{['trust', 'affection', 'attraction', 'irritation', 'fear', 'jealousy', 'respect', ...Object.keys(value)].filter((v, i, a) => a.indexOf(v) === i).map(k => <label key={k}>{k}<Input type="number" value={String((value as Item)[k] ?? '')} onChange={e => { const next = { ...value } as Item; if (e.target.value === '')
        delete next[k];
    else
        next[k] = Number(e.target.value); setValue(next); }}/></label>)}</div> : <Textarea aria-label={edit.label} value={Array.isArray(value) ? value.join('\n') : String(value ?? '')} onChange={e => setValue(Array.isArray(value) ? e.target.value.split('\n') : e.target.value)}/>}{nullableEdit && <Button variant="outline" onClick={()=>{setValue(null);setStructuredEdit('null');}}>Оставить неизвестным</Button>}<Button disabled={locked||editRevision!==draft?.revision} onClick={() => {setBusy(true);setEditError('');void (async () => { await api(`/workspaces/${id}/draft`, { revision: editRevision, operation: 'patch', kind: edit.kind, entity_id: edit.id, field: edit.field, value: structuredField(edit.field,value,editSchema) ? JSON.parse(structuredEdit) : value, warnings_ack: ack }, 'PATCH'); sessionStorage.removeItem(editBufferKey(edit));setEdit(null); await refresh(); })().catch(e=>setEditError((e as Error).message)).finally(()=>setBusy(false))}}>Сохранить поле</Button></>}
 {edit?.field === '__character' && <div><p>Связанные записи останутся неизменными; проверь их после изменения биографии:</p>{related.map(d => <p key={d.kind + d.id}>{d.kind} · {d.id}</p>)}</div>}<Textarea aria-label="Указание генератору" placeholder="Как изменить? Например: сделать характер мягче, сохранив биографию." value={instruction} onChange={e => setInstruction(e.target.value)}/><label><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)}/> Изменить всё равно при семантических замечаниях</label><Button variant="outline" disabled={locked} onClick={() => edit && void generate({ task: edit.field === '__character' ? 'character' : 'field', kind: edit.kind, entity_id: edit.id, field: edit.field, text: instruction, warnings_ack: ack })}>Перегенерировать {edit?.field === '__character' ? 'персонажа' : 'поле'}</Button></DialogContent></Dialog>
 <Dialog open={!!removal} onOpenChange={o => { if (!o)
        setRemoval(null); }}><DialogContent><DialogHeader><DialogTitle>Удалить запись?</DialogTitle><DialogDescription>{removal?.deps.length ? 'Сначала измени связанные записи. Автоматически удалять их нельзя.' : 'Будет создана новая версия. Предыдущую можно восстановить из истории.'}</DialogDescription></DialogHeader>{removal?.deps.map(d => <p key={d.kind + d.id}>{d.kind} · {characters.find(c => c.id === d.id)?.name || d.id}</p>)}<Button disabled={locked || !!removal?.deps.length} onClick={() => void run(async () => { await api(`/workspaces/${id}/draft`, { revision: draft?.revision, operation: 'remove', kind: removal?.kind, entity_id: removal?.id }, 'PATCH'); setRemoval(null); refresh(); })}>Удалить</Button></DialogContent></Dialog>
 <Dialog open={confirmStart} onOpenChange={setConfirmStart}><DialogContent><DialogHeader><DialogTitle>Начать эту историю?</DialogTitle><DialogDescription>Будет сохранена текущая версия мира. Повторной генерации или разбора текста не будет.</DialogDescription></DialogHeader><dl className="ww-launch-summary"><dt>Версия</dt><dd>#{draft?.version_id}</dd><dt>Главный герой</dt><dd>{person(state?.protagonist_id)}</dd><dt>Управляемый персонаж</dt><dd>{person(state?.controlled_actor_id)}</dd><dt>Камера / сцена</dt><dd>{place(beginning?.location)}</dd><dt>Когда</dt><dd>{weekTime()}</dd></dl>{draft?.pending_editor && <p>Предложение AI ещё не применено. Игра начнётся с текущей версии мира.</p>}{draft?.start_warning && <p>{draft.start_warning}</p>}{draft?.validation.warnings.map(x => <p key={x}>{x}</p>)}<Button disabled={busy || loading || !draft?.technical_valid} onClick={() => void run(async () => { const result = await api<{
        world: number;
        save: number;
    }>(`/workspaces/${id}/draft/confirm`, { revision: draft?.revision, version_id: draft?.version_id, accept_warnings:!!draft?.start_warning, stop_review:active(job) }); setConfirmStart(false); onGame(result.world, result.save); })}>Подтвердить и открыть игру</Button></DialogContent></Dialog>
 </main>;
}
