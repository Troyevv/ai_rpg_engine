import type {Character, DossierPersonalRelation} from '../types';

type RomanticKind = 'partner' | 'engaged' | 'spouse';
export type PersonalRelationship =
  | {kind: RomanticKind; partnerId: string}
  | {kind: 'divorced' | 'widowed'};
const priority: Record<RomanticKind, number> = {partner: 1, engaged: 2, spouse: 3};
const compareId = (a: string, b: string) => a < b ? -1 : a > b ? 1 : 0;

// Compare only compatible canonical clocks. ISO dates also cover pre-game phases
// whose runtime minute is unknown. Never parse prose or mix dates with minutes.
function compareTime(a: DossierPersonalRelation, ak: 'since'|'until', b: DossierPersonalRelation, bk: 'since'|'until'): number|null {
  if (a[ak] != null && b[bk] != null) return Math.sign(a[ak]! - b[bk]!);
  const ad=a[`${ak}_date`], bd=b[`${bk}_date`];
  if (ad && bd && /^\d{4}-\d{2}-\d{2}$/.test(ad) && /^\d{4}-\d{2}-\d{2}$/.test(bd)) return compareId(ad,bd);
  return null;
}

/** Presentation of the canonical dossier directory only. Never writes world truth. */
export function personalRelationships(
  characterId: string,
  relations: readonly DossierPersonalRelation[] = [],
  characters: readonly Pick<Character, 'id' | 'name'>[] = [],
): PersonalRelationship[] {
  const available = new Set(characters.filter(c => c.name.trim()).map(c => c.id));
  const active = new Map<string, RomanticKind>();
  const historical: DossierPersonalRelation[] = [];
  const relevant = relations.filter(r => Object.hasOwn(priority,r.kind) &&
    (r.source_id === characterId || r.target_id === characterId) && r.source_id !== r.target_id);
  let conflict = false;
  for (const r of relevant) {
    const other = r.source_id === characterId ? r.target_id : r.source_id;
    if (r.status === 'active') {
      // A closed phase of equal/higher rank contradicts a stale active phase
      // unless an explicit later start establishes a new relationship.
      const closures = relevant.filter(c => c.status === 'closed' && c.outcome !== 'superseded' &&
        [c.source_id,c.target_id].includes(other) && priority[c.kind as RomanticKind] >= priority[r.kind as RomanticKind]);
      if (closures.some(c => compareTime(r,'since',c,'until') !== 1)) { conflict = true; continue; }
      const kind = r.kind as RomanticKind;
      if (!active.has(other) || priority[kind] > priority[active.get(other)!]) active.set(other, kind);
    } else if (r.status === 'closed' && r.kind === 'spouse' && ['divorced', 'widowed'].includes(r.outcome)) {
      historical.push(r);
    }
  }
  // Even an unavailable active endpoint prevents a false historical status.
  if (active.size) return [...active].filter(([id]) => available.has(id))
    .sort(([a, ka], [b, kb]) => priority[kb] - priority[ka] || compareId(a, b))
    .map(([partnerId, kind]) => ({kind, partnerId}));
  if (conflict) return [];
  // An outcome is safe only if it is later than every incompatible outcome.
  // Equal/unknown chronology must not pick an arbitrary relation ID.
  const latest = historical.find(r => historical.every(other =>
    other.outcome === r.outcome || compareTime(r,'until',other,'until') === 1));
  return latest ? [{kind: latest.outcome as 'divorced' | 'widowed'}] : [];
}
