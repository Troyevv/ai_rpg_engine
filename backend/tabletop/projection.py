"""All player-facing surfaces use the same whitelist; never serialize DM state."""
from .rules import RulesEngine


def public_state(state):
    hero = state.actor(state.session_state.controlled_actor)
    sheets = {}
    for aid in state.party:
        a = state.actor(aid)
        sheets[aid] = {k: v for k, v in a.model_dump().items() if k not in ('goals', 'traits', 'knowledge', 'relationships', 'morale', 'faction')}
        rules = RulesEngine()
        sheets[aid]['modifiers'] = {k: rules.modifier(v) for k, v in a.abilities.items()}
        sheets[aid]['skill_modifiers'] = {k: rules.check_modifier(a, ability, k, state.ruleset) for k, ability in state.ruleset.skills.items()}
        sheets[aid]['save_modifiers'] = {k: rules.save_modifier(a, k) for k in a.abilities}
        sheets[aid]['attack_modifiers'] = {k: rules.attack_modifier(a, k) for k in a.attacks}
    visible_npcs = {k: {'id': k, 'name': a.name, 'position': a.position, 'status': 'выведен из боя' if a.hp == 0 else 'сбежал' if 'fled' in a.conditions else 'готов к бою'} for k, a in state.npcs.items() if a.location == hero.location}
    pending = state.session_state.pending
    e = state.encounter
    # Enemy AC/HP, hidden DC, unrevealed object data and AI internals are absent.
    return {'campaign': state.campaign.name, 'ruleset': {'id': state.ruleset.id, 'name': state.ruleset.name},
            'world': {'name': state.world.name, 'description': state.world.description}, 'location': state.locations[hero.location],
            'party': state.party, 'characters': sheets, 'npcs': visible_npcs, 'controlled_actor': hero.id,
            'mode': state.session_state.mode, 'game_time': state.game_time, 'quests': state.quests,
            'knowledge': state.player_knowledge, 'objects': [{'id': k, 'name': o['name']} for k, o in state.dm_state.get('objects', {}).items() if o['location'] == hero.location],
            'pending': {k: v for k, v in pending.model_dump().items() if k in ('id', 'purpose', 'actor', 'expression', 'modifier', 'advantage', 'critical', 'ability', 'skill')} if pending else None,
            'encounter': {'order': e.order, 'initiative': e.initiative, 'round': e.round, 'current_actor': e.order[e.index], 'action': e.action, 'bonus_action': e.bonus_action, 'reaction': e.reaction.get(hero.id, False), 'movement': e.movement} if e else None}
