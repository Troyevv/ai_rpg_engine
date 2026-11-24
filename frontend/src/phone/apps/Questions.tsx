import { useDevice } from '../usePhone';
import { Catalog, TextForm, useListing } from './Listings';
import { Discussion, useVisiblePublications } from './Social';
import { Generation, useDraft } from '../data';

function Detail({ id }: { id: string }) {
  const d = useDevice(),
    { item: q, status } = useListing('questions', id);
  useVisiblePublications();
  return (
    <section className="smart-app">
      {status}
      {q && (
        <>
          <h3 data-publication={q.id}>{q.text}</h3>
          {q.sender ? (
            <button onClick={() => d.visit('social', { screen: 'profile', id: q.sender!.id })}>
              {q.sender.name}
            </button>
          ) : (
            <span>Аноним</span>
          )}
          <button onClick={() => d.push('person', q.recipient!.id)}>
            Страница ответов · {q.recipient?.name}
          </button>
          {q.publication_id ? (
            <Discussion id={q.publication_id} />
          ) : q.recipient?.id === d.phone.actor_id ? (
            <div className="smart-actions">
              <button onClick={() => d.push('answer', id)}>Ответить на вопрос</button>
              <button
                disabled={d.locked}
                onClick={async () => {
                  if (await d.command('questions', 'hide', { target: id })) d.back();
                }}
              >
                Скрыть вопрос
              </button>
            </div>
          ) : (
            <p>Ответ пока не опубликован.</p>
          )}
          <Generation app="questions" />
        </>
      )}
    </section>
  );
}
function Ask({ id }: { id: string }) {
  const d = useDevice(),
    [mode, set] = useDraft('question-mode:' + id, 'anonymous');
  return (
    <TextForm
      label="Ваш вопрос"
      button="Отправить вопрос"
      draft={'question:' + id}
      submit={(text) =>
        d.command('questions', 'ask', { target: id, text, desired: mode === 'anonymous' }, true)
      }
    >
      <label>
        Авторство
        <select value={mode} onChange={(e) => set(e.target.value)}>
          <option value="anonymous">Анонимно</option>
          <option value="named">От своего имени</option>
        </select>
      </label>
    </TextForm>
  );
}
export function Questions() {
  const d = useDevice(),
    r = d.route;
  if (r?.screen === 'detail') return <Detail key={r.id} id={r.id!} />;
  if (r?.screen === 'answer')
    return (
      <TextForm
        label="Ваш ответ"
        button="Опубликовать ответ"
        draft={'answer:' + r.id}
        submit={(text) => d.command('questions', 'answer', { target: r.id, text })}
      />
    );
  if (r?.screen === 'ask') return <Ask id={r.id!} />;
  if (r?.screen === 'people')
    return (
      <div className="smart-people">
        {d.save.state.characters.map((p) => (
          <button key={p.id} onClick={() => d.push('person', p.id)}>
            {p.name}
          </button>
        ))}
      </div>
    );
  if (r?.screen === 'person')
    return (
      <Catalog app="questions" profile={r.id}>
        <h3>{d.save.state.characters.find((p) => p.id === r.id)?.name}</h3>
        {r.id !== d.phone.actor_id && <button onClick={() => d.push('ask', r.id)}>Задать вопрос</button>}
      </Catalog>
    );
  return (
    <Catalog app="questions" tabs={{ '': 'Опубликованные', inbox: 'Входящие', sent: 'Отправленные' }}>
      <button onClick={() => d.push('people')}>Страницы персонажей</button>
      <Generation app="questions" />
    </Catalog>
  );
}
