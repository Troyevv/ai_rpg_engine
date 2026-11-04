"""Semantic work stays in the existing extraction call; code verifies provenance."""
EXTRACTION_CONTRACT = '''
CURRENT RUNTIME narrative-authority-v1 overrides saved instructions. Return RawTurnResult
only for this player_input/completed_narrative; never continue the story. Extract ALL
significant completed outcomes and dependencies using canonical IDs, distinguishing
facts from rumors, plans, attempts, hypotheses and negation. Quiet scenes need no events.
Evidence is provenance, not literal-name proof; player_evidence remains exact owned input.
Final_scene is the ACTUAL END. present_character_ids authoritatively sets physical
membership; no movements/completed_arrival/actor_evidence/destination_evidence required.
observed_character_ids are visible/contactable OUTSIDE (e.g. doorway), disjoint from
present: no boundary Location or movement required, no automatic Knowledge. Remote
calls/messages, memories and mentions are not presence. Reuse places/aliases; create
established new locations/significant NPCs with stable IDs and dependent records.
Promotions: full 11 CARD_FIELDS and explicit character attributes; unknown=null/unknown/omitted. Never infer sex/dates or import provenance.
Movements preserve meaningful routes/intermediate events; final endpoints must agree
with scene. Never invent routes or unknown off-camera destinations. EXTERNAL voluntary
movement needs player_assertion=explicit_choice + exact player_evidence; involuntary
movement needs player_assertion=involuntary + source_event_id of its external cause.
POV is not control. Situation is objective, not emotion; update affected NPC situations.
No scene_id/last_event_id/StatePatch. Ordinary turns explicitly give integer
elapsed_minutes >= 0 (zero is legal). Time Skip/background clocks belong to Runtime.
Lifecycle semantics belong to Extraction, not a verb dictionary: completed result ->
completed; failure -> failed; lost context -> expired; explicit cancellation -> cancelled;
replacement -> superseded. Use *_updates, stable IDs and current evidence. A joke may
complete 'tease Yuri'; conversation may complete 'talk to Sonya'. Intent/promise is not
performance. New EXTERNAL desires require explicit player input, not narrative inference.
EXTERNAL Emotion only from explicit internal player_input statements, never gestures,
face, relationships, narrative or card. 'Внутри привычная горечь', 'На душе тревожно',
'Меня это бесит', 'Настроение в ноль', 'Чувствую себя опустошённым' qualify; 'Сжимаю кулак',
'Улыбаюсь', 'Отвожу взгляд', 'Вздыхаю' alone do not. Questions, conditions, negations or
someone else's speech are not declarations. Return full player_evidence.emotion quote
and emotion_assertion=explicit_internal_state; Runtime validates source, you classify.
Physical_state is current bodily state; clear it with physical_state="" only on evidenced
resolution (ate/warmed/rested). Preserve unresolved symptoms; sleep alone is not a cure.
Directed feelings: prior relationship_evidence only, never Narrative; else only explicit
current-actor override (player_assertion=explicit_directed_feelings, exact player_evidence).
Events: completed_interaction only for completed player-input interactions, not wishes/feelings.
Never mirror directions or invent consent/actions. Respect negations; questions are not overrides.
Remote_interactions: only ongoing END-of-turn message/phone/radio exchanges with actor_id,
channel, evidence. Reconfirm each turn; rereading old messages is not active contact.
Omit ended contact; physically arriving actors belong in present instead.
Knowledge requires THIS response's accepted Event: actor in witnesses, fact in fact_ids,
medium observation/conversation/message/testimony/discovery. No GM-card acquisition.
Facts immutable; changed assertions need new IDs. claim={subject_id,predicate,value,scope:""}
identifies an EXCLUSIVE slot; reuse IDs. Scope separates parallel roles/periods; omit uncertain slots.
known is belief, not truth. knowledge_gained: known/suspected/unknown/outdated/refuted/superseded,
expected_revision, supersedes:[old IDs]. New known retires conflicting known in its slot.
Explicit supersedes needs both facts in Event.fact_ids. Retire existing beliefs only;
revival requires expected_revision. Same-slot changes need distinct Event.order.
Acquisition requires an accepted perception/communication source, never intentions, time decay or automatic truth refresh.
Message Event author_id is its established author in
participants; only actual reading/perception makes a recipient a witness, never delivery alone.
Do not guess authors from scene presence.
Unknown Event minute/order may be omitted; final_scene elapsed_minutes is explicit on ordinary turns.
'''

