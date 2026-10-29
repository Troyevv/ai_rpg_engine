import type {Character, SocialRelation} from '../types';

type RomanticKind = 'partner' | 'engaged' | 'spouse';
export type PersonalRelationship =
  | {kind: RomanticKind; partnerId: string}
  | {kind: 'divorced' | 'widowed'};
const priority: Record<RomanticKind, number> = {partner: 1, engaged: 2, spouse: 3};
const compareId = (a: string, b: string) => a < b ? -1 : a > b ? 1 : 0;

/** Presentation only. Callers pass the authorized projection, never world truth.
 * Suspicion is deliberately omitted; absence never establishes single status.
 */
export function personalRelationships(
  characterId: string,
  relations: readonly SocialRelation[] = [],
  characters: readonly Pick<Character, 'id' | 'name'>[] = [],
): PersonalRelationship[] {
  const available = new Set(characters.filter(c => c.name.trim()).map(c => c.id));
  const active = new Map<string, RomanticKind>();
  const historical: SocialRelation[] = [];
  for (const r of relations) {
    if (r.certainty !== 'known' || !Object.hasOwn(priority, r.kind)) continue;
    if (r.source_id !== characterId && r.target_id !== characterId) continue;
    const other = r.source_id === characterId ? r.target_id : r.source_id;
    if (other === characterId) continue;
    if (r.status === 'active') {
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
  // Only projected closure times participate; do not infer dates from prose.
  historical.sort((a, b) => (b.until ?? -Infinity) - (a.until ?? -Infinity) || compareId(a.id, b.id));
  if (!historical.length) return [];
  const latest = historical[0];
  // Unknown or tied chronology cannot choose between incompatible outcomes.
  if (historical.some(r => r.outcome !== latest.outcome &&
      (r.until == null || latest.until == null || r.until === latest.until))) return [];
  return [{kind: latest.outcome as 'divorced' | 'widowed'}];
}
