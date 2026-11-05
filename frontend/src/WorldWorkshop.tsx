import {ReviewDecisions,type ReviewDecision} from './workshop/ReviewDecisions';
import {reviewIssues} from './workshop/reviewIssues';
import {WorldTimeEditor} from './workshop/WorldTimeEditor';
import {RecordEditor,type RecordEditTarget} from './workshop/RecordEditor';
import {FieldProposal} from './workshop/FieldProposal';
import {CreateRecordDialog,type CreationTarget} from './workshop/CreateRecordDialog';
import {FeelingEditor} from './workshop/FeelingEditor';
import {VersionPreview} from './workshop/VersionPreview';
import {StartConfirmation,type LaunchSnapshot} from './workshop/StartConfirmation';
import {workshopSearch} from './workshop/workshopSearch';
import {IdeaGeneration} from './workshop/IdeaGeneration';
import {IdeaAtelier} from './workshop/IdeaAtelier';
import {readIdeaBuffer,writeIdeaBuffer} from './workshop/ideaBuffer';
import {ReferenceChecklist} from './workshop/ReferenceChecklist';
import {RelationshipMap} from './workshop/RelationshipMap';
import {RecordPreview} from './workshop/RecordPreview';
import {useWorkshopBack} from './workshop/useWorkshopBack';
import {ReadableText} from './workshop/ReadableText';
import {FieldVisibility,fromBinding,wirePolicy,type FieldPolicy} from './workshop/FieldVisibility';
import {DossierRecords} from './workshop/DossierRecords';
import {RecordCollection} from './workshop/RecordCollection';
import {WorkshopShell,type WorkshopSection} from './workshop/WorkshopShell';
import {CharacterCollection,CharacterCard,emptyCollection,type CollectionView,type WorkshopCharacter} from './workshop/CharacterCollection';
import {CharacterDossier} from './workshop/CharacterDossier';
import {StructuredValueEditor} from './workshop/StructuredValueEditor';
import {Home,Users,MapPin,Link,BookOpen,ShieldCheck,ArrowRight,Search,Plus,Clock,Pencil} from 'lucide-react';
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
    card_field_facts?:Record<string,Record<string,string[]>>;
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
        scene_id: string; mode?:string; subject_id?:string; pov_actor_id?:string;
    };
    world_clock: {
        minute: number;
    };
};
type Draft = {
    author?:boolean;
    portraits?:Record<string,Partial<WorkshopCharacter>>;
    editor?:{field_visibility_excluded?:string[];fields:Record<string,string[]>;definitions?:Record<string,Item>;enums:Record<string,Record<string,string[]>>;schemas:Record<string,Record<string,Item>>} | null;
    creation_settings?: Partial<Creation>;
    presentation?: {launch?:{protagonist:string;controlled_actor:string;camera_mode:string;pov:string;subject:string};clock:{label:string;effective?:{month_names:string[];weekday_names:string[];month_lengths:(number|null)[];year:number|null;regional?:{country:string;subdivision:string|null}|null;seasons:{name:string;month:number;day:number}[];observances:{name:string;month:number;day:number}[]}};notices?:string[];event_times?:Record<string,string>;event_periods?:Record<string,'today'|'past'|'future'>;scene_times?:Record<string,string>;thread_visibility?:Record<string,string>} | null;
    id: string;
    name: string;
    revision: number;
    version_id: number | null;
    version_origin_job_id?: string | null;
    version_is_candidate?: boolean;
    games?: {world:number;save:number;version_id:number}[];
    candidate?: Record<string,unknown> | null;
    relation_merges?: {ids:string[];paths:string[];differences:string[];safe:boolean;records:Item[]}[];
    review?: {status:string;reason?:string;checked_revision?:number;issues?:{message:string;severity:string;path?:string|null;patch_paths?:string[];related_paths?:string[];protocol_warnings?:unknown[]}[]} | null;
    review_decisions?:ReviewDecision[];
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
const labels: Record<string, string> = { public_description: 'Аннотация для игрока', title: 'Название', setting: 'Обстановка', era: 'Эпоха', genre: 'Жанр', tone: 'Тон', description: 'Описание', rules: 'Правила повествования', name: 'Имя / название', aliases: 'Другие имена', location: 'Местоположение', situation: 'Сейчас', goals: 'Цели', intentions: 'Намерения', emotion: 'Эмоциональное состояние', obligations: 'Обязательства', source_id: 'От кого', target_id: 'К кому', context: 'Динамика отношений', dimensions: 'Показатели отношений', visible_to_ids: 'Кому известна информация', text: 'Описание', secret: 'Приватный факт', story_secret: 'Сюжетная тайна', secret_subject_ids: 'О ком тайна', secret_keeper_ids: 'Кто хранит тайну', secret_biography_ids: 'Чья скрытая биография', secret_existence: 'Показывать существование', owner_id: 'Чья тайна', character_ids: 'Связанные персонажи', evidence: 'Основания', actor_id: 'Кто знает', fact_id: 'Факт', status: 'Статус', source_event_id: 'Источник знания', state: 'Текущее развитие', public_state: 'Известное герою состояние', relevance: 'Значимость', participants: 'Участники', start_minute: 'Начало · минуты недели', end_minute: 'Конец · минуты недели', protagonist_id: 'Основной герой', controlled_actor_id: 'Управляемый персонаж', scene_id: 'Стартовая сцена', minute: 'Игровое время · минуты недели', witnesses: 'Свидетели', fact_ids: 'Факты', player_observed: 'Известно игроку' };
Object.assign(labels,{parent_id:'Родительская локация',location_id:'Локация',organization_id:'Организация',kind:'Тип',since:'Начало периода',until:'Конец периода',physical_state:'Физическое состояние',life_status:'Жизненный статус',birth_date:'Дата рождения',calendar:'Календарь',appearance:'Внешность',personality:'Характер',values:'Ценности',capabilities:'Возможности',developmental_stage:'Этап жизни',claim:'Структурированный факт',holder_id:'У кого находится'});
Object.assign(labels,runtimeLabels,{appearance:'Особые приметы',personality:'Черты характера'});
const fields: Record<string, string[]> = { campaign: ['title', 'setting', 'era', 'genre', 'tone', 'description', 'rules'], actor: ['location', 'situation', 'goals', 'intentions', 'emotion', 'obligations'], relationship: ['source_id', 'target_id', 'context', 'dimensions', 'visible_to_ids'], location: ['name', 'text'], fact: ['text', 'secret', 'story_secret', 'secret_subject_ids', 'secret_keeper_ids', 'secret_biography_ids', 'secret_existence', 'character_ids', 'evidence'], knowledge: ['actor_id', 'fact_id', 'status', 'source_event_id'], thread: ['description', 'state', 'public_state', 'status', 'character_ids', 'relevance', 'visible_to_ids'], scene: ['location', 'participants', 'text', 'start_minute', 'end_minute', 'status'], event: ['text', 'participants', 'witnesses', 'minute', 'fact_ids', 'player_observed'], start: ['protagonist_id', 'controlled_actor_id', 'scene_id', 'minute'] };
const versionReasons:Record<string,string>={patch:'Изменение поля',portrait:'Портрет персонажа',draft_world:'Мир создан',generation_candidate:'Промежуточная версия генерации',import:'Импорт мира',restore:'Восстановление версии',add:'Добавление записи',remove:'Удаление записи',ai_edit:'Изменения с ИИ',draft_field:'Поле изменено с ИИ',draft_character:'Карточка изменена с ИИ',calendar:'Настройки календаря',communication:'Настройки связи'};
const extensionGroups: Record<string,string> = {objective_relations:'Родство и социальные связи',organizations:'Организации',residences:'Проживание',roles:'Профессии и роли',possessions:'Значимое имущество',conditions:'Обстоятельства',pregnancies:'Беременности',contacts:'Контакты',reproductive_events:'Репродуктивные события',naming_decisions:'Выбор имён',scheduled_events:'Будущие события и договорённости'};
const groups = [['Персонажи', 'character', 'characters'], ['Отношения', 'relationship', 'relationships'], ['Места', 'location', 'locations'], ['Факты и тайны', 'fact', 'facts'], ['Знания персонажей', 'knowledge', 'knowledge'], ['Сюжетные линии', 'thread', 'threads'], ['Сцены', 'scene', 'scenes'], ['События', 'event', 'events']];
const short = (value: unknown, max = 180) => { const s = String(value || '').replace(/\s+/g, ' ').trim(); return s.length > max ? s.slice(0, max).trimEnd() + '…' : s; };
const dimensions: Record<string,string> = {trust:'Доверие',affection:'Привязанность',attraction:'Влечение',irritation:'Раздражение',fear:'Страх',jealousy:'Ревность',respect:'Уважение'};
const strength = (n: number) => Math.abs(n) < 25 ? 'слабое' : Math.abs(n) < 60 ? 'заметное' : 'сильное';
type WorkshopView={section:WorkshopSection;collection:CollectionView;selected:string;subsection:Record<string,string>};
const viewKey=(wid:string,author:boolean)=>`workshop-view:${wid}:${author?'author':'reader'}`;
function storedView(wid:string,author=false):Partial<WorkshopView>{
    try{
        const saved=JSON.parse(sessionStorage.getItem(viewKey(wid,author))||'{}');
        // Navigation can survive a reload; search terms are private to each view.
        const route=sessionStorage.getItem('workshop-section:'+wid);
        return route?{...saved,section:route}:saved;
    }catch{return {}}
}
export function WorldWorkshop({ prefs, apiKey, onWorld, onGame, onBack, onSettings }: {
    onBack?:()=>void;
    onSettings?:()=>void;
    prefs: Preferences;
    apiKey: string;
    onWorld: (id: number) => void;
    onGame: (world: number, save: number) => void;
}) {
    useWorkshopBack(onBack);
    const initialBuffer=useRef(readIdeaBuffer(localStorage.getItem('draftWorkspace')||'')).current;
    const restoredCreation=useRef(!!initialBuffer);
    const [inputSaved,setInputSaved]=useState(true);
    const [launchError,setLaunchError]=useState('');
    const [creation,setCreation]=useState<Creation>(()=>initialBuffer?.creation||structuredClone(defaultCreation));
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
    const [pendingVisibility,setPendingVisibility]=useState<FieldPolicy|null>(null);
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
    const [deleteError,setDeleteError]=useState('');
    const [reviewQuery,setReviewQuery]=useState('');
    const [reviewSeverity,setReviewSeverity]=useState('all');
    const [reviewView,setReviewView]=useState<'active'|'decisions'>('active');
    const [timeValid,setTimeValid]=useState(true);
    const [deleteDraft, setDeleteDraft] = useState<WorkspacePick | null>(null);
    const [author, setAuthor] = useState(false);
    const [authorAsk, setAuthorAsk] = useState(false);
    const [authorAcknowledged, setAuthorAcknowledged] = useState(false);
    const [text, setText] = useState(()=>initialBuffer?.text??sessionStorage.getItem('workshop-idea:'+ (localStorage.getItem('draftWorkspace')||''))??'');
    const [importFormat, setImportFormat] = useState<'text'|'json'>('text');
    const [importFile, setImportFile] = useState('');
    const detectedImport = useMemo(() => detectWorldImport(text, importFile ? importFormat : undefined), [text, importFile, importFormat]);
    const [name, setName] = useState(initialBuffer?.name||'');
    const [useIdea, setUseIdea] = useState(initialBuffer?.useIdea||false);
    const [busy, setBusy] = useState(false);
    const [resuming, setResuming] = useState(false);
    const resumeGuard = useRef(false);
    const [emptyRetry, setEmptyRetry] = useState<{token:string;epoch:number}|null>(null);
    const [edit, setEdit] = useState<Target | null>(null);
    const fieldTrigger=useRef<HTMLElement|null>(null);
    const [value, setValue] = useState<unknown>('');
    const [fieldJob,setFieldJob]=useState<string|null>(null);
    const [instruction, setInstruction] = useState('');
    const [ack, setAck] = useState(false);
    const [confirmStart, setConfirmStart] = useState<LaunchSnapshot|null>(null);
    const [recordEdit,setRecordEdit]=useState<RecordEditTarget|null>(null);
    const [aiExample,setAiExample]=useState('');
    const [creating,setCreating]=useState<CreationTarget|null>(null);
    const [previewVersion,setPreviewVersion]=useState<number|null>(null);

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
    const selectWorkspace = (wid: string, nextDraft: Draft | null = null, nextAuthor=author,saveCurrent=true) => {
        if (nextDraft && String(nextDraft.id) !== String(wid)) throw new Error('Workspace identity mismatch');
        viewBuffers.current.set(viewKey(id,author),{section,collection,selected:selectedCharacter,subsection});
        if(saveCurrent)writeIdeaBuffer(id,{text,name,useIdea,creation});
        const view=viewBuffers.current.get(viewKey(wid,nextAuthor))||storedView(wid,nextAuthor);
        setSearch('');setSearchOpen(false);setRecordTarget(null);setCreating(null);setRecordEdit(null);setPreviewVersion(null);setAuthor(nextAuthor);setLaunchError('');
        setSection(view?.section||'overview');setCollection(view?.collection||emptyCollection);setSubsection(view?.subsection||{});setSelectedCharacter(view?.selected||'');setDossierOpen(false);
        const buffer=readIdeaBuffer(wid);
        restoredCreation.current=!!buffer;
        setText(buffer?.text??sessionStorage.getItem('workshop-idea:'+wid)??'');
        setName(buffer?.name||nextDraft?.name||'');setUseIdea(buffer?.useIdea||false);
        setCreation(buffer?.creation||{...structuredClone(defaultCreation),...nextDraft?.creation_settings});
        loadController.current?.abort();
        if (wid) localStorage.setItem('draftWorkspace', wid);
        else localStorage.removeItem('draftWorkspace');
        dispatchWorkspace({type: 'select', id: wid, draft: nextDraft, request: ++requestSequence.current});
        setEdit(null); setRemoval(null); setConfirmStart(null);
    };
    const switchView = (next:boolean) => {
        if(next===author)return;
        setSearch('');setSearchOpen(false);setRecordTarget(null);setCreating(null);setRecordEdit(null);setPreviewVersion(null);
        setCollection(storedView(id,next).collection||emptyCollection);
        setAuthor(next);
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
    useEffect(() => {
        const controller=new AbortController(), initialId=id;
        void api<typeof list>('/workspaces',undefined,'GET',controller.signal).then(items=>{
            if(controller.signal.aborted)return;
            setList(items);
            if(initialId && localStorage.getItem('draftWorkspace')===initialId && !items.some(w=>w.id===initialId)){
                selectWorkspace('',null,false);
            }
        }).catch(e=>{if(!controller.signal.aborted)toast.error(e.message)});
        return ()=>controller.abort();
    }, []);
    useEffect(() => {
        void refresh();
        return () => loadController.current?.abort();
    }, [id, author]);
    const savedCreation=JSON.stringify(draft?.creation_settings||{});
    useEffect(()=>{const saved=JSON.parse(savedCreation);if(!restoredCreation.current&&draft?.id===id&&(draft.author||!draft.version_id)){setCreation({...structuredClone(defaultCreation),...saved});setName(draft.name);restoredCreation.current=true;}},[id,savedCreation,draft?.id,draft?.author,draft?.version_id]);
    useEffect(()=>{if(!id||restoredCreation.current)setInputSaved(writeIdeaBuffer(id,{text,name,useIdea,creation}));},[id,text,name,useIdea,creation]);
    const { job: streamedJob, reconnecting } = useJob(draft?.job, refresh);
    // useJob synchronizes its source in an effect. A newly loaded workspace must
    // render its own job immediately, rather than briefly mounting the editor
    // toolbar with no job (or a different workspace's last streamed job).
    const job = (streamedJob?.id === draft?.job?.id ? streamedJob : draft?.job) ?? null;
    // Phase snapshots arrive over SSE before the draft view is refreshed. Read
    // persisted lineage at stage boundaries, without replacing the live job
    // with a possibly older HTTP snapshot or re-opening its event stream.
    useEffect(()=>{
        if(!id||job?.kind!=='draft_world'||!active(job)||!job.phase)return;
        const controller=new AbortController(), sequence=requestSequence.current, jobId=job.id;
        void api<Draft>(`/workspaces/${id}/draft?author=${author}`,undefined,'GET',controller.signal).then(next=>{
            if(!controller.signal.aborted&&requestSequence.current===sequence)
                dispatchWorkspace({type:'update',id,update:current=>current?.job?.id===jobId?{...next,job:current.job}:current});
        }).catch(()=>{/* SSE/reconnect owns connectivity; a later phase or completion refreshes again. */});
        return()=>controller.abort();
    },[id,author,job?.id,job?.kind,job?.phase,job?.status,job?.attempt_epoch]);
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
    const change = (body: Item) => body.operation==='add' ? setCreating({kind:String(body.kind),source:body.source as string|undefined,revision:draft?.revision||0}) : run(async () => { const updated=await api<Draft&{entity_id?:string}>(`/workspaces/${id}/draft`, { revision: draft?.revision, ...body }, 'PATCH'); await refresh();if(body.operation==='add'&&body.kind==='relationship'&&updated.entity_id)setRecordTarget({kind:'relationship',id:updated.entity_id}); });
    const generate = async (body: Item) => {
        if(operationGuard.current)return;
        operationGuard.current=true;setBusy(true);setEditError('');
        try {
            const j=await api<Job>(`/workspaces/${id}/draft/generate`,{revision:editRevision,preview:true,config:prefs.summary,api_key:apiKey,...body});
            setFieldJob(j.id);
            dispatchWorkspace({type:'update',id,update:d=>d?{...d,job:j}:d});
        } catch(e) {setEditError((e as Error).message)}
        finally {operationGuard.current=false;setBusy(false)}
    };
    const editBufferKey=(target:Target)=>`workshop-field:${id}:${target.kind}:${target.id}:${target.field}`;
    const openEdit = (target: Target) => {
        let saved:{value:unknown;structured:string;revision:number;instruction?:string;jobId?:string;visibility?:FieldPolicy}|null=null;
        try{saved=JSON.parse(sessionStorage.getItem(editBufferKey(target))||'null')}catch{/* isolated invalid UI buffer */}
        fieldTrigger.current=document.activeElement instanceof HTMLElement?document.activeElement:null;
        setPendingVisibility(saved?.visibility??null);setTimeValid(true);
        setEdit(target);setValue(saved?saved.value:target.value);setStructuredEdit(saved?saved.structured:JSON.stringify(target.value??null,null,2));setEditRevision(saved?.revision??draft?.revision??0);setEditError(saved&&saved.revision!==draft?.revision?'Мир изменился с момента ввода. Проверьте значение и явно разрешите сохранение в текущую версию.':'');setInstruction(saved?.instruction||'');setFieldJob(saved?.jobId||null);setAck(false);setRelated([]);if(target.field==='__character')void api<{kind:string;id:string}[]>(`/workspaces/${id}/draft/dependencies?kind=character&entity_id=${target.id}`).then(setRelated).catch(e=>toast.error(e.message));
    };
    useEffect(()=>{sessionStorage.setItem('workshop-section:'+id,section);sessionStorage.setItem(viewKey(id,author),JSON.stringify({section,collection,selected:selectedCharacter,subsection}))},[id,author,section,collection,selectedCharacter,subsection]);
    useEffect(()=>{if(edit)sessionStorage.setItem(editBufferKey(edit),JSON.stringify({value,structured:structuredEdit,revision:editRevision,instruction,jobId:fieldJob,visibility:pendingVisibility}))},[edit,value,structuredEdit,editRevision,instruction,fieldJob,pendingVisibility]);
    useEffect(()=>{
        if(!edit||!fieldJob||job?.id!==fieldJob||active(job)||loading||draft?.job?.status!==job.status)return;
        if(job.status==='error'||job.status==='stopped') {
            setEditError(job.error||'Изменение остановлено. Прежнее значение сохранено.');
            return;
        }
        if(job.status==='saved'&&job.phase!=='preview') {
            sessionStorage.removeItem(editBufferKey(edit));
            setFieldJob(null);setEdit(null);toast.success(`Поле «${edit.label}» сохранено`);
        }
    },[fieldJob,job?.id,job?.status,draft?.revision,draft?.job?.status,loading,edit]);
    const state = !!draft?.author===author ? draft?.state : null;
    const excludedVisibility=draft?.editor?.field_visibility_excluded;
    const fieldName=edit?.field.startsWith('fields.')?edit.field.slice(7):'';
    const canDeclareVisibility=!!(author&&state&&edit?.kind==='character'&&fieldName&&excludedVisibility&&!excludedVisibility.includes(fieldName));
    const existingVisibility=fromBinding(edit&&state?.card_field_facts?.[edit.id]?.[fieldName]||undefined);
    const fieldVisibility=pendingVisibility??existingVisibility;
    const visibilityDirty=canDeclareVisibility&&JSON.stringify(wirePolicy(fieldVisibility))!==JSON.stringify(wirePolicy(existingVisibility));
    const visibilityFacts:[string,string][]=canDeclareVisibility?Object.entries(state!.world.facts||{}).filter(([fid,f])=>
      f.secret||f.story_secret||f.visibility==='secret'||typeof fieldVisibility==='object'&&fieldVisibility.after.includes(fid))
      .map(([fid,f])=>[fid,String(f.text||'Факт без описания')]):[];
    const invalidVisibility=canDeclareVisibility&&typeof fieldVisibility==='object'&&
      (!fieldVisibility.after.length||fieldVisibility.after.some(fid=>!visibilityFacts.some(([key])=>key===fid)));
    const fieldDirty=!!edit&&(JSON.stringify(value)!==JSON.stringify(edit.value)||visibilityDirty);
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
        if (characterRefs.has(field))
            return characters.map(c => [c.id, c.name]);
        const group = field === 'scene_id' ? 'scenes' : field === 'fact_id' || field === 'fact_ids' ? 'facts' : field === 'source_event_id' ? 'events' : null;
        if (group)
            return Object.entries(state?.world[group] || {}).map(([k, v]) => [k, String(v.text || v.location || k)]);
        if (['location','location_id','location_ids'].includes(field)||field==='parent_id'&&edit?.kind!=='organizations') return (state?.locations || []).filter(p=>field!=='parent_id'||!invalidParents.has(p.id)).map(p=>[p.id,p.name]);
        if (field === 'organization_id'||field==='parent_id'&&edit?.kind==='organizations') return Object.entries(state?.world.organizations || {}).map(([id,v])=>[id,String(v.name || id)]);
        const linked=field==='pregnancy_id'?'pregnancies':field==='condition_id'?'conditions':field==='depends_on'?'scheduled_events':field==='replaced_by'||field==='life_fact_id'||field==='parentage_complete_fact_id'?'facts':field==='contact_id'?'contacts':null;
        if(linked)return Object.entries(state?.world[linked]||{}).map(([key,item])=>[key,recordTitle(linked,item,resolve,author)]);
        if (field === 'secret_existence') return [['hidden','Скрыть существование'],['discoverable','Показывать безымянный слот']];
        if (field === 'status')
            return (edit?.kind === 'knowledge' ? ['known', 'suspected', 'unknown', 'outdated', 'refuted', 'superseded'] : edit?.kind === 'thread' ? ['active', 'developing', 'dormant', 'resolved'] : ['active', 'closed']).map(x => [x, enumLabels[x] || x]);
        return null;
    };
    const capabilitySummary=(value:Item)=>{
        const abilities:Record<string,string>={conscious:'без сознания',can_perceive:'не воспринимает происходящее',can_act:'не может действовать',can_speak:'не может говорить',can_move:'не может передвигаться'};
        if(Object.keys(abilities).every(k=>value[k]===true))return 'Основные возможности сохранены';
        const limits=Object.entries(abilities).filter(([k])=>value[k]===false).map(([,label])=>label);
        return limits.length?'Ограничения: '+limits.join(', '):'Указанные возможности';
    };
    const row = (kind: string, eid: string, field: string, v: unknown, editable=true) => <div className="draft-field" key={field}><div className="draft-field-heading"><span>{kind==='character'&&field==='name'?'Имя':labels[field] || field.replace('fields.', '')}</span>{author && editable && (field.startsWith('fields.') || draft?.editor?.fields[kind]?.includes(field)) && <Button variant="ghost" size="sm" disabled={locked} aria-label={`Изменить ${labels[field] || field}`} onClick={() => {setStructuredEdit(JSON.stringify(v,null,2));openEdit({ kind, id: eid, field, value: v, label: labels[field] || field.replace('fields.', '') });}}>Изменить</Button>}</div>{v && typeof v==='object' ? <details><summary>{field==='capabilities'?capabilitySummary(v as Item):field==='calendar' ? enumLabels[String(((v as Item).profile as Item)?.system || 'gregorian')] : `Сведения · ${Array.isArray(v)?v.length:Object.keys(v).length}`}</summary><RuntimeValue field={field} value={v} resolve={resolve} author={author}/></details> : <RuntimeValue field={field} value={v} resolve={resolve} author={author}/>}</div>;
    const recordPreview=(kind:string)=>['relationship','objective_relations','fact','thread','event','scene','location','organizations'].includes(kind)?(eid:string,item:Item)=><RecordPreview {...{kind,item,characters,author}} id={eid} wid={id} knowledge={state?.world.knowledge||{}} sceneLabel={place(item.location)} currentScene={eid===state?.camera.scene_id} visibility={draft?.presentation?.thread_visibility?.[eid]} startPlace={kind==='location'&&eid===beginning?.location} relatedPeople={kind==='location'?Object.entries(state?.world.characters||{}).filter(([,c])=>c.location===eid).map(([cid])=>cid):kind==='organizations'?Object.values(state?.world.roles||{}).filter(r=>r.organization_id===eid&&r.status!=='closed').map(r=>r.actor_id):[]} organizationPlace={kind==='organizations'&&Array.isArray(item.location_ids)?item.location_ids.map(place).join(' · '):undefined} onQuickEdit={author&&kind==='fact'?()=>openEdit({kind:'fact',id:eid,field:'text',label:'Текст факта',value:item.text}):undefined} onOpen={openPerson}/>:undefined;
    const extensionFields=(key:string,eid:string,item:Item,inDossier=false)=>{
      const present=(v:unknown)=>v!=null && v!=='' && (typeof v!=='object'||Object.keys(v).length>0);
      const values=Object.entries(item).filter(([k])=>!['id','revision','source_turn','turn_id','provenance','applied'].includes(k));
      if(inDossier&&!author){
        // The surrounding row already names the person, subject and status.
        const caption=new Set(['status','actor_id','context',...(key==='roles'?['title','organization_id']:key==='residences'?['location_id']:key==='conditions'?['description']:['source_id','target_id','kind'])]);
        const extra=values.filter(([k,v])=>!caption.has(k)&&present(v));
        return <>{!!item.context&&<p className="workshop-literary">{String(item.context)}</p>}
          {extra.length>0&&<dl className="ww-reader-properties">{extra.map(([k,v])=><div key={k}><dt>{labels[k]||k}</dt><dd><RuntimeValue field={k} value={v} resolve={resolve}/></dd></div>)}</dl>}
          {!item.context&&!extra.length&&<p className="ww-dossier-note">Дополнительных сведений пока нет.</p>}</>;
      }
      const show=([k,v]:[string,unknown])=>row(key,eid,k,v);
      const optional=author&&inDossier?values.filter(([,v])=>!present(v)):[];
      const main=author&&!inDossier?values:values.filter(([,v])=>present(v));
      return <>{main.map(show)}
        {optional.length>0&&<details><summary>Дополнительные поля · {optional.length}</summary>{optional.map(show)}</details>}
        {author&&<details><summary>Технические сведения</summary><pre>{JSON.stringify(item,null,2)}</pre></details>}</>;
    };
    const dossierRecords=(kind:'roles'|'residences'|'conditions'|'objective_relations')=>{
      const rows=Object.entries(state?.world[kind]||{}).filter(([,r])=>kind==='objective_relations'
        ? [r.source_id,r.target_id].includes(selectedCharacter)
        : r.actor_id===selectedCharacter||(Array.isArray(r.character_ids)&&r.character_ids.includes(selectedCharacter)));
      if(!rows.length)return null;
      const describe=(r:Item)=>{
        if(kind==='roles')return {title:String(r.title||'Роль без названия'),subtitle:r.organization_id?resolve('organization_id',r.organization_id):null};
        if(kind==='residences')return {title:place(r.location_id),subtitle:null};
        if(kind==='conditions')return {title:String(r.description||'Обстоятельство'),subtitle:null};
        return {title:recordTitle(kind,r,resolve,author),subtitle:null};
      };
      return <DossierRecords key={kind+selectedCharacter+author} heading={extensionGroups[kind]} entries={rows} describe={describe}
        render={(eid,r)=>extensionFields(kind,eid,r,true)}/>;
    };
    const extension = (key:string,title:string,filter?:(item:Item)=>boolean) => <RecordCollection onClose={()=>setRecordTarget(null)} key={id+key+author} entries={Object.entries(state?.world[key]||{}).filter(([,item])=>!filter||filter(item))} initialSelected={recordTarget?.kind===key?recordTarget.id:undefined} groupBy={key==='residences'?item=>resolve(residenceGrouping==='actor'?'actor_id':'location_id',item[residenceGrouping==='actor'?'actor_id':'location_id'])||'Не указано':undefined} tools={key==='residences'?<label>Группировать по <select aria-label="Группировка проживания" value={residenceGrouping} onChange={e=>setResidenceGrouping(e.target.value)}><option value="actor">персонажам</option><option value="location">местам</option></select></label>:undefined} title={title} kind={key} searchText={item=>[recordTitle(key,item,resolve,author),item.text,item.description,item.context,...Array.isArray(item.aliases)?item.aliases:[]].filter(Boolean).join(' ')} card={recordPreview(key)} storageKey={`workshop:${id}:${key}:${author}`} disabled={locked} describe={item=>recordTitle(key,item,resolve,author)} render={(eid,item)=>extensionFields(key,eid,item)}/>;
    const editRecord=(kind:string,eid:string,item:Item,title:string)=>{
      const available=kind==='character'?{name:item.name,...Object.fromEntries(Object.entries(item.fields as Item||{}).filter(([k])=>!['Сейчас','Чего хочет','Намерения','Обязательства'].includes(k)).map(([k,v])=>['fields.'+k,v]))}:Object.fromEntries(Object.entries(item).filter(([key])=>draft?.editor?.fields[kind]?.includes(key)));
      setRecordEdit({kind,id:eid,title,values:available,revision:draft?.revision||0});
    };
    const entity = (kind: string, eid: string, item: Item) => <div className="draft-entity" key={eid}>{author&&<Button variant="outline" disabled={locked} onClick={()=>editRecord(kind,eid,item,kind==='character'?'Редактировать карточку':'Редактировать запись')}>Редактировать запись</Button>}
 {kind === 'character' ? <>{row(kind, eid, 'name', item.name)}{Array.isArray(item.aliases) && item.aliases.length > 0 ? row(kind, eid, 'aliases', item.aliases) : null}{Object.entries(item.fields as Record<string, string>).filter(([k]) => !['Сейчас', 'Чего хочет', 'Намерения'].includes(k)).map(([k, v]) => row(kind, eid, 'fields.' + k, v))}<details><summary>Состояние, цели и намерения</summary>{[...fields.actor,...Object.keys(state?.world.characters[eid] || {}).filter(f=>!fields.actor.includes(f) && !!draft?.editor?.fields.actor?.includes(f))].map(f => row('actor', eid, f, state?.world.characters[eid]?.[f] ?? null))}<details><summary>Технические сведения состояния</summary><pre>{JSON.stringify(state?.world.characters[eid],null,2)}</pre></details></details></> : [...fields[kind],...Object.keys(item).filter(f=>!fields[kind].includes(f) && !['id','revision','source_turn','time_semantics'].includes(f))].map(f => row(kind, eid, f, (f in item ? item[f] : (['secret','story_secret'].includes(f) ? false : f==='secret_existence' ? 'hidden' : ['secret_subject_ids','secret_keeper_ids','secret_biography_ids','character_ids', 'visible_to_ids', 'participants', 'witnesses', 'fact_ids', 'evidence'].includes(f) ? [] : ''))))}
 {author && <div className="actions">{kind === 'character' && <Button variant="outline" disabled={locked} onClick={() => { setEdit({ kind, id: eid, field: '__character', value: '', label: 'Перегенерировать персонажа целиком' }); setInstruction(''); setAck(false); setRelated([]); void api<{
        kind: string;
        id: string;
    }[]>(`/workspaces/${id}/draft/dependencies?kind=character&entity_id=${eid}`).then(setRelated).catch(e => toast.error(e.message)); }}>Новая версия персонажа</Button>}<Button variant="ghost" disabled={locked} onClick={() => void run(async () => { const deps = await api<{
        kind: string;
        id: string;
    }[]>(`/workspaces/${id}/draft/dependencies?kind=${kind}&entity_id=${eid}`); setRemoval({ kind, id: eid, deps }); })}>Удалить</Button></div>}
 </div>;
    const editContext=()=>{
        if(!edit)return workspaceTitle;
        const personName=characters.find(c=>c.id===edit.id)?.name;
        if(personName)return personName;
        const placeName=state?.locations.find(l=>l.id===edit.id)?.name;
        if(placeName)return placeName;
        const groups:Record<string,string>={fact:'facts',thread:'threads',event:'events',relationship:'relationships'};
        const group=groups[edit.kind]||edit.kind;
        const item=state?.world[group]?.[edit.id];
        return item?(group==='relationships'?`${person(item.source_id)} → ${person(item.target_id)}`:recordTitle(group,item,resolve,author)):workspaceTitle;
    };
    const dossierKnowledge=(cid:string)=>{
      const beliefs=Object.entries(state?.world.knowledge||{}).filter(([,k])=>k.actor_id===cid);
      const byFact=new Map(beliefs.map(([,k])=>[k.fact_id,k]));
      const available=facts.filter(([fid,f])=>['character_ids','secret_subject_ids','secret_keeper_ids','secret_biography_ids']
        .some(key=>Array.isArray(f[key])&&f[key].includes(cid))||['known','suspected'].includes(String(byFact.get(fid)?.status)));
      return [
        ...available.map(([fid,f])=><details className="workshop-detail" key={'fact:'+fid}>
          <summary>{short(f.text,150)}</summary>{author?entity('fact',fid,f):<p>{String(f.text)}</p>}
          {!author&&byFact.has(fid)&&<small>{byFact.get(fid)?.status==='known'?'Известно персонажу':'Персонаж подозревает'}</small>}
        </details>),
        ...(author?beliefs.map(([eid,k])=><div key={'belief:'+eid} className="ww-dossier-belief">{entity('knowledge',eid,k)}</div>):[])
      ];
    };
    const collectionRecords=(kind:string,title:string,entries:[string,Item][],describe:(item:Item)=>string,scope='')=> <RecordCollection onClose={()=>setRecordTarget(null)} initialSelected={recordTarget?.kind===kind?recordTarget.id:undefined} key={id+kind+author+scope} {...{entries,title,kind,describe}} card={kind==='event'?(eid,item)=><>{draft?.presentation?.event_periods?.[eid]&&<span className="ww-record-badge">{{today:'Сегодня',past:'Предыстория',future:'Позднее стартового времени'}[draft.presentation.event_periods[eid]]}</span>}{recordPreview(kind)?.(eid,item)}</>:recordPreview(kind)} selectionEntries={kind==='relationship'?relations:undefined} searchText={item=>[describe(item),item.text,item.description,item.context,...Array.isArray(item.aliases)?item.aliases:[]].filter(Boolean).join(' ')} caption={kind==='event'?(eid)=>draft?.presentation?.event_times?.[eid]||'Дата неизвестна':kind==='scene'?(eid)=>draft?.presentation?.scene_times?.[eid]||'Дата неизвестна':undefined} disabled={locked} storageKey={`workshop:${id}:${kind}:${author}${scope?':'+scope:''}`} onAdd={author?()=>void change({operation:'add',kind,source:kind==='relationship'?scope:undefined}):undefined} render={(eid,item)=>author?entity(kind,eid,item):<RuntimeValue field="record" value={item} resolve={resolve}/>}/>;
    const validateIdea = async () => {
        await api('/world-creation/validate',{workspace_id:id||null,name,revision:draft?.revision||0,
          task:'world',text,use_idea:useIdea,creation_settings:creation,config:prefs.summary});
    };
    const startIdea = async () => {
        if(operationGuard.current||active(job))return;
        operationGuard.current=true;setBusy(true);setLaunchError('');
        let wid=id;
        try {
            let current=draft;
            if(!current) {
                if(wid)throw new Error('Дождитесь загрузки черновика.');
                const w=await api<Workspace>('/workspaces',{name:name.trim()||'Новая история'});
                wid=w.id;current={id:wid,name:w.name,revision:w.revision,version_id:null,state:null,
                  validation:{errors:[],warnings:[]},import_warnings:[],source_text:'',outline:'',history:[],job:null};
                // Adopt identity before the second request. A failed/retried request reuses it.
                writeIdeaBuffer(wid,{text,name:w.name,useIdea,creation});
                setList(items=>[w,...items]);selectWorkspace(wid,current);
                try{sessionStorage.removeItem('workshop-idea-form:');sessionStorage.removeItem('workshop-idea:')}catch{/* The open form remains usable if browser storage is unavailable. */}
            }
            const j=await api<Job>(`/workspaces/${wid}/draft/generate`,{revision:current.revision,task:'world',text,use_idea:useIdea,creation_settings:creation,config:prefs.summary,api_key:apiKey});
            selectWorkspace(wid,{...current,job:j},author,false);
            setEditingIdea(false);setSection('idea');
        } catch(e) {
            setLaunchError((e as Error).message);setEditingIdea(true);
            // A lost generate response may still have started a job. Reconcile before another launch.
            if(wid){const next=await api<Draft>(`/workspaces/${wid}/draft?author=${author}`).catch(()=>null);if(next){selectWorkspace(wid,next,author,false);setLaunchError((e as Error).message);if(next.job)setEditingIdea(false)}}
            throw e;
        } finally {operationGuard.current=false;setBusy(false)}
    };
    const launchSnapshot=():LaunchSnapshot=>({wid:id,revision:draft?.revision||0,version:draft?.version_id||0,
      warning:!!draft?.start_warning||!!draft?.validation.warnings.length,stale:draft?.review?.status==='stale',running:active(job),jobId:job?.id,
      title:String(state?.campaign.title||draft?.name||''),technical:!!draft?.technical_valid,pending:!!draft?.pending_editor,
      warnings:[...(draft?.start_warning?[draft.start_warning]:[]),...(draft?.validation.warnings||[])],
      summary:[['Версия',`#${draft?.version_id} · ревизия ${draft?.revision}`],['Главный герой',draft?.presentation?.launch?.protagonist||'Не определён'],['Управляемый персонаж',draft?.presentation?.launch?.controlled_actor||'Не определён'],['Режим камеры',draft?.presentation?.launch?.camera_mode||'Не определён'],['Носитель POV',draft?.presentation?.launch?.pov||'Не определён'],['Фокус камеры',draft?.presentation?.launch?.subject||'Не определён'],['Стартовая сцена',String(beginning?.text||state?.camera.scene_id||'Не выбрана')],['Место',place(beginning?.location)],['Когда',weekTime()]]});
    const invalidParents=new Set(edit?.kind==='location'&&edit.field==='parent_id'?[edit.id]:[]);
    if(invalidParents.size){let changed=true;while(changed){changed=false;for(const location of state?.locations||[])if(invalidParents.has(String(location.parent_id))&&!invalidParents.has(location.id)){invalidParents.add(location.id);changed=true}}}
    const familyKinds=new Set(['spouse','partner','engaged','parent','adoptive_parent','guardian','foster_parent','step_parent','sibling']);
    const familyIds=[...new Set(Object.values(state?.world.objective_relations||{}).filter(r=>familyKinds.has(String(r.kind))&&r.status!=='closed').flatMap(r=>[String(r.source_id),String(r.target_id)]))].filter(cid=>characters.some(c=>c.id===cid));
    const characterGroups=[...(familyIds.length?[{id:'family',label:'Семья',ids:familyIds}]:[]),...Object.entries(state?.world.organizations||{}).map(([oid,o])=>({id:'org:'+oid,label:String(o.name),ids:Object.values(state?.world.roles||{}).filter(role=>role.organization_id===oid&&role.status!=='closed').map(role=>String(role.actor_id)).filter(cid=>characters.some(c=>c.id===cid))})).filter(g=>g.ids.length)];
    const searchResults=workshopSearch(state,search);
    const selectedCard=characters.find(c=>c.id===selectedCharacter) as WorkshopCharacter|undefined;
    const navigate=(next:WorkshopSection)=>{setMode('quick');setRecordTarget(null);setSection(next);if(next==='idea')setEditingIdea(true)};
    const pageHeader=(title:string,description:string)=><header className="ww-page-head"><div><p className="ww-eyebrow">Мастерская миров</p><h1>{title}</h1><p>{description}</p></div></header>;
    const tab=(key:string,items:[string,string][])=>{const value=subsection[key]||items[0][0];return <SectionTabs label={key} value={value} onChange={value=>setSubsection({...subsection,[key]:value})} items={items.map(([id,label])=>({id,label}))}/>};
    const currentSub=(key:string,fallback:string)=>subsection[key]||fallback;
    const reviewLink=(path:string)=>{
        const parts=path.split('/').slice(1).map(v=>v.replace(/~1/g,'/').replace(/~0/g,'~'));
        const root=parts[0];const group=root==='world'?parts[1]:root;
        const eid=root==='world'?parts[2]:group==='characters'?(state?.characters.find(c=>c.id===parts[1])||state?.characters[Number(parts[1])])?.id:group==='locations'?(state?.locations.find(l=>l.id===parts[1])||state?.locations[Number(parts[1])])?.id:undefined;
        const field=root==='world'?parts[3]:parts[2];
        if(group==='characters'&&eid&&characters.some(c=>c.id===eid))return {label:person(eid)+(field?' · '+(labels[field]||field):''),open:()=>openPerson(eid)};
        const routes:Record<string,[WorkshopSection,string,string,string]>={locations:['world','Места','locations','location'],organizations:['world','Места','organizations','organizations'],residences:['world','Места','residences','residences'],roles:['world','Места','roles','roles'],conditions:['world','Места','conditions','conditions'],possessions:['world','Места','possessions','possessions'],contacts:['world','Места','contacts','contacts'],relationships:['relations','Связи','feelings','relationship'],objective_relations:['relations','Связи','objective_relations','objective_relations'],pregnancies:['relations','Связи','pregnancies','pregnancies'],facts:['knowledge','Знания','facts','fact'],knowledge:['knowledge','Знания','knowledge','knowledge'],threads:['story','Сюжеты','threads','thread'],scenes:['timeline','Хронология','scenes','scene'],events:['timeline','Хронология','events','event'],scheduled_events:['timeline','Хронология','scheduled_events','scheduled_events'],reproductive_events:['timeline','Хронология','reproductive_events','reproductive_events'],naming_decisions:['timeline','Хронология','naming_decisions','naming_decisions']};
        const route=routes[group];
        const item=group==='locations'?state?.locations.find(l=>l.id===eid):eid?state?.world[group]?.[eid]:null;
        if(route&&item&&eid)return {label:short(group==='locations'?String(item.name):recordTitle(group,item,resolve,author),100)+(field?' · '+(labels[field]||field):''),open:()=>{setSection(route[0]);if(route[1])setSubsection({...subsection,[route[1]]:route[2]});setRecordTarget({kind:route[3],id:eid})}};
        if(['campaign','world_clock','camera','protagonist_id','controlled_actor_id'].includes(root))return {label:'Сцена и правила',open:()=>navigate('start')};
        return null;
    };
    const reviewLinks=(paths:(string|null|undefined)[])=><div className="ww-review-links">{[...new Set(paths.filter((v):v is string=>!!v))].map(path=>{const link=reviewLink(path);return link?<button key={path} onClick={link.open}>{link.label} →</button>:null})}</div>;
    const overviewIssues=reviewIssues(draft?.review?.issues,draft?.validation,draft?.import_warnings);
    const allIssues=[...new Set([...(draft?.validation.errors||[]),...(draft?.validation.warnings||[]),...(draft?.import_warnings||[]),...(draft?.review?.issues||[]).map(issue=>issue.message)])];
    const viewChanging=!!draft?.state&&!!draft.author!==author;
    const showIdea=(!state&&!viewChanging)||section==='idea';
    // The original creative brief may explicitly spell out future plot twists.
    // Preserve the author's input locally, but never mount it in an existing world's reader view.
    const canOpenBrief=author||!id||!!draft&&!state&&!viewChanging&&!draft.version_id;
    const workspaceTitle=String(state?.campaign.title||draft?.name||'Новая история');
    const ideaGenerationVisible=showIdea&&job?.kind==='draft_world'&&!!draft&&!editingIdea;
    const resumeAction=((job?.resumable && !(job as Job & {fragment_recovery?:boolean;transport_blocked?:boolean}).fragment_recovery && !(job as Job & {transport_blocked?:boolean}).transport_blocked) || (draft?.review?.status==='stale' && job?.status==='saved' && job.kind!=='draft_editor')) && <Button className={ideaGenerationVisible?"fl-primary":undefined} disabled={locked} onClick={()=>void resume({})}>{job?.kind==='draft_editor' ? 'Продолжить AI-редактирование' : draft?.creative_status && draft.creative_status !== 'applied' ? 'Продолжить творческое развитие' : draft?.review && !(job as Job & {transport_incomplete?:boolean})?.transport_incomplete ? 'Повторить проверку' : 'Продолжить сохранённую генерацию'}</Button>;
    const emptyRetryAction=job?.empty_retry_token && <Button className={ideaGenerationVisible?"fl-primary":undefined} disabled={locked} onClick={()=>setEmptyRetry({token:job.empty_retry_token!,epoch:job.attempt_epoch || 0})}>Повторить после сбоя провайдера</Button>;
    const generationActivity = (resuming || active(job)) && <section className="workshop-generating" role="status" aria-live="polite" aria-label="Ход проверки мира">
        <span className="workshop-pulse"/><div><strong>{resuming ? 'Запускаем повторную проверку…' : reconnecting ? 'Восстанавливаем соединение…' : status[0]}</strong><p>{resuming ? 'Отправляем запрос на продолжение сохранённого задания.' : reconnecting ? 'Ожидаем связь с сервером. Генерация продолжает выполняться.' : status[1]}</p>{!reconnecting && !!job?.progress_chars && !['validating','saving'].includes(job.phase || '') && <small>Получено {job.progress_chars.toLocaleString('ru-RU')} символов ответа</small>}</div>
        <Button variant="ghost" disabled={resuming || busy} onClick={() => void run(async () => {await api(`/jobs/${job!.id}/stop`, {}); refresh();})}>Остановить</Button>
      </section>;
    return <main className="world-workshop" aria-busy={loading} data-workspace-id={id} data-draft-workspace-id={draft?.id || ''}>
    <WorkshopShell workspaceId={id} section={showIdea?'idea':section} onSection={navigate} title={workspaceTitle} revision={draft?.revision} loading={loading} busy={busy} author={author} onAuthor={()=>author?switchView(false):authorAcknowledged?switchView(true):setAuthorAsk(true)} onStart={()=>setConfirmStart(launchSnapshot())} startLabel={draft?.games?.length?'Начать игру из этой версии':active(job)?'Остановить проверку и начать':draft?.start_warning?'Начать с предупреждениями':previousWorld?'Начать игру в предыдущем мире':'Подтвердить мир и начать игру'} canStart={!!state&&!busy&&!loading&&!!draft?.technical_valid} counts={{characters:characters.length,world:state?.locations.length,relations:relations.length,story:threads.length,knowledge:facts.length,review:allIssues.length}} onDrafts={()=>{setDraftsOpen(true);void api<WorkspacePick[]>('/workspaces').then(setList).catch(e=>toast.error(e.message))}} onContinue={draft?.games?.length?()=>onGame(draft.games![0].world,draft.games![0].save):undefined} onBack={onBack} onSettings={onSettings} onSearch={()=>setSearchOpen(true)}>
    {mode==='scenario'?<><Button className="workshop-back" variant="ghost" onClick={()=>setMode('quick')}>← Генератор мира</Button><Preparation key={id} initialWorkspaceId={id} onWorkspaceChange={wid=>{selectWorkspace(wid);setSection('idea')}} worldSettings={<WorldCreationSettings value={creation} onChange={setCreation} disabled={locked}/>} prefs={prefs} apiKey={apiKey} onWorld={onWorld} onDraft={wid=>{selectWorkspace(wid);setUseIdea(true);setMode('quick')}}/></>:<>
    {previousWorld&&<section className="ww-panel" role="status"><h2>Ранее сохранённый мир</h2><p>Новая генерация не завершена. Сейчас показана предыдущая сохранённая версия; она не заменена неполным ответом.</p><button className="ww-text-button" onClick={()=>navigate('review')}>Продолжить генерацию →</button></section>}
    {!previousWorld&&job?.status==='error'&&section!=='review'&&section!=='idea'&&section!=='ai'&&<section className="ww-panel" role="status"><h2>Задание требует внимания</h2><p>Полученный результат сохранён. Откройте проверку, чтобы увидеть причину и доступные способы продолжения.</p><button className="ww-text-button" onClick={()=>navigate('review')}>Открыть проверку →</button></section>}
    {viewChanging&&<p role="status">Загружаем выбранный вид мира…</p>}
    {showIdea&&!canOpenBrief&&!!state&&(!job||job.kind!=='draft_world'||editingIdea)&&<section className="ww-panel"><p className="ww-eyebrow">Замысел мира</p><h1>{workspaceTitle}</h1><ReadableText text={String(state.campaign.public_description||'')} /><p>Исходный замысел может содержать неизвестные герою тайны.</p><button className="ww-soft" onClick={()=>authorAcknowledged?switchView(true):setAuthorAsk(true)}>Открыть замысел автора</button></section>}
    {showIdea&&canOpenBrief&&mode==='quick'&&(job?.kind==='idea'||job?.kind==='summary')&&<section className="ww-panel"><h2>Работа со Сценаристом</h2><p>Сценарий и выжимка этого мира доступны в редакторе. {active(job)?'Генерация продолжается после закрытия страницы.':'Сохранённый результат можно открыть и продолжить.'}</p><button className="ww-soft" onClick={()=>setMode('scenario')}>Вернуться к Сценаристу</button></section>}
    {showIdea&&canOpenBrief&&mode!=='quick'&&<>{pageHeader('Придумай свою историю','Свободный замысел станет миром, который можно прочитать, изменить и проверить перед началом игры.')}
      <nav className="workshop-paths" aria-label="Способ создания">
        <button className={mode === 'quick' ? 'selected' : ''} onClick={() => setMode('quick')}>По моей идее</button>
        <button onClick={() => setMode('scenario')}>Со Сценаристом</button>
        <button className={mode === 'import' ? 'selected' : ''} onClick={() => setMode('import')}>Импортировать</button>
      </nav>
      </>}
      <Dialog open={draftsOpen} onOpenChange={setDraftsOpen}><DialogContent><DialogHeader><DialogTitle>Мои черновики</DialogTitle><DialogDescription>Выберите мир, создайте новый или восстановите удалённый.</DialogDescription></DialogHeader>
      <details className="workshop-continue" open><summary>Мои черновики {draft ? `· ${draft.name}` : ''}</summary>
        <div className="workshop-draft-list">
          <button disabled={locked} className={!id ? 'selected' : ''} onClick={() => { selectWorkspace('',null,false);  setDraftsOpen(false); }}>+ Новая история</button>
          {list.map(w => <div className="workshop-draft-row" data-workspace-id={w.id} key={w.id}>
            <button aria-label={w.name} aria-describedby={`draft-meta-${w.id}`} disabled={locked} className={id === w.id ? 'selected' : ''} onClick={() => { selectWorkspace(w.id,null,false); setDraftsOpen(false); }}>{w.name}<small id={`draft-meta-${w.id}`}>Ревизия {w.id===id?draft?.revision??w.revision:w.revision}{w.id===id?' · Открыт':''}</small></button>
            <Button variant="ghost" size="sm" aria-label={`Удалить черновик «${w.name}»`} disabled={locked} onClick={() => {setDeleteError('');setDeleteDraft({...w,revision:w.id===id?draft?.revision??w.revision:w.revision})}}><Trash2 size={16}/></Button>
          </div>)}
        </div>
        <details className="workshop-trash" onToggle={e => { if (e.currentTarget.open) void api<WorkspacePick[]>('/workspaces?deleted=true').then(setRemoved).catch(err => toast.error(err.message)); }}><summary>Удалённые черновики</summary>
          {removed.length === 0 ? <p>Корзина пуста.</p> : removed.map(w => <div className="workshop-draft-row" data-workspace-id={w.id} key={w.id}><span>{w.name}</span><Button variant="ghost" size="sm" disabled={locked} onClick={() => void run(async () => { await api(`/workspaces/${w.id}/restore`,{revision:w.revision}); setList(await api<WorkspacePick[]>('/workspaces')); setRemoved(await api<WorkspacePick[]>('/workspaces?deleted=true')); selectWorkspace(w.id); toast.success('Черновик восстановлен'); })}>Восстановить</Button></div>)}
        </details>
      </details>
      </DialogContent></Dialog>
      {showIdea&&job?.kind==='draft_world'&&draft&&!editingIdea&&<IdeaGeneration job={job} draft={draft} activity={generationActivity} recoveryActions={<>{resumeAction}{emptyRetryAction}</>} title={workspaceTitle} description={String(state?.campaign.public_description||'')} onEditor={()=>{setSection('overview');if(!author){if(authorAcknowledged)switchView(true);else setAuthorAsk(true)}}} onEdit={()=>setEditingIdea(true)}/>}
      {(showIdea||section==='review'||section==='ai'&&job?.kind==='draft_editor')&&<div className={showIdea?"atelier-scope atelier-recovery":undefined}>
      {job?.status==='error' && (job as Job & {transport_incomplete?:boolean}).transport_incomplete && <section role="status"><h3>Восстановление ответа</h3><p>Полученный ответ сохранён. Продолжение проверит сборку, запросит недостающий конец при необходимости и завершит проверку мира. Полный проверенный мир ещё не готов.</p></section>}
      {!ideaGenerationVisible&&resumeAction}
      {draft?.creative_status && ['rejected','cancelled','interrupted'].includes(draft.creative_status) && !active(job) && <p role="status">Творческое развитие не завершено. Последний кандидат сохранён; его можно открыть в редакторе.</p>}
      {job?.response_diagnostic?.code === 'provider_http_rejection' && job.response_diagnostic.http_status === 400 && !active(job) && <p className="workshop-hint">HTTP-отказ не применён к миру. Перед продолжением проверь причину: для ошибки параметров нужно исправить настройки или сборку запроса. Неизменённый запрос с известной причиной HTTP 400 повторно не отправляется.</p>}
      {!ideaGenerationVisible&&emptyRetryAction}
      <Dialog open={!!emptyRetry} onOpenChange={open=>{if(!open)setEmptyRetry(null)}}><DialogContent><DialogHeader><DialogTitle>Повторная проверка после сбоя</DialogTitle><DialogDescription>Провайдер завершил запрос без текста. Если временный сбой устранён, можно подтвердить одну новую проверку сохранённого мира. Это новый запрос, который может быть оплачен. Предыдущие ответы и расходы сохранятся, общий бюджет не сбрасывается. Каждому повтору нужно новое подтверждение; автоматических повторов не будет.</DialogDescription></DialogHeader><div className="workshop-dialog-actions"><Button variant="ghost" onClick={()=>setEmptyRetry(null)}>Отмена</Button><Button disabled={locked} onClick={()=>{if(!emptyRetry)return;const retry=emptyRetry;setEmptyRetry(null);void resume({retry_empty_response:retry.token,expected_epoch:retry.epoch})}}>Подтвердить одну повторную проверку</Button></div></DialogContent></Dialog>
      {job?.resumable && <p className="workshop-hint">Модель и Thinking генерации закреплены за заданием. Смысловая проверка выполняется с Thinking Off; из текущих настроек применяются контекст и потолок ответа. Общий бюджет не сбрасывается.</p>}
      {(job as Job & {transport_blocked?:boolean})?.transport_blocked && <p role="alert">Сборка остановлена: повреждены исходные данные или нет безопасной границы для повтора. Скачайте диагностику; автоматическая замена сохранённых частей запрещена.</p>}
      {(job as Job & {fragment_recovery?:boolean})?.fragment_recovery && <details><summary>Повторить проблемное продолжение</summary><p>Предыдущие части останутся неизменными. Отклонённая часть сохранится в диагностике; новый запрос может быть оплачен.</p><Button disabled={locked} onClick={()=>void resume({retry_last_fragment:true})}>Запросить только последнее продолжение</Button></details>}
      {(job?.status === 'error' || job?.status === 'stopped') && <div>{author && <Button variant="outline" onClick={()=>void run(async()=>{download(JSON.stringify(await api(`/workspaces/${id}/draft/raw`),null,2),'generation-response.json');})}>Скачать исходный ответ и диагностику</Button>}
      {(job as Job & {unknown_outcome?:boolean}).unknown_outcome && <details><summary>Восстановить запрос с неизвестным исходом</summary><p>Провайдер мог списать оплату. Повтор может быть оплачен ещё раз; полученный текст останется в истории.</p><Button disabled={locked} onClick={()=>void resume({acknowledge_unknown:true})}>Повторить с возможной повторной оплатой</Button></details>}</div>}
      {!resuming && !active(job) && draft?.review && ['failed','running','not_started','stale'].includes(draft.review.status) && <section className="workshop-review" role="status"><h3>Смысловая проверка не завершена</h3><p>Мир сохранён. Автоматическая проверка не завершилась. Это не установленная ошибка поля мира.</p><p>{draft.review.reason || 'При технической готовности можно начать с предупреждениями без повторной проверки.'}</p></section>}

      {draft?.start_warning && <p role="status">{draft.start_warning} Можно начать с предупреждениями.</p>}
      {draft?.start_block_reason && <p role="alert">Запуск заблокирован: {draft.start_block_reason}</p>}
      {!state && draft?.version_id && !(job as Job & {transport_incomplete?:boolean})?.transport_incomplete && job && <Button variant="outline" onClick={()=>authorAcknowledged ? switchView(true) : setAuthorAsk(true)}>Открыть результат в редакторе автора</Button>}
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
      </div>}
      {showIdea&&launchError&&<p role="alert" className="workshop-error">{launchError} {id?'Черновик сохранён; повтор использует тот же мир.':'Замысел остаётся в открытой форме.'}</p>}
      {showIdea&&canOpenBrief&&mode==='quick'&&(!job||job.kind!=='draft_world'||editingIdea)&&!active(job)&&!resuming&&<IdeaAtelier key={id} id={id} name={name||draft?.name||''} text={text} useIdea={useIdea} creation={creation} disabled={locked} saved={inputSaved} onName={setName} onText={setText} onScenario={setUseIdea} onCreation={setCreation} validate={validateIdea} launch={startIdea} onMethod={setMode} onBack={state?()=>{setEditingIdea(false);setSection('overview')}:undefined}/>}
      {showIdea && canOpenBrief && mode==='import' && <section className="workshop-inspiration">
        <div className="workshop-inspiration-head"><span className="workshop-step">01 · ЗАМЫСЕЛ</span><h2>{mode === 'import' ? 'Загрузи готовую выжимку' : 'С чего начинается история?'}</h2></div>
        <p>{mode === 'import' ? 'Подойдёт .md, .txt или готовый .json мира. Можно вставить текст выжимки ниже.' : 'Пиши свободно, как Сценаристу: персонажи, атмосфера, отношения, важные события. Пробелы генератор заполнит сам.'}</p>

        {mode === 'import' && <Input type="file" accept=".md,.txt,.json" disabled={locked} aria-label="Файл мира" onChange={e => { const f = e.target.files?.[0]; if (f) void run(async () => {const content = await f.text(); setText(content); setImportFormat(f.name.toLowerCase().endsWith('.json') ? 'json' : 'text'); setImportFile(f.name);}); }}/ >}
        {mode === 'import' && <p role="status">Распознано: {detectedImport.format === 'json' ? detectedImport.error ? 'JSON (ошибка)' : 'JSON World State' : 'текстовая выжимка'}{importFile && ` · ${importFile}`}{importFile && importFormat === 'json' && <> · Будет импортирован готовый World State. <Button variant="ghost" disabled={locked} onClick={() => {setImportFormat('text'); setImportFile('');}}>Вставить текст выжимки</Button></>}</p>}
        {mode === 'import' && detectedImport.error && <p className="workshop-error" role="alert">{detectedImport.error}</p>}
        {!id && <Input aria-label="Название черновика" value={name} onChange={e => setName(e.target.value)} placeholder="Название истории (можно изменить позже)" />}
                {<label>Содержимое файла или текст выжимки<Textarea className="workshop-idea-input" value={text} onChange={e => {setText(e.target.value); setImportFile(''); setImportFormat('text');}} aria-label="Описание мира или текст импорта" placeholder={mode === 'import' ? 'Вставь здесь текст выжимки или JSON мира…' : 'Например: современная клиника. Я играю за врача. Придумай важных коллег и напряжённые, но живые отношения. Сейчас четверг, 14:00…'} /></label>}
        {draft && mode!=='import' && <label className="workshop-scenario-option"><input type="checkbox" checked={useIdea} onChange={e => setUseIdea(e.target.checked)}/> Взять за основу сценарий этого черновика</label>}
        <div className="workshop-create-actions">
          <Button disabled={locked || (!text.trim() && (mode==='import'||!useIdea)) || (mode === 'import' && !!detectedImport.error)} onClick={() => void run(async () => {
            if (mode === 'import' && detectedImport.error) throw new Error(detectedImport.error);
            let current = draft; let wid = id;
            if (!current) {
              const w = await api<Workspace>('/workspaces', {name: name.trim() || 'Новая история'});
              wid = w.id; current = {id: wid, name: w.name, revision: w.revision, version_id: null, state: null,
                validation: {errors: [], warnings: []}, import_warnings: [], source_text: '', outline: '', history: [], job: null};
              setList(items => [w, ...items]);selectWorkspace(wid,current);
            }
            if (mode === 'import') {
              const imported = await api<Draft>(`/workspaces/${wid}/draft/import`, {text, format: detectedImport.format, revision: current.revision});
              const opened = author ? await api<Draft>(`/workspaces/${wid}/draft?author=true`) : imported;
              selectWorkspace(wid, opened);
            }
            else {
              const j = await api<Job>(`/workspaces/${wid}/draft/generate`, {revision: current.revision, task: 'world', text, use_idea: useIdea, creation_settings: creation, config: prefs.summary, api_key: apiKey});
              sessionStorage.setItem('workshop-idea:'+wid,text);
              selectWorkspace(wid, {...current, job: j});
            }
            if(!id)sessionStorage.removeItem('workshop-idea:');
            setEditingIdea(false);setSection('overview');
            if (mode === 'import' && detectedImport.format === 'json') {setText(''); setImportFormat('text'); setImportFile('');}
          })}>{mode === 'import' ? 'Открыть в редакторе' : state ? 'Создать новую версию мира' : 'Развить идею и создать мир'}</Button>
          {state && <Button variant="ghost" onClick={() => {setEditingIdea(false);setSection('overview')}}>Вернуться к миру</Button>}
        </div>
      </section>}
      {!(showIdea&&job?.kind==='draft_world'&&!editingIdea)&&generationActivity}
      <Dialog open={!!deleteDraft} onOpenChange={open => { if (!open) setDeleteDraft(null); }}><DialogContent><DialogHeader><DialogTitle>Удалить «{deleteDraft?.name}»?</DialogTitle><DialogDescription>Черновик переместится в удалённые. Готовые игровые сохранения не затрагиваются. Ревизия {deleteDraft?.revision}.</DialogDescription></DialogHeader>{deleteError&&<p role="alert">{deleteError}</p>}<div className="workshop-dialog-actions"><Button variant="ghost" onClick={() => setDeleteDraft(null)}>Отмена</Button><Button disabled={busy} onClick={() => void run(async () => { if (!deleteDraft) return; try{await api(`/workspaces/${deleteDraft.id}`,{revision:deleteDraft.revision},'DELETE')}catch(e){const latest=await api<WorkspacePick[]>('/workspaces');setList(latest);const changed=latest.find(w=>w.id===deleteDraft.id);if(changed&&changed.revision!==deleteDraft.revision){setDeleteDraft(changed);setDeleteError(`Мир изменён в другом окне: теперь ревизия ${changed.revision}. Проверьте обновлённый мир перед повторным подтверждением удаления.`);return}throw e} setList(await api<WorkspacePick[]>('/workspaces')); setRemoved(await api<WorkspacePick[]>('/workspaces?deleted=true')); if (id === deleteDraft.id) { selectWorkspace(''); } setDeleteDraft(null); toast.success('Черновик перемещён в удалённые'); })}>Удалить</Button></div></DialogContent></Dialog>
      {!(showIdea&&job?.kind==='draft_world'&&!editingIdea) && !resuming && !active(job) && (job?.response_diagnostic?.message || job?.error) && <p className="workshop-error" role="alert">{job?.response_diagnostic?.message || job?.error}</p>}
      {(showIdea||section==='review'||section==='ai'&&job?.kind==='draft_editor')&&<>
      {(job?.pinned_config||job?.effective_config)&&<details className="workshop-detail ww-request-details"><summary>Параметры запроса</summary>
      {job?.pinned_config && <p className="workshop-hint">Модель задания: {job.pinned_config.provider} / {job.pinned_config.model} · Thinking генерации: {job.pinned_config.thinking || 'off'} · Thinking проверки: off</p>}
      {job?.effective_config && <p className="workshop-hint" aria-label="Фактические параметры запроса">Последний запрос: {job.effective_config.provider} / {job.effective_config.model} · Thinking: {job.effective_config.thinking} · Контекст: {job.effective_config.context_length} · Лимит ответа: {job.effective_config.max_tokens} · Попытка: {(job.attempt_epoch || 0)+1}</p>}
      </details>}
      {!ideaGenerationVisible && job?.status==='saved' && draft?.review?.status==='completed' && <p role="status">Смысловая проверка завершена. Результат сохранён.</p>}
      {calendarNotices.map((notice,i)=><p key={i} role="status">{notice}</p>)}
      </>}
      {state && <section className="workshop-result">
        {job?.status === 'saved' && ['partial','rejected'].includes(draft?.quality_status || '') && <p className="workshop-hint" role="status">Мир сохранён. {draft?.quality_status === 'partial' ? 'Некоторые творческие детали модель оставила неполными.' : 'Необязательное дополнение не было принято; проверенные данные сохранены.'} Проверить и дополнить детали можно в режиме «Автор мира».</p>}
        {!ideaGenerationVisible&&<div className="workshop-result-toolbar">
          <div className="workshop-view"><span>Вид:</span><button className={!author ? 'selected' : ''} aria-pressed={!author} onClick={() => switchView(false)}>Игрок</button><button className={author ? 'selected' : ''} aria-pressed={author} onClick={() => authorAcknowledged ? switchView(true) : setAuthorAsk(true)}>Автор мира</button></div>
          <span className="workshop-hint">{author ? 'Полное состояние: секреты и намерения NPC доступны для редактирования.' : `Сведения о мире для чтения. Тайны, неизвестные персонажу ${person(actor)}, скрыты.`}</span>
        </div>}
        {section==='ai'&&!author&&<div className="ww-empty"><h2>Изменения с ИИ</h2><p>Редактор работает с полным авторским миром, включая тайны и знания персонажей.</p><button onClick={()=>authorAcknowledged?switchView(true):setAuthorAsk(true)}>Открыть авторский редактор</button></div>}
        {section==='ai' && author && draft && <WorldAIEditor title={workspaceTitle} version={draft.version_id} example={aiExample} onHistory={setPreviewVersion} onObject={(section,eid)=>{if(section==='characters'){if(characters.some(c=>c.id===eid))openPerson(eid);return}const path='/'+section+'/'+eid;const link=reviewLink(path);if(link)link.open();else toast.info('Объект недоступен в текущей версии. Откройте историю изменений.')}} wid={id} revision={draft.revision} job={job} locked={locked} prefs={prefs} apiKey={apiKey} refresh={refresh} resolve={resolve} onJob={next=>dispatchWorkspace({type:'update',id,update:d=>d?{...d,job:next}:d})}/>}
        <div className="workshop-content" key={section}>
          {section === 'overview' && <>
            <section className="ww-hero">
              {author&&<button className="ww-hero-edit" aria-label="Изменить описание и правила" title="Изменить описание и правила" onClick={()=>editRecord('campaign','',state.campaign,'Описание и правила мира')}><Pencil size={18}/></button>}
              <div className="ww-eyebrow">Ваш мир. Ваши истории.</div><h1>{workspaceTitle}</h1>
              <ReadableText limit={140} text={String(state.campaign.public_description||state.campaign.description||'Начните с персонажей и первой сцены — все детали мира можно раскрыть и изменить.')}/>
              <details className="ww-hero-description"><summary>Подробнее о мире</summary><p>{String(state.campaign.setting||'Место не задано')}</p><p>{String(state.campaign.genre||'Жанр не задан')}</p>{author&&!!state.campaign.public_description&&!!state.campaign.description&&<ReadableText text={String(state.campaign.description)}/>}</details>
              <div className="ww-hero-meta"><span><MapPin size={13}/>{place(beginning?.location)}</span><span>{weekTime()}</span></div>
            </section>
            <div className="ww-stats">{([['characters',characters.length,'Персонажей',Users],['world',state.locations.length,'Локаций',MapPin],['relations',relations.length,'Отношений',Link],['story',threads.length,'Сюжетных линий',BookOpen]] as const).map(([key,count,label,Icon])=><button key={key} onClick={()=>navigate(key)}><Icon/><div><strong>{count}</strong><span>{label}</span></div></button>)}</div>
            <div className="ww-overview-grid"><div><header className="ww-section-head"><h2>Те, кто оживляет историю</h2><button onClick={()=>navigate('characters')}>Все персонажи <ArrowRight size={16}/></button></header><div className="ww-characters-grid is-overview">{characters.slice(0,4).map(c=><CharacterCard compact key={c.id} card={c as WorkshopCharacter} wid={id} author={author} protagonist={state.protagonist_id} onOpen={openPerson}/>)}</div><section className="ww-panel ww-opening"><p className="ww-eyebrow">Первая сцена</p><h2>{place(beginning?.location||actorState?.location)}</h2><p className="workshop-literary">{String(beginning?.text||actorState?.situation||'Стартовая ситуация пока не описана.')}</p><p>{weekTime()}</p><button className="ww-text-button" onClick={()=>navigate('start')}>Открыть начало истории →</button></section></div><aside className="ww-overview-aside"><section className="ww-panel"><h3><ShieldCheck size={20}/>{allIssues.length?'Миру нужно немного внимания':'Готовность мира'}</h3><p>{draft?.technical_valid?'Структура мира корректна.':'Проверьте ошибки перед запуском.'}</p>{draft?.start_warning&&<p role="status">{draft.start_warning} Можно начать с предупреждениями.</p>}{overviewIssues.slice(0,3).map((issue,i)=><article className="ww-issue-summary" key={i}><p>{issue.message}</p>{reviewLinks(issue.paths)}{!issue.paths.length&&<button className="ww-text-button" onClick={()=>navigate('review')}>Подробнее о замечании →</button>}</article>)}<button className="ww-soft" onClick={()=>navigate('review')}>Перейти к проверке <ArrowRight size={16}/></button></section><section className="ww-panel"><h3>У истории есть продолжение</h3><p>Опишите, что изменить. Сначала появится предложение — решение останется за вами.</p><button className="ww-text-button" onClick={()=>{setAiExample('Раскрой мотивы второстепенных персонажей, сохранив известные факты.');navigate('ai')}}>Изменить с ИИ →</button></section><section className="ww-panel ww-recent"><h3>Последние изменения</h3>{draft?.history.slice(0,3).map(v=><p key={v.id}>{versionReasons[v.reason]||'Обновление мира'}<small>{new Date(v.created_at).toLocaleString('ru-RU')}</small></p>)}{!draft?.history.length&&<p>Изменений пока нет.</p>}<button className="ww-text-button" onClick={()=>navigate('more')}>История версий →</button></section></aside></div>
          </>}
          {section==='characters'&&<CharacterCollection groups={characterGroups} characters={characters as WorkshopCharacter[]} wid={id} author={author} protagonist={state.protagonist_id} view={collection} setView={setCollection} onOpen={openPerson} onAdd={()=>void change({operation:'add',kind:'character'})} disabled={locked}/>}
          {section==='world'&&<>{pageHeader('Места и сообщества','Где проходит жизнь и что объединяет людей.')}{tab('Места',[['locations','Локации'],['organizations','Сообщества'],['residences','Проживание'],['roles','Роли'],['conditions','Обстоятельства'],['possessions','Имущество'],['contacts','Контакты']])}{currentSub('Места','locations')==='locations'?collectionRecords('location','Места',state.locations.map(l=>[l.id,l]),l=>String(l.name||l.text||'Место')):extension(currentSub('Места','locations'),extensionGroups[currentSub('Места','locations')])}</>}
          {section==='knowledge'&&<>{pageHeader('Факты и знания','Что известно, что скрыто и кто владеет информацией.')}{tab('Знания',[['facts','Все факты'],['secrets','Сюжетные тайны'],['private','Приватные факты'],['knowledge','Кто что знает']])}{currentSub('Знания','facts')!=='knowledge'?collectionRecords('fact',author?'Факты и тайны':'Доступные факты',facts.filter(([,f])=>currentSub('Знания','facts')==='secrets'?!!f.story_secret:currentSub('Знания','facts')==='private'?!!f.secret:true),f=>String(f.text||'Факт')):collectionRecords('knowledge','Знания персонажей',Object.entries(state.world.knowledge||{}),k=>recordTitle('knowledge',k,resolve,author))}</>}
          {section==='relations'&&<>{pageHeader('Связи и семьи','Объективные связи и направленные чувства — разные записи мира.')}{tab('Связи',[['feelings','Направленные чувства'],['objective_relations','Семья и связи'],['pregnancies','Беременности']])}{author&&currentSub('Связи','feelings')==='objective_relations'&&<button className="ww-soft" onClick={()=>navigate('review')}>Проверить дубли семейных связей →</button>}{currentSub('Связи','feelings')==='feelings'?<RelationshipMap key={id+author} {...{characters,author,actor}} wid={id} entries={relations} initialActor={recordTarget?.kind==='relationship'?String(state.world.relationships[recordTarget.id]?.source_id||''):undefined} onOpen={openPerson}>{source=>collectionRecords('relationship',`Чувства · ${person(source)}`,relations.filter(([,r])=>r.source_id===source),r=>`${person(r.source_id)} → ${person(r.target_id)} · ${String(r.context||'')}`,source)}</RelationshipMap>:extension(currentSub('Связи','feelings'),extensionGroups[currentSub('Связи','feelings')])}</>}
          {section==='story'&&<>{pageHeader('Нити вашей истории','Открытые возможности и развивающиеся линии. Они не принимают решения за героя.')}{tab('Сюжеты',[['threads','Сюжетные линии'],['secrets','Тайны и открытия']])}{currentSub('Сюжеты','threads')==='threads'?collectionRecords('thread','Сюжетные линии',threads,t=>String(t.description||'Сюжетная линия')):collectionRecords('fact','Тайны и открытия',facts.filter(([,f])=>!!f.story_secret),f=>String(f.text||'Факт'))}</>}
          {section==='timeline'&&<>{pageHeader('Хронология','Предыстория отдельно от планов и будущих договорённостей.')}{tab('Хронология',[['events','Прошедшие события'],['scenes','Сцены'],['scheduled_events','Будущие события'],['reproductive_events','Семейные события'],['naming_decisions','Выбор имён']])}{currentSub('Хронология','events')==='events'?collectionRecords('event','Уже произошедшие события',Object.entries(state.world.events||{}).sort(([,a],[,b])=>Number(a.minute??Infinity)-Number(b.minute??Infinity)),e=>String(e.text||'Событие')):currentSub('Хронология','events')==='scenes'?collectionRecords('scene','Сцены',Object.entries(state.world.scenes||{}),s=>`${place(s.location)} · ${String(s.text||'Сцена')}`):extension(currentSub('Хронология','events'),extensionGroups[currentSub('Хронология','events')])}</>}
          {section==='start'&&<>{pageHeader('Сцена и правила','Герой, камера, время и правила вашей истории.')}{tab('Начало',[['scene','Стартовая сцена'],['world','Мир и повествование'],['calendar','Календарь и связь']])}
          {currentSub('Начало','scene')==='scene'&&<><div className="ww-start-layout">
            <section className="ww-panel ww-start-controls"><h2>Кто проживает историю</h2><p>Главный герой, управление и камера — разные настройки.</p>
              {author&&<details className="workshop-detail" open><summary>Изменить стартовых участников и время</summary>{fields.start.map(f=>row('start','',f,f==='scene_id'?state.camera.scene_id:f==='minute'?state.world_clock.minute:state[f as 'protagonist_id'|'controlled_actor_id']))}</details>}
              <dl className="ww-launch-summary"><div><dt>Главный герой</dt><dd>{state.protagonist_id?person(state.protagonist_id):'Мир без протагониста'}</dd></div><div><dt>Кем управляете вы</dt><dd>{actor?person(actor):'Нет управляемого персонажа'}</dd></div><div><dt>Режим камеры</dt><dd>{state.camera.mode==='observer'?'Наблюдатель':'Взгляд персонажа'}</dd></div><div><dt>Чья точка зрения</dt><dd>{state.camera.mode==='observer'?'Наблюдение за сценой':actor?person(actor):'Не закреплена'}</dd></div></dl>
            </section><aside className="ww-panel ww-start-preview"><p className="ww-eyebrow">Перед первой репликой</p><h2>{place(beginning?.location||actorState?.location)}</h2><p className="ww-start-time">{weekTime()}</p>{!!beginning?.text&&<ReadableText text={String(beginning.text)} limit={650}/>}<div className="workshop-start"><div><span>Управление</span><strong>{person(actor)}</strong></div><div><span>Рядом</span><strong>{(beginning?.participants as string[]||[]).filter(cid=>cid!==actor).map(person).join(' · ')||'Пока никто'}</strong></div></div>{!!actorState?.situation&&<details><summary>Ситуация персонажа</summary><ReadableText text={String(actorState.situation)}/></details>}</aside>
            </div>{author&&<section className="ww-start-scenes"><h2>Сцены мира</h2>{Object.entries(state.world.scenes||{}).map(([key,item])=><details className="workshop-detail" key={key}><summary>{place(item.location)} · {short(item.text||key,90)}</summary>{entity('scene',key,item)}</details>)}<Button variant="outline" disabled={locked} onClick={()=>void change({operation:'add',kind:'scene'})}>+ Добавить сцену</Button></section>}</>}
          {currentSub('Начало','scene')==='world'&&<section className="ww-panel"><h2>Описание и правила мира</h2>{author&&<Button variant="outline" onClick={()=>editRecord('campaign','',state.campaign,'Описание и правила мира')}>Редактировать описание и правила</Button>}{author?fields.campaign.concat('public_description').map(f=>row('campaign','',f,state.campaign[f]??'')):<RuntimeValue field="record" value={state.campaign} resolve={resolve}/>}</section>}
          {currentSub('Начало','scene')==='calendar'&&<>{author&&draft?<CommunicationEditor wid={id} revision={draft.revision} profile={(state.world.communication||{}) as CommunicationProfile} disabled={locked} refresh={refresh}/>:<CommunicationSettings value={(state.world.communication||{}) as CommunicationProfile}/>} {author&&draft&&<CalendarProfileEditor wid={id} revision={draft.revision} profile={((state.world_clock as unknown as {calendar?:{profile?:Record<string,unknown>}}).calendar?.profile||{})} selection={draft.creation_settings?.calendar_start?.presets} disabled={locked} refresh={refresh}/>}{draft?.presentation?.clock.effective && <section aria-label="Действующий календарь"><h4>Действующий календарь</h4><p>{draft.presentation.clock.effective.weekday_names.join(' · ')}</p><p>{draft.presentation.clock.effective.month_names.map((name,i)=>`${name}: ${draft.presentation!.clock.effective!.month_lengths[i] ?? '28–29 (год неизвестен)'}`).join(' · ')}</p><p>Сезоны: {draft.presentation.clock.effective.seasons.length ? draft.presentation.clock.effective.seasons.map(s=>`${s.name} — ${s.day}.${s.month}`).join(' · ') : 'Не заданы'}. Праздники: {draft.presentation.clock.effective.regional ? `${draft.presentation.clock.effective.regional.country} · годозависимый набор; ближайшие даты — в предпросмотре` : draft.presentation.clock.effective.observances.length ? draft.presentation.clock.effective.observances.map(o=>`${o.name} — ${o.day}.${o.month}`).join(' · ') : 'Не заданы'}.</p></section>}{author && row('clock','clock','calendar',(state.world_clock as unknown as Item).calendar || {})}<button className="ww-text-button" onClick={()=>{navigate('world');setSubsection(prev=>({...prev,'Места':'contacts'}))}}>Настроить контакты →</button></>}
          </>}
          {section === 'more' && <>{pageHeader('Можно вернуться назад','История версий, исходные материалы и экспорт мира.')}<button className="ww-soft" onClick={()=>setDraftsOpen(true)}>Мои черновики и корзина</button><button className="ww-text-button" onClick={()=>{navigate('start');setSubsection(prev=>({...prev,'Начало':'world'}))}}>Стиль и правила повествования →</button><button className="ww-text-button" onClick={()=>navigate('review')}>Проверка и восстановление генерации →</button>
            <details className="workshop-detail"><summary>История версий · {draft?.history.length}</summary>{draft?.history.map((v,i)=><div className="workshop-version" key={v.id}><span>Версия {draft.history.length-i} · {versionReasons[v.reason]||'Обновление мира'}</span><small>{new Date(v.created_at).toLocaleString('ru-RU')}</small>{author && <Button disabled={locked} variant="outline" onClick={() => setPreviewVersion(v.id)}>Посмотреть версию</Button>}</div>)}</details>
            {author && <>{Object.entries(state.world).filter(([key])=>!['version','characters','relationships','facts','knowledge','threads','scenes','events',...Object.keys(extensionGroups)].includes(key)).map(([key,v])=><details className="workshop-detail" key={key}><summary>{runtimeLabels[key] || key} · просмотр</summary><RuntimeValue field={key} value={v} resolve={resolve} author/></details>)}<details className="workshop-detail"><summary>Исходный замысел или импорт</summary><Markdown text={draft?.source_text || 'Исходный текст не сохранён.'}/></details>{draft?.outline && <details className="workshop-detail"><summary>Как сценарист развил идею</summary><Markdown text={draft.outline}/></details>}<div className="workshop-export">{['plain','md','txt','json'].map(format=><Button key={format} variant="outline" onClick={()=>void run(async()=>{const response=await fetch(`/api/workspaces/${id}/draft/export?version_id=${draft?.version_id}&format=${format}`);if(!response.ok)throw new Error('Не удалось экспортировать мир');download(await response.text(),`world.${format==='plain'?'txt':format}`)})}>{format==='plain'?'Читаемый TXT':format==='txt'?'TXT для повторного импорта':format==='json'?'Экспорт JSON':'Скачать Markdown'}</Button>)}</div></>}
          </>}
        </div>
        {section==='review'&&!author&&<section className="ww-empty"><ShieldCheck/><h2>Этот раздел доступен автору</h2><p>Здесь могут быть скрытые сведения о мире.</p><button className="ww-primary" onClick={()=>authorAcknowledged?switchView(true):setAuthorAsk(true)}>Открыть авторский взгляд</button></section>}
        {section==='review'&&author&&<>{pageHeader('Проверка мира','Ошибки структуры, смысловые замечания и состояние проверки.')}<p>Совпадающие пары активных семейных связей: {draft?.relation_merges?.length||0}. Это структурная проверка; она не оценивает смысл описаний.</p><section className="ww-panel"><h3>{draft?.technical_valid?'Структура корректна':'Структура требует исправления'}</h3><p>Смысловая проверка: {({completed:'завершена',stale:'устарела',running:'выполняется',failed:'прервана'} as Record<string,string>)[draft?.review?.status||'']||'не выполнялась'}</p><p>{draft?.review?.reason}</p>{draft?.review?.checked_revision!==undefined&&<p>Проверена ревизия {draft.review.checked_revision} · текущая ревизия {draft.revision}</p>}{draft?.review?.status==='completed'&&!allIssues.length&&!draft?.review?.issues?.length&&<p>Замечаний в текущем отчёте нет.</p>}</section><div className="ww-filters" role="group" aria-label="Состояние замечаний"><button aria-pressed={reviewView==='active'} onClick={()=>setReviewView('active')}>Требуют внимания · {overviewIssues.length}</button><button aria-pressed={reviewView==='decisions'} onClick={()=>setReviewView('decisions')}>Решения проверки · {draft?.review_decisions?.length||0}</button></div>{reviewView==='decisions'?<ReviewDecisions items={draft?.review_decisions||[]} links={reviewLinks}/>:<><div className="ww-review-counts">{([['error','Ошибки'],['warning','Предупреждения'],['recommendation','Рекомендации']] as const).map(([severity,label])=><button key={severity} aria-pressed={reviewSeverity===severity} onClick={()=>setReviewSeverity(reviewSeverity===severity?'all':severity)}><strong>{overviewIssues.filter(i=>i.severity===severity).length}</strong><span>{label}</span></button>)}</div><label className="ww-search-field">Найти замечание<input aria-label="Поиск замечаний" value={reviewQuery} onChange={e=>setReviewQuery(e.target.value)}/></label>{overviewIssues.filter(issue=>(reviewSeverity==='all'||issue.severity===reviewSeverity)&&(issue.message+issue.paths.join(' ')).toLocaleLowerCase('ru').includes(reviewQuery.toLocaleLowerCase('ru'))).map((issue,i)=><article className={`ww-panel ww-review-issue is-${issue.severity}`} key={issue.message}><span className="ww-record-badge">{{error:'Ошибка',warning:'Предупреждение',recommendation:'Рекомендация'}[issue.severity]}</span><p>{issue.message}</p><small>{issue.sources.join(' · ')}</small>{reviewLinks(issue.paths)}{issue.paths.length>0&&<details><summary>Пути диагностики</summary>{issue.paths.map(path=><p key={path}><code>{path}</code></p>)}</details>}</article>)}</>}</>}
        {(section==='review'||section==='start')&&<div className="workshop-finish"><p>{previousWorld?'Новая генерация не завершена. Доступен предыдущий мир.':'Запуск сохранит выбранную версию и откроет настоящую игру.'}</p><Button disabled={busy||loading||!draft?.technical_valid} onClick={()=>setConfirmStart(launchSnapshot())}>Перейти к запуску</Button></div>}
      </section>}
    </>}</WorkshopShell>
    <CharacterDossier onEdit={()=>{if(selectedCard)editRecord('character',selectedCard.id,selectedCard,'Редактировать карточку')}} locationLabel={place(state?.world.characters?.[selectedCharacter]?.location_id||state?.world.characters?.[selectedCharacter]?.location)} protagonist={state?.protagonist_id} open={dossierOpen} onClose={()=>setDossierOpen(false)} card={selectedCard} characters={characters as WorkshopCharacter[]} wid={id} author={author} locked={locked} actor={state?.world.characters?.[selectedCharacter]||{}} onAddValues={()=>openEdit({kind:'actor',id:selectedCharacter,field:'values',value:state?.world.characters?.[selectedCharacter]?.values??{},label:'Ценности'})}
      actorFields={author?Array.from(new Set([...fields.actor,...draft?.editor?.fields.actor||[]])):
        [...fields.actor,'location_id','birth_date','biological_sex','life_status','developmental_stage','physical_state','capabilities','reproductive_capability','identity_components','display_name','name_history','personality','values']}
      row={row} life={[dossierRecords('conditions'),dossierRecords('roles'),dossierRecords('residences')]}
      refresh={refresh} onSelect={setSelectedCharacter} returnFocus={()=>dossierTrigger.current?.isConnected&&dossierTrigger.current.focus()}
      connections={[...relations.filter(([,r])=>r.source_id===selectedCharacter||r.target_id===selectedCharacter).map(relation),dossierRecords('objective_relations')]}
      knowledge={dossierKnowledge(selectedCharacter)} onRegenerate={()=>{if(selectedCard)openEdit({kind:'character',id:selectedCard.id,field:'__character',value:'',label:'Перегенерировать персонажа целиком'})}} onDelete={()=>void run(async()=>{const deps=await api<{kind:string;id:string}[]>(`/workspaces/${id}/draft/dependencies?kind=character&entity_id=${selectedCharacter}`);setRemoval({kind:'character',id:selectedCharacter,deps})})}/>
    <Dialog open={searchOpen} onOpenChange={setSearchOpen}><DialogContent><DialogTitle>Поиск по миру</DialogTitle><DialogDescription>Персонажи, места, сообщества, сюжеты и факты текущего взгляда.</DialogDescription><Input autoFocus aria-label="Поиск по миру" value={search} onChange={e=>setSearch(e.target.value)}/>{!search.trim()&&<p>Объекты вашего мира</p>}<div className="ww-search-results">{searchResults.map(r=><button key={r.kind+':'+r.id} onClick={()=>{setSearchOpen(false);if(r.kind==='character'){openPerson(r.id);return}const routes:Record<string,[WorkshopSection,string,string]>={location:['world','Места','locations'],organizations:['world','Места','organizations'],thread:['story','Сюжеты','threads'],fact:['knowledge','Знания','facts']};const [section,key,sub]=routes[r.kind];navigate(section);setSubsection(prev=>({...prev,[key]:sub}));setRecordTarget({kind:r.kind,id:r.id})}}><span>{short(r.label,180)}</span><small>{r.type}</small></button>)}</div>{!searchResults.length&&<p role="status">{search.trim()?'Ничего не найдено. Попробуйте другое слово или описание.':'В этом взгляде пока нет доступных объектов.'}</p>}</DialogContent></Dialog>
    {recordEdit&&author&&<RecordEditor key={id+recordEdit.kind+recordEdit.id} wid={id} target={{...recordEdit,revision:draft?.revision||0}} labels={labels} schemas={draft?.editor?.schemas[recordEdit.kind]} definitions={draft?.editor?.definitions} enums={draft?.editor?.enums[recordEdit.kind]} references={options} onClose={()=>setRecordEdit(null)} onSaved={refresh}/>}
    {creating&&author&&<CreateRecordDialog key={id+creating.kind+creating.revision} wid={id} target={creating} characters={characters} facts={facts} onClose={()=>setCreating(null)} onCreated={async(kind,eid)=>{await refresh();if(kind==='character'){openPerson(eid);return}const routes:Record<string,[WorkshopSection,string,string]>={location:['world','Места','locations'],relationship:['relations','Связи','feelings'],fact:['knowledge','Знания','facts'],knowledge:['knowledge','Знания','knowledge'],thread:['story','Сюжеты','threads'],event:['timeline','Хронология','events'],scene:['timeline','Хронология','scenes']};const route=routes[kind];if(route){setSection(route[0]);setSubsection(prev=>({...prev,[route[1]]:route[2]}))}setRecordTarget({kind,id:eid})}}/>}
    {previewVersion!==null&&author&&<VersionPreview key={id+':'+previewVersion} wid={id} version={previewVersion} revision={draft?.revision||0} head={draft?.version_id||null} onClose={()=>setPreviewVersion(null)} onRestore={refresh}/>}

 <Dialog open={authorAsk} onOpenChange={setAuthorAsk}><DialogContent><DialogHeader><DialogTitle>Открыть вид автора?</DialogTitle><DialogDescription>Ты увидишь тайны, неизвестные персонажам факты и скрытые намерения. Это может раскрыть будущие события.</DialogDescription></DialogHeader><Button onClick={() => { setAuthorAsk(false); setAuthorAcknowledged(true); switchView(true); }}>Показать всё</Button></DialogContent></Dialog>
 <Dialog open={!!edit} onOpenChange={o => { if (!o)
        setEdit(null); }}><DialogContent className="ww-field-dialog" onCloseAutoFocus={e=>{if(fieldTrigger.current?.isConnected){e.preventDefault();fieldTrigger.current.focus()}}}><DialogHeader><DialogTitle>{edit?.label}</DialogTitle><DialogDescription>{editContext()} · Меняется только выбранное поле.{edit?.field==='fields.Внешность'&&' Сохранённая иллюстрация настраивается отдельно — карандашом на портрете.'}</DialogDescription></DialogHeader>{editError&&<div><p role="alert">{editError}</p>{fieldJob&&<Button variant="outline" onClick={()=>void run(async()=>download(JSON.stringify(await api(`/workspaces/${id}/draft/raw?job_id=${fieldJob}`),null,2),'generation-response.json'))}>Скачать исходный ответ и диагностику</Button>}</div>}{fieldJob&&job?.id===fieldJob&&active(job)&&<div><p role="status">ИИ изменяет выбранное поле. Прежнее значение сохранено.</p><Button variant="outline" disabled={busy} onClick={()=>void run(async()=>{await api(`/jobs/${fieldJob}/stop`,{});await refresh()})}>Остановить изменение</Button></div>}{edit&&edit.field!=='__character'&&<p className="ww-field-status" role="status">{busy?'Сохраняем…':fieldDirty?'Есть несохранённые изменения. При закрытии ввод сохранится в этом браузере.':'Поле соответствует сохранённой версии.'}</p>}{edit?.field==='secret_keeper_ids'&&<p className="workshop-hint">Персонажи, которые сознательно хранят эту личную тайну. На старте они будут знать её содержание.</p>}{edit?.field==='secret_biography_ids'&&<p className="workshop-hint">Чью скрытую биографию описывает факт. Эта связь сама по себе не даёт персонажу знания тайны.</p>}{edit&&editRevision!==draft?.revision&&<Button variant="outline" onClick={()=>{setEditRevision(draft?.revision||0);setEditError('')}}>Использовать ввод для текущей версии</Button>}{edit && edit.field !== '__character' && <fieldset className="ww-field-input" disabled={locked}>{['minute','start_minute','end_minute'].includes(edit.field)?<WorldTimeEditor onValidity={setTimeValid} wid={id} value={value} label={edit.label} onChange={setValue}/>:edit.field==='dimensions'?<FeelingEditor value={(value||{}) as Item} onChange={setValue}/>:options(edit.field) ? Array.isArray(value) ? <ReferenceChecklist key={`${edit.kind}:${edit.id}:${edit.field}`} label={edit.label} options={options(edit.field)!} value={value} onChange={setValue}/> : <select aria-label={edit.label} value={String(value ?? '')} onChange={e => setValue(e.target.value || null)}><option value="">Не указано</option>{options(edit.field)!.map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select> : editTypes.includes('boolean') && nullableEdit ? <select aria-label={edit.label} value={value==null?'unknown':String(value)} onChange={e=>setValue(e.target.value==='unknown'?null:e.target.value==='true')}><option value="unknown">Неизвестно</option><option value="true">Да</option><option value="false">Нет</option></select> : typeof value === 'boolean' ? <label><input type="checkbox" checked={value} onChange={e => setValue(e.target.checked)}/>Да</label> : typeof value === 'number' || editTypes.includes('integer') || editTypes.includes('number') ? <Input type="number" aria-label={edit.label} value={value==null?'':String(value)} onChange={e => setValue(e.target.value==='' && nullableEdit?null:Number(e.target.value))}/> : structuredField(edit.field,value,editSchema) ? <StructuredValueEditor label={edit.label} field={edit.field} value={value} schema={editSchema} definitions={draft?.editor?.definitions} references={options} onChange={v=>{setValue(v);setStructuredEdit(JSON.stringify(v,null,2))}}/> : value && typeof value === 'object' && !Array.isArray(value) ? <div>{['trust', 'affection', 'attraction', 'irritation', 'fear', 'jealousy', 'respect', ...Object.keys(value)].filter((v, i, a) => a.indexOf(v) === i).map(k => <label key={k}>{runtimeLabels[k]||k}<Input type="number" min={-100} max={100} value={String((value as Item)[k] ?? '')} onChange={e => { const next = { ...value } as Item; if (e.target.value === '')
        delete next[k];
    else
        next[k] = Number(e.target.value); setValue(next); }}/></label>)}</div> : ['name','title'].includes(edit.field) ? <Input aria-label={edit.label} value={String(value??'')} onChange={e=>setValue(e.target.value)}/> : <Textarea aria-label={edit.label} value={Array.isArray(value) ? value.join('\n') : String(value ?? '')} onChange={e => setValue(Array.isArray(value) ? e.target.value.split('\n') : e.target.value)}/>}{nullableEdit && <Button variant="outline" onClick={()=>{setValue(null);setStructuredEdit('null');}}>Оставить неизвестным</Button>}{canDeclareVisibility&&<FieldVisibility policy={fieldVisibility} onChange={setPendingVisibility} facts={visibilityFacts}/>}<Button disabled={locked||!fieldDirty||invalidVisibility||['minute','start_minute','end_minute'].includes(edit.field)&&!timeValid||editRevision!==draft?.revision} onClick={() => {setBusy(true);setEditError('');void (async () => { await api(`/workspaces/${id}/draft`, { revision: editRevision, operation: 'patch', kind: edit.kind, entity_id: edit.id, field: edit.field, value: structuredField(edit.field,value,editSchema) ? JSON.parse(structuredEdit) : value, warnings_ack: ack, ...(visibilityDirty?{field_visibility:wirePolicy(fieldVisibility)}:{}) }, 'PATCH'); sessionStorage.removeItem(editBufferKey(edit));await refresh();setBusy(false);setEdit(null);toast.success(`Поле «${edit.label}» сохранено`); })().catch(e=>setEditError((e as Error).message)).finally(()=>setBusy(false))}}>Сохранить поле</Button></fieldset>}
 {fieldJob&&job?.id===fieldJob&&job.phase==='preview'&&<FieldProposal wid={id} jobId={fieldJob} revision={draft?.revision||0} resolve={resolve} onApplied={async()=>{if(edit)sessionStorage.removeItem(editBufferKey(edit));await refresh();setFieldJob(null);setEdit(null)}} onRejected={()=>{setFieldJob(null);if(edit)sessionStorage.removeItem(editBufferKey(edit))}}/>}{edit?.field === '__character' && <div><p>Связанные записи останутся неизменными; проверь их после изменения биографии:</p>{related.map(d => <p key={d.kind + d.id}>{d.kind} · {d.id}</p>)}</div>}<Button variant="ghost" disabled={locked} onClick={()=>{if(edit)sessionStorage.removeItem(editBufferKey(edit));setEdit(null)}}>Отменить правки поля</Button><details className="ww-field-ai" open={edit?.field==='__character'||undefined}><summary>Изменить это поле с ИИ</summary><Textarea disabled={busy||active(job)} aria-label="Указание генератору" placeholder="Как изменить? Например: сделать характер мягче, сохранив биографию." value={instruction} onChange={e => setInstruction(e.target.value)}/><label><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)}/> Изменить всё равно при семантических замечаниях</label>{(visibilityDirty||invalidVisibility)&&<p className="workshop-hint">Сохраните правило видимости или верните прежнее перед генерацией.</p>}<Button variant="outline" disabled={locked||visibilityDirty||invalidVisibility||editRevision!==draft?.revision} onClick={() => edit && void generate({ task: edit.field === '__character' ? 'character' : 'field', kind: edit.kind, entity_id: edit.id, field: edit.field, text: instruction, warnings_ack: ack })}>Перегенерировать {edit?.field === '__character' ? 'персонажа' : 'поле'}</Button></details></DialogContent></Dialog>
 <Dialog open={!!removal} onOpenChange={o => { if (!o)
        setRemoval(null); }}><DialogContent><DialogHeader><DialogTitle>Удалить запись?</DialogTitle><DialogDescription>{removal?.deps.length ? 'Сначала измени связанные записи. Автоматически удалять их нельзя.' : 'Будет создана новая версия. Предыдущую можно восстановить из истории.'}</DialogDescription></DialogHeader>{removal?.deps.map(d => <p key={d.kind + d.id}>{d.kind} · {characters.find(c => c.id === d.id)?.name || d.id}</p>)}<Button disabled={locked || !!removal?.deps.length} onClick={() => void run(async () => { await api(`/workspaces/${id}/draft`, { revision: draft?.revision, operation: 'remove', kind: removal?.kind, entity_id: removal?.id }, 'PATCH'); setRemoval(null); refresh(); })}>Удалить</Button></DialogContent></Dialog>
 {confirmStart&&<StartConfirmation shown={confirmStart} current={launchSnapshot()} onClose={()=>setConfirmStart(null)} onGame={onGame} onContinue={draft?.games?.length?()=>onGame(draft.games![0].world,draft.games![0].save):undefined}/>}

 </main>;
}