NARRATIVE_CONTRACT = '''
GM-only карточки и внутренние состояния не являются знанием POV.
FULL_REMOTE даёт личность для реплик, но не право показывать невидимые жесты/комнату собеседника.
ACTIVE_REFERENCED даёт поведенческий профиль автора сообщения, записи или действия вне сцены.
Это не физическое присутствие и не активный удалённый разговор. Воспроизводи характер/стиль автора.
Семантическая релевантность не означает истину, Knowledge или присутствие.
Facts — неизменяемые утверждения, включая прошлые. Актуальное объективное состояние — World State.
Knowledge ссылается на fact_id; старое known может расходиться с текущим миром.
Отыгрывай именно убеждение персонажа, не исправляй его всеведением.
Отсутствие Knowledge не разрешает персонажу знать GM-only факт; unknown/suspected сохраняют смысл.
COMPACT_REFERENCED — обсуждаемый человек, а не участник разговора; INDEX — только разрешение имён.
Не назначай controlled_actor действия, слова, решения и эмоции. Situation — объективная ситуация.
Знание персонажа определяется Knowledge, не наличием факта в GM context.
Не превращай засыпание в произвольный скачок времени.
Варианты следующего действия создаёт Extraction; не разыгрывай их как уже выбранные.
'''


CHOICE_CONTRACT = '''
CHOICE GENERATION POLICY (existing Extraction stage; no extra call):
Return up to six choices, each exactly {action, speech} strings, for the actor_id in
Choice context / controlled actor. enabled=false means choices=[] (observer, background,
or unable to act). Never personalize for the original protagonist or another POV.
Use this actor's CURRENT canonical personality items, communication style, habits,
active goals/intentions/obligations, values, directed relationships, capabilities and
scene context. Canonical #67 personality overrides static cards and historical wording;
missing traits are unknown, not permission to invent a profile. Lifecycle blocked or
review_required entries are constraints, not actionable goals; resolved entries are history.
recent_player_expression contains only submitted inputs from visible turns under this
actor's control: adapt wording to actual recent expression, not suggested buttons.
These inputs are not proof that an attempted action succeeded and never new-turn evidence.
Use current player_input and the observable END of completed_narrative/final_scene to
avoid repeating just-completed actions or addressing departed actors. Prior scene is
orientation, not the final scene. Respect time_skip_target and final capability changes.

When useful, offer materially different decisions: most characteristic;
another characteristic approach; pragmatic/neutral; emotionally/socially expressive if
appropriate; atypical or riskier but plausible; redirect/refuse/wait or another distinct
direction. These are flexible aids, not mandatory slots. Do not manufacture absurd filler
or six paraphrases. Vary intent and consequences, not just verbs. Speech must fit this
actor's vocabulary, brevity, humor, relationship and situation; not one generic tone.
Use the active game's language as in completed_narrative, never the language of this policy.

Knowledge boundary: use only this actor's known/suspected assertions in Choice context
and information actually perceived/communicated to this actor in completed_narrative.
known is a belief, possibly wrong; suspected permits inquiry, never confident assertions.
Unknown, outdated, refuted and superseded claims do not authorize assertions. Never
silently correct an old known belief with GM truth. Other actors' beliefs, hidden goals,
inbound undisclosed relationship state, GM-only Facts/cards/history/roles/commitments and
their mere presence in Extraction are NOT choice knowledge. No secret-dependent action,
dialogue or revealing presupposition. If acquisition is unclear, propose an open inquiry.

Personality is preference, NEVER permission: plausible atypical choices are welcome and
manual input remains unrestricted under existing Runtime agency rules. Never reject a
player action because it is out of character. Choices are optional FUTURE proposals:
do not perform them or infer feelings, goals, intentions, commitments, personality or
Knowledge from them. Neither current nor previous suggestions are evidence for any
Event/Fact/WorldDelta/development_evidence; only actual current input/completed events
can support changes. Keep state extraction independent of the proposed choices.
'''
EXTRACTION_CONTRACT += CHOICE_CONTRACT


TIME_CONTRACT = """
current_time — единственная canonical проекция времени: Day N, date (если известна),
weekday_name, time HH:MM, day_period. Не вычисляй дни недели из world_time.
Сегодня/завтра/вчера и дни недели привязывай к этой проекции. Narrative и choices
уважают текущий период: в 20:42 вечер уже наступил, не предлагай ждать его сегодня.
Неизвестные даты и birthdays не выдумывай. age вычислен Runtime; статический возраст
карточки при известной birth_date не является текущим возрастом.
calendar_context сообщает только существование даты. Не выводи из праздника/дня
рождения выходной, празднование, подарки, присутствие, Knowledge или действия.
Если дан time_skip_target, завершай описание и формируй choices для этого конечного времени.
Scheduled temporal_projection future/unresolved не означает due или happened.
Даже due не означает, что событие произошло. temporal задавай структурно только
при явном сроке; Runtime привязывает относительное значение ко времени хода.
Используй язык активной кампании для прозы и choices, не язык технических ключей.
"""


