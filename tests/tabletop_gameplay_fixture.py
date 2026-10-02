"""Gameplay acceptance world, covering checks with observable canonical stakes."""

from tabletop_fixture import definition
from backend.tabletop.definitions import SceneCheck, CheckEffect, Secret


def gameplay_definition():
    d = definition()
    d.ruleset_id = "d20-fantasy-v2"
    d.ruleset_version = 4
    for a in d.characters + d.creatures:
        a.build.feature_choices = ["defense_style"]
    d.secrets.extend(
        [
            Secret(
                id="room_clue",
                name="Следы",
                location_id="market",
                description="Следы ведут к архиву.",
            ),
            Secret(
                id="rune_clue",
                name="Руна",
                location_id="market",
                description="Руна открывает путь в хранилище.",
            ),
        ]
    )
    d.checks = [
        SceneCheck(
            id="investigation_check",
            name="Исследовать следы",
            location_id="market",
            category="exploration",
            ability="intelligence",
            skill="investigation",
            success=[CheckEffect(type="reveal_secret", target="room_clue")],
        ),
        SceneCheck(
            id="deception_check",
            name="Представиться посланником",
            location_id="market",
            category="dialogue",
            ability="charisma",
            skill="deception",
            actor_id="archivist",
            success=[
                CheckEffect(type="attitude", target="archivist", attitude="friendly")
            ],
            failure=[
                CheckEffect(type="attitude", target="archivist", attitude="hostile")
            ],
        ),
        SceneCheck(
            id="climb_check",
            name="Взобраться по мокрой стене",
            location_id="market",
            category="environment",
            ability="strength",
            skill="athletics",
            difficulty="EXTREME",
            success=[CheckEffect(type="move", target="vault")],
            failure=[CheckEffect(type="damage", amount=3), CheckEffect(type="prone")],
        ),
        SceneCheck(
            id="arcana_check",
            name="Прочитать руны",
            location_id="market",
            category="knowledge",
            ability="intelligence",
            skill="arcana",
            success=[CheckEffect(type="reveal_secret", target="rune_clue")],
        ),
        SceneCheck(
            id="stealth_check",
            name="Прокрасться за стражем",
            location_id="vault",
            category="stealth",
            difficulty="VERY_HARD",
            ability="dexterity",
            skill="stealth",
            actor_id="sentinel",
            success=[CheckEffect(type="reveal_object", target="drawer")],
            failure=[CheckEffect(type="alert", target="sentinel")],
        ),
    ]
    return d
