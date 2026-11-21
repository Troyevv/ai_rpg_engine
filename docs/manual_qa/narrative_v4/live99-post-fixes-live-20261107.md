# #99 — Live Retest после #241–#244

Refs #99, предыдущий отчёт #239; единственный новый QA PR — #245.
**Первый этап не пройден. Stage C не завершён. Второй этап не запускался.**
Продуктовый код и исходные QA-артефакты не изменены. PR не мёрджится, #99 не закрывается.

## Версии, исходные данные и подготовка

- Проверен свежий `origin/master` **d81a52c9980b79d1be99acfde9fc1a1452d71176**, включающий #241/#237, #242/#240, #243/#238 и #244/#223.
- Исполняемый QA HEAD: **32eb3ee0017a2a0515059fd3afd1e21fe85140b2**. Отличия от master относятся только к QA: скопированный ledger, отдельный лимит, action paths и проверки ограничителя.
- Архив пользователя `live99-campaign-evidence-20261107.tar.gz`: **29,089,712 bytes**, SHA256 **3979c8b87ce923ccf21737c8a7cd17718f218b36535997b752c5118d4d15a277**. Проверены все **353** исходных хеша; после работы они совпадают. SQLite game/budget/budget-before исправны.
- Полные SQLite и ledger физически скопированы. Использованы сохранённые Social save1, Family save10, Crisis/incapacity save8, Knowledge save4, Campaign save5, Phone save6. Новые миры не создавались. Старые jobs отменены, Crisis/Phone восстановлены через UI rollback; все шесть World State/history_head точно совпали с исходными before-checkpoints до платных вызовов.
- Прочитаны AGENTS.md, #99/#239, Issues и исправления. Проверены production Context Builder, RawTurnResult, engine/jobs, bounded repair, StateResolver, History, Knowledge, POV, agency и persistence.
- Сначала выполнены бесплатные replay оригинальных payload всех четырёх проблем и Campaign/011 на отдельных копиях SQLite. Неверные Crisis/provenance/due payload отвергаются; явные диагностические controls принимаются. Phone с ложным, структурно валидным completed_arrival по-прежнему принимается: Runtime не интерпретирует прозу. Controls не применялись к live-save.
- Первоначальный Campaign replay при context40960 показал overflow repair. Бесплатный повтор при49152 подтвердил достаточный контекст и полный отказ/успех соответствующих payload; первоначальная ошибка сохранена. Это изменение настройки модели, не обход валидации.

Бесплатная регрессия подробно сохранена в [preflight-отчёте](live99-post-fixes-preflight-20261107.md): **145** целевых backend tests; полный backend **3583 passed / 1 failed / 1 skipped**, где failure — Hypothesis timing/DeadlineExceeded без семантического assertion, а неизменённый отдельный тест прошёл; **151** frontend tests; build; **12** desktop/mobile E2E. Полный неуспешный запуск не переименован в зелёный. После изменения QA-ограничителя: **26 passed** в budget/transport/retest/postfix наборах. Финальный offline reproducer #246 проходит без ключа и провайдера. CI прежнего preflight-коммита e75d61e был зелёным; это не доказательство live semantics.

## Бюджет и реальные вызовы

Проверены исходные **283 settled reservations**, **175 QA actions**, исторический baseline205. Ранее разрешённые $2: расход $0.3586539, фактический остаток allowance перед прогоном **$1.6413461**. Оригинальные rows и authorization tables сохранены. Новое явное разрешение: **этап1, максимум36 вызовов / $0.60 peak-cold**; оно не было выведено из прежнего allowance. Новый guard атомарно проверяет оба лимита, полную резервируемую context-capacity, unknown outcomes и исторический prefix. Автоматические provider retries не добавлялись.

| Сценарий | Новых вызовов | Input tokens | Output tokens | USD по usage/тарифу |
| --- | ---: | ---: | ---: | ---: |
| Crisis | 3 | 42,777 | 3,617 | 0.007438974 |
| Social | 2 | 28,353 | 1,415 | 0.002712465 |
| Knowledge, включая recovery | 4 | 68,041 | 6,779 | 0.010115214 |
| Campaign/011 retry | 1 | 20,906 | 1,147 | 0.003033828 |
| Family | 3 | 44,800 | 1,753 | 0.004930584 |
| Phone | 2 | 26,664 | 1,486 | 0.002821440 |
| **Всего** | **15** | **231,541** | **16,197** | **0.031052505** |