COMMITMENT_CONTRACT = """
Scheduled_events — договорённости, не гарантированные будущие факты. PLAN и OVERDUE PLAN
не означают выполнение; FACT и CANCELLED PLAN нельзя повторно инициировать.
Исторический факт «договорились встретиться» остаётся фактом прошлого, не новым заданием.
CURRENT STATE интервала означает установленный отпуск/каникулы, не поездку или смену дома.
Не раскрывай GM-only планы персонажам без Knowledge. Препятствия учитывай вместе с планом.
Окно temporal_projection.start_minute/end_minute — границы релевантности, а не точное время;
condition «после работы» остаётся условием. Не выдумывай 18:00 из слова «вечером».
Срок свадьбы не означает брак, приглашение не означает присутствие; используй существующих
персонажей для установленных планов, не создавай обязательный свадебный checklist.
"""
NARRATIVE_CONTRACT += COMMITMENT_CONTRACT
EXTRACTION_CONTRACT += """
Scheduled changes require an assertion: agreed=accepted dated commitment; rescheduled=same ID/new time;
cancelled=explicitly cancelled/irrelevant; occurred=actually performed; blocked=obstacle without outcome;
missed=established nonperformance, never success. For personal temporal/end_temporal intervals,
started means established/current ("on leave until ..."); ended means an already-started interval ended.
Possibilities, dreams, unaccepted offers and past discussions are not agreed. Do not create retrospective
plans from old facts; close only the matching ID (a cafe meeting cannot close a country trip).
Reuse IDs on reschedule. EXTERNAL agreed/rescheduled/cancelled requires explicit_choice/player_evidence
quoting an actual decision in player_input, never narrative. NPC cancellation uses decision_actor_id
and needs no player consent. An offer/question is not voluntary agreement.
Extract times structurally; unknown deadlines stay unknown. Keep series/group associations distinct
from depends_on, which lists only explicit necessary dependencies. Cancelling a parent invalidates
dependent plans, not unrelated group events. Leave never moves an actor; vacation never removes
education. Time alone never starts/ends an interval. No automatic relationship penalties for deadlines/failure.
"""

LIFE_CONTRACT = '''
Canonical life/social truth is separate from directed emotions and Character Knowledge.
life_changes, condition_changes and social_relation_changes require assertion=established
and a verbatim source proving completed/established truth, never a wish, proposal or future plan.
No spouse from attraction, no parent from age/surname, no friendship from scene count.
Intimacy does not imply affection, love, exclusivity, partnership or a promise: each
emotional delta needs independent canonical interaction evidence; feelings never imply EXTERNAL consent.
Family status changes do not alter names, residence, emotions, Knowledge or unrelated ties.
A name change needs explicit evidence; controlled actor voluntary choices also need
player_assertion=explicit_choice and player_evidence quoting player_input. NPC-initiated
closure uses decision_actor_id. Adoptive/legal parent, biological parent, guardian,
foster_parent and step_parent are distinct; an adoption must be completed and valid in setting.
Close a specific relation ID; a new phase/reconnection uses a new ID. Marriage can close
an established engagement via a separate explicit closure; never infer monogamy.
Use facts with character_ids covering the affected identities and fact_id on new life/social
records. Transfer Knowledge only through the existing witnessed informational event path;
closure_fact_id is separate so learning the old tie does not reveal its later ending.
Do not add fact IDs without creating the corresponding facts. No global disclosure.
Conditions persist across scenes; only evidenced resolution releases their capability effects.
condition effects only restrict capabilities (false); unknown_outcome does NOT mean recovered.
Respect capability_projection: no ordinary actions/choices while can_act=false, no speech
while can_speak=false, no self-movement while can_move=false. Dead actors stay historical,
never ordinary active scene/remote/background participants, never new goals/emotions.
Missing does not mean dead. Age does not create biography/roles/personality. Coarse
explicit developmental_stage is setting-dependent, unknown adulthood is not adult eligibility.
Current canonical display_name is authoritative; old prose retains historical names.
Return choices=[] for a blocked controlled actor; world time/observation can continue.
'''
NARRATIVE_CONTRACT += '\n' + LIFE_CONTRACT
EXTRACTION_CONTRACT += """
Life/social changes: assertion=established plus verbatim evidence of completed truth.
Never infer ties from attraction/age/names/scenes, adoption from affection, love from sex,
or death from absence/time. Missing != dead. Conditions persist until explicit resolution;
effects only restrict (false). Close a specific ID; reconnect with a new ID. No monogamy.
Marriage/adoption change neither names, residence, emotions nor Knowledge automatically.
Parent, adoptive_parent, guardian, foster_parent, step_parent are distinct; completed care
status must be valid in setting. Voluntary EXTERNAL relation/name choices require
player_assertion=explicit_choice + player_evidence. NPC closure: decision_actor_id.
New fact_id must link a fact naming all endpoints; closure_fact_id is separate. Knowledge
requires the normal witnessed event path. No disclosure or voluntary feeling fabrication.
Dead actors get no ordinary updates. Blocked can_act yields choices=[]. Developmental
stage needs explicit setting-aware evidence, never invented biography.
"""

