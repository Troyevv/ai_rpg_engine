"""Fixed inputs for the classic portrait review through real Workshop components."""
import json

from backend.runtime_v3.portrait_catalog import CATALOG
from backend.services.draft_portraits import default_descriptor


def cases():
    ages = ["infant", "child", "adolescent", "young_adult", "mature_adult", "elderly"]
    population = []
    for i in range(36):
        age = ages[i % len(ages)]
        stage = age if age in ages[:3] else "adult"
        world = i // 6
        actor = {"biological_sex": ["male", "female"][(i + world) % 2]}
        p = default_descriptor(f"npc-{i}", stage, actor, age_style=age, version=3,
                               world_id=f"classic-{world}", profile=["modern", "historical", "neutral"][world % 3])
        population.append({"portrait": p, "label": f"{i + 1:02} · {age}"})
    base = {**population[3]["portrait"], "facial_hair": "clean_shaven", "visage": "oval", "hairstyle": "parted",
            "garment": "shirt", "eye_shape": "almond", "nose_shape": "straight", "lip_shape": "defined",
            "body_frame": "male", "skin": 1, "hair_color": 1, "clothing_color": 2, "body_build": "average"}
    groups = {"population": population}
    for name, key in [("face", "visage"), ("hair", "hairstyle"), ("clothing", "garment"), ("facial_hair", "facial_hair")]:
        groups[name] = [{"label": label, "portrait": {**base, key: code}} for code, label in CATALOG["styles"][name].items()]
    groups["age"] = [{"label": age, "portrait": {**base, "visual_age": age, "stage": age if age in ages[:3] else "adult"}} for age in ages]
    for name, options in CATALOG.get("features", {}).items():
        groups[name] = [{"label": label, "portrait": {**base, name: code}} for code, label in options.items()]
    return groups


if __name__ == "__main__":
    print(json.dumps(cases(), ensure_ascii=False))
