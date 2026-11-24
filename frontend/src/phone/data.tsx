import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { active, type Job } from '../types';
import { useDevice } from './usePhone';

export function useRecords<T>(path: string) {
  const { save, scope } = useDevice();
  const [result, setResult] = useState<{ key: string; data: T } | null>(null);
  const [error, setError] = useState('');
  const [attempt, retry] = useState(0);
  const key = scope + ':' + path;
  useEffect(() => {
    const abort = new AbortController();
    setError('');
    api<T>(`/saves/${save.id}/apps/${path}`, undefined, 'GET', abort.signal)
      .then((data) => {
        if (!abort.signal.aborted) setResult({ key, data });
      })
      .catch((e) => {
        if (!abort.signal.aborted) setError(e.message);
      });
    return () => abort.abort();
  }, [key, save.revision, attempt]);
  return {
    data: result?.key === key ? result.data : null,
    status: error ? (
      <p role="alert">
        {error} <button onClick={() => retry((n) => n + 1)}>Повторить загрузку</button>
      </p>
    ) : result?.key !== key ? (
      <p role="status">Загрузка…</p>
    ) : null,
  };
}

export function useDraft(key: string, fallback = '') {
  const { scope } = useDevice();
  const id = 'phone-editor:' + scope + ':' + key;
  const [entry, setEntry] = useState(() => ({ id, value: sessionStorage.getItem(id) ?? fallback }));
  const value = entry.id === id ? entry.value : (sessionStorage.getItem(id) ?? fallback);
  return [
    value,
    (v: string) => {
      if (v) sessionStorage.setItem(id, v);
      else sessionStorage.removeItem(id);
      setEntry({ id, value: v });
    },
  ] as const;
}

export function useGeneration(app: string) {
  const { job, save } = useDevice();
  return (job?.kind === 'smartphone' || job?.kind === 'communication') &&
    job.presentation?.app === app &&
    job.revision === save.revision &&
    (active(job) || job.status === 'stopped' || job.status === 'error')
    ? job
    : null;
}

export function Generation({ app }: { app: string }) {
  const { apiKey, config, onJob, setError } = useDevice();
  const job = useGeneration(app);
  const retryPending = useRef(false);
  const [retrying, setRetrying] = useState(false);
  if (!job) return null;
  const path = '/jobs/' + job.id;
  const running = active(job);
  const action = job.presentation?.action;
  const status = {
    search: ['Поиск анкет', 'Не удалось подготовить выдачу. Параметры поиска сохранены.'],
    accept: ['Создание карточки', 'Не удалось завершить карточку. Выбранная анкета сохранена.'],
    generate: ['Подготовка публикаций', 'Не удалось обновить каталог.'],
    invite: ['Ответы на приглашения', 'Приглашения сохранены. Не удалось обработать ответы.'],
    apply: ['Обработка отклика', 'Отклик сохранён. Не удалось завершить отправку или обработать ответ.'],
    refresh: ['Новые публикации', 'Не удалось обновить ленту.'],
  };
  const [label, failure] = status[action as keyof typeof status] ?? [
    'Ответы персонажей',
    'Ваша запись сохранена. Не удалось подготовить ответы.',
  ];
  return (
    <div className="smart-generation" role={running ? 'status' : 'alert'}>
      <strong>{label}</strong>
      {running ? (
        <button onClick={() => api(path + '/stop', {}).catch((e) => setError(e.message))}>Остановить</button>
      ) : (
        <>
          <p>
            {job.status === 'stopped' ? 'Генерация остановлена.' : failure}
            {action === 'refresh' && job.status === 'error' && job.error && ' ' + job.error}
          </p>
          <button
            disabled={retrying}
            onClick={async () => {
              if (retryPending.current) return;
              retryPending.current = true;
              setRetrying(true);
              try {
                onJob(
                  await api<Job>(path + '/retry', {
                    revision: job.revision,
                    attempt_epoch: job.attempt_epoch,
                    config,
                    api_key: apiKey,
                  }),
                );
              } catch (e) {
                setError(String(e));
              } finally {
                retryPending.current = false;
                setRetrying(false);
              }
            }}
          >
            Повторить генерацию
          </button>
        </>
      )}
    </div>
  );
}