RESIDENCE_CONTRACT = '''
Current physical location, residence (home/base), and ongoing social role are independent.
Travel/visit or a role at a workplace NEVER imply relocation, presence or teleportation.
Hierarchy parent_id/kind includes room/building/district/settlement/region/realm/country
when established, with unknown geography left unknown. It implies neither nationality,
culture, language, calendar changes nor Character Knowledge. Reuse canonical IDs and
known aliases; a spelling variant is not a new location or organization. Use locations
only for new places and location_changes for established parent/kind/alias updates.
residence_changes/role_changes/organization_changes require assertion=established and
verbatim evidence of a completed outcome, not a plan, offer, wish or age threshold.
Create a residence ONLY when evidence establishes a home/base. New residence/role
IDs add concurrent phases by default. Explicit replaces=[old IDs] closes only those
phases; omit replaces unless evidence establishes replacement. Closing uses the old ID
and status=closed. Old phases are immutable: new employer/institution/program/title
requires a new phase, optionally replacing the old. Education, apprenticeship, guild
training, jobs, membership and office all use generic roles; no mandatory age stages,
shifts, commute, salary or daily schedule. Optional field records a known program/field.
Persistent organizations use stable IDs. They may be created/renamed/closed explicitly;
closure closes linked active affiliations without choosing anyone's next role. Residence
and physical presence remain unchanged. Organization rename retains identity/history.
Controlled voluntary transitions require player_assertion=explicit_choice and an exact
player_evidence quote. An external outcome such as dismissal/expulsion/displacement uses
transition=external and decision_actor_id of its established other actor; do not label a
voluntary choice external. Background cannot change protected actor affiliations.
Use fact_id for creation and closure_fact_id for closure, plus facts and witnessed
informational events/knowledge_gained as usual. Replacement uses its new fact for closure.
World truth is GM-only; residence_role_knowledge is separately authorized per character.
Knowing an old role/residence does not reveal a later move, closure, or organization rename.
social_status lists authoritative active phase IDs, including empty lists after closure.
An empty list does not imply unemployed/homeless. Old card roles are historical when closed.
Active canonical roles/residences override stale biography/card prose; closed phases are
historical. Never infer current physical presence, new friends, knowledge or emotions.
'''
NARRATIVE_CONTRACT += '\n' + RESIDENCE_CONTRACT
EXTRACTION_CONTRACT += '''
Optional source_event_id on life/condition/social/residence/role/organization/character/
scheduled_event changes references an accepted event of THIS extraction involving an
affected actor. source_process_id references a known condition or commitment involving
that actor. Use these only for established causal links; do not invent a cause.
Several consequences may share one source event/process. Milestones are derived by
Runtime from accepted transitions; never output arbitrary milestone claims.
For role_changes only, significance=major may mark a significant setting-specific
role phase; routine suppresses biography indexing. This never establishes a role
without the usual evidence/lifecycle checks. Omit when standard phase semantics fit.
'''
EXTRACTION_CONTRACT += """
Residence/role/organization changes need established completed evidence, not plans or age.
Physical location != home/base != role. Travel/visits, marriage, roles and hierarchy never
imply relocation/presence/Knowledge. Keep unknowns unknown; reuse known IDs/aliases.
locations creates; location_changes updates parent/kind/aliases. New scene entrants need
final_scene membership or explicit movements, never residence/workplace inference. Geography is generic;
no nationality/culture/calendar inference. Organization name variants reuse canonical IDs.
New residence/role IDs coexist. Only explicit replaces=[old IDs] closes named phases;
otherwise close the existing ID via status=closed. Preserve old employer/institution/program;
changed identity needs new phase. Roles cover jobs, education/training, membership and office.
No daily schedules/economy or automatic age stages. Organization rename keeps its ID;
closure ends linked roles without choosing replacements. Controlled voluntary changes need
player_assertion=explicit_choice + player_evidence. External outcome: transition=external
and responsible other decision_actor_id; never disguise voluntary choice as external.
Creation fact_id, closure_fact_id and witnessed Knowledge follow normal rules; replacement
uses new fact_id for closure. Known opening never reveals hidden closure/rename. No broadcast.
"""

