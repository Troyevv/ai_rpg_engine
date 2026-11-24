"""Deterministic LLM transport for the real smartphone jobs in backend and browser tests."""

import json


def response(messages):
    instruction = messages[0]["content"]
    data = json.loads(messages[1]["content"])
    if instruction.startswith("Dating search/1"):
        f = data["filters"]
        return dict(
            candidates=[
                dict(
                    name=name,
                    age=f["min_age"] + min(i, f["max_age"] - f["min_age"]),
                    gender="female" if f["gender"] == "any" else f["gender"],
                    occupation="Иллюстратор",
                    personality="Любознательная",
                    appearance="Короткие каштановые волосы",
                    interests=["Книги", "Вернисажи"],
                    location=f["location"] or "Москва",
                    bio="Рисую ночные улицы, ищу компанию в кино.",
                )
                for i, name in enumerate(
                    ("Ася Миронова", "Мария Орлова", "Ника Ветрова", "Лида Ланская", "Лера Озерова")
                )
            ]
        )
    if instruction.startswith("Dating character/1"):
        c = data["candidate"]
        year = int((c["search_date"] or "2026-10-10")[:4]) - c["age"]
        fields = {k: "Подробная история выбранного персонажа" for k in data["card_fields"]}
        fields.update(Характер=c["personality"], Внешность=c["appearance"], Роль=c["occupation"])
        return dict(name=c["name"], birth_date=f"{year:04d}-01-01", fields=fields)
    authors = [a["id"] for a in data["authors"]]
    if "Игрок обновил ленту" in instruction:
        batch = max((p["sequence"] for p in data["public_posts"]), default=0) + 1
        return dict(
            actions=[
                dict(
                    kind="post", author=authors[0], text=f"На набережной расцвела сирень. Зарисовка №{batch}."
                ),
                dict(
                    kind="post", author=authors[-1], text=f"Собираем квартет для репетиции. Афиша №{batch}."
                ),
                dict(kind="comment", author=authors[0], target="@2", text="Присоединюсь со скрипкой."),
            ]
        )
    first = dict(
        kind="comment" if data["source"] else "post",
        author=authors[0],
        target=data["source"],
        text="Буду у галереи вечером. Кто ещё идёт?",
    )
    return dict(
        actions=[first, dict(kind="comment", author=authors[-1], target="@1", text="Я приду после работы.")]
    )


def author_batch(messages, *, mixed):
    """Deliberately imperfect model reply; @N refers to the original action ordinal."""
    roster = json.loads(messages[1]["content"])["authors"]
    rows = [dict(kind="post", author="outside-the-roster", text="Отклонённая запись.")]
    if mixed:
        rows.extend(
            [
                dict(kind="post", author=roster[0]["name"], text="Сегодня открыли летнюю читальню."),
                dict(kind="comment", author=roster[1]["id"], target="@1", text="Ответ отклонённой записи."),
                dict(kind="comment", author=roster[1]["id"], target="@2", text="Зайду за книгой вечером."),
                dict(kind="like", author=roster[0]["id"], target="@3"),
                dict(kind="post", author=roster[1]["id"], text="Сыграем во дворе после обеда?"),
            ]
        )
    return dict(actions=rows)
