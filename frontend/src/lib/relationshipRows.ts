import type { State, WorldRelation } from "../types";
export type RelationshipRow = WorldRelation & {
  change?: { direction: string; reason: string };
};
/** Read-only adapter for the existing canonical and legacy API projections. */
export function relationshipRows(state: State): RelationshipRow[] {
  const structured = Object.values(state.world?.relationships || {});
  const rows: RelationshipRow[] = structured.map((r) => ({
    ...r,
    change: state.relationships.find(
      (v) => v.source_id === r.source_id && v.target_id === r.target_id,
    )?.change,
  }));
  for (const r of state.relationships) {
    if (
      structured.some(
        (x) =>
          x.source_id === r.source_id &&
          (x.target_id === r.target_id ||
            state.characters.find((c) => c.id === x.target_id)?.name ===
              r.target_name),
      )
    )
      continue;
    rows.push({
      source_id: r.source_id,
      target_id: r.target_id || r.target_name || "Неизвестно",
      context: r.text,
      dimensions: {},
      change: r.change,
    });
  }
  return rows;
}