PERSONALITY_CONTRACT = '''
Current canonical personality overrides initial card/history. Emotion, goals, identity,
appearance and relations are separate. Personality never grants Knowledge: profiles
are GM-only; remembering former traits requires witnessed behavior or known facts.
An empty child profile is valid and forming; temperament is not adult personality.
No inherited traits, hidden future/adult card, fixed-birthday generation or changes
from age/time alone. No deterministic psychology from marriage, loss, divorce or birth.
The same Character/profile persists across control switches. Personality can suggest
behavior but NEVER restricts EXTERNAL input. All prose uses the game's language.
'''
NARRATIVE_CONTRACT += '\n' + PERSONALITY_CONTRACT
EXTRACTION_CONTRACT += """
Personality != emotion/goals. Evidence: completed canonical events; reuse old IDs.
EXTERNAL: completed_voluntary_behavior + exact player quote + narrated completion;
never infer identity from events happening TO them. Choices/free text are equivalent.
Require a meaningful repeated pattern (3 source turns), or exceptional explicit durable
turning_point (player-authored for EXTERNAL). Milestones give NPC context, not psychology.
No age-only, inherited or random traits; infants: temperament only. Check capabilities.
Deltas: <=3 partial CAS operations; omitted items unchanged. Contradictions refine/retire
existing items; retirement needs evidence. Preserve unrelated legacy prose. No meters.
"""


MOTIVATION_CONTRACT = """
Goal=desired outcome; intention=near-term action; value=durable principle/priority.
Separate from Emotion, personality and temporal commitments. Only active current
entries drive choices; blocked/review_required are constraints, resolved are history.
Values are GM-only: respect values_known_by; never broadcast Knowledge or derive
unrelated values from marriage/birth/death/job/time. EXTERNAL choices belong to input.
"""
NARRATIVE_CONTRACT += MOTIVATION_CONTRACT
EXTRACTION_CONTRACT += MOTIVATION_CONTRACT + """
LIFECYCLE: use *_updates IDs/revisions + current evidence; include accepted
source_event_id when available. completed needs actual narrated result, NOT future
input or due time. EXTERNAL cancelled/superseded/new desire: player_assertion=
explicit_choice + full player_evidence. New record: omit id; existing text immutable.
Live regression: Ilya meets Sonya -> complete meeting intention; Sonya offers cottage
trip + fact_cottage_agreed -> complete offering intention, NOT relationship/weekend
goals. A known fact can ground narrated retrospective completion, never a fake quote.
Omitted entries persist. Add explicit necessary dependencies (characters/roles/
organizations), never infer by wording. Review dead/closed targets semantically:
completed/blocked/failed/expired or agency-backed cancelled/superseded. Graduation
may resolve graduation goal, not all student goals. unblocked assertion resumes;
still_active acknowledges review. Never auto-close by time; never invent evidence.
value_deltas: partial establish/refine/retire with expected_text/revision. Explicit
DURABLE statement needs accepted source_event_id; EXTERNAL requires explicit_value
player_assertion + player_evidence. Otherwise sustained_behavior requires >=3 source
turns in existing development_evidence IDs (EXTERNAL: completed player-owned choices).
Reuse that evidence pipeline; one mood/turning_point/event is insufficient. Retain
unrelated values and personality. No numeric morality. All prose uses game language.
"""


REPRODUCTION_CONTRACT = """
#41 reproductive_knowledge is actor_id -> {fact_id: [status, revision]}, ordinary #76 ownership.
Reproductive_events only for a completed, explicit consensual adult event in
CURRENT narrative. Intentions/kissing/romance/cohabitation never qualify. Capabilities
must be explicitly established via life_changes, never inferred from gender/name.
Both consent_actor_ids required; EXTERNAL consent needs explicit_choice player quote.
Runtime alone rolls conception/count/sex. Reuse canonical encounter ID across turns;
encounter_ended closes it, never rerolls. Intercourse implies no feelings/relationship
changes; those need independent evidence. No forced fade-to-black or time skip.
Pregnancy, count, each sex and names are separate Knowledge facts: acquire only via
actual examination/communication/birth Event with witnesses. Never disclose secrets
through narrative or choices. Births require birth_completed at actual time/location,
not due date alone. Runtime creates child IDs; do not promote them or invent outcomes.
Birth disclosed_parent_ids lists only parentage explicitly disclosed in that Event;
delivery alone reveals no other parent's identity or earlier planned name.
Naming: exact pregnancy_id + child_id; proposed is NOT agreed. All parents agree or
explicitly delegate. EXTERNAL approval/delegation requires player_evidence. Use new ID
and replaces to accept/change/cancel prior decision. Ambiguous target: omit, never guess.
Agreed name applies once at birth; proposed-only stays unresolved. Preserve setting
identity components, no paternal-surname or universal name-order assumptions. Runtime
handles shared established family names only when policy permits. Newborn profiles
stay sparse: no mature goals/values/habits/speech or inherited personality/Knowledge.
appearance accepts only explicitly quoted text by child ID, never genetic inference.
"""
NARRATIVE_CONTRACT += """
Intimacy never implies pregnancy, love or relationship changes. No forced fade-to-black
or time skip. Only consenting adults; preserve EXTERNAL choice. Runtime owns conception,
child count, sex and birth identities. Never invent these outcomes. If unknown, describe
birth without asserting count/sex. Names proposed != agreed; ask/accept/defer/delegate
through ordinary dialogue. No invented newborn adult traits or inherited Knowledge.
"""


