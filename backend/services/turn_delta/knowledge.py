"""Knowledge requires a sourced Fact → Event → Witness path, not geometry."""
from backend.services.world_delta_errors import SecondaryDeltaError


def apply_knowledge(world, records, events, channels):
    for index,k in enumerate(records):
        event=events.get(k['source_event_id'])
        if (event is None or k['actor_id'] not in event['witnesses'] or k['fact_id'] not in event['fact_ids'] or event['medium'] not in channels):
            raise SecondaryDeltaError('knowledge',index,'нет подтверждённого пути передачи знания',entity=k['actor_id']+':'+k['fact_id'],code='knowledge_path_invalid')
        world['knowledge'][k['actor_id']+':'+k['fact_id']]=k