Все15 запросов завершены, неизвестных исходов0; cache-hit input91,135. Лимит учитывается консервативно без cache/off-peak скидок: **$0.0888987**, остаток нового лимита **$0.5111013**, старого allowance **$1.5524474**. USD по usage — тарифная оценка, не долларовый invoice. Реальный provider balance до/после: **CNY16.19 → CNY16.00** (округлённый account balance, не точная стоимость отдельного запроса), USD0.00. `GET /models`/balance, UI, reload и replay inference-вызовов не создавали.

Все платные действия выполнялись настоящим DeepSeek Flash через production FastAPI и Chromium, с UI submit/retry. В каждый ordinary job разрешён единственный automatic Extraction repair. Дополнительно выполнен только один вручную проверенный Knowledge retry после измеренного context overflow; успешные Narrative не повторялись. После подтверждения блокеров платные вызовы остановлены.

## Результаты обязательного этапа

| Сценарий | Вердикт | Проверенное поведение |
| --- | --- | --- |
| Crisis / #237 | **BLOCKED; atomic safety PASS** | Отсутствующая Вера не попала в канон; попытка не стала ложным completed History, но Narrative выдумал её присутствие, repair не исправил классификацию, ход отклонён |
| Social / #238 | **PASS для выданного compound action; частичное покрытие** | Согласованный Event/action/точная цитата, нет чужого согласия; модель не разделила два действия, live repair этой формы не проверен |
| Knowledge / #238 | **FAIL semantics; provenance восстановлен** | Retry сохранил Narrative и корректную договорённость, но четыре приобретения знания потеряны: новая #246 |
| Campaign/011 / #238 | **PASS targeted recovery** | Исходный Narrative неизменен; абсолютная минута и provenance исправлены одной новой Extraction |
| Family / #240 | **BLOCKED** | Ошибка классификации наблюдения маскирует temporal repair; состояние неизменно, рождения нет |
| Phone / #223 | **FAIL, прежний дефект воспроизведён** | План/подготовка превратились в два completed_arrival, ложные locations и History пережили reload |

### Crisis — исходный Crisis/001, save8

Input: «Я, Нина, спрашиваю Веру о состоянии Кирилла и предлагаю практическую помощь.»
Job `e3b9501fc2494c6d9a8bb9c6a35206b6`, time558→558, error `event_presence_invalid`.

В before Веры нет в библиотеке; Narrative изображает её физически отвечающей Нине. Initial Extraction и единственный repair оставляют её среди participants/witnesses. Runtime отвергает оба. **Полный before/after идентичен**, новых Events, movements, Knowledge и actor commitments нет. Нина остаётся controlled actor. В context physical present Вера отсутствует, remote interactions пусты; одно упоминание в actor references не является разрешением телепортации. Подтверждённая ошибка на Narrative/Extraction пути; отказ Runtime корректен. Прежний escape #237 с сохранением completed в этом live-ответе не воспроизведён: guard срабатывает раньше. Live сохранение attempted outcome осталось непроверенным; соответствующие offline controls проходят. #237 обновлена без дубликата.

### Social — исходный Social/001, save1

Input: «Я согласен сейчас сортировать фотографии по датам, оставляя оригинал карты на месте. Прошу Веру показать первую пачку.»
Job `6175b8229df4454cbf61fd54c537f979`, saved567→570.

Вера согласилась, оставила карту на месте и показала первую пачку. Extraction создала один compound PlayerAction, его полную точную цитату и соответствующий Event. History не утверждает, что вся сортировка уже закончена; чужое согласие не приписано игроку. PC goals/intentions/obligations не изменились. Новых Knowledge/relationships нет. Optional continuity beat получил `continuity_player_interaction_unconfirmed / drop_record`; это записано, а не скрыто. Буквальное разделение двух независимых действий и его repair покрыты исходными offline payload, но не данным live-ответом. Успешный вызов ради иной формы Extraction не повторялся.

### Knowledge — исходный Knowledge/001, save4

Input: «Я согласен прийти завтра в библиотеку в 15:00. Спрашиваю Веру, подходит ли ей именно это время.»
Job `b47b39afb3374cebafa383b7c8c177d6`, финально saved553→555.

