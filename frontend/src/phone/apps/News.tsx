import { useDevice } from '../usePhone';
import { Catalog, useListing } from './Listings';
import { Discussion, useVisiblePublications } from './Social';
import { Generation } from '../data';

function Article({ id }: { id: string }) {
  const { item, status } = useListing('news', id);
  const { push } = useDevice();
  useVisiblePublications();
  return (
    <section className="smart-app">
      {status}
      {item && (
        <>
          <small>
            {item.category} · {item.published}
          </small>
          <h3>{item.title}</h3>
          {item.previous_id && (
            <button onClick={() => push('detail', item.previous_id!)}>Предыдущая статья</button>
          )}
          <Discussion id={id} />
          <Generation app="news" />
        </>
      )}
    </section>
  );
}
export function News() {
  const { route } = useDevice();
  return route?.id ? <Article key={route.id} id={route.id} /> : <Catalog app="news" />;
}
