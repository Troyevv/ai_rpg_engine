"""Deterministic LLM transport for the real smartphone jobs in backend and browser tests."""

import json


def response(messages):
    instruction = messages[0]["content"]
    data = json.loads(messages[1]["content"])
    if instruction.startswith("Phone catalog/1"):
        place = next(iter(data["places"]), {"id": None, "name": "Город"})
        now = data["calendar"]["world_time"]
        n = len(data["news"])+1
        if "news." in instruction:
            return dict(articles=[dict(topic=f"investigation-{i}",title=f"Хроника набережной {n}.{i}",summary="Репортаж из "+place["name"],
                body=(data["recent_events"][-1]["text"] if i==0 and data["recent_events"] else "Издание сообщает о поиске утраченной коллекции."),category="Общество",source="Городской вестник",
                previous_id=data["news"][0]["id"] if data["news"] else None,
                event_id=data["recent_events"][-1]["id"] if i==0 and data["recent_events"] else None) for i in range(5)])
        if "events." in instruction:
            return dict(events=[dict(listing_key="music-"+str(len(data["events"])+1),title="Вечер музыки "+str(len(data["events"])+1),description="Открытая репетиция",
                location_id=place["id"],category="Музыка",start=now+1440,end=now+1550)])
        profession, pay = {"Парусный век":("Парусный мастер","Доля от фрахта"),
                           "Орбитальная эпоха":("Техник орбитальной верфи","Расчёт в кредитах станции")}.get(
                               data["world"].get("era"),("Мастер переплёта","Сдельная"))
        employer = data["organizations"][0] if data["world"].get("era") in ("Парусный век","Орбитальная эпоха") else None
        return dict(vacancies=[dict(listing_key="restorer-"+str(len(data["vacancies"])+i+1),title=profession+" "+str(len(data["vacancies"])+i+1),description="Работа на верфи" if employer else "Реставрация книг",
            category="Ремесло",location_id=place["id"],employer=employer["name"] if employer else "Переплётная мастерская",
            organization_id=employer["id"] if employer else None,employment=k,
            requirements="Опыт в мастерской" if employer else "Бережное обращение с книгами",schedule="По договорённости",pay=pay) for i,k in enumerate(("gig","permanent"))])
    if instruction.startswith("Phone questions/1"):
        return dict(answer="Мне нравится вечерняя музыка.") if data["question"] else dict(question=dict(
            recipient=data["people"][0],text="Куда пойдём после репетиции?",anonymous=True))
    if instruction.startswith("Phone employer/1"):
        fields={k:"Мастер реставрации книг" for k in data["card_fields"]}
        fields["Возраст"]="45"
        return dict(name="Марина Волкова",fields=fields)
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
                    kind="post", author=authors[-1], ref="new:quartet", text=f"Собираем квартет для репетиции. Афиша №{batch}."
                ),
                dict(kind="comment", author=authors[0], target="new:quartet", text="Присоединюсь со скрипкой."),
            ]
        )
    first = dict(
        kind="comment" if data["source"] else "post",
        author=authors[0],
        target=data["source"],
        ref="new:gallery",
        text="Буду у галереи вечером. Кто ещё идёт?",
    )
    return dict(
        actions=[first, dict(kind="comment", author=authors[-1], target="new:gallery", text="Я приду после работы.")]
    )


def author_batch(messages, *, mixed):
    """Deliberately imperfect model reply with dependencies on rejected publications."""
    roster = json.loads(messages[1]["content"])["authors"]
    rows = [dict(kind="post", author="outside-the-roster", ref="new:dropped", text="Отклонённая запись.")]
    if mixed:
        rows.extend(
            [
                dict(kind="post", author=roster[0]["name"], ref="new:reading", text="Сегодня открыли летнюю читальню."),
                dict(kind="comment", author=roster[1]["id"], ref="new:lost-reply", target="new:dropped", text="Ответ отклонённой записи."),
                dict(kind="comment", author=roster[1]["id"], target="new:reading", text="Зайду за книгой вечером."),
                dict(kind="like", author=roster[0]["id"], target="new:lost-reply"),
                dict(kind="post", author=roster[1]["id"], text="Сыграем во дворе после обеда?"),
            ]
        )
    return dict(actions=rows)
