"""Bounded identity preparation for accepted long-term event proposals.

The normal resolver still owns creation. A named incidental reference alone is
not enough: a selected cause and a continued canonical role/relation are required.
"""

from backend.runtime_v3.models import identity
from backend.runtime_v3.resolver import normalized


def prepare(raw, snapshot, candidate_ids):
    promotions = raw.records["promotions"]
    if len(promotions) > 2:
        raise ValueError("Не более двух новых личностей на группу исходов.")
    remap = {}
    allowed = set()
    names = {}
    for card in snapshot["character_cards"]:
        for name in [card["name"], *card.get("aliases", [])]:
            if name.strip():
                names.setdefault(normalized(name).casefold(), set()).add(card["id"])
    retained = []
    for row in promotions:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("name"), str)
            or not isinstance(row.get("id"), str)
        ):
            raise ValueError("Повреждена предлагаемая личность.")
        cid = row["id"]
        name = normalized(row["name"]).casefold()
        if not name:
            raise ValueError("Не указана личность нового персонажа.")
        existing = names.get(name, set())
        if len(existing) > 1:
            raise ValueError("Неоднозначная существующая личность.")
        if existing:
            if cid not in existing:
                raise ValueError(
                    "Возможный дубликат: используй существующий canonical ID, не объединяй личности по имени."
                )
            remap[cid] = cid
            continue
        continuity = any(
            cid in (r.get("actor_id"), r.get("source_id"), r.get("target_id"))
            for section in (
                "role_changes",
                "residence_changes",
                "social_relation_changes",
            )
            for r in raw.records[section]
            if isinstance(r, dict)
        )
        source = next(
            (
                e
                for e in raw.records["events"]
                if isinstance(e, dict)
                and cid in e.get("participants", [])
                and e.get("evidence")
            ),
            None,
        )
        if not continuity or not source:
            raise ValueError("Новый персонаж не нужен принятой роли или связи.")
        stable = identity("character", sorted(candidate_ids), name)
        if stable in snapshot["world_state"]["characters"]:
            remap[cid] = stable
            continue
        remap[cid] = stable
        allowed.add(stable)
        # Identity/role is sufficient. Appearance and personality have their own
        # evidence-bound canonical deltas, not a generated biography card.
        row["fields"] = {}
        retained.append(row)
        names[name] = {stable}
    raw.records["promotions"] = retained

    def replace(value):
        if isinstance(value, str):
            return remap.get(value, value)
        if isinstance(value, list):
            return [replace(v) for v in value]
        if isinstance(value, dict):
            return {k: replace(v) for k, v in value.items()}
        return value

    raw.records = replace(raw.records)
    raw.final_scene = replace(raw.final_scene)
    return allowed
