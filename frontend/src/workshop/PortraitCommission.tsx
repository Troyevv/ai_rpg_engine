import { createContext, useContext, useEffect, useRef, useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCheck,
  ChevronRight,
  Images,
  LoaderCircle,
  Search,
  Sparkles,
  Wallet,
  X,
} from 'lucide-react';
import { api } from '../api';
import { defaults, type Preferences } from '../types';
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Button } from '../components/ui/button';
import { type ProceduralPortrait } from './proceduralPortrait';
import { ViewablePortrait, CharacterAvatar, type PortraitSubject } from '../Portrait';
import '../styles/portrait-commission.css';

export const PortraitModels = createContext({ prefs: defaults as Preferences, apiKey: '' });
type Ticket = {
  id: string;
  ids?: string[];
  revision: number;
  model: string;
  thinking: string;
  input: number;
  output: number;
  cost: string | null;
  requests: number;
  count: number;
  status?: string;
  message?: string;
  proposals?: Record<string, { descriptor: ProceduralPortrait; warnings: string[] }>;
  errors?: Record<string, string>;
};
type Props = {
  workspaceId?: string;
  saveId?: number;
  revision: number;
  cards: PortraitSubject[];
  disabled?: boolean;
  onPreview?: (p: ProceduralPortrait) => void;
  refresh?: () => void | Promise<void>;
};
type Filter = 'all' | 'illustration' | 'photo' | 'selected';
const filters: Record<Filter, string> = {
  all: 'Все',
  illustration: 'Иллюстрации',
  photo: 'Фото',
  selected: 'Выбранные',
};
const toggle = (values: string[], id: string) =>
  values.includes(id) ? values.filter((v) => v !== id) : [...values, id];
const money = (cost: string | null) =>
  cost === null
    ? 'Тариф неизвестен'
    : Number(cost) === 0
      ? 'Без оплаты'
      : '≈ $' + Number(cost).toFixed(5);
const role = (card: PortraitSubject) => card.fields?.['Роль'] || card.fields?.['Возраст'] || '';
const MAX_CAST = 64;

