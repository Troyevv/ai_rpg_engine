# Genre catalog (#193)

The issue table contains **25** new genres, despite saying 24. All named entries
are implemented: **37 standard IDs + `custom`**. The twelve original IDs and
GenreConfig wire shape are unchanged. No data migration or historical rewrite.

`backend/runtime_v3/genre_catalog.json` is the single authored catalog: stable IDs,
RU/EN copy, group membership, search aliases and soft themes. Python derives its
Literal schema and THEMES; TypeScript imports the same JSON at build time. No
catalog HTTP request, model call, additional policy or setting is introduced.
Groups are navigation metadata and never serialized into GenreConfig.

The existing GenreSettings component serves both IdeaAtelier and NarrativePolicy.
The initial group is Life & relationships. Search spans both languages and aliases
and switches to All; explicit category filters remain visible. Primary/secondary
role controls keep selection unambiguous. Disabled accent cards remain focusable
and explain the cap. Selected accents can be removed directly; promoting one
removes its duplicate. Neutral primary, secondary-only policies and unselected
custom text are preserved. Clear selection has undo; search reset never edits
policy. Draft buffering, API revisions, history and regeneration remain owned by
the existing application.

The shared guidance is kept concise rather than expanding the context budget.
No genre invents technologies, geography, magic, player decisions or required
outcomes. Existing Context Builder and Director/Extraction boundaries remain
unchanged. Locale comes from the existing gameLocale convention.

## Catalog

Names and descriptions below are a review snapshot of the JSON, not a second
runtime catalog. Themes are reviewed directly in that file.

