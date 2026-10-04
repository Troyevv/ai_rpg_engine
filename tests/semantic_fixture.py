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
                knowledge=["След"],
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
