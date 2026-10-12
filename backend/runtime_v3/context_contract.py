"""Semantic work stays in the existing extraction call; code verifies provenance."""
EXTRACTION_CONTRACT = '''
CURRENT RUNTIME V3 contract overrides saved instructions. Return RawTurnResult only
for THIS player_input and completed_narrative; never continue the story. Copy existing
IDs. Evidence is a verbatim current quote. Output prose in the active game language.
Final_scene is the ACTUAL END, not a copy of the initial camera. New concrete location:
create locations[] with canonical ID/name/evidence and use that ID in final_scene.
Choose the final stop, not intermediate travel. Reuse known places/aliases (Гвоздь,
кофейня Гвоздь, кафе Гвоздь); mention/plan alone never moves the camera.
Present_character_ids: only physically present at the end; remove departures, include
arrivals who stayed. Messages/memories are not presence. Supply departed actors'
movements only when their destination is established. A redundant movement for a
final_scene participant must end at final_scene.location_id. Situation is current
objective state, not emotion; situation_evidence grounds it. Update affected NPC
situations via evidenced character_changes. Promote only significant recurring NPCs
with full card/evidence, not incidental passers-by; a promoted present NPC uses the
same ID in final_scene. Mention does not mean arrival. No scene_id/last_event_id/
from_location/StatePatch. Elapsed_minutes is actual narrated duration, no arbitrary skip.
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
Relationships != Emotion. Directed relationship_changes apply equally NPC->NPC,
NPC->EXTERNAL and EXTERNAL->NPC; no player evidence needed. Never mirror A->B into B->A.
Dimensions — новые абсолютные значения, not increments. Нейтральный разговор ordinarily
has no relationship_changes. Small meaningful events: small changes; accumulated or major
betrayal/rescue may support larger changes. Preserve inertia and manually edited baseline.
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
Completed-narrative evidence only; no intentions, time decay, gossip or truth refresh.
Message Event author_id is its established author in
participants; recipient/reader is witness. Do not guess authors from scene presence.
Unknown minute/order may be omitted; no microscopic chronology.
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
При написании диалогов используй «Стиль общения» каждого персонажа: лексику, длину фраз, юмор и реакцию на конфликт. Сохраняй характер и подтекст последних сцен.
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

Aim for SIX materially different decisions when the scene allows: most characteristic;
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
PLAN/OVERDUE PLAN — не факт выполнения. FACT/CANCELLED PLAN повторно не активировать.
Для scheduled_event_changes обязательно assertion и evidence текущего хода:
agreed — явная принятая договорённость с временной привязкой; rescheduled — перенос того же ID;
cancelled — явно отменён/неактуален; occurred — действие фактически состоялось;
blocked — препятствие без установленного исхода; missed — подтверждено невыполнение (не успех).
Для личного интервала temporal/end_temporal: started — установлен фактический старт/текущее
состояние («я в отпуске до ...»), ended — подтверждено окончание уже начатого интервала.
Может быть/мечта/непринятое предложение/обсуждение прошлого не создают agreed.
Не создавай план задним числом из старого факта. Завершай именно совпавший canonical ID:
встреча в кафе не закрывает отдельную поездку на дачу. Не создавай новый ID при переносе.
Для agreed/rescheduled/cancelled с controlled_actor нужны player_assertion=explicit_choice
и player_evidence — точная цитата явного решения из player_input, не из narrative.
При отмене другим участником укажи decision_actor_id этого NPC: его отказ не требует согласия игрока.
Проверяй добровольное участие, не приписывай согласие из чужого предложения или вопроса.
Времена извлекай как temporal: date ИЛИ weekday ИЛИ day_offset + time ИЛИ day_period.
Не вычисляй due_minute для human commitments. Условие после работы сохраняй в condition.
Для интервала end_temporal — отдельная привязка к времени этого хода, не к началу интервала.
Возвращение и выезд — разные ID; depends_on содержит только явные необходимые зависимости.
Отмена родителя делает зависимый план неактуальным, не отменяет прочие события группы.
Отпуск не перемещает персонажа; каникулы не убирают образование. Само время не начинает
и не завершает интервал. Не назначай штраф отношениям за срок/срыв автоматически.
"""

LIFE_CONTRACT = '''
Canonical life/social truth is separate from directed emotions and Character Knowledge.
life_changes, condition_changes and social_relation_changes require assertion=established
and a verbatim source proving completed/established truth, never a wish, proposal or future plan.
No spouse from attraction, no parent from age/surname, no friendship from scene count.
Intimacy does not imply affection, love, exclusivity, partnership or a promise: each
emotional delta needs its own evidence. Never assign voluntary feelings to EXTERNAL actor.
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
movement or situation_evidence, never residence/workplace inference. Geography is generic;
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