| Stable ID | RU name and description | EN name and description |
|---|---|---|
| `slice_of_life` | **Повседневность** — Повседневные занятия, отношения и небольшие перемены в жизни. | **Everyday life** — Everyday activities, relationships and small changes. |
| `family_saga` | **Семейная сага** — История семьи на протяжении лет и поколений. Будущие браки, дети и переходы героя заранее не определены. | **Family saga** — Family ties across generations, without predetermined marriages or children. |
| `romance` | **Романтика** — Сближение и личные отношения, когда они согласуются с желаниями персонажей и вашим замыслом. | **Romance** — Closeness and relationships consistent with character intentions. |
| `drama` | **Драма** — Внутренние противоречия и сложные отношения без обязательной трагедии. | **Drama** — Conflicting values and relationships without mandatory tragedy. |
| `detective` | **Детектив** — Наблюдения, улики и поиск объяснений. Преступление не обязательно. | **Detective** — Clues and competing explanations; crime is optional. |
| `thriller` | **Триллер** — Ожидание, неопределённость и напряжение без предрешённого насилия. | **Thriller** — Suspense and uncertainty without predetermined violence. |
| `science_fiction` | **Научная фантастика** — Научные идеи, технологии и их влияние на жизнь общества. | **Science fiction** — Science, technology and their human consequences. |
| `fantasy` | **Фэнтези** — Необычный мир и возможное волшебство в пределах заданных правил. | **Fantasy** — Wonder within the established rules of the world. |
| `horror` | **Ужасы** — Неизвестность и тревожная атмосфера. Не задаёт уровень риска или обязательные травмы. | **Horror** — Unease and the unknown; does not set risk or require injuries. |
| `adventure` | **Приключения** — Открытия, путешествия и новые обстоятельства без обязательного героического подвига. | **Adventure** — Discovery and exploration without mandatory heroism. |
| `post_apocalyptic` | **Постапокалипсис** — Жизнь после крупных перемен мира; причины и последствия определяет ваш замысел. | **Post-apocalyptic** — Life after major disruption; the world defines its causes. |
| `historical` | **Исторический** — Жизнь в выбранной эпохе. Страна, даты и биографии не выводятся из названия жанра. | **Historical** — Life in the established era, without inventing dates or biographies. |
| `psychological_drama` | **Психологическая драма** — Внутренние противоречия, субъективный опыт и тонкие перемены. | **Psychological drama** — Inner conflict, subjective experience and subtle changes. |
| `political_drama` | **Политическая драма** — Убеждения, публичные решения и их человеческая цена. | **Political drama** — Beliefs, public choices and their human cost. |
| `crime_drama` | **Криминальная драма** — Лояльность, ответственность и последствия нарушения закона. | **Crime drama** — Loyalty, responsibility and consequences around the law. |
| `space_opera` | **Космическая опера** — Масштабные истории и далёкие горизонты в рамках заданного мира. | **Space opera** — Expansive stories and distant horizons within the authored world. |
| `dystopia` | **Антиутопия** — Общественное давление, свобода и цена привычного порядка. | **Dystopia** — Social pressure, freedom and the cost of accepted order. |
| `alternate_history` | **Альтернативная история** — Последствия исторических развилок, заданных автором. | **Alternate history** — Consequences of historical divergences established by the author. |
| `cyberpunk` | **Киберпанк** — Личность, неравенство и власть технологий, если они есть в мире. | **Cyberpunk** — Identity, inequality and technological power where the world supports it. |
| `dark_fantasy` | **Тёмное фэнтези** — Неоднозначность и тревожное чудо без обязательной жестокости. | **Dark fantasy** — Ambiguity and unsettling wonder without mandatory cruelty. |
| `urban_fantasy` | **Городское фэнтези** — Необычное рядом с привычной городской жизнью. | **Urban fantasy** — The unusual alongside familiar urban life. |
| `epic_fantasy` | **Эпическое фэнтези** — Широкий масштаб и переплетение судеб без обязательного пророчества. | **Epic fantasy** — Broad scope and intersecting lives without a required prophecy. |
| `mysticism` | **Мистика** — Совпадения, неоднозначные знаки и граница объяснимого. | **Mysticism** — Coincidences, ambiguous signs and the limits of explanation. |
| `gothic` | **Готика** — Тени прошлого, выразительные места и тревожные семейные истории. | **Gothic** — Shadows of the past, evocative places and uneasy family histories. |
| `supernatural_thriller` | **Сверхъестественный триллер** — Напряжение вокруг необъяснимого без навязывания его природы. | **Supernatural thriller** — Suspense around the unexplained without imposing its nature. |
| `dynastic_saga` | **Династическая сага** — Наследие рода, преемственность и личные интересы поколений. | **Dynastic saga** — Dynastic legacy, continuity and personal interests across generations. |
| `court_intrigue` | **Придворные интриги** — Репутация, влияние и скрытые интересы в установленном круге власти. | **Court intrigue** — Reputation, influence and private interests around established power. |
| `war_drama` | **Военная драма** — Долг, близость и человеческий опыт конфликтов, уже заданных миром. | **War drama** — Duty, bonds and human experiences of conflicts established in the world. |
| `music_drama` | **Музыкальная драма** — Творческий голос, совместная работа и отношения вокруг музыки. | **Music drama** — Creative voice, collaboration and relationships around music. |
| `sports_drama` | **Спортивная драма** — Мастерство, соперничество и повседневная работа над собой. | **Sports drama** — Skill, rivalry and everyday practice. |
| `business_drama` | **Бизнес-драма** — Предпринимательство, ответственность и отношения в работе. | **Business drama** — Enterprise, responsibility and working relationships. |
| `comedy` | **Комедия** — Юмор характеров, диалогов и повседневных несовпадений. | **Comedy** — Humour in characters, dialogue and everyday incongruities. |
| `satire` | **Сатира** — Иронический взгляд на общественные привычки и противоречия. | **Satire** — An ironic view of social habits and contradictions. |
| `black_comedy` | **Чёрная комедия** — Мрачная ирония и абсурд без обязательных трагедий. | **Black comedy** — Dark irony and absurdity without mandatory tragedy. |
| `survival` | **Выживание** — Практические решения, ресурсы и взаимопомощь в текущих условиях. | **Survival** — Practical choices, resources and mutual support in current conditions. |
| `exploration` | **Исследование** — Любопытство, наблюдения и постепенное открытие мира. | **Exploration** — Curiosity, observation and gradual discovery of the world. |
| `nautical_adventure` | **Морские приключения** — Пути по воде, команды и встречи, когда это допускает мир. | **Nautical adventure** — Waterborne journeys, crews and encounters where the world allows them. |
| `custom` | **Свой жанр** — Направление задаётся вашим описанием ниже. | **Custom genre** — Themes from your description below. |

## Verification and visual evidence