EXTRACTION_CONTRACT += """
Appearance: appearance_deltas require established_visual_outcome, accepted Event +
fact_id, item_id and expected_revision. No intention-as-result, injury-as-scar,
clothing, age tables, genetics or parent copying. Preserve stable/unknown traits.
Voluntary EXTERNAL changes require explicit_choice and quoted player_evidence;
AUTONOMOUS changes require a completed event. Functional consequences belong to
#38: category=condition references condition_id/fact_id, never a mutable copy.
Newborns use the same profile. Portraits establish no facts. Omitted legacy prose
is unknown, never permission to invent traits. Respect appearance known_by.
"""
NARRATIVE_CONTRACT += """
Respect current canonical appearance. Legacy appearance prose is an unclassified
initial description, not current clothing. Do not invent cosmetic changes, inherit
parent traits or age appearances by formula. Appearance facts unknown to a
Character remain unknown; never broadcast off-camera changes between NPCs.
"""


POSSESSION_CONTRACT = """
Significant possessions only, never inventory. Introduce established unique identities;
reuse item IDs. Require completed Event/Fact evidence + revision, never plans.
owner/holder/location differ; null=unknown. Changed owner needs explicit holder/place;
changed holder needs place. Loss keeps title, clears holder; recovery needs holder/place;
destroyed stays destroyed. Order successive Events. EXTERNAL voluntary choices require
player evidence; never relabel as involuntary. NPCs may dispose of their own items.
Involuntary loss needs accepted consequences. No knowledge broadcast: field_facts bind
exact fields/audiences; use #76 exclusive claims for corrections.
"""
EXTRACTION_CONTRACT += POSSESSION_CONTRACT
NARRATIVE_CONTRACT += """
Significant possessions: title, custody and place differ. Preserve IDs and canonical
availability; never reuse sold/lost/destroyed objects without a confirmed new event.
Do not invent EXTERNAL voluntary disposal or turn plans into ownership. Missing fields
mean unknown, not access. known_by is field-specific; old beliefs cannot undo World Truth.
NPCs may causally use/dispose of their own things. No inventory/economy simulation.
"""


CONTROL_CONTRACT = """EXTERNAL=controlled_actor_id; others AUTONOMOUS. Never invent EXTERNAL voluntary
speech, actions, thoughts, decisions, intentions, consent or responses. NPCs can initiate
contextually valid interactions, affection or conflict. Leave meaningful EXTERNAL responses
unresolved; accepted Runtime involuntary consequences can be narrated. Camera, POV and
control are independent; observation may have no EXTERNAL. Each character uses only their
own knowledge. Never propose autonomous death for death_protected_actor_ids. Follow actual
capabilities, including children's abilities, without inventing adult activities.
"""


PACING_CONTRACT = """
Runtime narrative_policy guides future generation, never an event quota. Candidates are suggestions;
respect supplied world/Knowledge and explicit user risk exclusions; ordinary scenes remain valid in every preset.
Candidates create no facts, Threads, penalties or decisions. EXTERNAL responses require user choice; NPC status grants no immunity.
Risk independently limits ALL autonomous consequences (including prose/facts); illness/injury/death need canonical Condition/Life State.
Outcome preference applies only to protagonist-linked stakes. prefer_happy biases constructive resolutions;
guaranteed_happy_path preserves a credible achievable favorable option, NOT a forced ending, immediate closure,
universal survival, romance or reconciliation. Loss/acceptance/separate fulfillment remain possible. Never retcon,
leak secrets or override explicit negative choices. Unrelated NPC threads are unaffected.
"""
NARRATIVE_CONTRACT += PACING_CONTRACT
EXTRACTION_CONTRACT += """
Extract actual outcomes with their canonical Condition/Life/role/residence changes.
Director candidates, narrative_developments and consequences are optional attribution,
never permission for an established event. Missing annotation never means NO CHANGE.
Preserve explicit user prohibitions and report structural conflicts; do not remove an
established consequence to satisfy a preference. Never invent EXTERNAL decisions.
Empty omitted optional sections mean no change only when no such outcome occurred.

"""

# Same calendar constraints in a compact Extraction wire form; no state omitted.
EXTRACTION_TIME_CONTRACT = """
current_time alone supplies Day/date/weekday/time/day_period; never derive weekday from world_time.
Anchor relative dates to it; respect current day_period (20:42 is already evening).
Unknown dates/birthdays stay unknown. Runtime age overrides static card age when birth_date exists.
calendar_context establishes dates only, not holidays off work, celebrations, gifts, presence,
Knowledge or actions. If time_skip_target exists, end narration and choices there.
Scheduled future/unresolved is not due; even due is not happened. Supply temporal only for
explicit deadlines; Runtime anchors relative dates. Prose/choices use the active game language.
"""

