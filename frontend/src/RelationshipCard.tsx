import type { ReactNode } from "react";
import { ArrowRight } from "lucide-react";
import { CharacterAvatar } from "./Portrait";
import { Markdown } from "./Markdown";
import type { State, WorldRelation } from "./types";
import { relationshipLabel } from "./lib/relationships";
import "./styles/relationships.css";

export function RelationshipPair({
  state,
  source,
  target,
  saveId,
  onCharacter,
}: {
  state: State;
  source: string;
  target: string;
  saveId?: number;
  onCharacter?: (id: string) => void;
}) {
  const person = (id: string) => {
    const c = state.characters.find((c) => c.id === id);
    return c ? (
      <button
        type="button"
        className="relationship-person"
        disabled={!onCharacter}
        onClick={() => onCharacter?.(id)}
        aria-label={`Открыть досье: ${c.name}`}
      >
        <CharacterAvatar subject={c} saveId={saveId} size={44} />
        <span>{c.name}</span>
      </button>
    ) : (
      <span className="relationship-person">{id}</span>
    );
  };
  return (
    <div className="relationship-pair">
      {person(source)}
      <ArrowRight aria-label="отношение к" size={20} />
      {person(target)}
    </div>
  );
}
export function RelationshipCard({
  state,
  relation,
  saveId,
  onCharacter,
  actions,
  change,
}: {
  state: State;
  relation: WorldRelation;
  saveId?: number;
  onCharacter?: (id: string) => void;
  actions?: ReactNode;
  change?: { direction: string; reason: string };
}) {
  return (
    <article
      className="inspector-card inspector-relation relationship-card"
      data-source={relation.source_id}
      data-target={relation.target_id}
    >
      <div>
        <RelationshipPair
          state={state}
          source={relation.source_id}
          target={relation.target_id}
          saveId={saveId}
          onCharacter={onCharacter}
        />
        <div
          className="relationship-context"
          tabIndex={0}
          role="region"
          aria-label="Описание отношения"
        >
          <Markdown text={relation.context} />
        </div>
      </div>
      <div className="inspector-metrics">
        {Object.entries(relation.dimensions).map(([key, value]) => (
          <div key={key} data-dimension={key} className="inspector-metric">
            <div>
              <span>{relationshipLabel(key)}</span>
              <strong>{typeof value === "number" ? value : "Изменение"}</strong>
            </div>
            {typeof value === "number" ? (
              <meter
                min={-100}
                max={100}
                value={value}
                aria-label={`${relationshipLabel(key)}: ${value}; от −100 до 100`}
              />
            ) : (
              <p>
                {value.direction === "up"
                  ? "↑"
                  : value.direction === "down"
                    ? "↓"
                    : "→"}{" "}
                {value.reason}
              </p>
            )}
          </div>
        ))}
        {!Object.keys(relation.dimensions).length && (
          <p className="muted small">Показатели не заданы</p>
        )}
        {Object.values(relation.dimensions).some(
          (v) => typeof v === "number",
        ) && <small className="muted">Диапазон: −100…100</small>}
      </div>
      {(change || actions) && (
        <footer className="inspector-card-footer">
          {change && (
            <p>
              {change.direction === "up"
                ? "↑"
                : change.direction === "down"
                  ? "↓"
                  : "↕"}{" "}
              {change.reason}
            </p>
          )}
          {actions}
        </footer>
      )}
    </article>
  );
}
