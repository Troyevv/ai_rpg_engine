import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { api, download } from './api';
import { useJob } from './hooks';
import { active, type Job, type Preferences, type Workspace } from './types';
import { Preparation } from './Preparation';
import { Button } from './components/ui/button';
import { Input } from './components/ui/input';
import { Textarea } from './components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './components/ui/dialog';
import { Markdown } from './Markdown';
type Item = Record<string, unknown>;
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
    id: string;
    name: string;
    revision: number;
    version_id: number | null;
    state: DraftState | null;
    validation: {
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
const weekTime = (minute: number) => {
    if (!Number.isFinite(minute)) return 'Не указано';
    const days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
    return `День ${Math.floor(minute/1440)+1} (${days[Math.floor(minute/1440)%7]}) ${String(Math.floor(minute%1440/60)).padStart(2,'0')}:${String(minute%60).padStart(2,'0')}`;
};
const labels: Record<string, string> = { public_description: 'Аннотация для игрока', title: 'Название', setting: 'Обстановка', era: 'Эпоха', genre: 'Жанр', tone: 'Тон', description: 'Описание', rules: 'Правила повествования', name: 'Имя / название', aliases: 'Другие имена', location: 'Местоположение', situation: 'Сейчас', goals: 'Цели', intentions: 'Намерения', emotion: 'Эмоциональное состояние', obligations: 'Обязательства', source_id: 'От кого', target_id: 'К кому', context: 'Динамика отношений', dimensions: 'Показатели отношений', text: 'Описание', secret: 'Секрет', character_ids: 'Связанные персонажи', evidence: 'Основания', actor_id: 'Кто знает', fact_id: 'Факт', status: 'Статус', source_event_id: 'Источник знания', state: 'Текущее развитие', relevance: 'Значимость', participants: 'Участники', start_minute: 'Начало · минуты недели', end_minute: 'Конец · минуты недели', protagonist_id: 'Основной герой', controlled_actor_id: 'Управляемый персонаж', scene_id: 'Стартовая сцена', minute: 'Игровое время · минуты недели', witnesses: 'Свидетели', fact_ids: 'Факты', player_observed: 'Известно игроку' };
const fields: Record<string, string[]> = { campaign: ['title', 'setting', 'era', 'genre', 'tone', 'description', 'rules'], actor: ['location', 'situation', 'goals', 'intentions', 'emotion', 'obligations'], relationship: ['source_id', 'target_id', 'context', 'dimensions'], location: ['name', 'text'], fact: ['text', 'secret', 'character_ids', 'evidence'], knowledge: ['actor_id', 'fact_id', 'status', 'source_event_id'], thread: ['description', 'state', 'status', 'character_ids', 'relevance'], scene: ['location', 'participants', 'text', 'start_minute', 'end_minute', 'status'], event: ['text', 'participants', 'witnesses', 'minute', 'fact_ids', 'player_observed'], start: ['protagonist_id', 'controlled_actor_id', 'scene_id', 'minute'] };
const groups = [['Персонажи', 'character', 'characters'], ['Отношения', 'relationship', 'relationships'], ['Места', 'location', 'locations'], ['Факты и тайны', 'fact', 'facts'], ['Знания персонажей', 'knowledge', 'knowledge'], ['Сюжетные линии', 'thread', 'threads'], ['Сцены', 'scene', 'scenes'], ['События', 'event', 'events']];
export function WorldWorkshop({ prefs, apiKey, onWorld, onGame }: {
    prefs: Preferences;
    apiKey: string;
    onWorld: (id: number) => void;
    onGame: (world: number, save: number) => void;
}) {
    const [mode, setMode] = useState('quick');
    const [section, setSection] = useState<'overview'|'characters'|'world'|'relations'|'story'|'start'|'more'>('overview');
    const [selectedCharacter, setSelectedCharacter] = useState('');
    const [editingIdea, setEditingIdea] = useState(false);
    const [id, setId] = useState(localStorage.getItem('draftWorkspace') || '');
    const [list, setList] = useState<{
        id: string;
        name: string;
    }[]>([]);
    const [draft, setDraft] = useState<Draft | null>(null);
    const [author, setAuthor] = useState(false);
    const [authorAsk, setAuthorAsk] = useState(false);
    const [text, setText] = useState('');
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
    const refresh = () => { if (id)
        void api<Draft>(`/workspaces/${id}/draft?author=${author}`).then(setDraft).catch(e => toast.error(e.message)); };
    useEffect(() => { void api<typeof list>('/workspaces').then(setList).catch(e => toast.error(e.message)); }, []);
    useEffect(() => { setDraft(null); if (id) {
        localStorage.setItem('draftWorkspace', id);
        const controller = new AbortController();
        void api<Draft>(`/workspaces/${id}/draft?author=${author}`, undefined, 'GET', controller.signal).then(setDraft).catch(e => { if (!controller.signal.aborted)
            toast.error(e.message); });
        return () => controller.abort();
    } }, [id, author]);
    const { job, reconnecting } = useJob(draft?.job, refresh);
    const locked = busy || active(job);
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
    const generate = (body: Item) => run(async () => { const j = await api<Job>(`/workspaces/${id}/draft/generate`, { revision: draft?.revision, config: prefs.summary, api_key: apiKey, ...body }); setDraft(d => d ? { ...d, job: j } : d); setEdit(null); });
    const openEdit = (target: Target) => { setEdit(target); setValue(target.value ?? ''); setInstruction(''); setAck(false); };
    const state = draft?.state;
    const characters = state?.characters || [];
    const options = (field: string): [
        string,
        string
    ][] | null => {
        if (['protagonist_id', 'controlled_actor_id', 'source_id', 'target_id', 'actor_id', 'character_ids', 'participants', 'witnesses'].includes(field))
            return characters.map(c => [c.id, c.name]);
        const group = field === 'scene_id' ? 'scenes' : field === 'fact_id' || field === 'fact_ids' ? 'facts' : field === 'source_event_id' ? 'events' : null;
        if (group)
            return Object.entries(state?.world[group] || {}).map(([k, v]) => [k, String(v.text || v.location || k)]);
        if (field === 'status')
            return (edit?.kind === 'knowledge' ? ['known', 'suspected', 'unknown'] : edit?.kind === 'thread' ? ['active', 'developing', 'dormant', 'resolved'] : ['active', 'closed']).map(x => [x, x]);
        return null;
    };
    const printable = (field: string, v: unknown): string => { const opts = options(field); if (Array.isArray(v))
        return v.map(x => opts?.find(([k]) => k === x)?.[1] || String(x)).join(' · '); if (typeof v === 'boolean')
        return v ? 'Да' : 'Нет'; if (v && typeof v === 'object')
        return Object.entries(v).map(([k, x]) => `${k}: ${x}`).join(' · '); return opts?.find(([k]) => k === v)?.[1] || String(v ?? 'Не указано'); };
    const row = (kind: string, eid: string, field: string, v: unknown) => <div className="draft-field" key={field}><div className="draft-field-heading"><span>{labels[field] || field.replace('fields.', '')}</span>{author && <Button variant="ghost" size="sm" disabled={locked} aria-label={`Изменить ${labels[field] || field}`} onClick={() => openEdit({ kind, id: eid, field, value: v, label: labels[field] || field.replace('fields.', '') })}>Изменить</Button>}</div><details><summary>{printable(field, v) || 'Не указано'}</summary><Markdown text={printable(field, v)}/></details></div>;
    const entity = (kind: string, eid: string, item: Item) => <div className="draft-entity" key={eid}>
 {kind === 'character' ? <>{row(kind, eid, 'name', item.name)}{row(kind, eid, 'aliases', item.aliases || [])}{Object.entries(item.fields as Record<string, string>).filter(([k]) => !['Сейчас', 'Чего хочет', 'Намерения'].includes(k)).map(([k, v]) => row(kind, eid, 'fields.' + k, v))}<details><summary>Состояние, цели и намерения</summary>{fields.actor.map(f => row('actor', eid, f, state?.world.characters[eid]?.[f] ?? (['goals', 'intentions', 'obligations'].includes(f) ? [] : '')))}</details></> : fields[kind].map(f => row(kind, eid, f, item[f] ?? (['character_ids', 'participants', 'witnesses', 'fact_ids', 'evidence'].includes(f) ? [] : '')))}
 {author && <div className="actions">{kind === 'character' && <Button variant="outline" disabled={locked} onClick={() => { setEdit({ kind, id: eid, field: '__character', value: '', label: 'Перегенерировать персонажа целиком' }); setInstruction(''); setAck(false); setRelated([]); void api<{
        kind: string;
        id: string;
    }[]>(`/workspaces/${id}/draft/dependencies?kind=character&entity_id=${eid}`).then(setRelated).catch(e => toast.error(e.message)); }}>Новая версия персонажа</Button>}<Button variant="ghost" disabled={locked} onClick={() => void run(async () => { const deps = await api<{
        kind: string;
        id: string;
    }[]>(`/workspaces/${id}/draft/dependencies?kind=${kind}&entity_id=${eid}`); setRemoval({ kind, id: eid, deps }); })}>Удалить</Button></div>}
 </div>;
    if (mode === 'scenario')
        return <><Button className="workshop-back" variant="ghost" onClick={() => setMode('quick')}>← Генератор мира</Button><Preparation prefs={prefs} apiKey={apiKey} onWorld={onWorld} onDraft={wid => { setId(wid); setUseIdea(true); setMode('quick'); }}/></>;
    return <main className="preparation world-workshop">
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
        <select aria-label="Черновик мира" value={id} onChange={e => { setId(e.target.value); setAuthor(false); setUseIdea(false); setText(''); }}>
          <option value="">Новая история</option>{list.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
        </select>
        {id && <Button variant="ghost" onClick={() => { setId(''); setAuthor(false); setText(''); }}>+ Другая история</Button>}
      </details>
      {(!state || editingIdea) && <section className="workshop-inspiration">
        <div className="workshop-inspiration-head"><span className="workshop-step">01 · ЗАМЫСЕЛ</span><h2>{mode === 'import' ? 'Загрузи готовую выжимку' : 'С чего начинается история?'}</h2></div>
        <p>{mode === 'import' ? 'Подойдёт старый .md или .txt. Можно вставить текст ниже.' : 'Пиши свободно, как Сценаристу: персонажи, атмосфера, отношения, важные события. Пробелы генератор заполнит сам.'}</p>
        {mode === 'import' && <Input type="file" accept=".md,.txt" aria-label="Файл мира" onChange={e => { const f = e.target.files?.[0]; if (f) void f.text().then(setText); }}/ >}
        {!id && <Input aria-label="Название черновика" value={name} onChange={e => setName(e.target.value)} placeholder="Название истории (можно изменить позже)" />}
        <Textarea className="workshop-idea-input" value={text} onChange={e => setText(e.target.value)} aria-label="Описание мира или текст импорта" placeholder={mode === 'import' ? 'Вставь здесь текст выжимки…' : 'Например: современная клиника. Я играю за врача. Придумай важных коллег и напряжённые, но живые отношения. Сейчас четверг, 14:00…'} />
        {mode === 'quick' && draft && <label className="workshop-scenario-option"><input type="checkbox" checked={useIdea} onChange={e => setUseIdea(e.target.checked)}/> Взять за основу сценарий этого черновика</label>}
        <div className="workshop-create-actions">
          <Button disabled={locked || (!text.trim() && !useIdea)} onClick={() => void run(async () => {
            let current = draft; let wid = id;
            if (!current) {
              const w = await api<Workspace>('/workspaces', {name: name.trim() || 'Новая история'});
              wid = w.id; current = {id: wid, name: w.name, revision: w.revision, version_id: null, state: null,
                validation: {errors: [], warnings: []}, import_warnings: [], source_text: '', outline: '', history: [], job: null};
              setList(items => [w, ...items]);
            }
            if (mode === 'import') await api(`/workspaces/${wid}/draft/import`, {text, revision: current.revision});
            else {
              const j = await api<Job>(`/workspaces/${wid}/draft/generate`, {revision: current.revision, task: 'world', text, use_idea: useIdea, config: prefs.summary, api_key: apiKey});
              setDraft(d => d ? {...d, job: j} : current && {...current, job: j});
            }
            if (!id) setId(wid);
            setEditingIdea(false);
            if (mode === 'import') void api<Draft>(`/workspaces/${wid}/draft?author=${author}`).then(setDraft);
          })}>{mode === 'import' ? 'Открыть в редакторе' : state ? 'Создать новую версию мира' : 'Развить идею и создать мир'}</Button>
          {state && <Button variant="ghost" onClick={() => setEditingIdea(false)}>Вернуться к миру</Button>}
        </div>
      </section>}
      {active(job) && <section className="workshop-generating" role="status">
        <span className="workshop-pulse"/><div><strong>{reconnecting ? 'Восстанавливаем соединение…' : 'Собираем твою историю…'}</strong><p>Персонажи, отношения, места и стартовая сцена. Можно свернуть окно — работа продолжится.</p></div>
        <Button variant="ghost" onClick={() => void run(async () => {await api(`/jobs/${job!.id}/stop`, {}); refresh();})}>Остановить</Button>
      </section>}
      {job?.error && <p className="workshop-error" role="alert">{job.error}</p>}
      {state && <section className="workshop-result">
        <div className="workshop-result-heading"><div><span className="workshop-step">02 · МИР ГОТОВ</span><h2>Посмотри, что получилось</h2></div>
          <Button variant="ghost" disabled={locked} onClick={() => {setEditingIdea(true); setText(draft?.source_text || text);}}>Изменить замысел</Button></div>
        <div className="workshop-result-toolbar">
          <span className="workshop-mode">{author ? 'Вид автора · со спойлерами' : 'Вид игрока · без спойлеров'}</span>
          <Button variant="outline" onClick={() => author ? setAuthor(false) : setAuthorAsk(true)}>{author ? 'Показать как игроку' : 'Редактировать мир'}</Button>
        </div>
        {(draft?.validation.errors.length || draft?.validation.warnings.length || draft?.import_warnings.length) ? <details className="workshop-review" open={!!draft?.validation.errors.length}>
          <summary>Проверка мира · {draft?.validation.errors.length || 0} ошибок · {(draft?.validation.warnings.length || 0) + (draft?.import_warnings.length || 0)} замечаний</summary>
          {[...(draft?.validation.errors || []), ...(draft?.validation.warnings || []), ...(draft?.import_warnings || [])].map((x,i)=><p key={i}>{x}</p>)}
        </details> : null}
        <nav className="workshop-tabs" aria-label="Разделы мира">
          {([['overview','Обзор'],['characters','Персонажи'],['world','Места и факты'],['relations','Отношения'],['story','Сюжет'],['start','Начало'],['more','Ещё']] as const).map(([key,label]) => <button key={key} className={section === key ? 'selected' : ''} aria-current={section === key ? 'page' : undefined} onClick={() => setSection(key)}>{label}</button>)}
        </nav>
        <div className="workshop-content" key={section}>
          {section === 'overview' && <>
            <p className="workshop-kicker">{String(state.campaign.genre || state.campaign.setting || 'Твоя история')}</p>
            <h3>{String(state.campaign.title || draft?.name)}</h3>
            <div className="workshop-literary"><Markdown text={String(state.campaign.description || 'Начало истории можно посмотреть во вкладке «Начало».')}/></div>
            {state.campaign.setting && <p className="workshop-quiet">{String(state.campaign.setting)}</p>}
            <div className="workshop-portrait"><span>Главный герой</span><strong>{characters.find(c => c.id === state.protagonist_id)?.name || 'Не выбран'}</strong><p>{characters.find(c => c.id === state.protagonist_id)?.fields['Статус'] || ''}</p></div>
            <div className="workshop-quicklinks"><button onClick={() => setSection('characters')}>Персонажи · {characters.length} →</button><button onClick={() => setSection('start')}>Начало игры →</button></div>
          </>}
          {section === 'characters' && <>
            <h3>Персонажи</h3><p className="workshop-hint">Выбери человека, чтобы посмотреть его историю и состояние.</p>
            <div className="workshop-character-list">{characters.map(c => <button key={c.id} className={selectedCharacter === c.id ? 'selected' : ''} onClick={() => setSelectedCharacter(c.id)}><span>{c.name}</span>{c.id === state.protagonist_id && <small>ГГ</small>}</button>)}</div>
            {characters.filter(c => c.id === (selectedCharacter && characters.some(x=>x.id===selectedCharacter) ? selectedCharacter : characters[0]?.id)).map(c => <article className="workshop-person" key={c.id}>
              <h4>{c.name}{c.id === state.protagonist_id && <span className="workshop-badge">ГГ</span>}</h4>
              {c.fields['Статус'] && <p className="workshop-person-role">{c.fields['Статус']}</p>}
              {author ? entity('character', c.id, c) : <><p className="workshop-literary">{c.fields['Внешность'] || 'Внешность пока не описана.'}</p><p>{c.id === state.controlled_actor_id ? (c.fields['Суть'] || '') : ''}</p></>}
            </article>)}
            {author && <Button variant="outline" disabled={locked} onClick={() => void change({operation:'add',kind:'character'})}>+ Добавить персонажа</Button>}
          </>}
          {section === 'world' && <><h3>Места и факты</h3>
            {state.locations.length ? state.locations.map(loc => <details className="workshop-detail" key={loc.id}><summary>{loc.name}</summary>{author ? entity('location',loc.id,loc) : <p>{String(loc.text || '')}</p>}</details>) : <p className="workshop-hint">Места можно уточнить в режиме автора.</p>}
            {author && <Button variant="outline" disabled={locked} onClick={() => void change({operation:'add',kind:'location'})}>+ Добавить место</Button>}
            {author && <div className="workshop-subsection"><h4>Факты и тайны</h4>{Object.entries(state.world.facts || {}).map(([key,item])=><details className="workshop-detail" key={key}><summary>{String(item.text || key)}{item.secret ? ' · тайна' : ''}</summary>{entity('fact',key,item)}</details>)}<Button variant="outline" disabled={locked} onClick={() => void change({operation:'add',kind:'fact'})}>+ Добавить факт</Button>
              <details className="workshop-detail"><summary>Кто что знает</summary>{Object.entries(state.world.knowledge || {}).map(([key,item])=><details className="workshop-detail" key={key}><summary>{characters.find(c=>c.id===item.actor_id)?.name || String(item.actor_id)} · {String(item.status)}</summary>{entity('knowledge',key,item)}</details>)}<Button variant="outline" disabled={locked} onClick={() => void change({operation:'add',kind:'knowledge'})}>+ Добавить знание</Button></details>
            </div>}
          </>}
          {section === 'relations' && <><h3>Отношения</h3>{author ? Object.entries(state.world.relationships || {}).map(([key,item]) => <details className="workshop-detail" key={key}><summary>{characters.find(c=>c.id===item.source_id)?.name || 'Не выбран'} → {characters.find(c=>c.id===item.target_id)?.name || 'Не выбран'}</summary><p className="workshop-literary">{String(item.context || '')}</p>{entity('relationship',key,item)}</details>) : <p className="workshop-hint">Личные отношения и мотивы персонажей откроются по мере игры.</p>}{author && <Button variant="outline" disabled={locked} onClick={() => void change({operation:'add',kind:'relationship'})}>+ Добавить отношение</Button>}</>}
          {section === 'story' && <><h3>Сюжетные линии</h3>{author ? <>
            {Object.entries(state.world.threads || {}).map(([key,item])=><details className="workshop-detail" key={key}><summary>{String(item.description || 'Новая линия')}</summary>{entity('thread',key,item)}</details>)}<Button variant="outline" disabled={locked} onClick={() => void change({operation:'add',kind:'thread'})}>+ Добавить линию</Button>
            <details className="workshop-detail"><summary>Уже произошедшие события</summary>{Object.entries(state.world.events || {}).map(([key,item])=><details className="workshop-detail" key={key}><summary>{String(item.text || key)}</summary>{entity('event',key,item)}</details>)}<Button variant="outline" disabled={locked} onClick={() => void change({operation:'add',kind:'event'})}>+ Добавить событие</Button></details>
          </> : <p className="workshop-hint">Сюжет раскрывается во время игры. Скрытые линии доступны в режиме автора.</p>}</>}
          {section === 'start' && <><h3>Точка старта</h3><div className="workshop-start"><div><span>Когда</span><strong>{weekTime(state.world_clock.minute)}</strong></div><div><span>Где</span><strong>{String(state.world.scenes?.[state.camera.scene_id]?.location || 'Не указано')}</strong></div><div><span>Кто рядом</span><strong>{(state.world.scenes?.[state.camera.scene_id]?.participants as string[] || []).map(cid=>characters.find(c=>c.id===cid)?.name||cid).join(' · ') || 'Пока никто'}</strong></div></div>
              {author && <>{Object.entries(state.world.scenes || {}).map(([key,item])=><details className="workshop-detail" key={key}><summary>{String(item.location || 'Сцена')}</summary>{entity('scene',key,item)}</details>)}<Button variant="outline" disabled={locked} onClick={() => void change({operation:'add',kind:'scene'})}>+ Добавить сцену</Button><details className="workshop-detail"><summary>Изменить стартовых участников и время</summary>{fields.start.map(f=>row('start','',f,f==='scene_id'?state.camera.scene_id:f==='minute'?state.world_clock.minute:state[f as 'protagonist_id'|'controlled_actor_id']))}</details></>}
            </>}
          {section === 'more' && <><h3>Дополнительно</h3><details className="workshop-detail"><summary>Стиль и правила повествования</summary>{author ? fields.campaign.map(f=>row('campaign','',f,state.campaign[f] || '')) : <p>{String(state.campaign.genre || '')} · {String(state.campaign.tone || '')}</p>}</details>
            <details className="workshop-detail"><summary>История версий · {draft?.history.length}</summary>{draft?.history.map((v,i)=><div className="workshop-version" key={v.id}><span>Версия {draft.history.length-i} · {v.reason}</span>{author && <Button disabled={locked||v.id===draft.version_id} variant="outline" onClick={() => void change({operation:'restore',source_id:v.id})}>Восстановить</Button>}</div>)}</details>
            {author && <><details className="workshop-detail"><summary>Исходный замысел или импорт</summary><Markdown text={draft?.source_text || 'Мир создан генератором.'}/></details>{draft?.outline && <details className="workshop-detail"><summary>Как сценарист развил идею</summary><Markdown text={draft.outline}/></details>}<div className="workshop-export">{['md','txt'].map(format=><Button key={format} variant="outline" onClick={()=>void run(async()=>{const response=await fetch(`/api/workspaces/${id}/draft/export?version_id=${draft?.version_id}&format=${format}`);if(!response.ok)throw new Error('Не удалось экспортировать мир');download(await response.text(),`world.${format}`)})}>Скачать .{format}</Button>)}</div></>}
          </>}
        </div>
        <div className="workshop-finish"><p>Всё готово? Начни игру в этом мире. Его можно будет редактировать до подтверждения.</p><Button disabled={locked || !!draft?.validation.errors.length} onClick={() => setConfirmStart(true)}>Подтвердить мир и начать игру</Button></div>
      </section>}
 <Dialog open={authorAsk} onOpenChange={setAuthorAsk}><DialogContent><DialogHeader><DialogTitle>Открыть вид автора?</DialogTitle><DialogDescription>Ты увидишь тайны, неизвестные персонажам факты и скрытые намерения. Это может раскрыть будущие события.</DialogDescription></DialogHeader><Button onClick={() => { setAuthorAsk(false); setAuthor(true); }}>Показать всё</Button></DialogContent></Dialog>
 <Dialog open={!!edit} onOpenChange={o => { if (!o)
        setEdit(null); }}><DialogContent><DialogHeader><DialogTitle>{edit?.label}</DialogTitle><DialogDescription>Меняется только выбранное поле. Остальные сущности сохраняются.</DialogDescription></DialogHeader>{edit && edit.field !== '__character' && <>{options(edit.field) ? Array.isArray(value) ? <div className="draft-options">{options(edit.field)!.map(([k, n]) => <label key={k}><input type="checkbox" checked={value.includes(k)} onChange={e => setValue(e.target.checked ? [...value, k] : value.filter(x => x !== k))}/>{n}</label>)}</div> : <select aria-label={edit.label} value={String(value ?? '')} onChange={e => setValue(e.target.value || null)}><option value="">Не указано</option>{options(edit.field)!.map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select> : typeof value === 'boolean' ? <label><input type="checkbox" checked={value} onChange={e => setValue(e.target.checked)}/>Да</label> : typeof value === 'number' ? <Input type="number" aria-label={edit.label} value={value} onChange={e => setValue(Number(e.target.value))}/> : value && typeof value === 'object' && !Array.isArray(value) ? <div>{['trust', 'affection', 'attraction', 'irritation', 'fear', 'jealousy', 'respect', ...Object.keys(value)].filter((v, i, a) => a.indexOf(v) === i).map(k => <label key={k}>{k}<Input type="number" value={String((value as Item)[k] ?? '')} onChange={e => { const next = { ...value } as Item; if (e.target.value === '')
        delete next[k];
    else
        next[k] = Number(e.target.value); setValue(next); }}/></label>)}</div> : <Textarea aria-label={edit.label} value={Array.isArray(value) ? value.join('\n') : String(value ?? '')} onChange={e => setValue(Array.isArray(value) ? e.target.value.split('\n') : e.target.value)}/>}<Button disabled={locked} onClick={() => void run(async () => { await api(`/workspaces/${id}/draft`, { revision: draft?.revision, operation: 'patch', kind: edit.kind, entity_id: edit.id, field: edit.field, value, warnings_ack: ack }, 'PATCH'); setEdit(null); refresh(); })}>Сохранить поле</Button></>}
 {edit?.field === '__character' && <div><p>Связанные записи останутся неизменными; проверь их после изменения биографии:</p>{related.map(d => <p key={d.kind + d.id}>{d.kind} · {d.id}</p>)}</div>}<Textarea aria-label="Указание генератору" placeholder="Как изменить? Например: сделать характер мягче, сохранив биографию." value={instruction} onChange={e => setInstruction(e.target.value)}/><label><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)}/> Изменить всё равно при семантических замечаниях</label><Button variant="outline" disabled={locked} onClick={() => edit && void generate({ task: edit.field === '__character' ? 'character' : 'field', kind: edit.kind, entity_id: edit.id, field: edit.field, text: instruction, warnings_ack: ack })}>Перегенерировать {edit?.field === '__character' ? 'персонажа' : 'поле'}</Button></DialogContent></Dialog>
 <Dialog open={!!removal} onOpenChange={o => { if (!o)
        setRemoval(null); }}><DialogContent><DialogHeader><DialogTitle>Удалить запись?</DialogTitle><DialogDescription>{removal?.deps.length ? 'Сначала измени связанные записи. Автоматически удалять их нельзя.' : 'Будет создана новая версия. Предыдущую можно восстановить из истории.'}</DialogDescription></DialogHeader>{removal?.deps.map(d => <p key={d.kind + d.id}>{d.kind} · {characters.find(c => c.id === d.id)?.name || d.id}</p>)}<Button disabled={locked || !!removal?.deps.length} onClick={() => void run(async () => { await api(`/workspaces/${id}/draft`, { revision: draft?.revision, operation: 'remove', kind: removal?.kind, entity_id: removal?.id }, 'PATCH'); setRemoval(null); refresh(); })}>Удалить</Button></DialogContent></Dialog>
 <Dialog open={confirmStart} onOpenChange={setConfirmStart}><DialogContent><DialogHeader><DialogTitle>Начать эту историю?</DialogTitle><DialogDescription>Будет сохранена текущая версия мира. Повторной генерации или разбора текста не будет.</DialogDescription></DialogHeader>{draft?.validation.warnings.map(x => <p key={x}>{x}</p>)}<Button disabled={locked} onClick={() => void run(async () => { const result = await api<{
        world: number;
        save: number;
    }>(`/workspaces/${id}/draft/confirm`, { revision: draft?.revision, version_id: draft?.version_id }); setConfirmStart(false); onGame(result.world, result.save); })}>Подтвердить и открыть игру</Button></DialogContent></Dialog>
 </main>;
}