- Backend: all IDs through creation/import/serialization, neutral and legacy reads,
  schema/API rejection, revisions, bounded guidance, identical Director/Extraction,
  controlled-provider handoff, ordinary turns, reopen, regeneration, rollback and branch.
- Frontend: alias/group search, immutable selection rules, promotion, cap, removal
  focus, custom validation, undo, English labels and disabled state.
- Browser: `genre-catalog.spec.ts`, `genre-policy.spec.ts`, `idea190.spec.ts`,
  `draft-v4.spec.ts`. Real FastAPI/SQLite with a controlled LLM boundary.
- Viewports: 360/390/430/768 and 1280/1440/1920; 200% text size; keyboard;
  reduced motion. All three skins have default, search, empty, selected/cap,
  custom/error/long-text screenshots. Frame samples exercise real transitions.

The initial PR commit `2d872a7` captures the unchanged master UI in all three skins,
desktop/mobile, with romance + drama. Subsequent commits capture the same policy
and the additional states. CI reports contain attached screenshots; final run
links and pass/fail results belong in the PR description. Local Chromium is blocked
by the execution sandbox's Unix-socket restrictions; no local browser pass is claimed.

These checks establish deterministic behavior, not live model literary quality.
No live DeepSeek request, paid model call or physical-device verification is claimed.

### Durable visual review

The following small contact sheets are derived from actual Chromium screenshots,
not mockups. Before: master `559456b` through baseline commit `2d872a7`.
After: implementation `485188e`. Both comparison sides select **Romance + Drama**.
Desktop screenshots are retained at 1440×900; mobile screenshots are normalized
to their 390×900 CSS-pixel viewport. Overview desktop sheets crop only the drawer.

| Skin | Desktop before / after | Mobile before / after |
|---|---|---|
| Graphite | [Comparison](media/genre193/graphite-desktop.webp) | [Comparison](media/genre193/graphite-mobile.webp) |
| Parchment | [Comparison](media/genre193/parchment-desktop.webp) | [Comparison](media/genre193/parchment-mobile.webp) |
| Cyberpunk | [Comparison](media/genre193/cyberpunk-desktop.webp) | [Comparison](media/genre193/cyberpunk-mobile.webp) |

[Default catalog — desktop](media/genre193/catalog-desktop.webp) ·
[Default catalog — mobile](media/genre193/catalog-mobile.webp)

Browser review caught and corrected inherited atelier fieldset spacing and custom
label padding; the first mobile card now fits fully above the footer at 390×900.
The existing shell, skin typography and disclosure transitions remain intact.

[Browser evidence run](https://github.com/Troyevv/ai_rpg_engine/actions/runs/42131072733):
all four smoke shards passed (88 passed, 4 existing mobile skips). The skips are
outside the genre scenarios. Full regression results are reported in the PR.
The workflow retains detailed artifacts for 7 days; these contact sheets remain
in the repository. `genre-catalog.spec.ts` reproduces all detailed states.

| State / behavior | Screenshot or trace evidence in smoke artifacts |
|---|---|
| Default catalog, expanded groups, cards | `default-*`, `groups-*`, `cards-*` |
| Same policy as baseline | `after-baseline-*` |
| Alias search, empty results, reset/focus | `search-*`, `empty-*`, catalog trace |
| Primary + 3 secondary; disabled cap | `selected-*`, `limit-*` |
| Custom invalid / long text | `invalid-custom-*`, `custom-long-*` |
| Saved policy in an existing game, all skins | `policy-*` in shard 1 |
| RU/EN, 200% text zoom, narrow viewport | `english-text-zoom-*`, `compact-input-viewport-*` |
| Keyboard, removal focus, reset/undo, reload | Catalog and policy E2E actions/assertions |
| Entry animation start/intermediate/end | Catalog trace + `motion-frame-samples` JSON attachment |
| Reduced motion | Computed opacity/transform and transition assertions |
| Generation → atomic handoff → policy edit → reload | Controlled-provider catalog E2E |

Keyboard-space testing uses an emulated 360×480 viewport with focused input.
It is **not** a physical Android keyboard test. Screen-reader semantics are
asserted through roles, labels and focus; no human assistive-technology session
is claimed. These limitations do not change the implemented controls.
