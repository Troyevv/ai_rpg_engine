import { useDevice } from '../usePhone';
import { Catalog, TextForm, useListing, employment } from './Listings';
import { Generation } from '../data';

function Vacancy({ id }: { id: string }) {
  const d = useDevice(),
    { item: r, status } = useListing('work', id);
  if (!r) return status;
  if (d.route?.screen === 'apply')
    return (
      <TextForm
        label="Текст отклика"
        button="Отправить отклик"
        draft={'application:' + id}
        initial={`Здравствуйте! Меня заинтересовала вакансия «${r.title}».`}
        submit={(text) => d.command('work', 'apply', { target: id, text }, true)}
      />
    );
  return (
    <section className="smart-app">
      <small>
        {r.published} · {r.category}
      </small>
      <h3>{r.title}</h3>
      <strong>{r.employer}</strong>
      <p>
        {r.location} · {employment[r.employment!]}
      </p>
      <p>{r.description}</p>
      <dl>
        {[
          ['Требования', r.requirements],
          ['График', r.schedule],
          ['Оплата', r.pay],
        ].map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v || 'Уточнить у работодателя'}</dd>
          </div>
        ))}
      </dl>
      <button
        aria-pressed={r.favorite}
        disabled={d.locked}
        onClick={() => void d.command('work', 'favorite', { target: id, desired: !r.favorite })}
      >
        {r.favorite ? 'Убрать из избранного' : 'В избранное'}
      </button>
      {!!r.previous_terms?.length && (
        <details>
          <summary>Условия изменились · прежние условия</summary>
          {r.previous_terms.map((t, i) => (
            <p key={i}>{[t.pay, t.schedule, t.requirements].filter(Boolean).join(' · ')}</p>
          ))}
        </details>
      )}
      {r.reply && <p>{r.reply}</p>}
      {r.conversation_id ? (
        <button
          onClick={() => {
            const c = d.phone.conversations.find((c) => c.id === r.conversation_id);
            if (c) void d.openChat(c);
          }}
        >
          Переписка с работодателем
        </button>
      ) : r.applied ? (
        <>
          <p>Отклик сохранён. Подготовка отправки.</p>
          {!d.locked && !d.job?.live && (
            <button
              onClick={() => void d.command('work', 'apply', { target: id, text: r.pending_text }, true)}
            >
              Продолжить отправку
            </button>
          )}
        </>
      ) : r.active ? (
        <button onClick={() => d.push('apply', id)}>Откликнуться</button>
      ) : (
        <p>Вакансия закрыта</p>
      )}
      {r.plans?.map((p) => (
        <button key={p.id} onClick={() => d.propose('Отправляюсь на встречу: ' + p.description)}>
          Отправиться · {p.description}
        </button>
      ))}
      <Generation app="work" />
    </section>
  );
}
export function Work() {
  const { route } = useDevice();
  return route?.id ? (
    <Vacancy id={route.id} />
  ) : (
    <Catalog
      app="work"
      tabs={{ '': 'Все вакансии', favorites: 'Избранное', mine: 'Мои отклики', roles: 'Моя работа' }}
    />
  );
}
