# Матрица полей конструктора (#117)

Источник: `WorldStateV3.model_json_schema()` — текущая модель эволюции Runtime v4.
Обновление: `python scripts/world_builder_matrix.py`. `*` — запись словаря, `[]` — элемент списка.

Формы используют эту же схему в `/api/world-builder/schema`; отдельной модели мира нет.
Обязательные поля вложенной записи требуются только когда автор добавил эту запись.
Числовые/enum/default значения заполняются программно; имя созданного персонажа вводит автор.
Пустой observer-мир разрешён Runtime; для actor-режима обязательны выбранный управляемый персонаж,
его присутствие и согласованные местоположения. Красная звёздочка не означает, что весь раздел обязателен.

Каждая строка дополнительно проверяется итоговыми canonical invariants: life, geography/residence,
reproduction, Knowledge, relationships, remote communication, календарь и камера.
Первый этап — строгий Pydantic, до runtime read-boundary salvage. История до игры использует
`WorldHistoryV3.events` и поля existing extraction schema; при старте один batch добавляется
в существующий immutable History DAG. Это staging истории, не второй Runtime.

Campaign title/setting/era/genre/tone/description/rules редактируются в «Обзор мира»;
биографии и роль — в существующих character_cards. IDs, ревизии, receipts и счётчики не вводятся вручную.
Portrait asset references обслуживает существующий менеджер портретов после начала игры;
конструктор не создаёт ссылки на несуществующие файлы. У Gregorian-даты weekday вычисляет Calendar.

