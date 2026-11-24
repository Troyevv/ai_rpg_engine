import { useDevice } from '../usePhone';
import { Catalog, TextForm, useListing, type RecordCard } from './Listings';
import { Generation, useDraft } from '../data';

function Invite({ item }: { item: RecordCard }) {
  const d = useDevice(),
    [selected, set] = useDraft('invite-people:' + item.id);
  const ids = selected.split(',').filter(Boolean);
  return (
    <TextForm
      label="Приглашение"
      disabled={ids.length === 0}
      button="Отправить приглашение"
      draft={'invite:' + item.id}
      initial={`Пойдём на «${item.title}»? ${item.time}. ${item.location || ''}`}
      submit={(text) => d.command('events', 'invite', { target: item.id, ids, text }, true)}
    >
      <fieldset>
        <legend>Кого пригласить</legend>
        {d.recipients
          .filter((r) => r.can_send)
          .map((r) => (
            <label key={r.id}>
              <input
                type="checkbox"
                checked={ids.includes(r.id)}
                onChange={(e) =>
                  set((e.target.checked ? [...ids, r.id] : ids.filter((i) => i !== r.id)).join(','))
                }
              />
              {r.subject.name}
            </label>
          ))}
      </fieldset>
    </TextForm>
  );
}
function Detail({ id }: { id: string }) {
  const d = useDevice(),
    { item: r, status } = useListing('events', id);
  if (!r) return status;
  if (d.route?.screen === 'invite') return <Invite item={r} />;
  return (
    <section className="smart-app">
      <Generation app="events" />
      <small>{r.category}</small>
      <h3>{r.title}</h3>
      <p>{r.description}</p>
      <p>
        {r.location} · {r.time}
        {r.end_time && ' — ' + r.end_time}
      </p>
      {r.previous_time && <p>Перенесено с {r.previous_time}</p>}
      {r.invitations?.map((i, n) => (
        <article className="smart-post" key={i.conversation_id + n}>
          <strong>
            {i.outgoing ? 'Приглашение для' : 'Приглашение от'} {i.person.name}
          </strong>
          {i.reply && <p>{i.reply}</p>}
          {i.plans.map((p) => (
            <p key={p}>{p}</p>
          ))}
          <button onClick={() => void d.openChat(i.conversation_id)}>Открыть чат</button>
        </article>
      ))}
      {r.planned && <p>В вашем календаре</p>}
      {(r.can_plan || r.planned) && (
        <button
          disabled={d.locked}
          onClick={() => void d.command('events', 'plan', { target: id, desired: !r.planned })}
        >
          {r.planned ? 'Отменить план' : 'Запланировать'}
        </button>
      )}
      {r.active ? (
        <>
          <button onClick={() => d.push('invite', id)}>Пригласить</button>
          <button
            onClick={() => d.propose(`Отправляюсь на «${r.title}»${r.location ? ' — ' + r.location : ''}.`)}
          >
            Отправиться
          </button>
        </>
      ) : (
        <p>{r.cancelled ? 'Отменено' : 'Мероприятие завершилось'}</p>
      )}
    </section>
  );
}
export function Events() {
  const { route } = useDevice();
  return route?.id ? <Detail id={route.id} /> : <Catalog app="events" />;
}
