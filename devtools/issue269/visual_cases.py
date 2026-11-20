"""Fixed inputs for inspecting the rasterized production renderer. Run as a module."""
import json

from backend.runtime_v3.portrait_catalog import ILLUSTRATION
from backend.services.draft_portraits import default_descriptor


def portrait(identity, world, age="young_adult", profile="neutral", actor=None):
    stage = age if age in {"infant", "child", "adolescent"} else "adult"
    return default_descriptor(
        identity, stage, actor=actor, age_style=age, world_id=world,
        profile=profile, version=4, art_style="anime",
    )


def vary(base, **traits):
    return {**base, "traits": {**base["traits"], **traits}}


def cases():
    ages = ["infant", "child", "adolescent", "young_adult", "mature_adult", "elderly"]
    base = vary(
        portrait("reference", "studio"), hair="parted", face="oval", clothing="shirt",
        build="average", facial_hair="clean_shaven", detail="none", expression="neutral",
    )
    groups = {}
    for field, choices in ILLUSTRATION["styles"].items():
        groups[field] = [
            {"label": label, "portrait": vary(base, **{field: key})} for key, label in choices.items()
        ]
    groups["trim"] = [
        {"label": label, "portrait": vary(base, clothing="blazer", trim=key)}
        for key, label in ILLUSTRATION["styles"]["clothing_color"].items()
    ]
    groups["body_frame"] = [
        {"label": frame, "portrait": {**base, "body_frame": frame}}
        for frame in ("female", "male", "neutral")
    ]
    groups["age"] = [
        {"label": age, "portrait": {**base, "visual_age": age, "stage": age if age in ages[:3] else "adult"}}
        for age in ages
    ]
    groups["combinations"] = [
        {"label": label, "portrait": vary(base, **traits)}
        for label, traits in [
            ("Узкая челюсть и борода", dict(face="narrow", facial_hair="full_beard")),
            ("Узкая челюсть и эспаньолка", dict(face="narrow", facial_hair="goatee")),
            ("Широкая челюсть и борода", dict(face="broad", facial_hair="short_beard")),
            ("Широкая челюсть и бакенбарды", dict(face="broad", facial_hair="sideburns")),
            ("Длинные волосы и высокий ворот", dict(hair="long", clothing="techcoat")),
            ("Очки и нависающее веко", dict(detail="round_specs", eye_shape="hooded")),
            ("Очки и распахнутые глаза", dict(detail="square_specs", eye_shape="open")),
            ("Крупная фигура в пиджаке", dict(build="full", clothing="blazer")),
        ]
    ]
    for age, hair, skin in [("child", "curly", "deep"), ("child", "bob", "light"),
                           ("elderly", "bun", "deep"), ("elderly", "short", "light")]:
        groups["combinations"].append({
            "label": f"{age} · {hair} · {skin}",
            "portrait": {**vary(base, hair=hair, skin=skin, hair_color="grey" if hair == "bun" else "brown"),
                         "visual_age": age, "stage": "child" if age == "child" else "adult"},
        })
    # All 36 IDs are used, including repeated choices. Change only art_style when comparing a pair.
    profiles = ["modern", "historical", "fantasy", "futuristic"]
    groups["population"] = []
    for i in range(36):
        world = i // 9
        identity = f"npc-{i % 9}"
        age = ages[i % len(ages)]
        sex = ["male", "female", None][(world + i // 2) % 3]
        actor = {"biological_sex": sex} if sex else {}
        descriptor = portrait(identity, f"world-{world}", age, profiles[world], actor)
        groups["population"].append({"label": f"{world + 1} / {identity} · {age}", "portrait": descriptor})
    return groups


if __name__ == "__main__":
    print(json.dumps(cases(), ensure_ascii=False))