| Поле Runtime | Раздел / вложенная форма | Обязательность | Default модели | Проверка | Ручное изменение |
|---|---|---|---|---|---|
| contacts.*.id | contacts | нет | "—" | string | служебное / read-only |
| contacts.*.owner_id | contacts | в заполненной записи | "—" | string | форма |
| contacts.*.character_id | contacts | нет | null | string | форма |
| contacts.*.label | contacts | в заполненной записи | "—" | string {"minLength": 1, "maxLength": 160} | форма |
| contacts.*.address | contacts | в заполненной записи | "—" | string {"minLength": 1, "maxLength": 160} | форма |
| contacts.*.kind | contacts | нет | "person" | enum: person, service, shared | форма |
| contacts.*.blocked | contacts | нет | false | boolean | форма |
| contacts.*.available | contacts | нет | true | boolean | форма |
| contacts.*.identity_visible | contacts | нет | false | boolean | форма |
| contacts.*.provenance | contacts | в заполненной записи | "—" | string {"minLength": 1, "maxLength": 1000} | форма |
| contacts.*.created_at | contacts | в заполненной записи | "—" | integer {"minimum": 0} | форма |
| conversations.*.id | conversations | нет | "—" | string | служебное / read-only |
| conversations.*.title | conversations | нет | "" | string {"maxLength": 160} | форма |
| conversations.*.group | conversations | нет | false | boolean | форма |
| conversations.*.members[].actor_id | conversations | в заполненной записи | "—" | string | форма |
| conversations.*.members[].joined_at | conversations | в заполненной записи | "—" | integer {"minimum": 0} | форма |
| conversations.*.members[].left_at | conversations | нет | null | integer {"minimum": 0} | форма |
| conversations.*.members[].provenance | conversations | в заполненной записи | "—" | string | форма |
| conversations.*.contact_id | conversations | нет | null | string | форма |
| conversations.*.provenance | conversations | в заполненной записи | "—" | string | форма |
| remote_events.*.id | remote_events | нет | "—" | string | служебное / read-only |
| remote_events.*.ordinal | remote_events | нет | 0 | integer {"minimum": 0} | форма |
| remote_events.*.channel | remote_events | в заполненной записи | "—" | enum: TEXT_MESSAGE, VOICE_CALL | форма |
| remote_events.*.sender_id | remote_events | в заполненной записи | "—" | string | форма |
| remote_events.*.recipient_ids[] | remote_events | нет | "—" | string | форма |
| remote_events.*.contact_id | remote_events | нет | null | string | форма |
| remote_events.*.destination | remote_events | в заполненной записи | "—" | string | форма |
| remote_events.*.service | remote_events | нет | null | enum: medical, police, fire | форма |
| remote_events.*.conversation_id | remote_events | нет | null | string | форма |
| remote_events.*.content | remote_events | нет | "" | string {"maxLength": 4000} | форма |
| remote_events.*.world_time | remote_events | в заполненной записи | "—" | integer {"minimum": 0} | форма |
| remote_events.*.updated_at | remote_events | в заполненной записи | "—" | integer {"minimum": 0} | форма |
| remote_events.*.turn_id | remote_events | нет | "—" | integer {"minimum": 0} | служебное / read-only |
| remote_events.*.status | remote_events | в заполненной записи | "—" | enum: sent, delivered, ringing, answered, declined, missed, ended | форма |
| remote_events.*.delivered_to[] | remote_events | нет | "—" | string | форма |
| remote_events.*.read_by[] | remote_events | нет | "—" | string | форма |
| remote_events.*.fact_ids[] | remote_events | нет | "—" | string | форма |
| remote_events.*.provenance | remote_events | в заполненной записи | "—" | string | форма |
| remote_events.*.operation_id | remote_events | нет | "—" | string | служебное / read-only |
| meta.communication.text_message | meta | нет | false | boolean | форма |
| meta.communication.voice_call | meta | нет | false | boolean | форма |
| meta.communication.presentation | meta | нет | "none" | enum: none, phone | форма |
| meta.communication.region | meta | нет | "" | string | форма |
| meta.communication.ring_timeout_minutes | meta | нет | 2 | integer {"minimum": 1, "maximum": 60} | форма |
| meta.communication.emergency_numbers.* | meta | нет | "—" | string | форма |
| meta.interaction_focus | meta | нет | "physical" | enum: physical, call | форма |
| meta.narrative_pacing.preset | meta | нет | "moderate" | enum: calm, moderate, dynamic, intense, custom | форма |
| meta.narrative_pacing.intensity | meta | нет | 0.45 | number {"minimum": 0, "maximum": 1} | форма |
| meta.narrative_pacing.quiet_minutes | meta | нет | 360 | integer {"minimum": 0, "maximum": 43200} | форма |
| meta.narrative_pacing.pressure_limit | meta | нет | 1.5 | number {"minimum": 0.1, "maximum": 4} | форма |
| meta.narrative_pacing.disruption | meta | нет | 0.3 | number {"minimum": 0, "maximum": 1} | форма |
| meta.narrative_pacing.escalation | meta | нет | 0.4 | number {"minimum": 0, "maximum": 1} | форма |
| meta.narrative_pacing.thread_cap | meta | нет | 4 | integer {"minimum": 1, "maximum": 12} | форма |
| meta.narrative_pacing.candidate_budget | meta | нет | 2 | integer {"minimum": 0, "maximum": 6} | форма |
| meta.narrative_pacing.relevance_floor | meta | нет | 0.6 | number {"minimum": 0, "maximum": 1} | форма |
| meta.narrative_pacing.extra_llm_calls | meta | нет | 0 | integer | форма |
| meta.narrative_risk.preset | meta | нет | "realistic" | enum: safe, realistic, harsh, unrestricted, custom | форма |
| meta.narrative_risk.minor_illness | meta | нет | true | boolean | форма |
| meta.narrative_risk.serious_illness | meta | нет | true | boolean | форма |
| meta.narrative_risk.injury | meta | нет | true | boolean | форма |
| meta.narrative_risk.permanent_injury | meta | нет | false | boolean | форма |
| meta.narrative_risk.relationship_loss | meta | нет | true | boolean | форма |
| meta.narrative_risk.career_loss | meta | нет | true | boolean | форма |
| meta.narrative_risk.life_role_loss | meta | нет | true | boolean | форма |
| meta.narrative_risk.major_accident | meta | нет | true | boolean | форма |
| meta.narrative_risk.npc_death | meta | нет | true | boolean | форма |
| meta.narrative_risk.protagonist_death | meta | нет | false | boolean | форма |
| meta.outcome_preference | meta | нет | "natural" | enum: natural, prefer_happy, guaranteed_happy_path | форма |
| meta.pacing_recent[].source_event_id | meta | нет | null | string | служебное / read-only |
| meta.pacing_recent[].source_id | meta | нет | "—" | string | служебное / read-only |
| meta.pacing_recent[].family | meta | нет | "—" | enum: life_opportunity, existing_thread, external_disruption | служебное / read-only |
| meta.pacing_recent[].minute | meta | нет | "—" | integer {"minimum": 0} | служебное / read-only |
| meta.pacing_recent[].weight | meta | нет | "—" | number {"minimum": 0, "maximum": 1} | служебное / read-only |
| meta.current_protagonist_id | meta | нет | null | string | форма |
| meta.protagonist_required | meta | нет | false | boolean | форма |
| meta.protagonist_periods[].actor_id | meta | нет | "—" | string | служебное / read-only |
| meta.protagonist_periods[].since | meta | нет | "—" | integer {"minimum": 0} | служебное / read-only |
| meta.protagonist_periods[].until | meta | нет | null | integer {"minimum": 0} | служебное / read-only |
| meta.protagonist_periods[].operation_id | meta | нет | "—" | string | служебное / read-only |
| meta.schema_version | meta | нет | 3 | integer | служебное / read-only |
| meta.calendar.start_minute | meta | в заполненной записи | "—" | integer {"minimum": 0} | форма |
| meta.calendar.start_weekday | meta | в заполненной записи | "—" | integer {"minimum": 0, "maximum": 13} | форма |
| meta.calendar.start_date | meta | нет | null | string | форма |
| meta.calendar.profile.id | meta | нет | "gregorian" | string | служебное / read-only |
| meta.calendar.profile.system | meta | нет | "gregorian" | enum: gregorian, custom | форма |
| meta.calendar.profile.month_lengths[] | meta | нет | "—" | integer | форма |
| meta.calendar.profile.month_names[] | meta | нет | "—" | string | форма |
| meta.calendar.profile.weekday_names[] | meta | нет | "—" | string | форма |
| meta.calendar.profile.observances[].id | meta | нет | "—" | string | служебное / read-only |
| meta.calendar.profile.observances[].name | meta | в заполненной записи | "—" | string | форма |
| meta.calendar.profile.observances[].month | meta | в заполненной записи | "—" | integer {"minimum": 1, "maximum": 24} | форма |
| meta.calendar.profile.observances[].day | meta | в заполненной записи | "—" | integer {"minimum": 1, "maximum": 99} | форма |
| meta.calendar.profile.observances[].character_ids[] | meta | нет | "—" | string | форма |
| meta.calendar.profile.seasons[].name | meta | в заполненной записи | "—" | string | форма |
| meta.calendar.profile.seasons[].month | meta | в заполненной записи | "—" | integer {"minimum": 1, "maximum": 24} | форма |
| meta.calendar.profile.seasons[].day | meta | в заполненной записи | "—" | integer {"minimum": 1, "maximum": 99} | форма |
| meta.turn_id | meta | нет | 0 | integer {"minimum": 0} | служебное / read-only |
| meta.world_time | meta | нет | 0 | integer {"minimum": 0} | форма |
| camera.subject_id | camera | нет | null | string | форма |
| camera.pov_actor_id | camera | нет | null | string | форма |
| camera.location_id | camera | нет | null | string | форма |
| camera.present_character_ids[] | camera | нет | "—" | string | форма |
| camera.controlled_actor_id | camera | нет | null | string | форма |
| camera.mode | camera | нет | "actor" | enum: actor, observer | форма |
| camera.situation | camera | нет | "" | string | форма |
| camera.remote_interactions[].actor_id | camera | в заполненной записи | "—" | string | форма |
| camera.remote_interactions[].channel | camera | в заполненной записи | "—" | enum: message, phone, video, radio, other | форма |
| camera.remote_interactions[].last_active_turn | camera | в заполненной записи | "—" | integer {"minimum": 0} | форма |
| characters.*.id | characters | нет | "—" | string | служебное / read-only |
| characters.*.location_id | characters | нет | null | string | форма |
| characters.*.situation | characters | нет | "" | string | форма |
| characters.*.birth_date | characters | нет | null | string | форма |
| characters.*.life_status | characters | нет | "unknown" | enum: alive, dead, missing, unknown | форма |
| characters.*.life_fact_id | characters | нет | null | string | форма |
| characters.*.display_name | characters | имя карточки | null | string {"minLength": 1} | форма |
| characters.*.name_history[].previous | characters | в заполненной записи | "—" | string {"minLength": 1} | форма |
| characters.*.name_history[].current | characters | в заполненной записи | "—" | string {"minLength": 1} | форма |
| characters.*.name_history[].minute | characters | в заполненной записи | "—" | integer {"minimum": 0} | форма |
| characters.*.name_history[].date | characters | нет | null | string | форма |
| characters.*.name_history[].turn_id | characters | нет | "—" | integer {"minimum": 0} | служебное / read-only |
| characters.*.name_history[].evidence | characters | в заполненной записи | "—" | string | форма |
| characters.*.name_history[].fact_id | characters | нет | null | string | форма |
| characters.*.capabilities.conscious | characters | нет | null | boolean | форма |
| characters.*.capabilities.can_perceive | characters | нет | null | boolean | форма |
| characters.*.capabilities.can_act | characters | нет | null | boolean | форма |
| characters.*.capabilities.can_speak | characters | нет | null | boolean | форма |
| characters.*.capabilities.can_move | characters | нет | null | boolean | форма |
| characters.*.developmental_stage | characters | нет | "unknown" | enum: unknown, infant, child, adolescent, adult | форма |
| characters.*.parentage_complete_fact_id | characters | нет | null | string | форма |
| characters.*.reproductive_capability | characters | нет | "unknown" | enum: can_become_pregnant, can_impregnate, neither, unknown | форма |
| characters.*.biological_sex | characters | нет | null | enum: female, male | форма |
| characters.*.identity_components.* | characters | нет | "—" | string | форма |
| characters.*.birth_provenance.* | characters | нет | "—" | string | форма |
| characters.*.appearance.items.*.category | characters | в заполненной записи | "—" | enum: intrinsic, body, modification, presentation, condition | форма |
| characters.*.appearance.items.*.kind | characters | в заполненной записи | "—" | enum: eye_color, natural_hair_color, skin, face, build, height, scar, tattoo, piercing, hairstyle, facial_hair, cosmetic, condition | форма |
| characters.*.appearance.items.*.text | characters | нет | "" | string {"maxLength": 600} | форма |
| characters.*.appearance.items.*.revision | characters | нет | 1 | integer {"minimum": 1} | служебное / read-only |
| characters.*.appearance.items.*.condition_id | characters | нет | null | string | форма |
| characters.*.appearance.items.*.source_event_id | characters | нет | null | string | форма |
| characters.*.appearance.items.*.fact_id | characters | нет | null | string | форма |
| characters.*.appearance.items.*.evidence | characters | нет | "" | string | форма |
| characters.*.appearance.legacy_text | characters | нет | "" | string | форма |
| characters.*.appearance.applied[] | characters | нет | "—" | string | служебное / read-only |
| characters.*.portraits[].id | characters | нет | "—" | string {"pattern": "^[a-f0-9]{32}$"} | служебное / read-only |
| characters.*.portraits[].asset_id | characters | нет | "—" | string {"pattern": "^[a-f0-9]{32}$"} | служебное / read-only |
| characters.*.portraits[].width | characters | нет | "—" | integer {"minimum": 256, "maximum": 4096} | служебное / read-only |
| characters.*.portraits[].height | characters | нет | "—" | integer {"minimum": 256, "maximum": 4096} | служебное / read-only |
| characters.*.portraits[].crop.x | characters | нет | 0.5 | number {"minimum": 0, "maximum": 1} | служебное / read-only |
| characters.*.portraits[].crop.y | characters | нет | 0.5 | number {"minimum": 0, "maximum": 1} | служебное / read-only |
| characters.*.portraits[].crop.zoom | characters | нет | 1.0 | number {"minimum": 1, "maximum": 4} | служебное / read-only |
| characters.*.portraits[].stage | characters | нет | "unknown" | enum: unknown, infant, child, adolescent, adult | служебное / read-only |
| characters.*.portraits[].min_age | characters | нет | null | integer {"minimum": 0, "maximum": 10000} | служебное / read-only |
| characters.*.portraits[].max_age | characters | нет | null | integer {"minimum": 0, "maximum": 10000} | служебное / read-only |
| characters.*.portraits[].label | characters | нет | "" | string {"maxLength": 120} | служебное / read-only |
| characters.*.portraits[].order | characters | нет | 0 | integer {"minimum": 0} | служебное / read-only |
| characters.*.portraits[].deleted | characters | нет | false | boolean | служебное / read-only |
| characters.*.personality.items.*.field | characters | в заполненной записи | "—" | enum: traits, communication, habits, strengths, weaknesses, fears, preferences, temperament | форма |
| characters.*.personality.items.*.text | characters | в заполненной записи | "—" | string {"minLength": 1} | форма |
| characters.*.personality.items.*.revision | characters | нет | 0 | integer {"minimum": 0} | служебное / read-only |
| characters.*.personality.items.*.source_ids[] | characters | нет | "—" | string | форма |
| characters.*.personality.items.*.witnesses[] | characters | нет | "—" | string | форма |
| characters.*.personality.items.*.fact_ids[] | characters | нет | "—" | string | форма |
| characters.*.personality.evidence.*.id | characters | нет | "—" | string | служебное / read-only |
| characters.*.personality.evidence.*.source_event_id | characters | в заполненной записи | "—" | string | форма |
| characters.*.personality.evidence.*.source_turn | characters | в заполненной записи | "—" | integer {"minimum": 0} | форма |
| characters.*.personality.evidence.*.minute | characters | в заполненной записи | "—" | integer {"minimum": 0} | форма |
| characters.*.personality.evidence.*.meaning | characters | в заполненной записи | "—" | string {"minLength": 1, "maxLength": 300} | форма |
| characters.*.personality.evidence.*.kind | characters | в заполненной записи | "—" | enum: behavior, experience, turning_point | форма |
| characters.*.personality.evidence.*.player_owned | characters | нет | false | boolean | форма |
| characters.*.personality.evidence.*.evidence | characters | в заполненной записи | "—" | string {"minLength": 1, "maxLength": 1000} | форма |
| characters.*.personality.evidence.*.witnesses[] | characters | нет | "—" | string | форма |
| characters.*.personality.evidence.*.fact_ids[] | characters | нет | "—" | string | форма |
| characters.*.personality.applied[] | characters | нет | "—" | string | служебное / read-only |
| characters.*.personality.seen_sources[] | characters | нет | "—" | string | служебное / read-only |
| characters.*.values.*.id | characters | нет | "—" | string | служебное / read-only |
| characters.*.values.*.text | characters | в заполненной записи | "—" | string {"minLength": 1, "maxLength": 2000} | форма |
| characters.*.values.*.status | characters | нет | "active" | enum: active, retired | форма |
| characters.*.values.*.revision | characters | нет | 0 | integer {"minimum": 0} | служебное / read-only |
| characters.*.values.*.source_ids[] | characters | нет | "—" | string | форма |
| characters.*.values.*.witnesses[] | characters | нет | "—" | string | форма |
| characters.*.values.*.fact_ids[] | characters | нет | "—" | string | форма |
| characters.*.physical_state | characters | нет | "" | string | форма |
| characters.*.emotion | characters | нет | "" | string | форма |
| characters.*.emotion_source_sequence | characters | нет | null | integer | служебное / read-only |
| characters.*.goals[].id | characters | нет | "—" | string | служебное / read-only |
| characters.*.goals[].text | characters | в заполненной записи | "—" | string | форма |
| characters.*.goals[].status | characters | нет | "active" | enum: active, completed, cancelled, failed, superseded, expired, blocked | форма |
| characters.*.goals[].source_sequence | characters | нет | null | integer | форма |
| characters.*.goals[].evidence | characters | нет | "" | string | форма |
| characters.*.goals[].due_minute | characters | нет | null | integer {"minimum": 0} | форма |
| characters.*.goals[].revision | characters | нет | 0 | integer {"minimum": 0} | служебное / read-only |
| characters.*.goals[].source_event_id | characters | нет | null | string | форма |
| characters.*.goals[].dependencies.*[] | characters | нет | "—" | string | форма |
| characters.*.goals[].review_required[] | characters | нет | "—" | string | служебное / read-only |
| characters.*.goals[].reviewed_signature | characters | нет | "" | string | служебное / read-only |
| characters.*.intentions[].id | characters | нет | "—" | string | служебное / read-only |
| characters.*.intentions[].text | characters | в заполненной записи | "—" | string | форма |
| characters.*.intentions[].status | characters | нет | "active" | enum: active, completed, cancelled, failed, superseded, expired, blocked | форма |
| characters.*.intentions[].source_sequence | characters | нет | null | integer | форма |
| characters.*.intentions[].evidence | characters | нет | "" | string | форма |
| characters.*.intentions[].due_minute | characters | нет | null | integer {"minimum": 0} | форма |
| characters.*.intentions[].revision | characters | нет | 0 | integer {"minimum": 0} | служебное / read-only |
| characters.*.intentions[].source_event_id | characters | нет | null | string | форма |
| characters.*.intentions[].dependencies.*[] | characters | нет | "—" | string | форма |
| characters.*.intentions[].review_required[] | characters | нет | "—" | string | служебное / read-only |
| characters.*.intentions[].reviewed_signature | characters | нет | "" | string | служебное / read-only |
| characters.*.obligations[].id | characters | нет | "—" | string | служебное / read-only |
| characters.*.obligations[].text | characters | в заполненной записи | "—" | string | форма |
| characters.*.obligations[].status | characters | нет | "active" | enum: active, completed, cancelled, failed, superseded, expired, blocked | форма |
| characters.*.obligations[].source_sequence | characters | нет | null | integer | форма |
| characters.*.obligations[].evidence | characters | нет | "" | string | форма |
| characters.*.obligations[].due_minute | characters | нет | null | integer {"minimum": 0} | форма |
| characters.*.obligations[].revision | characters | нет | 0 | integer {"minimum": 0} | служебное / read-only |
| characters.*.obligations[].source_event_id | characters | нет | null | string | форма |
| characters.*.obligations[].dependencies.*[] | characters | нет | "—" | string | форма |
| characters.*.obligations[].review_required[] | characters | нет | "—" | string | служебное / read-only |
| characters.*.obligations[].reviewed_signature | characters | нет | "" | string | служебное / read-only |
| locations.*.id | locations | нет | "—" | string | служебное / read-only |
| locations.*.name | locations | в заполненной записи | "—" | string | форма |
| locations.*.description | locations | нет | "" | string | форма |
| locations.*.parent_id | locations | нет | null | string | форма |
| locations.*.kind | locations | нет | "unknown" | string {"minLength": 1} | форма |
| locations.*.aliases[] | locations | нет | "—" | string | форма |
| facts.*.id | facts | нет | "—" | string | служебное / read-only |
| facts.*.text | facts | в заполненной записи | "—" | string | форма |
| facts.*.visibility | facts | нет | "public" | enum: public, secret | форма |
| facts.*.character_ids[] | facts | нет | "—" | string | форма |
| facts.*.claim.subject_id | facts | в заполненной записи | "—" | string {"minLength": 1, "maxLength": 200} | форма |
| facts.*.claim.predicate | facts | в заполненной записи | "—" | string {"minLength": 1, "maxLength": 100} | форма |
| facts.*.claim.value | facts | в заполненной записи | "—" | string {"minLength": 1, "maxLength": 500} | форма |
| facts.*.claim.scope | facts | нет | "" | string {"maxLength": 200} | форма |
| knowledge.*.actor_id | knowledge | в заполненной записи | "—" | string | форма |
| knowledge.*.fact_id | knowledge | в заполненной записи | "—" | string | форма |
| knowledge.*.status | knowledge | нет | "known" | enum: known, suspected, unknown, outdated, refuted, superseded | форма |
| knowledge.*.revision | knowledge | нет | 0 | integer {"minimum": 0} | служебное / read-only |
| knowledge.*.source_event_id | knowledge | нет | null | string | форма |
| knowledge.*.evidence | knowledge | нет | "" | string | форма |
| knowledge.*.source_turn | knowledge | нет | null | integer {"minimum": 0} | форма |
| knowledge.*.replaced_by | knowledge | нет | null | string | форма |
| relationships.*.source_id | relationships | в заполненной записи | "—" | string | форма |
| relationships.*.target_id | relationships | в заполненной записи | "—" | string | форма |
| relationships.*.dimensions.* | relationships | нет | "—" | number | форма |
| relationships.*.context | relationships | нет | "" | string | форма |
| threads.*.source_event_id | threads | нет | null | string | форма |
| threads.*.stakes_for[] | threads | нет | "—" | string | форма |
| threads.*.favorable_path.opportunity | threads | в заполненной записи | "—" | string {"minLength": 1, "maxLength": 500} | форма |
| threads.*.favorable_path.next_step | threads | в заполненной записи | "—" | string {"minLength": 1, "maxLength": 300} | форма |
| threads.*.favorable_path.basis_ids[] | threads | нет | "—" | string | форма |
| threads.*.id | threads | нет | "—" | string | служебное / read-only |
| threads.*.description | threads | в заполненной записи | "—" | string | форма |
| threads.*.character_ids[] | threads | нет | "—" | string | форма |
| threads.*.status | threads | нет | "active" | enum: active, developing, dormant, resolved, paused | форма |
| threads.*.state | threads | нет | "" | string | форма |
| threads.*.relevance | threads | нет | 0.5 | number {"minimum": 0, "maximum": 1} | форма |
| scheduled_events.*.id | scheduled_events | нет | "—" | string | служебное / read-only |
| scheduled_events.*.description | scheduled_events | в заполненной записи | "—" | string | форма |
| scheduled_events.*.character_ids[] | scheduled_events | нет | "—" | string | форма |
| scheduled_events.*.due_minute | scheduled_events | нет | null | integer {"minimum": 0} | форма |
| scheduled_events.*.status | scheduled_events | нет | "pending" | enum: pending, resolved, cancelled | форма |
| scheduled_events.*.condition | scheduled_events | нет | "" | string | форма |
| scheduled_events.*.type | scheduled_events | нет | "event" | string | форма |
| scheduled_events.*.location_id | scheduled_events | нет | null | string | форма |
| scheduled_events.*.interrupts | scheduled_events | нет | false | boolean | форма |
| scheduled_events.*.last_attempt_minute | scheduled_events | нет | null | integer {"minimum": 0} | служебное / read-only |
| scheduled_events.*.temporal.date | scheduled_events | нет | null | string | форма |
| scheduled_events.*.temporal.weekday | scheduled_events | нет | null | integer {"minimum": 0, "maximum": 13} | форма |
| scheduled_events.*.temporal.day_offset | scheduled_events | нет | null | integer {"minimum": -366, "maximum": 366} | форма |
| scheduled_events.*.temporal.time | scheduled_events | нет | null | string {"pattern": "^([01]\\d\|2[0-3]):[0-5]\\d$"} | форма |
| scheduled_events.*.temporal.day_period | scheduled_events | нет | null | enum: night, morning, afternoon, evening | форма |
| scheduled_events.*.time_reference_minute | scheduled_events | нет | null | integer {"minimum": 0} | форма |
| scheduled_events.*.commitment | scheduled_events | нет | false | boolean | форма |
| scheduled_events.*.end_temporal.date | scheduled_events | нет | null | string | форма |
| scheduled_events.*.end_temporal.weekday | scheduled_events | нет | null | integer {"minimum": 0, "maximum": 13} | форма |
| scheduled_events.*.end_temporal.day_offset | scheduled_events | нет | null | integer {"minimum": -366, "maximum": 366} | форма |
| scheduled_events.*.end_temporal.time | scheduled_events | нет | null | string {"pattern": "^([01]\\d\|2[0-3]):[0-5]\\d$"} | форма |
| scheduled_events.*.end_temporal.day_period | scheduled_events | нет | null | enum: night, morning, afternoon, evening | форма |
| scheduled_events.*.depends_on[] | scheduled_events | нет | "—" | string | форма |
| scheduled_events.*.started_minute | scheduled_events | нет | null | integer {"minimum": 0} | форма |
| scheduled_events.*.outcome | scheduled_events | нет | "" | enum: , fulfilled, blocked, missed, cancelled, dependency_cancelled | форма |
| scheduled_events.*.evidence | scheduled_events | нет | "" | string | форма |
| scheduled_events.*.source_turn | scheduled_events | нет | null | integer {"minimum": 0} | форма |
| scheduled_events.*.remote_source_ids[] | scheduled_events | нет | "—" | string | форма |
| objective_relations.*.id | objective_relations | нет | "—" | string {"minLength": 1} | служебное / read-only |
| objective_relations.*.kind | objective_relations | в заполненной записи | "—" | enum: spouse, partner, engaged, parent, adoptive_parent, guardian, foster_parent, step_parent, sibling, contact, friend, close_friend, coworker | форма |
| objective_relations.*.source_id | objective_relations | в заполненной записи | "—" | string | форма |
| objective_relations.*.target_id | objective_relations | в заполненной записи | "—" | string | форма |
| objective_relations.*.status | objective_relations | нет | "active" | enum: active, closed | форма |
| objective_relations.*.since | objective_relations | нет | null | integer {"minimum": 0} | форма |
| objective_relations.*.until | objective_relations | нет | null | integer {"minimum": 0} | форма |
| objective_relations.*.since_date | objective_relations | нет | null | string | форма |
| objective_relations.*.until_date | objective_relations | нет | null | string | форма |
| objective_relations.*.outcome | objective_relations | нет | "" | enum: , ended, divorced, widowed, superseded, revoked | форма |
| objective_relations.*.context | objective_relations | нет | "" | string | форма |
| objective_relations.*.evidence | objective_relations | нет | "" | string | форма |
| objective_relations.*.source_turn | objective_relations | нет | null | integer {"minimum": 0} | форма |
| objective_relations.*.fact_id | objective_relations | нет | null | string | форма |
| objective_relations.*.closure_fact_id | objective_relations | нет | null | string | форма |
| conditions.*.id | conditions | нет | "—" | string {"minLength": 1} | служебное / read-only |
| conditions.*.actor_id | conditions | в заполненной записи | "—" | string | форма |
| conditions.*.description | conditions | в заполненной записи | "—" | string {"minLength": 1} | форма |
| conditions.*.status | conditions | нет | "active" | enum: active, resolved, cancelled, unknown_outcome | форма |
| conditions.*.duration | conditions | нет | "unknown" | enum: temporary, persistent, unknown | форма |
| conditions.*.effects.conscious | conditions | нет | null | boolean | форма |
| conditions.*.effects.can_perceive | conditions | нет | null | boolean | форма |
| conditions.*.effects.can_act | conditions | нет | null | boolean | форма |
| conditions.*.effects.can_speak | conditions | нет | null | boolean | форма |
| conditions.*.effects.can_move | conditions | нет | null | boolean | форма |
| conditions.*.since | conditions | нет | null | integer {"minimum": 0} | форма |
| conditions.*.until | conditions | нет | null | integer {"minimum": 0} | форма |
| conditions.*.evidence | conditions | нет | "" | string | форма |
| conditions.*.source_turn | conditions | нет | null | integer {"minimum": 0} | форма |
| conditions.*.fact_id | conditions | нет | null | string | форма |
| residences.*.id | residences | нет | "—" | string {"minLength": 1} | служебное / read-only |
| residences.*.status | residences | нет | "active" | enum: active, closed | форма |
| residences.*.since | residences | нет | null | integer {"minimum": 0} | форма |
| residences.*.until | residences | нет | null | integer {"minimum": 0} | форма |
| residences.*.since_date | residences | нет | null | string | форма |
| residences.*.until_date | residences | нет | null | string | форма |
| residences.*.context | residences | нет | "" | string | форма |
| residences.*.evidence | residences | нет | "" | string | форма |
| residences.*.source_turn | residences | нет | null | integer {"minimum": 0} | форма |
| residences.*.fact_id | residences | нет | null | string | форма |
| residences.*.closure_fact_id | residences | нет | null | string | форма |
| residences.*.outcome | residences | нет | "" | string | форма |
| residences.*.actor_id | residences | в заполненной записи | "—" | string | форма |
| residences.*.location_id | residences | в заполненной записи | "—" | string | форма |
| roles.*.id | roles | нет | "—" | string {"minLength": 1} | служебное / read-only |
| roles.*.status | roles | нет | "active" | enum: active, closed | форма |
| roles.*.since | roles | нет | null | integer {"minimum": 0} | форма |
| roles.*.until | roles | нет | null | integer {"minimum": 0} | форма |
| roles.*.since_date | roles | нет | null | string | форма |
| roles.*.until_date | roles | нет | null | string | форма |
| roles.*.context | roles | нет | "" | string | форма |
| roles.*.evidence | roles | нет | "" | string | форма |
| roles.*.source_turn | roles | нет | null | integer {"minimum": 0} | форма |
| roles.*.fact_id | roles | нет | null | string | форма |
| roles.*.closure_fact_id | roles | нет | null | string | форма |
| roles.*.outcome | roles | нет | "" | string | форма |
| roles.*.actor_id | roles | в заполненной записи | "—" | string | форма |
| roles.*.kind | roles | в заполненной записи | "—" | string {"minLength": 1} | форма |
| roles.*.title | roles | в заполненной записи | "—" | string {"minLength": 1} | форма |
| roles.*.organization_id | roles | нет | null | string | форма |
| roles.*.field | roles | нет | null | string | форма |
| organizations.*.id | organizations | нет | "—" | string {"minLength": 1} | служебное / read-only |
| organizations.*.status | organizations | нет | "unknown" | enum: active, closed, unknown | форма |
| organizations.*.since | organizations | нет | null | integer {"minimum": 0} | форма |
| organizations.*.until | organizations | нет | null | integer {"minimum": 0} | форма |
| organizations.*.since_date | organizations | нет | null | string | форма |
| organizations.*.until_date | organizations | нет | null | string | форма |
| organizations.*.context | organizations | нет | "" | string | форма |
| organizations.*.evidence | organizations | нет | "" | string | форма |
| organizations.*.source_turn | organizations | нет | null | integer {"minimum": 0} | форма |
| organizations.*.fact_id | organizations | нет | null | string | форма |
| organizations.*.closure_fact_id | organizations | нет | null | string | форма |
| organizations.*.outcome | organizations | нет | "" | string | форма |
| organizations.*.name | organizations | в заполненной записи | "—" | string {"minLength": 1} | форма |
| organizations.*.kind | organizations | нет | "unknown" | string {"minLength": 1} | форма |
| organizations.*.aliases[] | organizations | нет | "—" | string | форма |
| organizations.*.location_ids[] | organizations | нет | "—" | string | форма |
| organizations.*.name_history[].previous | organizations | в заполненной записи | "—" | string {"minLength": 1} | форма |
| organizations.*.name_history[].current | organizations | в заполненной записи | "—" | string {"minLength": 1} | форма |
| organizations.*.name_history[].minute | organizations | в заполненной записи | "—" | integer {"minimum": 0} | форма |
| organizations.*.name_history[].date | organizations | нет | null | string | форма |
| organizations.*.name_history[].turn_id | organizations | нет | "—" | integer {"minimum": 0} | служебное / read-only |
| organizations.*.name_history[].evidence | organizations | в заполненной записи | "—" | string | форма |
| organizations.*.name_history[].fact_id | organizations | нет | null | string | форма |
| reproduction_policy.protected | reproduction_policy | нет | 0.01 | number {"minimum": 0, "maximum": 1} | форма |
| reproduction_policy.unprotected | reproduction_policy | нет | 0.2 | number {"minimum": 0, "maximum": 1} | форма |
| reproduction_policy.unknown | reproduction_policy | нет | 0 | number {"minimum": 0, "maximum": 1} | форма |
| reproduction_policy.child_weights[] | reproduction_policy | нет | "—" | number | форма |
| reproduction_policy.gestation_days | reproduction_policy | нет | 280 | integer {"minimum": 1, "maximum": 1000} | форма |
| reproduction_policy.adult_age | reproduction_policy | нет | 18 | integer {"minimum": 18} | форма |
| reproduction_policy.shared_family_name | reproduction_policy | нет | true | boolean | форма |
| reproductive_events.*.id | reproductive_events | нет | "—" | string | служебное / read-only |
| reproductive_events.*.participants[] | reproductive_events | нет | "—" | string | форма |
| reproductive_events.*.gestational_actor_id | reproductive_events | в заполненной записи | "—" | string | форма |
| reproductive_events.*.impregnating_actor_id | reproductive_events | в заполненной записи | "—" | string | форма |
| reproductive_events.*.protection | reproductive_events | в заполненной записи | "—" | enum: protected, unprotected, unknown | форма |
| reproductive_events.*.source_event_id | reproductive_events | в заполненной записи | "—" | string | форма |
| reproductive_events.*.evidence | reproductive_events | в заполненной записи | "—" | string | форма |
| reproductive_events.*.turn_id | reproductive_events | нет | "—" | integer | служебное / read-only |
| reproductive_events.*.earliest_minute | reproductive_events | в заполненной записи | "—" | integer {"minimum": 0} | форма |
| reproductive_events.*.latest_minute | reproductive_events | в заполненной записи | "—" | integer {"minimum": 0} | форма |
| reproductive_events.*.exact_minute | reproductive_events | нет | null | integer {"minimum": 0} | форма |
| reproductive_events.*.conceived | reproductive_events | в заполненной записи | "—" | boolean | форма |
| reproductive_events.*.pregnancy_id | reproductive_events | нет | null | string | форма |
| reproductive_events.*.closed | reproductive_events | нет | false | boolean | форма |
| reproductive_events.*.policy.protected | reproductive_events | нет | 0.01 | number {"minimum": 0, "maximum": 1} | форма |
| reproductive_events.*.policy.unprotected | reproductive_events | нет | 0.2 | number {"minimum": 0, "maximum": 1} | форма |
| reproductive_events.*.policy.unknown | reproductive_events | нет | 0 | number {"minimum": 0, "maximum": 1} | форма |
| reproductive_events.*.policy.child_weights[] | reproductive_events | нет | "—" | number | форма |
| reproductive_events.*.policy.gestation_days | reproductive_events | нет | 280 | integer {"minimum": 1, "maximum": 1000} | форма |
| reproductive_events.*.policy.adult_age | reproductive_events | нет | 18 | integer {"minimum": 18} | форма |
| reproductive_events.*.policy.shared_family_name | reproductive_events | нет | true | boolean | форма |
| pregnancies.*.id | pregnancies | нет | "—" | string | служебное / read-only |
| pregnancies.*.event_id | pregnancies | в заполненной записи | "—" | string | форма |
| pregnancies.*.gestational_actor_id | pregnancies | в заполненной записи | "—" | string | форма |
| pregnancies.*.parent_ids[] | pregnancies | нет | "—" | string | форма |
| pregnancies.*.status | pregnancies | нет | "active" | enum: active, due, born | форма |
| pregnancies.*.earliest_minute | pregnancies | в заполненной записи | "—" | integer {"minimum": 0} | форма |
| pregnancies.*.latest_minute | pregnancies | в заполненной записи | "—" | integer {"minimum": 0} | форма |
| pregnancies.*.conception_minute | pregnancies | нет | null | integer {"minimum": 0} | форма |
| pregnancies.*.due_minute | pregnancies | в заполненной записи | "—" | integer {"minimum": 0} | форма |
| pregnancies.*.children[].id | pregnancies | нет | "—" | string | служебное / read-only |
| pregnancies.*.children[].sex | pregnancies | в заполненной записи | "—" | enum: female, male | форма |
| pregnancies.*.birth_event_id | pregnancies | нет | null | string | форма |
| pregnancies.*.birth_minute | pregnancies | нет | null | integer | форма |
| pregnancies.*.fact_id | pregnancies | в заполненной записи | "—" | string | форма |
| pregnancies.*.count_fact_id | pregnancies | в заполненной записи | "—" | string | форма |
| pregnancies.*.sex_fact_ids.* | pregnancies | нет | "—" | string | форма |
| naming_decisions.*.id | naming_decisions | нет | "—" | string | служебное / read-only |
| naming_decisions.*.pregnancy_id | naming_decisions | в заполненной записи | "—" | string | форма |
| naming_decisions.*.child_id | naming_decisions | в заполненной записи | "—" | string | форма |
| naming_decisions.*.components.* | naming_decisions | нет | "—" | string | форма |
| naming_decisions.*.display_name | naming_decisions | нет | null | string | форма |
| naming_decisions.*.status | naming_decisions | в заполненной записи | "—" | enum: proposed, agreed, cancelled, replaced | форма |
| naming_decisions.*.decision_actor_ids[] | naming_decisions | нет | "—" | string | форма |
| naming_decisions.*.delegated_to | naming_decisions | нет | null | string | форма |
| naming_decisions.*.established | naming_decisions | нет | false | boolean | форма |
| naming_decisions.*.source_event_id | naming_decisions | в заполненной записи | "—" | string | форма |
| naming_decisions.*.evidence | naming_decisions | в заполненной записи | "—" | string | форма |
| naming_decisions.*.fact_id | naming_decisions | в заполненной записи | "—" | string | форма |
| naming_decisions.*.replaces | naming_decisions | нет | null | string | форма |
| possessions.*.id | possessions | нет | "—" | string {"minLength": 1, "maxLength": 100} | служебное / read-only |
| possessions.*.name | possessions | в заполненной записи | "—" | string {"minLength": 1, "maxLength": 160} | форма |
| possessions.*.kind | possessions | в заполненной записи | "—" | string {"minLength": 1, "maxLength": 80} | форма |
| possessions.*.owner_id | possessions | нет | null | string | форма |
| possessions.*.holder_id | possessions | нет | null | string | форма |
| possessions.*.location_id | possessions | нет | null | string | форма |
| possessions.*.status | possessions | нет | "unknown" | enum: unknown, available, lost, destroyed | форма |
| possessions.*.revision | possessions | нет | 0 | integer {"minimum": 0} | служебное / read-only |
| possessions.*.fact_id | possessions | нет | null | string | форма |
| possessions.*.field_facts.* | possessions | нет | "—" | string | форма |
| possessions.*.source_event_id | possessions | нет | null | string | форма |
| possessions.*.source_turn | possessions | нет | null | integer | форма |
| possessions.*.applied.* | possessions | нет | "—" | string | служебное / read-only |
