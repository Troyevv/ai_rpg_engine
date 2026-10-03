import { useEffect, useRef } from "react";
import type { Roll } from "../types";
import { canonicalDice } from "./canonical";
import "./dice.css";
export function DiceTray({ rolls, done }: { rolls: Roll[]; done: () => void }) {
  const host = useRef<HTMLDivElement>(null),
    callback = useRef(done);
  callback.current = done;
  const { dice, omitted } = canonicalDice(rolls);
  useEffect(() => {
    let disposed = false,
      cleanup: (() => void) | undefined;
    const finish = () => {
      if (!disposed) callback.current();
    };
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const timer = window.setTimeout(finish, reduced ? 250 : 3000);
    if (!reduced)
      void import("./renderer")
        .then(({ renderDice }) => {
          if (!disposed && host.current) {
            try {
              cleanup = renderDice(host.current, dice, finish);
            } catch {
              finish();
            }
          }
        })
        .catch(finish);
    return () => {
      disposed = true;
      clearTimeout(timer);
      cleanup?.();
    };
  }, [rolls]);
  return (
    <section
      className="tt-dice-tray"
      aria-label="3D-бросок кубиков"
      role="status"
    >
      <div ref={host} className="tt-dice-surface" aria-hidden="true" />
      <div className="tt-dice-values">
        {dice.map((d, i) => (
          <span
            key={i}
            data-die={d.sides}
            data-value={d.label}
            data-selected={!d.muted}
            className={d.muted ? "tt-die-muted" : ""}
          >
            d{d.sides}: {d.label}
            {d.muted ? " · не выбран" : ""}
          </span>
        ))}
      </div>
      {omitted > 0 && (
        <small>Ещё {omitted} кубиков — в полном результате.</small>
      )}
      <button onClick={done}>Пропустить анимацию</button>
    </section>
  );
}
