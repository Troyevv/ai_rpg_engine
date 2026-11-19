# Issue #255 — real combined-repair recovery

**Narrow live acceptance: PASS. General #255/playtest acceptance remains pending.**

Run on `28378c88b74e9dae543b1ed0d4bd549ca0882621`, DeepSeek Flash, thinking off,
with the full production schema and FastAPI job path. The user separately
authorized eight new calls / $0.50. No product code changed during the run.
No model reply was substituted, edited or regenerated to obtain a better result.

## Recovery of the original cafe departure

An independent backup of `work/issue255-live/smoke-final.sqlite` retained the
original failed job, its Narrative, before state and all three earlier attempts.
One production Retry started attempt epoch 3 at save revision 43. There was one
server per working SQLite, with ordinary startup recovery enabled.

The first new Extraction repeated all three errors: departure with a destination,
controlled arrival without input authority, and an observer-only camera override.
This time all three diagnostics reached the **same single bounded repair**:

- `movement_endpoint_invalid`, `scene_steps[1]`;
- `movement_agency`, `scene_steps[2]`;
- `camera_invalid`, `scene.observer_location_id`.

The real repair set the departure endpoint to null, attached the existing input
quote «иду домой к маме на Лесную» to the arrival, and cleared the observer override
with null. The assembled candidate is exactly the first reply with those three
changes; all independent fields and steps were retained. It passed recompilation,
Runtime and atomic persistence, revision **43 → 44**. The original complete
Narrative is byte-for-byte unchanged, including Viktor's farewell and Tamara's
invitation. No additional automatic repair or manual retry occurred.

History records departure `loc_cafe → null`, then completed arrival
`null → loc_home_galina`, both with explicit player input authority. Alexey and
actor camera are at his mother's home. Existing Knowledge and prior variants are
unchanged. A cold production restart reloads the exact committed snapshot.

The existing background scheduler also ran naturally. At the Kovalevs' home,
Marina marks notebooks and Pasha hesitates at his room's doorway. This independent
scene and interaction were saved as unobserved by the player. They did not move
Alexey, expose Knowledge to him or replace his foreground scene. This is one
accepted background result, not a general lifecycle/LTA acceptance.

## One natural next turn after reload

Input: **«Стучу в дверь и жду. “Мам, это я”.»**

The actual Narrative request received `loc_home_galina` in its current-state
context. Galina opened the door, welcomed Alexey, mentioned the apple pie and
asked about his grandfather. The story continued from the mother's doorway,
without returning to the cafe or teleporting another NPC.

This first Extraction again supplied an invalid observer override. One real
bounded repair cleared that field; the turn saved at revision **44 → 45**, with
Alexey and Galina present at `loc_home_galina`. A second cold restart reproduced
the complete final snapshot and retained earlier History/variants. The ordinary
remote-initiative call was included in the budget; no calls were hidden or free.

There is a small remaining interpretive imprecision: the extracted situation
says Alexey entered the flat, while the input only knocks and the prose invites
him inside. No new location, relationship or commitment was imposed. This run
does not establish broader agency accuracy. No code was changed to address it.

## Measured calls and cost

| Stage | Input tokens | Output tokens | Provider seconds |
|---|---:|---:|---:|
| Recovery Extraction | 29,158 | 812 | 4.741 |
| Recovery repair | 24,570 | 672 | 3.886 |
| Background Narrative | 12,705 | 647 | 5.958 |
| Background Extraction | 26,308 | 186 | 2.916 |
| Next-turn remote initiative | 2,341 | 74 | 1.606 |
| Next Narrative | 17,012 | 398 | 4.236 |
| Next Extraction | 27,487 | 1,213 | 6.163 |
| Next repair | 21,357 | 143 | 1.842 |

**8/8 calls; 160,938 input + 4,145 output tokens; $0.0532554/$0.50** at the
existing conservative $0.30/M input + $1.20/M output rates, without cache discounts.
All reservations 647–654 settled from actual receipts. The call limit was reached
and paid execution stopped; the later reload server explicitly disabled provider
dispatch. No unsettled reservation was zeroed and the original ledger was retained.

Provider Extraction+repair totals: **8.628s recovery**, **8.005s next turn**.
Production job totals, including local/background work: **25.670s** and **21.486s**.
Both foreground first Extractions required repair (**0/2 first-pass; 2/2 repaired**).
This supports the targeted collection/repair fix, not a claim of low repair rate,
long-session reliability or completion of the ordinary 30–50-turn playtest.

## Evidence and limits

Raw first replies, patches, full repair feedback, diagnostics, eight provider
streams, receipts, request timings, before/after/reloaded snapshots and final
SQLite are retained at `/workspace/work/issue255-recovery-live/`. The original
source SQLite SHA256 is unchanged. The existing Budget/ledger was used with
only the approved cumulative configuration: 449 calls / $3.830492 from baseline
205. No new budgeting system or retry mechanism was introduced.

These were production HTTP jobs; **no new desktop/mobile UI PASS is claimed**.
A small evidence-export script initially compared string request IDs with an
integer; it was corrected without touching jobs, provider responses or canon.
No full CI was rerun. No product fixes were made during the paid run. PR #248
remains unmerged and #255 remains open for broader live playability acceptance.