Первый Narrative+Extraction запросил repair из-за отсутствующего `scheduled_event_changes.player_assertion`; контекст repair **36745/36608** не поместился. Состояние осталось неизменным. До retry выполнено бесплатное построение именно repair feedback: context49152, estimate41791, hard limit44800. Единственный retry повторил только Extraction; один bounded repair добавил `explicit_choice`. Старый Narrative сохранён байт-в-байт.

Event и compound action имеют одинаковую точную цитату, договорённость завтра15:00 обеспечена явным input и ответом Веры. Но Narrative сообщает Кириллу и Тимуру о подсобке и дне рождения Веры; Extraction создаёт два факта и четыре knowledge_gained, **пропуская Event.fact_ids**. Runtime предупреждает `knowledge_path_invalid / drop_record` четыре раза и сохраняет остальную сцену. В каноне Facts есть, Knowledge слушателей не изменён, History.knowledge_acquisitions пуст. После reload расхождение остаётся. Дополнительно отвергнуты optional NPC continuity beat и один choice kind; warnings сохранены.

**Новая подтверждённая #246**: первичная ошибка Extraction — отсутствующая перекрёстная ссылка; Runtime правильно не принимает неподтверждённое знание, но warning не приводит к полноценному correction этой сцены. Read-only control с единственным добавлением двух существующих fact IDs к Event восстанавливает четыре приобретения. Продуктового исправления в QA нет.

Воспроизведение: `env -u DEEPSEEK_API_KEY .venv/bin/python -m devtools.live99.replay_postfix_knowledge`. [Минимальная сохранённая live-фикстура](../../../tests/fixtures/issue99_postfix/knowledge.json) использует неизменённый hash-checked before из #238. Это characterization текущего дефекта, не тест исправления.

### Campaign/011 — исходный failed job после прежнего LTA, save5

Input: «Я спрашиваю, что стало с договорённостями, делами мастерской и звонком Олегу.»
Повторно обработан **тот же** job `df90fbfbb25c4018911b4ba13c2d8f77`, saved2631444→2631446.

Один новый вызов Extraction; новых Narrative0. Сохранены весь старый текст и отсутствие совершённых обещаний/звонка в нём. Новая Extraction задаёт minute2631444 вместо старого564 и точные `player_action_id=ask_status`/player_evidence. History сохраняет эти значения; новых Knowledge или решений игрока нет. Исходные diagnostics и responses остались в job. UI prose, SQLite reload и предыдущие siblings согласованы. Это успех восстановления #238; он **не является новым тестом LTA**, и качество прежней многолетней истории заново не сертифицируется.

### Family — исходный Family/002, save10

Input: «Я остаюсь рядом и наблюдаю, что происходит с Верой, не вмешиваясь в её действия.»
Job `d3b5d1ec662245ad830713bd28f219a9`, error; time1980→1980.

Narrative описывает продолжающиеся роды и указания врача, ребёнок не родился. Оба extracts выдают due_birth_assessment=ongoing, но elapsed_minutes=3 и completed interaction с Верой для пассивного наблюдения без player-linked Event. Repair повторяет это; `player_action_completion_invalid` срабатывает **раньше temporal validation**. Канон и History не изменились, выдуманного ребёнка нет.

Бесплатная изоляция actual live payload: original→completion error; только target_mode=reference→`ordinary_temporal_boundary`, max_minutes0; reference плюс elapsed0→ongoing accepted, время1980, новых characters0. Нельзя называть такой control успехом живой модели. #237/#240 обновлены. Несколько live нулевых ходов, live завершение родов, BirthClaim, канонический пол и Knowledge/POV ребёнка остаются **не проверены в этом прогоне**. Соответствующие детерминированные проверки проходят; известная #231 этим запуском не пересертифицирована.

### Phone — исходный Phone/001, save6

Input: «Я остаюсь на месте, занимаюсь своими фотографиями и даю другим возможность связаться со мной.»
Job `77dbff1e216a4091a5485f50ed264407`, saved548→558.

Тимур говорит «Я занесу их Олегу», поднимается и задерживается у стола. Прибытия в мастерскую нет. Вера уходит собираться; в конце её шаги ещё слышны внутри дома. Extraction вопреки полученному #244 contract создаёт completed_arrival Тимура в мастерскую `location_567f2d7db666cb5e4abf` и Веры в библиотеку `location_cc730cd3a861be83e138`. Они исключены из present, канонические locations и **оба History.movements** сохранены, diagnostics отсутствуют; reload повторяет дефект.

