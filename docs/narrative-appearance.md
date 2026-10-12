# Canonical appearance and portrait attachments (#74)

Parent: #36. Extends the existing Character, StateResolver, Context Builder,
History DAG and save snapshots; Narrative Runtime remains v3. No Tabletop rules,
phone, genetics, age-driven cosmetics or general card redesign are introduced.

## Ownership and semantic boundary

`Character.appearance` is one `AppearanceProfile` for every life stage and agency.
`items` separates intrinsic traits, body traits, cosmetic modifications, current
presentation and references to functional conditions. Unknown fields are absent.
The same Character ID and profile survive birth, growth and control changes.
`legacy_text` preserves unclassified imported appearance verbatim: it is not
parsed into invented eye colour, sex, body measurements or permanent clothing.
Cards show it separately as «Исходное описание внешности».

Extraction reports `appearance_deltas`, not whole profiles. Each operation needs
an accepted current Event involving the Character, its appearance Fact, an exact
quote from completed narrative, semantic `established_visual_outcome`, a stable
item ID and expected revision. Runtime validates those references, category/kind,
agency, CAS, profile bounds and source identity. Invalid optional operations are
reported locally. Tattoos/piercings/haircuts/cosmetics require a voluntary
transition; EXTERNAL changes additionally require explicit player choice quoted
from input. AUTONOMOUS choices still require a completed outcome. An intention,
ordinary injury or elapsed time alone never triggers a runtime mutation.

The semantic meaning of a quoted sentence is Extraction's responsibility. Quote
matching and a typed assertion do not constitute an independent natural-language
proof that the claim is true. No extra LLM verification or per-character calls
are added. Involuntary scars require an explicitly established visual result.

Functional consequences have no independent mutable appearance description:
`category=condition` stores `condition_id`, with matching actor/fact, and empty
text. Read projections obtain the description from #38 only while that condition
is active. Resolution/change of #38 immediately invalidates/updates the visual
projection. Cosmetic scars without a functional condition are standalone items.

Accepted changes append before/after/provenance to the existing History DAG;
permanent modifications also enter #40 Milestones. `applied` guards use the
canonical source Event and item ID, plus Event/Fact/kind so a renamed extraction
item cannot duplicate the same accepted consequence. Snapshots own current state and guards;
rollback, branches and original regeneration context remain unchanged.

## Knowledge, UI and prompt budgets

Appearance changes do not write Character Knowledge. Updated traits require
self-knowledge or a known supporting Fact in POV projections; #76's normal
observation/communication pipeline acquires that Fact. Context includes bounded
current traits and `known_by`, never the applied ledger, full history, portrait
references or bytes. Imported baseline prose is explicitly labelled, not used to
broadcast later changes. Source-less initial traits retain initial-card semantics.

Cards render the full authorized current profile and at most 24 recent authorized
appearance transitions. Context uses at most 1600 characters per selected profile
and at most 600 characters of unclassified baseline. Under extraction budget
pressure baseline prose is omitted; optional personality evaluation without
accumulated evidence is reduced before failing the hard model limit. Current
structured appearance, scene continuity and original model limits are retained.

## Portrait API and storage

All consumers use `runtime_v3.portraits` for applicability/selection and the shared
`CharacterAvatar` component. The public API is scoped to
`/api/saves/{sid}/characters/{cid}/portraits`:

- GET: authorized attachments, current selection, silhouette and save revision.
- POST: raw PNG/JPEG/WebP body, `revision`, optional `replace_id`, JSON `settings`.
- PATCH `/{portrait_id}`: revision plus crop, label, life stage/age bounds and
  `make_current`; unknown fields/invalid ranges fail closed.
- DELETE `/{portrait_id}?revision=…`: detach in this snapshot, with revision guard.
- GET `/assets/{asset_id}`: authorized full, orientation-normalized PNG original.

