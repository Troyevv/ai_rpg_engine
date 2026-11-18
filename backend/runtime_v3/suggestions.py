"""Optional private trailer on the Narrative stream. Only grounded entries reach the UI."""
import json

MARKER = '<action_suggestions>'
NARRATIVE_INSTRUCTION = ("\nAfter prose append <action_suggestions> on its own line then a JSON array of "
                         "4–6 short action strings in the game's language, grounded in the player's POV. No device controls.")


def split_suggestions(text, *, complete=False, verbatim=False):
    prose, found, trailer = text.partition(MARKER)
    if found:
        try:
            items = json.loads(trailer) if complete else None
        except ValueError:
            items = None
        # Preserve indexes even if an individual entry is unusable.
        choices = [item if isinstance(item, str) and 0 < len(item.strip()) <= 800 else None
                   for item in items[:6]] if isinstance(items, list) else []
        return (prose.removesuffix('\n') if verbatim else prose.rstrip()), choices
    if verbatim and complete:
        return text, []
    # A delimiter can span provider chunks. Never stream its prefix.
    for size in range(min(len(text), len(MARKER)-1), 0, -1):
        if text.endswith(MARKER[:size]):
            return text[:-size], []
    return text, []


def bind_suggestions(rows, suggestions, warnings):
    valid = []
    for row in rows[:6] if isinstance(rows, list) else []:
        index = row.get('index') if isinstance(row, dict) else None
        if type(index) is not int or not 0 <= index < len(suggestions) or not suggestions[index] or not isinstance(row.get('grounding'), dict):
            warnings.append(dict(section='choices', code='choice_index_invalid', action='drop'))
            continue
        valid.append({**{k:row[k] for k in ('grounding','basis_ids','kind','interaction_channel','device_control') if k in row},
                      'action':suggestions[index], 'speech':''})
    return valid
