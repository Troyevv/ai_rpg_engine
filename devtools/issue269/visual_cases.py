"""Fixed inputs for the classic portrait review through real Workshop components."""
import json

from backend.runtime_v3.portrait_catalog import CATALOG
from backend.services.draft_portraits import default_descriptor


def cases():
    ages = ["infant", "child", "adolescent", "young_adult", "mature_adult", "elderly"]
    population = []
    for i in range(60):
        age = ages[i % len(ages)]
        stage = age if age in ages[:3] else "adult"
        world = i // 6
        actor = {"biological_sex": ["male", "female"][(i + world) % 2]}
        p = default_descriptor(f"npc-{i}", stage, actor, age_style=age, version=3,
                               world_id=f"classic-{world}", profile=["modern", "historical", "neutral", "fantasy", "futuristic"][world % 5])
        population.append({"portrait": p, "label": f"{i + 1:02} · {age}"})
    base = {**population[3]["portrait"], "facial_hair": "clean_shaven", "visage": "oval", "hairstyle": "parted",
            "garment": "shirt", "eye_shape": "almond", "nose_shape": "straight", "lip_shape": "defined",
            "body_frame": "male", "skin": 1, "hair_color": 1, "clothing_color": 2, "accent_color": 1, "eyewear":"none", "face_detail":"none", "body_build": "average"}
    groups = {"population": population}
    for name, key in [("face", "visage"), ("hair", "hairstyle"), ("clothing", "garment"), ("facial_hair", "facial_hair")]:
        groups[name] = [{"label": label, "portrait": {**base, key: code}} for code, label in CATALOG["styles"][name].items()]
    groups["age"] = [{"label": age, "portrait": {**base, "visual_age": age, "stage": age if age in ages[:3] else "adult"}} for age in ages]
    for name, options in CATALOG.get("features", {}).items():
        groups[name] = [{"label": label, "portrait": {**base, name: code}} for code, label in options.items()]
    for field in ('hair_color', 'clothing_color', 'accent_color'):
        colors = CATALOG['styles']['clothing_color' if field=='accent_color' else field]
        groups[field] = [{'label':label, 'portrait':{**base, 'garment':'sailor', field:i}}
                         for i,label in enumerate(colors.values())]
    groups['fit'] = [
        {'label':f'{build} · {age}', 'portrait':{**base, 'body_build':build, 'garment':outfit,
         'visual_age':age, 'stage':age if age in ages[:3] else 'adult'}}
        for build in CATALOG['features']['body_build']
        for age, outfit in [('child','parka'), ('young_adult','kimono'), ('mature_adult','tech_shell'), ('elderly','lamellar')]]
    for build in CATALOG['features']['body_build']:
        groups['body_' + build] = [
            {'label': label, 'portrait': {**base, 'body_build': build, 'garment': garment}}
            for garment, label in CATALOG['styles']['clothing'].items()]
    probes = ['shirt', 'dress', 'blazer', 'kimono', 'parka', 'wrap_blanket']
    groups['body_ages'] = [
        {'label': f'{age} · {build}', 'portrait': {
            **base, 'body_build': build, 'garment': probes[(i+j) % len(probes)],
            'visual_age': age, 'stage': age if i < 3 else 'adult'}}
        for i, age in enumerate(ages) for j, build in enumerate(CATALOG['features']['body_build'])]
    # Both turns for every age. Change one seed byte, leaving the rest of
    # the person's landmarks alone. Each sheet holds that sitter fixed.
    faces = list(CATALOG['styles']['face'])
    for i, age in enumerate(ages):
        for mirrored in range(2):
            sitter = population[i * 6 + i]['portrait']
            yaw = '00' if mirrored == 0 else 'ff'
            seed = sitter['seed'][:28] + yaw + sitter['seed'][30:]
            person = {**sitter, 'seed': seed, 'visage': faces[i * 2 + mirrored],
                      'skin': (i + mirrored) % 7, 'body_revision': 3}
            groups[f'hair_{age}_{mirrored}'] = [
                {'label': label, 'portrait': {**person, 'hairstyle': style}}
                for style, label in CATALOG['styles']['hair'].items()]
    # Each row keeps the same person, pose, tone and eyes across all six noses.
    groups['nose_matrix'] = []
    groups['nose_previous'] = []
    tones = [0, 3, 6, 2, 5, 1, 4, 3]
    faces = ['round','broad','heart','oblong','diamond','pear','angular','square']
    for index, (tone, face) in enumerate(zip(tones, faces)):
        age = ages[index % 6] if index < 6 else ['young_adult','elderly'][index-6]
        person = {**population[index]['portrait'], 'skin':tone, 'visage':face, 'visual_age':age,
                  'stage':age if age in ages[:3] else 'adult', 'hairstyle':'parted', 'garment':'shirt',
                  'facial_hair':'clean_shaven','eyewear':'none','face_detail':'none','eye_shape':'almond'}
        for shape, label in CATALOG['features']['nose_shape'].items():
            art = {**person, 'nose_shape':shape}
            groups['nose_matrix'].append({'label':label, 'portrait':art})
            groups['nose_previous'].append({'label':label, 'portrait':{k:v for k,v in art.items() if k!='nose_revision'}})
    return groups


if __name__ == "__main__":
    print(json.dumps(cases(), ensure_ascii=False))