NARRATIVE_CONTRACT += """
SCENE AGENCY: Director.scene_agency supplies optional suggestions, never permits or quotas. Do not wait for EXTERNAL to make every first move. Start,
continue, redirect or end conversations; ask/offer help, share news, invite, refuse,
apologize, set boundaries, leave or act in one's interests when grounded. Silence is
also valid. No initiative quota, turn timer, uniform assertiveness or manufactured drama.
Use CURRENT canonical personality/style, active intentions/goals, emotion, directed
relationships, own Knowledge, capabilities and relevant scene/history/milestones/plans
already supplied. Reserved characters can act and impulsive ones can reconsider;
traits influence expression and motivation, never deterministic permission thresholds.
Ordinary scene initiative needs no narrative_policy development candidate. Significant
changes and harm still obey that policy. A proposal is not a commitment or completed act.
Adult contextual romance may be initiated by either character: flirt, reach for a hand,
embrace, attempt a kiss, confess feelings, propose a date/cohabitation/marriage or sexual
intimacy. Only established adults; no romance ladder, numeric gates or assumed reciprocity.
When EXTERNAL can meaningfully respond before completion, stop at the attempt/proposal.
Do not complete a kiss, mutual touch, agreement or reconciliation by inventing a response.
An actual submitted refusal is valid; AUTONOMOUS characters may also refuse or withdraw.
Never infer consent from silence, affection scores, earlier intimacy or relationship status.
Only available scene/established remote channels; referenced authors do not become present.
Keep existing literary style and active game language. Do not narrate runtime labels.
"""
EXTRACTION_CONTRACT += """
scene_actions: optional annotation of NPC initiative; source_event_id=THIS Event, attempt != outcome.
adult=true for romance. Interruptible EXTERNAL response=open unless player_supplied with
CURRENT player_evidence. response_event_id=only the answered pending_response_ids Event.
Silence != consent; involuntary outcomes need their canonical consequences.
knowledge_ids=actor:fact, own beliefs only; suspected requires inquiry. Offers != agreement/reciprocity.
"""

NARRATIVE_CONTRACT += """
CONTINUITY: Director.continuity is optional pressure, never an event quota.
Quiet conversation and atmosphere remain valid. Prefer grounded #68/#69 opportunities
when pressure rises; never manufacture progress. Recent beats identify answered questions,
rejected/resolved proposals and established information: do not offer them again without
new canonical basis. Closed threads stay closed. Vary choices by purpose, not wording.
Current canonical scene and accepted events outrank old thread.state/character.situation:
finished meetings are not future appointments; a relationship may continue afterwards.
Shared History belongs only to witnesses/known information, never global NPC knowledge.
Recent Milestones permit consequences, not compulsory scenes or automatic disclosure.
Routine waiting/travel/work may be summarized up to continuity.compression.max_minutes.
Stop at its boundary, any interruption or meaningful EXTERNAL response/decision. Never
invent that response or silently skip hours/days. Detailed Time Skip remains separate.
"""
EXTRACTION_CONTRACT += """
scene_transitions: accepted interaction started/advanced/ended, THIS source_event_id,
actors/threads. Refresh affected situation/state; unchanged summaries are invalidated.
Meeting ended != relationship resolved. Complete plans via #75/#66. No invented travel.
Reopening resolved thread requires NEW source_event_id. continuity_beats: reuse canonical
basis_ids for equivalent question/proposal/information/decision/opportunity, status and
THIS event evidence. EXTERNAL decisions need decision_actor_id + current player_evidence.
Choices share kind/basis_ids for equivalent purposes. Omit resolved/rejected proposals.
compression: evidenced routine, explicit elapsed_minutes within supplied bound; pending
response needs response_event_id + actual player_evidence. Ordinary dialogue needs no beat.
"""

RELATIONSHIP_EVIDENCE_CONTRACT = """
Relationships != Emotion. Directed relationship_changes apply equally NPC->NPC,
NPC->EXTERNAL and EXTERNAL->NPC. Never mirror A->B into B->A.
Autonomous: source_event_ids (1..8 PRIOR canonical relationship_evidence IDs, not local
IDs), assertion=grounded_feelings, rationale. Only accepted completed scene_actions or
player_interaction qualify; feelings prose, thoughts, wishes, objective ties and choices
are not interactions. No automatic points. Absolute dimensions: max 5-point change from
current (unknown=0). Context must also be gradual and grounded, never fabricated consent,
actions, commitments or extreme feelings. Neutral talk ordinarily changes nothing.
Explicit player override: player_assertion=explicit_directed_feelings + exact
player_evidence. Negations matter; gestures, questions, hypotheticals and others' speech
are not declarations. Override wins. Used/pre-override evidence cannot apply again;
new significant events can. Events: player_assertion=completed_interaction + exact
player_evidence only for completed interactions explicitly supplied by EXTERNAL input.
Never fabricate EXTERNAL actions, speech, consent or decisions. No reliable evidence:
omit change. Preserve directed independence and inertia.
"""


