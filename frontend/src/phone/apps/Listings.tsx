import { type ReactNode } from 'react';
import { useDevice } from '../usePhone';
import { Generation, useDraft, useRecords } from '../data';
import type { PortraitSubject } from '../../Portrait';

export interface RecordCard {
  id: string;
  title?: string;
  text?: string;
  summary?: string;
  description?: string;
  category?: string;
  published: string;
  source?: string;
  previous_id?: string;
  publication_id?: string;
  sender?: PortraitSubject | null;
  recipient?: PortraitSubject;
  employer?: string;
  employment?: string;
  location?: string;
  time?: string;
  end_time?: string;
  active?: boolean;
  cancelled?: boolean;
  can_plan?: boolean;
  planned?: boolean;
  favorite?: boolean;
  applied?: boolean;
  conversation_id?: string;
  schedule?: string;
  pay?: string;
  requirements?: string;
  previous_terms?: { pay: string; schedule: string; requirements: string; changed_at: number }[];
  pending_text?: string;
  previous_time?: string;
  reply?: string;
  invitations?: {
    conversation_id: string;
    person: PortraitSubject;
    outgoing: boolean;
    reply: string | null;
    plans: string[];
  }[];
  plans?: { id: string; description: string }[];
}
interface Results {
  items: RecordCard[];
  next: string | null;
  categories: string[];
  places: Record<string, string>;
  dates: Record<string, string>;
  roles: { id: string; label: string; organization?: string; status: string; workplace?: string }[];
}
export function useListing(app: string, id?: string) {
  const r = useRecords<Results>(app + '?item=' + encodeURIComponent(id || ''));
  return { item: r.data?.items[0], status: r.status };
}
export function TextForm({
  label,
  button,
  draft,
  initial = '',
  submit,
  children,
}: {
  label: string;
  button: string;
  draft: string;
  initial?: string;
  submit: (text: string) => Promise<boolean>;
  children?: ReactNode;
}) {
  const [text, setText] = useDraft(draft, initial);
  const d = useDevice();
  return (
    <form
      className="smart-compose"
      onSubmit={async (e) => {
        e.preventDefault();
        if (await submit(text)) {
          setText('');
          d.back();
        }
      }}
    >
      {children}
      <label>
        {label}
        <textarea maxLength={5000} required value={text} onChange={(e) => setText(e.target.value)} />
      </label>
      <button className="smart-primary" disabled={d.locked || !text.trim()}>
        {button}
      </button>
    </form>
  );
}
export const employment: Record<string, string> = {
  permanent: 'Постоянная работа',
  temporary: 'Временная работа',
  gig: 'Разовый заказ',
};
function Filter({
  label,
  value,
  set,
  options,
}: {
  label: string;
  value: string;
  set: (v: string) => void;
  options: Record<string, string>;
}) {
  return (
    <label>
      {label}
      <select value={value} onChange={(e) => set(e.target.value)}>
        <option value="">Все</option>
        {Object.entries(options).map(([k, v]) => (
          <option key={k} value={k}>
            {v}
          </option>
        ))}
      </select>
    </label>
  );
}
export function Catalog({
  app,
  tabs = {},
  profile,
  children,
}: {
  app: string;
  tabs?: Record<string, string>;
  profile?: string;
  children?: ReactNode;
}) {
  const d = useDevice();
  const [tab, setTab] = useDraft(app + ':tab');
  const [query, setQuery] = useDraft(app + ':query');
  const [category, setCategory] = useDraft(app + ':category');
  const [place, setPlace] = useDraft(app + ':place');
  const [kind, setKind] = useDraft(app + ':kind');
  const [date, setDate] = useDraft(app + ':date');
  const filter = new URLSearchParams({
    tab: profile ? '' : tab,
    profile: profile || '',
    query,
    category,
    place,
    kind,
    date,
  }).toString();
  const [cursor, setCursor] = useDraft(app + ':cursor:' + filter);
  const { data, status } = useRecords<Results>(app + '?' + filter + '&cursor=' + encodeURIComponent(cursor));
  const generate = app !== 'questions';
  return (
    <section className="smart-app phone-catalog">
      {children}
      {Object.keys(tabs).length > 0 && !profile && (
        <nav className="smart-toolbar">
          {Object.entries(tabs).map(([k, v]) => (
            <button key={k} aria-pressed={tab === k} onClick={() => setTab(k)}>
              {v}
            </button>
          ))}
        </nav>
      )}
      {generate && (
        <>
          <button
            className="smart-primary"
            disabled={d.locked}
            onClick={() => void d.command(app, 'generate', {}, true)}
          >
            {app === 'news' ? 'Новые статьи' : app === 'events' ? 'Найти мероприятия' : 'Найти ещё вакансии'}
          </button>
          <Generation app={app} />
        </>
      )}
      {app === 'work' && tab !== 'roles' && (
        <label>
          Поиск вакансий
          <input value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
      )}
      {generate && tab !== 'roles' && (
        <Filter
          label="Категория"
          value={category}
          set={setCategory}
          options={Object.fromEntries((data?.categories || []).map((c) => [c, c]))}
        />
      )}
      {app === 'events' && <Filter label="Дата" value={date} set={setDate} options={data?.dates || {}} />}
      {app === 'work' && tab !== 'roles' && (
        <>
          <Filter label="Место" value={place} set={setPlace} options={data?.places || {}} />
          <Filter label="Тип занятости" value={kind} set={setKind} options={employment} />
        </>
      )}
      {status}
      {data?.roles.map((r) => (
        <article key={r.id} className="smart-post">
          <strong>{r.label}</strong>
          <p>
            {r.organization} · {r.status === 'active' ? 'Действует' : 'Завершено'}
          </p>
          {r.workplace && (
            <button onClick={() => d.propose('Отправляюсь на работу — ' + r.workplace + '.')}>
              Отправиться на работу
            </button>
          )}
        </article>
      ))}
      {data?.items.map((r) => (
        <button className="smart-post listing-preview" key={r.id} onClick={() => d.push('detail', r.id)}>
          <small>
            {r.category || r.recipient?.name} · {r.time || r.published}
          </small>
          <strong>{r.title || r.text}</strong>
          {r.summary && <span>{r.summary}</span>}
          {r.employer && (
            <span>
              {r.employer} · {employment[r.employment!]}
            </span>
          )}
          {r.active === false && <small>{r.cancelled ? 'Отменено' : 'Завершено'}</small>}
          {app === 'questions' && (
            <small>
              {r.sender?.name || 'Аноним'} · {r.publication_id ? 'Есть ответ' : 'Без ответа'}
            </small>
          )}
        </button>
      ))}
      {data && !data.items.length && !data.roles.length && <p className="smart-empty">Пока нет записей.</p>}
      {cursor && <button onClick={() => setCursor('')}>К началу списка</button>}
      {data?.next && <button onClick={() => setCursor(data.next!)}>Следующая страница</button>}
    </section>
  );
}
