import { useEffect, useState } from 'react';
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

export function Generation({ app }: { app: string }) {
  const { job, save, apiKey, config, onJob, setError } = useDevice();
  if (job?.kind !== 'smartphone' || job.presentation?.app !== app || job.revision !== save.revision)
    return null;
  const path = '/jobs/' + job.id;
  const running = active(job);
  const label =
    job.presentation.action === 'search'
      ? 'Поиск анкет'
      : job.presentation.action === 'accept'
        ? 'Создание карточки'
        : 'Ответы персонажей';
  if (!running && !['stopped', 'error'].includes(job.status)) return null;
  return (
    <div className="smart-generation" role={running ? 'status' : 'alert'}>
      <strong>{label}</strong>
      {running ? (
        <button onClick={() => api(path + '/stop', {}).catch((e) => setError(e.message))}>Остановить</button>
      ) : (
        <>
          <p>
            {job.status === 'stopped'
              ? 'Генерация остановлена.'
              : app === 'social'
                ? 'Ваша запись сохранена. Не удалось подготовить ответы.'
                : job.presentation.action === 'search'
                  ? 'Не удалось подготовить выдачу. Параметры поиска сохранены.'
                  : 'Не удалось завершить карточку. Выбранная анкета сохранена.'}
          </p>
          <button
            onClick={async () => {
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
