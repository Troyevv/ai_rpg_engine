import type { Build, Catalog, Entry } from "./types";
export function StartingShop({
  build,
  catalog,
  change,
}: {
  build: Build;
  catalog: Catalog;
  change: (b: Build) => void;
}) {
  const bought = build.purchases || [];
  const capital =
    catalog.starting_gold +
    (catalog.classes[build.character_class].starting_gold || 0) +
    (catalog.backgrounds[build.background].starting_gold || 0);
  const spent = bought.reduce(
    (n, e) =>
      n +
      (catalog.items.find((i) => i.id === e.item_id)?.value || 0) * e.quantity,
    0,
  );
  const buy = (id: string) => {
    const item = catalog.items.find((i) => i.id === id)!;
    const entries = bought.map((e) => ({ ...e }));
    const existing = entries.find((e) => e.item_id === id);
    if (existing) {
      existing.quantity++;
      existing.equipped = false;
      existing.slot = "";
    } else {
      const allowed =
        item.type !== "armor" ||
        catalog.classes[build.character_class].armor?.includes(
          item.armor_category,
        );
      const slot = allowed ? item.slots[0] || "" : "";
      entries.forEach((e) => {
        if (
          slot &&
          (e.slot === slot ||
            (item.hands === 2 &&
              ["MAIN_HAND", "OFF_HAND"].includes(e.slot || "")) ||
            (["MAIN_HAND", "OFF_HAND"].includes(slot) &&
              catalog.items.find((i) => i.id === e.item_id)?.hands === 2))
        ) {
          e.equipped = false;
          e.slot = "";
        }
      });
      entries.push({
        item_id: id,
        quantity: 1,
        equipped: !!slot,
        slot,
      } as Entry);
    }
    change({ ...build, purchases: entries });
  };
  return (
    <section>
      <h3>Стартовый магазин</h3>
      <p role="status" aria-label="Бюджет снаряжения">
        Капитал: {capital} · Потрачено: {spent} · Осталось: {capital - spent}{" "}
        золота
      </p>
      <p>
        Остаток золота сохранится у героя. Покупки с подходящим слотом
        надеваются; смена класса может потребовать снять недоступную броню.
      </p>
      <div className="tt-catalog-grid">
        {catalog.items
          .filter((i) => i.value > 0 && i.type !== "quest")
          .map((i) => {
            const own = bought.find((e) => e.item_id === i.id);
            return (
              <article className="tt-feature" key={i.id}>
                <h3>
                  {i.name} · {i.value} золота
                </h3>
                <p>{i.description}</p>
                {i.type === "weapon" && (
                  <p>
                    Урон 1d{i.weapon_die} + модификатор ·{" "}
                    {i.hands === 2 ? "две руки" : "одна рука"}
                  </p>
                )}
                {i.type === "armor" && (
                  <p>
                    {i.ac_bonus
                      ? `КД +${i.ac_bonus}`
                      : `КД ${i.armor_base} + Ловкость (до ${i.dex_cap})`}
                    {i.stealth_disadvantage ? " · помеха Скрытности" : ""}
                  </p>
                )}
                <p>
                  {own
                    ? `Куплено: ${own.quantity}${own.equipped ? " · надето" : " · в рюкзаке"}`
                    : "Не куплено"}
                </p>
                <button
                  disabled={capital - spent < i.value || !!own?.equipped}
                  onClick={() => buy(i.id)}
                >
                  Купить: {i.name}
                </button>
                {own && (
                  <>
                    <button
                      onClick={() =>
                        change({
                          ...build,
                          purchases: bought.flatMap((e) =>
                            e !== own
                              ? [e]
                              : e.quantity > 1
                                ? [{ ...e, quantity: e.quantity - 1 }]
                                : [],
                          ),
                        })
                      }
                    >
                      Вернуть: {i.name}
                    </button>
                    {!own.equipped &&
                      own.quantity === 1 &&
                      i.slots.length > 0 && (
                        <button
                          onClick={() => {
                            const entries = bought.map((e) => ({ ...e }));
                            const entry = entries.find(
                              (e) => e.item_id === i.id,
                            )!;
                            const slot =
                              i.slots.find(
                                (s) =>
                                  !entries.some(
                                    (e) => e.equipped && e.slot === s,
                                  ),
                              ) || i.slots[0];
                            entries.forEach((e) => {
                              if (
                                e.slot === slot ||
                                (i.hands === 2 &&
                                  ["MAIN_HAND", "OFF_HAND"].includes(
                                    e.slot || "",
                                  )) ||
                                (["MAIN_HAND", "OFF_HAND"].includes(slot) &&
                                  catalog.items.find((i) => i.id === e.item_id)
                                    ?.hands === 2)
                              ) {
                                e.equipped = false;
                                e.slot = "";
                              }
                            });
                            entry.equipped = true;
                            entry.slot = slot;
                            change({ ...build, purchases: entries });
                          }}
                        >
                          Надеть: {i.name}
                        </button>
                      )}
                    {own.equipped && (
                      <button
                        onClick={() =>
                          change({
                            ...build,
                            purchases: bought.map((e) =>
                              e === own
                                ? { ...e, equipped: false, slot: "" }
                                : e,
                            ),
                          })
                        }
                      >
                        Снять: {i.name}
                      </button>
                    )}
                  </>
                )}
              </article>
            );
          })}
      </div>
    </section>
  );
}
