import {CharacterAvatar} from "./Portrait";
import {it} from "./lib/inspector";
import type {State,Save} from "./types";

export function CharacterPeople({
  ids,
  state,
  save,
  onCharacter,
  hideUnavailable=false,
}: {
  hideUnavailable?: boolean;
  ids: string[];
  state: State;
  save?: Save | null;
  onCharacter: (id: string) => void;
}) {
  return (
    <div className="inspector-people">
      {[...new Set(ids)].map((id) => {
        const c = state.characters?.find((c) => c.id === id);
        return c ? (
          <button
            type="button"
            aria-label={`Открыть досье: ${c.name}`}
            data-character-id={id}
            className="inspector-person-chip"
            key={id}
            onClick={() => onCharacter(id)}
          >
            <CharacterAvatar subject={c} saveId={save?.id} size={26} />
            <span>{c.name}</span>
          </button>
        ) : hideUnavailable ? null : (
          <span className="muted small" key={id}>
            {it("unknown")}
          </span>
        );
      })}
    </div>
  );
}