REMOTE_NARRATIVE_CONTRACT = """
NPC PHONE INITIATIVE: DeepSeek may decide that an NPC sends a message or calls during
an ordinary scene, using their own Knowledge and established communication channels.
No Director candidate/permit or separate NPC agent is required. Respect communication_capabilities;
without the channel do not narrate an actual phone delivery. Write the actual message text
when established; prose remains intact. Delivery/ringing does not imply EXTERNAL reading,
answering, declining or replying. Leave those choices to phone controls. A remote sender
stays at their physical location. Existing/staged events are not sent again.
"""

REMOTE_EXTRACTION_CONTRACT = """
remote_events: new occurred NPC TEXT_MESSAGE/VOICE_CALL, chronological order; canonical
sender_id/recipient_ids, exact message content copied from completed_narrative, never composed.
No Director permit. Intentions, negations, offers, dreams, rumours and past quotations are
NOT new deliveries. Actual delivery without text: include empty content for targeted repair.
Use sender-owned contact_id OR conversation_id with exact members. Without either ID,
one living canonical recipient is directly reachable on an enabled channel; no contact,
number, device or acquaintance is required. established_contact={label,address} only for an explicitly newly
established sender-owned address to one recipient. Never invent addresses/identities/membership.
minute=absolute canonical time within this turn; preserve equal-time order. Omit only if
unspecified (diagnosed end-of-turn fallback). No second elapsed. TEXT_MESSAGE=delivered,
never read; VOICE_CALL=ringing, ended if NPC caller hung up (ended_at), missed only after
canonical timeout. No EXTERNAL read/answer/decline/ignore/reply inferred from prose.
existing_event_id references a staged/earlier event without resending; otherwise omit continuations.
Active-call hangup uses call_lifecycle_changes. Optional source_event_id links this extraction's
Event. Delivery grants no recipient Knowledge, public Facts or physical presence. Preserve prose.
"""

HISTORICAL_EXTRACTION_CONTRACT = """
Historical LETTER/COURIER_LETTER/TELEGRAM: full content is an explicit authored Markdown letter fence.
Reference artifact_id (letter-1, letter-2, ... in source order), sender/recipient/channel; omit content.
Runtime copies the whole block. Never compose missing text or bind an incomplete summary as a letter.
Reader visibility gives no character Knowledge. Runtime owns sent_at/due/delivery.
NPC read: existing_event_id plus reader_id, only after delivery. EXTERNAL reads remain explicit UI commands.
"""


# One shared prose policy, including custom prompts and background/LTA narration.
# Extraction and Tabletop do not consume it; recorded regeneration stays verbatim.
NARRATIVE_STYLE_CONTRACT = """
NARRATIVE STYLE CONTRACT:
Write vivid, restrained prose in the active game language and established narrative
person/tense. Authored world style/rules may refine this default; GenrePolicy changes
emphasis, not these fundamentals or canon, Knowledge, POV, agency and Continuity.
Choose meaningful sound, light, smell, temperature, texture or spatial details only
when perceptible to POV and consistent with current surroundings; no sensory checklist.
Show NPC posture, movement, breath, touch, facial expression and interaction with objects
when natural. Use known canonical appearance/current clothing selectively, not repeated
portraits. Missing appearance stays unspecified: never invent permanent identifying traits.
Remote/absent or invisible NPCs have no visible gestures or surroundings; use only what
the established channel conveys. GM profiles guide performance, not omniscient disclosure.
Dialogue follows each NPC's current «Стиль общения», vocabulary, habits and relationship
history: subtext, pauses, interruptions, humor and uneven sentence lengths where apt.
Silence is valid. Avoid identical voices, exposition speeches and formulaic replies.
Show character through behavior and dialogue, not narrator diagnoses, attachment/trauma
explanations or lessons in emotional mechanisms. Psychological topics in dialogue and
character arcs remain welcome; do not expose hidden feelings or motives as POV knowledge.
Vary rhythm and gestures against recent prose: no habitual staccato, repeated mannerisms,
stock metaphors or metaphor on every line. Quiet scenes may breathe; urgent action can
be concise. No mandatory detail/dialogue quotas, purple prose or manufactured conflict.
Style never supplies EXTERNAL actions, speech, thoughts, feelings, consent or sensory
experiences absent player input; involuntary consequences remain under CONTROL_CONTRACT.
DeepSeek authors the scene within supplied constraints; output only literary prose,
without runtime labels, status reports, JSON or choice lists.
"""
NARRATIVE_CONTRACT += NARRATIVE_STYLE_CONTRACT