Upload checks MIME against actual decoded format, complete image decoding,
10 MiB source limit and a separate 32,000,000-pixel decoded source budget before
resizing. Pillow decompression-bomb warnings/errors are also rejected. Output
dimensions are 256–4096 on each side. Animated
images and corrupt content are rejected. Pillow is the project-owned adapter's
only added dependency (`>=11.3,<13`); metadata is removed and full oriented pixels
are safely re-encoded without crop or aspect-ratio distortion. Sources with a
side above 4096 are proportionally reduced; sources with a side below 256 are
proportionally enlarged only if the result fits within 4096. Both use Pillow
LANCZOS (with nearest integer pixel rounding). Aspect ratios beyond 16:1 cannot
satisfy both limits and are rejected with HTTP 422; corrupt/unsafe sources also
return 422, oversized request bodies return 413. The editor warns before saving
that enlargement can blur an image or reduce quality. The stored original is
the full normalized frame, never the circular crop; source pixel dimensions may
therefore change. Existing assets are untouched. Pixel decoding follows Pillow's
[security guidance](https://pillow.readthedocs.io/en/stable/handbook/security.html).

Immutable images are managed BLOB assets in `portrait_assets`, outside WorldState
JSON. The additive `portrait_assets_v1` migration creates this table. UUID names
and parameterized DB queries have no user-provided filesystem path to traverse.
WorldState contains only typed references, dimensions, crop, period and ordering.
Asset insertion, reference edits, History and save revision update share one
SQLite transaction; failed edits cannot create an orphan. Busy saves reject edits.

Read requires an active world, the requested Character's current authorized
reference and matching asset world. Hidden newborns remain hidden. Images are
served `private, no-store`, `nosniff`, with no global static asset route. Another
save cannot fetch an attachment it does not reference; a genuine copied branch
can. Separate user databases cannot resolve each other's assets.

**Existing deployment boundary:** this repository is a local single-user app,
with no authenticated accounts or per-user save ACL. Portraits use exactly its
existing DB/save/POV boundary; this change does not turn it into an authenticated
multi-user hosting service. Shared network deployment requires authorization for
all save routes, including these, when the application gains account support.

## Period, crop, retention and limits

Selection is deterministic: nondeleted references matching the current canonical
life period and inclusive optional age range, then greatest `(order, id)`. Missing
age does not satisfy age-specific portraits. A portrait uploaded for unknown
period is applicable only while that period stays unknown. Explicit age determines
portrait applicability (infant <2, child <13, adolescent <18, adult otherwise),
falling back to canonical developmental stage when age is unknown. This changes
only attachment selection, never textual physical traits. Childhood images do not
automatically become adult likenesses; they remain accessible in history.

Crop `x,y ∈ [0,1]`, `zoom ∈ [1,4]` describes a square viewport over the full image;
every avatar uses that same geometry under a circular mask. Missing/broken images
show a silhouette plus initials, with sex variant only from authorized canonical
sex; names and prose are never inspected. One adjacent pencil opens upload, crop,
history, replacement and confirmed removal; the avatar opens the original viewer.
The editor uses explicit save/cancel. The viewer supports fit, zoom, mouse/touch
pan and accessible close. Phone will reuse this contract without another store.

Removal is reference detachment, not global erasure. Replaced originals remain
in portrait history. Physical retention is conservatively the database lifetime,
including soft-deleted worlds: old variants, archived turns and independent
branches may retain references. No TTL or partial reachability garbage collector
is used. Failed transactions leave no assets. Deleting an entire local database
removes its assets; backup/copy the database as one unit. Up to 128 references per
Character (including detached history) and 48 current appearance items are
supported. No AI generation, image-derived facts, thumbnail cache, external image
service, export bundle or account system is implemented.

## Migration

Existing saved snapshots default to an empty profile and no portraits. Read-time
initialization preserves old prose without changing stored historical JSON or
initializing unrelated calendar/personality state. Explicit structured imported
appearance is retained. Invalid optional appearance/portrait entries are logged
and omitted locally while valid siblings remain. #41 preserves explicit newborn
appearance in the same profile. Nothing derives traits from parents or age.

See [manual QA](manual_qa/narrative_v4/appearance.md).