export function PortraitCommission({
  workspaceId,
  saveId,
  revision,
  cards,
  disabled,
  onPreview,
  refresh,
}: Props) {
  const { prefs, apiKey } = useContext(PortraitModels);
  const config = workspaceId ? prefs.summary : prefs.game;
  const base =
    '/portrait-proposals/' +
    (workspaceId ? 'workspace/' + encodeURIComponent(workspaceId) : 'save/' + saveId);
  const cacheKey = [base, revision, onPreview ? cards[0]?.id : 'batch'].join('/');
  const selectionKey = cacheKey + '/selection';
  const [open, setOpen] = useState(false),
    [busy, setBusy] = useState(false),
    [sending, setSending] = useState(false);
  const [ticket, setTicket] = useState<Ticket | null>(null),
    [ids, setIds] = useState<string[]>([]),
    [chosen, setChosen] = useState<string[]>([]);
  const [restoreFailed, setRestoreFailed] = useState(false);
  const [error, setError] = useState(''),
    [query, setQuery] = useState(''),
    [filter, setFilter] = useState<Filter>('all');
  const scroller = useRef<HTMLDivElement>(null),
    active = useRef(cacheKey);
  active.current = cacheKey;
  const byId = new Map(cards.map((c) => [c.id, c]));
  const avatar = (c: PortraitSubject, size: number, framing: 'avatar'|'plate'='avatar') => (
    <CharacterAvatar framing={framing} subject={c} workspaceId={workspaceId} saveId={saveId} author size={size} />
  );
  function select(values: string[]) {
    setIds(values);
    sessionStorage.setItem(selectionKey, JSON.stringify(values));
  }
  async function work(fn: () => Promise<void>) {
    setBusy(true);
    setError('');
    try {
      await fn();
    } catch (e) {
      if (active.current === cacheKey) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (active.current === cacheKey) setBusy(false);
    }
  }
  function receive(t: Ticket) {
    if (active.current !== cacheKey || sessionStorage.getItem(cacheKey) !== t.id) return;
    setTicket(t);
    if (t.ids) setIds(t.ids);
  }
  async function show() {
    let saved: string[] = [];
    try {
      const raw: unknown = JSON.parse(sessionStorage.getItem(selectionKey) || '[]');
      if (Array.isArray(raw)) saved = raw.filter((id) => byId.has(id)).slice(0, MAX_CAST);
    } catch {
      /* empty session */
    }
    setRestoreFailed(false);
    setIds(onPreview ? [cards[0].id] : saved);
    setQuery('');
    setFilter('all');
    setError('');
    setOpen(true);
    setTicket(null);
    setChosen([]);
    const stored = sessionStorage.getItem(cacheKey);
    if (stored)
      await work(async () => {
        try {
          const t = await api<Ticket>(base + '/' + stored);
          receive(t);
          restoreChoices(t);
        } catch (e) {
          setRestoreFailed(true);
          throw e;
        }
      });
  }
  function restoreChoices(t: Ticket) {
    if (active.current !== cacheKey || sessionStorage.getItem(cacheKey) !== t.id) return;
    const ids = t.proposals || {};
    try {
      const saved: unknown = JSON.parse(sessionStorage.getItem(cacheKey + '/apply/' + t.id) || '[]');
      if (Array.isArray(saved)) setChosen(saved.filter((k) => Object.hasOwn(ids, k)));
    } catch {
      /* empty session */
    }
  }
  function selectResult(values: string[]) {
    setChosen(values);
    if (ticket) sessionStorage.setItem(cacheKey + '/apply/' + ticket.id, JSON.stringify(values));
  }
  const quote = () =>
    work(async () => {
      const t = await api<Ticket>(base, {
        revision,
        ids,
        config,
        api_key: config.provider === 'deepseek' ? apiKey : undefined,
      });
      sessionStorage.setItem(cacheKey, t.id);
      receive({ ...t, status: 'quoted' });
      setChosen([]);
    });
  const generate = () =>
    work(async () => {
      if (!ticket) return;
      setSending(true);
      receive({ ...ticket, status: 'running' });
      try {
        receive(
          await api<Ticket>(base + '/' + ticket.id + '/generate', {
            api_key: config.provider === 'deepseek' ? apiKey : undefined,
          }),
        );
      } catch (e) {
        receive({ ...ticket, status: 'unknown' });
        throw e;
      } finally {
        setSending(false);
      }
    });
  const resetTicket = () => {
    sessionStorage.removeItem(cacheKey);
    setTicket(null);
    setError('');
    setChosen([]);
    setFilter('all');
  };
  const status = ticket?.status;
  useEffect(() => {
    if (!open || sending || status !== 'running' || !ticket) return;
    let current = true;
    const timer = window.setInterval(async () => {
      try {
        const next = await api<Ticket>(base + '/' + ticket.id);
        if (current) {
          receive(next);
          setError('');
        }
      } catch (e) {
        if (current) {
          setError(e instanceof Error ? e.message : String(e));
          setTicket({ ...ticket, status: 'unknown' });
        }
      }
    }, 2000);
    return () => {
      current = false;
      clearInterval(timer);
    };
  }, [open, sending, status, ticket?.id, base]);
  useEffect(() => {
    scroller.current?.scrollTo(0, 0);
  }, [filter, query, status]);
  const needle = query.trim().toLocaleLowerCase('ru');
  const visible = cards.filter(
    (c) =>
      (filter === 'all' ||
        (filter === 'selected'
          ? ids.includes(c.id)
          : filter === 'photo'
            ? !!c.portrait
            : !c.portrait)) &&
      [c.name, role(c)].some((s) => s.toLocaleLowerCase('ru').includes(needle)),
  );
  const results = Object.entries(ticket?.proposals || {}),
    failures = Object.entries(ticket?.errors || {});
  const waiting = status === 'running' || status === 'unknown';
  const reviewing = !!ticket && status !== 'quoted' && !waiting;
  const step = reviewing ? 2 : ticket ? 1 : 0;
  const nextIds = [...new Set([...ids, ...visible.map((c) => c.id)])].slice(0, MAX_CAST);
  const title = onPreview ? 'Создать по описанию' : 'Портретная мастерская';
  const apply = () =>
    work(async () => {
      if (!ticket) return;
      await api(base + '/' + ticket.id + '/apply', { ids: chosen, revision: ticket.revision });
      sessionStorage.removeItem(cacheKey);
      sessionStorage.removeItem(selectionKey);
      sessionStorage.removeItem(cacheKey + '/apply/' + ticket.id);
      await refresh?.();
      setOpen(false);
    });
  return (
    <>
      <Button
        className={onPreview ? '' : 'portrait-album-trigger'}
        variant="outline"
        disabled={disabled}
        onClick={() => void show()}
      >
        {onPreview ? <Sparkles size={16} /> : <Images size={17} />}{' '}
        {onPreview ? title : saveId ? 'Все портреты' : 'Портреты'}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          className={onPreview ? 'portrait-commission is-single' : 'portrait-commission'}
          onOpenAutoFocus={(e) => {
            e.preventDefault();
            document.querySelector<HTMLElement>('.portrait-commission .dialog-title')?.focus();
          }}
        >
          <header className="commission-head">
            <DialogTitle tabIndex={-1}>
              <Images aria-hidden="true" />
              {title}
            </DialogTitle>
            <DialogDescription>
              {onPreview
                ? 'Новая иллюстрация по сохранённой внешности персонажа.'
                : 'Подбор иллюстраций по описаниям персонажей.'}
            </DialogDescription>
            <ol className="commission-steps" aria-label="Этапы">
              {['Персонажи', 'Расчёт', 'Предпросмотр'].map((s, i) => (
                <li
                  key={s}
                  aria-current={i === step ? 'step' : undefined}
                  className={i < step ? 'done' : ''}
                >
                  {i < step ? <Check size={13} /> : <span>{i + 1}</span>}
                  {s}
                  {i < 2 && <ChevronRight size={13} />}
                </li>
              ))}
            </ol>
          </header>
          {!ticket && !onPreview && (
            <div className="commission-tools">
              <label className="commission-search">
                <Search size={18} />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Имя или роль"
                  aria-label="Поиск по имени или роли"
                />
                {query && (
                  <button aria-label="Очистить поиск" onClick={() => setQuery('')}>
                    <X size={16} />
                  </button>
                )}
              </label>
              <div className="commission-filters" role="group" aria-label="Фильтр персонажей">
                {(Object.keys(filters) as Filter[]).map((k) => (
                  <button key={k} aria-pressed={k === filter} onClick={() => setFilter(k)}>
                    {filters[k]}
                    {k === 'selected' && ' · ' + ids.length}
                  </button>
                ))}
              </div>
              <div className="commission-bulk">
                <span>Найдено · {visible.length}</span>
                <button disabled={nextIds.length === ids.length} onClick={() => select(nextIds)}>
                  <CheckCheck size={15} />
                  {nextIds.length === 64 && visible.length > 64 ? 'Выбрать до 64' : 'Выбрать найденных'}
                </button>
              </div>
            </div>
          )}
          <div className="commission-body" ref={scroller}>
            {!ticket && !onPreview && (
              <>
                <div className="cast-grid">
                  {visible.map((c) => (
                    <label className="cast-card" data-selected={ids.includes(c.id)} key={c.id}>
                      <input
                        type="checkbox"
                        aria-label={c.name}
                        checked={ids.includes(c.id)}
                        disabled={!ids.includes(c.id) && ids.length >= MAX_CAST}
                        onChange={() => select(toggle(ids, c.id))}
                      />
                      <span className="cast-art">
                        {avatar(c, 80,'plate')}
                        <i aria-hidden="true">{ids.includes(c.id) && <Check size={15} />}</i>
                      </span>
                      <span className="cast-name">{c.name}</span>
                      <small>{role(c) || (c.portrait ? 'Фотография' : 'Иллюстрация')}</small>
                    </label>
                  ))}
                </div>
                {!visible.length && (
                  <p className="commission-empty">
                    {filter === 'selected'
                      ? 'В этой подборке пока никого нет.'
                      : 'Персонажи не найдены.'}{' '}
                    <button
                      onClick={() => {
                        setQuery('');
                        setFilter('all');
                      }}
                    >
                      Показать всех
                    </button>
                  </p>
                )}
              </>
            )}
            {((onPreview && !ticket) || status === 'quoted') && (
              <>
                <h3>{ticket ? 'Состав запроса · ' + ticket.count : 'Персонаж'}</h3>
                <div className="commission-roster">
                  {ids.map((id) => {
                    const c = byId.get(id);
                    return (
                      c && (
                        <div key={id}>
                          {avatar(c, 42)}
                          <span>
                            {c.name}
                            <small>{role(c)}</small>
                          </span>
                        </div>
                      )
                    );
                  })}
                </div>
                {onPreview && cards[0]?.fields?.['Внешность'] && (
                  <p className="commission-appearance">{cards[0].fields['Внешность']}</p>
                )}
                {ticket && (
                  <p className="commission-note">
                    На входе около {ticket.input} токенов, на ответ до {ticket.output}. Отправка начнётся
                    после подтверждения.
                  </p>
                )}
              </>
            )}
            {waiting && (
              <div className="commission-message" role="status">
                {status === 'running' ? <LoaderCircle className="commission-spin" /> : <Wallet />}
                <h3>{status === 'running' ? 'Подбираем иллюстрации' : 'Проверка состояния запроса'}</h3>
                <p>
                  {status === 'running'
                    ? 'Окно можно закрыть и вернуться к результатам.'
                    : 'Проверьте состояние перед новым запросом: отправка могла состояться.'}
                </p>
                <Button
                  variant="outline"
                  onClick={async () => {
                    try {
                      receive(await api<Ticket>(base + '/' + ticket!.id + '/cancel', {}));
                    } catch (e) {
                      setError(e instanceof Error ? e.message : String(e));
                    }
                  }}
                >
                  Остановить запрос
                </Button>
              </div>
            )}
            {reviewing && (
              <>
                <h3>
                  {results.length
                    ? 'Выберите иллюстрации для сохранения'
                    : status === 'cancelled'
                      ? 'Запрос остановлен'
                      : 'Иллюстрации не получены'}
                </h3>
                <p className="commission-note">
                  {status === 'cancelled' && results.length > 0 && 'Запрос остановлен. '}
                  {ticket?.message ||
                    (results.length
                      ? 'Слева текущий портрет, справа предложение модели.'
                      : 'Сохранённые портреты остались в карточках.')}
                </p>
                {failures.length > 0 && (
                  <details className="commission-errors" open={!results.length}>
                    <summary>Не удалось подготовить · {failures.length}</summary>
                    {failures.map(([id, why]) => (
                      <p key={id}>
                        <b>{byId.get(id)?.name || id}</b> · {why}
                      </p>
                    ))}
                  </details>
                )}
                <div className="commission-results">
                  {results.map(([id, row]) => {
                    const c = byId.get(id);
                    if (!c) return null;
                    return (
                      <div className="commission-result" key={id} data-selected={chosen.includes(id)}>
                        <div className="result-pair">
                          <ViewablePortrait subject={c} workspaceId={workspaceId} saveId={saveId} author size={76} framing="plate"/>
                          <ArrowRight size={15} />
                          <ViewablePortrait subject={{id,name:c.name,procedural_portrait:row.descriptor}} size={76} framing="plate"/>
                        </div>
                        <strong>{c.name}</strong>
                        {row.warnings.length > 0 && <small>{row.warnings.join(' ')}</small>}
                        {onPreview ? (
                          <Button
                            onClick={() => {
                              onPreview(row.descriptor);
                              setOpen(false);
                            }}
                          >
                            В предпросмотр
                          </Button>
                        ) : (
                          <label>
                            <input
                              type="checkbox"
                              aria-label={'Применить для ' + c.name}
                              checked={chosen.includes(id)}
                              onChange={() => selectResult(toggle(chosen, id))}
                            />
                            {c.portrait ? 'Заменить фото' : 'Применить портрет'}
                          </label>
                        )}
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </div>
          <footer className="commission-foot">
            {error && (
              <div className="commission-recovery">
                <p role="alert">{error}</p>
                {refresh && (
                  <Button
                    variant="ghost"
                    onClick={async () => {
                      await refresh();
                      setOpen(false);
                    }}
                  >
                    Обновить карточки
                  </Button>
                )}
              </div>
            )}
            {!ticket && !onPreview && (
              <div className="commission-selection">
                <button
                  aria-label="Показать выбранных"
                  onClick={() => {
                    setFilter('selected');
                    setQuery('');
                  }}
                  disabled={!ids.length}
                >
                  <span className="cast-stack">
                    {ids
                      .slice(0, 3)
                      .map((id) => byId.has(id) && <span key={id}>{avatar(byId.get(id)!, 27)}</span>)}
                  </span>
                  Выбрано {ids.length} / 64
                </button>
                <button disabled={!ids.length} onClick={() => select([])}>
                  Снять выбор
                </button>
              </div>
            )}
            <div className="commission-summary">
              <span>
                <Wallet size={15} />
                <strong>{ticket ? money(ticket.cost) : 'Расход после расчёта'}</strong>
                {ticket && <span> · Запросов: {ticket.requests}</span>}
              </span>
              <small>
                {ticket && ticket.count + ' перс. · '}
                {ticket?.model || config.model} · Thinking {ticket?.thinking || config.thinking}
              </small>
            </div>
            <div className="commission-actions">
              {ticket && !waiting && (
                <Button variant="ghost" disabled={busy} onClick={resetTicket}>
                  <ArrowLeft size={15} />
                  {status === 'quoted' ? 'Изменить выбор' : 'Новый запрос'}
                </Button>
              )}
              {restoreFailed && (
                <Button variant="outline" disabled={busy} onClick={() => void show()}>
                  Восстановить запрос
                </Button>
              )}
              {!ticket && !restoreFailed && (
                <Button disabled={busy || !ids.length} onClick={() => void quote()}>
                  {busy ? 'Рассчитываем…' : 'Рассчитать расход'}
                  <ArrowRight size={16} />
                </Button>
              )}
              {status === 'quoted' && (
                <Button disabled={busy} onClick={() => void generate()}>
                  Подтвердить запрос
                </Button>
              )}
              {status === 'unknown' && (
                <Button
                  disabled={busy}
                  onClick={() =>
                    void work(async () => receive(await api<Ticket>(base + '/' + ticket!.id)))
                  }
                >
                  Обновить состояние
                </Button>
              )}
              {reviewing && !onPreview && results.length > 0 && (
                <Button disabled={busy || !chosen.length} onClick={() => void apply()}>
                  Применить выбранные · {chosen.length}
                </Button>
              )}
              {(waiting || (reviewing && (onPreview || !results.length))) && (
                <Button variant="outline" onClick={() => setOpen(false)}>
                  Закрыть окно
                </Button>
              )}
            </div>
          </footer>
        </DialogContent>
      </Dialog>
    </>
  );
}