В этом новом Narrative даже сам выход Тимура за пределы сцены выражен недостаточно явно; тем более не подтверждён endpoint. Это подтверждённая прежняя #223, а не новый Runtime prose-parser defect. Issue обновлена. От unknown-location требования live-сцена отклоняется. Новые локации и настоящие прибытия в новые/существующие места проходят бесплатные регрессионные controls, но дополнительные платные прибытия после повреждённого хода не запускались.

## Продолжение кампании и надёжность

Второй этап запрещён условием успешного первого, поэтому **не выполнены новые** NPC/background группы, отношения, секреты/смены POV, телефонные звонки/сообщения/групповые чаты, регенерация/sibling switching, LTA1 год и затем5 лет. NPC initiative наблюдалась в самих mandatory сценах, но это не завершённая автономная кампания. Предыдущие siblings сохранены; бесплатные rollback на оригинальные Crisis/Phone checkpoints проверены. Новые LTA события, изменения character state и история мира не создавались и не объявляются проверенными.

Runtime демонстрирует полезную атомарную защиту при ошибках присутствия/agency. Provenance repair Campaign работает. Однако сохранённая сцена может быть семантически неверной: Phone записал недостигнутые места, Knowledge потерял приобретения. **Narrative Mode пока недостаточно надёжен для завершения Stage C.** Блокеры: #223; playable Crisis/Family Narrative/Extraction failures; #246; непокрытые split-action live cases, многоходовые роды/BirthClaim и полный этап2. HTTP200, saved job и зелёный CI не заменяют эти проверки.

## UI, SQLite и доказательства

- До live проверены все6 original saves в desktop/mobile. В первом проходе Campaign calendar не успел показать дни за5s (11/12); отдельная бесплатная проверка с диагностическим ожиданием подтвердила загрузку за4.3008s, API181ms, без JS errors и изменений состояния. Первичный timeout сохранён.
- Финальный Chromium reload всех6 saves:3 desktop/3 mobile, canonical projection совпадает, state/history/variants неизменны, page errors0. Narrative сравнивался с UI для каждого сохранённого live хода; Family/Crisis показывают несохранённую сцену и controls отмены/retry. Phone UI выглядит работоспособным при семантически неверном каноне. Визуально просмотрены Crisis desktop, Family/Phone mobile и Campaign calendar. Скриншоты оставлены вне git.
- Во всех **17** изолированных SQLite `integrity_check=ok`. Все прежние варианты сохранены. Для отказов exact before/after equality; для saved — отдельно проверены semantic deltas и History, а не только integrity.
- Дополнительное UI-наблюдение: в исходном Campaign calendar безымянный ребёнок отображается техническим ID. Canonical display_name и card name пусты ещё до retest; этот запуск не установил новый регрессионный дефект. Наблюдение сохранено отдельно; продуктовая Issue не создавалась без достаточной изоляции/дедупликации.
- [Машинный индекс](live99-post-fixes-live-20261107-evidence.json) содержит checkpoint/hash, master/QA SHA, user input, job/status, все новые request IDs/токены/стоимость, Narrative SHA, verdict и reload для каждой группы.
- Полные before/after World State, History до/после, Knowledge, raw Narrative/initial Extraction/repair, context diagnostics, UI и SQLite сохранены в изолированном `work/live99-postfix-20261107`. Исходные и новые ошибки harness/context не удалены. Пакет raw evidence хранится отдельно от git с SHA256 manifest; в git только отчёт, индекс и минимальный reproducer. **Публичный download URL для нового raw-пакета не заявляется.** Выделенный chat output filesystem недоступен для записи в этом execution environment; наличие локального пакета не выдаётся за опубликованный asset.

Raw-пакет: `live99-postfix-evidence-20261107.tar.gz`, 30262307 bytes, 283 indexed files, SHA256 `e19a0b07ea8a76223c16c6b5805f3e7c9b85733aea0a5828719d0522e5176a36`. Дублирующие SQLite бесплатных replay исключены из архива; их snapshots/responses и scripts сохранены. Основные game/budget SQLite включены. Сконфигурированные credential values в экспортируемых данных не обнаружены.
