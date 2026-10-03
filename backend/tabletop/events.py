"""Explain observable state changes after trusted mechanics, before narration."""

from .encounter import event


def state_changes(before, after, events):
    for aid, actor in after.actors().items():
        old = before.actors().get(aid)
        if not old:
            continue
        if old.hp != actor.hp and not any(
            e.get("target") == aid and "hp_before" in e for e in events
        ):
            event(
                events,
                f"{actor.name}: {old.hp} → {actor.hp} HP.",
                kind="health",
                target=aid,
                hp_before=old.hp,
                hp_after=actor.hp,
                maximum=actor.max_hp,
            )
        for resource in actor.resources.keys() | old.resources.keys():
            previous, current = old.resources.get(resource, 0), actor.resources.get(
                resource, 0
            )
            if previous != current:
                label = next(
                    (
                        f.name
                        for f in after.ruleset.features.values()
                        if f.resource == resource
                    ),
                    resource,
                )
                event(
                    events,
                    f"{actor.name} · {label}: {previous} → {current}.",
                    kind="resource",
                    target=aid,
                    before=previous,
                    after=current,
                )
        for level, slot in actor.spell_slots.items():
            previous = old.spell_slots.get(level)
            if previous and previous.remaining != slot.remaining:
                event(
                    events,
                    f"{actor.name} · ячейки {level} круга: {previous.remaining} → {slot.remaining}.",
                    kind="spell_slot",
                    target=aid,
                    before=previous.remaining,
                    after=slot.remaining,
                )
        for condition in set(old.conditions) ^ set(actor.conditions):
            definition = after.ruleset.condition_definitions.get(condition)
            name = definition.name if definition else condition
            event(
                events,
                f'{actor.name}: {"получено" if condition in actor.conditions else "снято"} состояние «{name}».',
                kind="condition",
                target=aid,
                condition=condition,
                active=condition in actor.conditions,
            )
