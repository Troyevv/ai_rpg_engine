"""Semantic fixtures: names and intent only, shared with browser/API fixtures."""


def world():
    return dict(
        name="Стеклянные приливы",
        description="Город сохраняет голоса в кристаллах.",
        genre="Неизвестный мир",
        species=[
            dict(
                name="Слушатели",
                traits=[dict(name="Чуткость", intent="expertise", expertise="Слух")],
            )
        ],
        professions=[
            dict(
                name="Хранитель",
                role="defender",
                expertise=["Слух"],
                equipment=["Резонатор", "Оболочка"],
                resource=dict(name="Стойкость", model="stamina"),
                abilities=[
                    dict(name="Защита", intent="defense"),
                    dict(name="Импульс", intent="damage", damage_concept="Резонанс"),
                ],
            ),
            dict(
                name="Певец",
                role="caster",
                casting="prepared_slots",
                power_source="Голос",
                abilities=[
                    dict(name="Нота", intent="damage", damage_concept="Резонанс"),
                    dict(name="Эхо", intent="healing"),
                ],
            ),
        ],
        backgrounds=[
            dict(
                name="Архивист",
                expertise=["Слух"],
                contacts=["Хранитель архива"],
                knowledge=["Путь к архиву"],
            )
        ],
        skills=[dict(name="Слух", affinity="awareness")],
        damage_concepts=[dict(name="Резонанс")],
        items=[
            dict(
                name="Резонатор",
                category="weapon",
                style="ranged",
                approach="precision",
                damage_concept="Резонанс",
            ),
            dict(name="Оболочка", category="armor", weight="heavy"),
            dict(name="Лекарство", category="medical"),
        ],
        creatures=[dict(name="Осколок", role="minion", damage_concept="Резонанс")],
    )


def campaign():
    return dict(
        name="Пропавшие голоса",
        premise="Архив теряет память.",
        starting_situation="Дверь архива открыта.",
        starting_location="Площадь",
        player_hooks=["Исследовать исчезновение"],
        locations=[
            dict(name="Площадь", connections=["Архив"]),
            dict(
                name="Архив",
                connections=["Площадь"],
                environment=["indoor", "cluttered"],
            ),
        ],
        factions=[dict(name="Хранители", enemies=["Осколки"]), dict(name="Осколки")],
        npcs=[
            dict(
                name="Смотритель",
                location="Площадь",
                faction="Хранители",
                profession="Хранитель",
                known_secrets=["След"],
                knowledge=["История деревни"],
            )
        ],
        secrets=[
            dict(
                name="След",
                description="Голоса уносит неизвестный хранитель.",
                location="Архив",
            )
        ],
        objects=[
            dict(
                name="Сундук",
                location="Архив",
                capabilities=["lockable", "container"],
                secrets=["След"],
                loot=[dict(category="medical")],
            )
        ],
        quests=[
            dict(
                name="Найти голоса",
                description="Выяснить причину исчезновения.",
                location="Площадь",
                giver="Смотритель",
                goals=["Найти причину"],
                possible_outcomes=["Вернуть голоса", "Договориться"],
            )
        ],
        checks=[
            dict(
                name="Разобрать след",
                location="Архив",
                expertise="Слух",
                reveals="След",
            )
        ],
        encounters=[
            dict(
                name="Осколки архива",
                location="Архив",
                faction="Осколки",
                creatures=["Осколок"],
            )
        ],
    )


def world_blueprint():
    return dict(
        name="Стеклянные приливы",
        premise="Город сохраняет голоса в кристаллах.",
        genre="Неизвестный мир",
        tone="Тревожное исследование",
        themes=["Память"],
        peoples=[
            dict(name="Слушатели", description="Воспринимают колебания кристаллов.")
        ],
        archetypes=[
            dict(name="Хранитель", description="Защищает архивы."),
            dict(name="Певец", description="Работает с голосами."),
        ],
        origins=[dict(name="Архивист", description="Изучал историю голосов.")],
        skill_domains=[dict(name="Слух", description="Различение и передача голосов.")],
        equipment_families=[
            dict(
                name="Резонатор",
                purpose="weapon",
                medium="field",
                description="Направляет резонанс.",
            ),
            dict(name="Оболочка", purpose="protection"),
            dict(name="Лекарство", purpose="recovery"),
        ],
        power_traditions=[
            dict(
                name="Голос",
                description="Сохранённые голоса меняют кристаллы.",
                practice="learned",
            )
        ],
        threat_families=[
            dict(
                name="Осколок",
                nature="construct",
                description="Самостоятельный кристалл, поглощающий голоса.",
            )
        ],
        locations=[dict(name="Архив", description="Хранилище памяти.")],
        world_rules=["Голоса сохраняются в кристаллах."],
    )


def campaign_blueprint():
    return dict(
        name="Пропавшие голоса",
        premise="Архив теряет память.",
        central_conflict="Хранители скрывают потерю голосов.",
        starting_situation="Дверь архива открыта.",
        player_hooks=["Исследовать исчезновение"],
        locations=[
            dict(name="Площадь", description="Место встреч слушателей."),
            dict(name="Архив", description="Хранилище голосов."),
        ],
        actors=[
            dict(
                name="Смотритель",
                description="Следит за архивом.",
                motivation="Сохранить память",
                knowledge=["История деревни"],
            )
        ],
        secret_ideas=[
            dict(name="След", description="Голоса уносит неизвестный хранитель.")
        ],
        quest_hooks=[
            dict(name="Найти голоса", description="Выяснить причину исчезновения.")
        ],
        developments=["Вернуть голоса", "Договориться"],
    )
