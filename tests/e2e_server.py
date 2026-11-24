"""Browser-only fixture server. Never imported by the production application."""
from hashlib import sha256
from canonical_fixture import canonical
import json
import re
import os
# Browser transport fixtures use deterministic structural retrieval, not an optional
# local embedding-model installation. Embedding behavior has dedicated unit tests.
os.environ["RPG_SEMANTIC_ENABLED"] = "0"
from pathlib import Path
import sys
import tempfile
import time
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine
import llm
import backend.runtime_v3.player_actions as extraction_versions
CURRENT_SCENE_VERSION = extraction_versions.EXTRACTION_VERSION
extraction_versions.EXTRACTION_VERSION = 5  # Historical browser replies are v5.
scene255_mode = False
scene264_gate = None
scene255_attempts = 0
provider_chat_stream = llm.chat_stream
import backend.services.preparation as preparation
from backend.api.app import create_app
from test_worlds import summary
from test_engine import result
from test_pov_documents import background, SECRET
import uvicorn

NARRATIVE = '''Персонаж 1 подвигает свободный стул. «Садись, поговорим».

За окном медленно гаснет вечерний свет. На кухне пахнет свежим кофе, и кто-то оставил на столе раскрытую книгу. Персонаж 2 убирает телефон в карман и смотрит на собравшихся.

— Ну что, — говорит он, чуть улыбаясь, — рассказывай. Мы ведь не просто так здесь собрались?

Он ставит перед тобой тёплую чашку и отодвигает сахарницу. В соседней комнате затихает музыка. Несколько секунд никто не торопит разговор — только чайник щёлкает, остывая у окна.
'''


def runtime_v3_request(messages):
    """Dispatch the fixture by schema, not by mutable prompt wording."""
    for message in messages:
        if message['content'].startswith('JSON Schema\n'):
            schema=json.loads(message['content'].split('\n',1)[1])
            return 'final_scene' in schema.get('properties', {})
    # Exact old prompt snapshots remain playable during regeneration tests.
    return any('RawTurnResult v3' in message['content'] for message in messages)


idea190_provider=None
editor173_control=None
creative172_control=None
review170_control=None
review_protocol_attempts={}
fragment_attempts={}
handoff_provider=None
phone_mode="silent"
group_semantic_fail_once=False
letter130_provider=None
npc_review_start_payload=None
story168_payload=None
story168_gate=None
agency249=None
berezovsk_followup=None
policy252_selection=None
integrated247_case=None
integrated247_live=False
integrated247_repeat=False
integrated247_extractions=0
provenance238_case=None
provenance238_repeat=False
provenance238_extractions=0
agency232_attempts=0
agency237_mode=False
agency237_extractions=0
birth231_response=None
due240_responses=None

def browser_response(payload, kwargs):
    from runtime_v3_fixture import reviewed
    raw = reviewed(payload)
    # Explicit v4 provenance for synthetic browser scenarios only. Original
    # recorded-provider replays and choice-negative controls bypass this adapter.
    if kwargs.get('model') not in ('integrated-test', 'berezovsk-followup-test'):
        source = next((json.loads(m['content'].split('\n',1)[1]) for m in kwargs['messages']
                       if m['content'].startswith('completed_narrative\n')), None)
        if source:
            for choice in raw.get('choices', []):
                choice.setdefault('grounding', dict(fact_ids=[], from_scene=True))
    return raw


def scripted_stream(**kwargs):
    global provenance238_extractions, integrated247_extractions
    global phone_mode, group_semantic_fail_once, npc_review_start_payload, story168_payload, agency232_attempts, birth231_response, due240_responses, agency237_extractions
    if policy252_selection and kwargs.get('model') == 'policy252-test':
        from test_policy252 import chronology_payload
        from test_acceptance254 import calendar_payload
        calendar_case = policy252_selection.get('calendar_case', False)
        if 'Исправь только хронологические' in str(kwargs['messages']):
            policy252_selection['corrected'] = True
            yield json.dumps(dict(edits=[dict(original=policy252_selection['correction_original'],replacement=policy252_selection['correction_replacement'])]),ensure_ascii=False)
        elif kwargs.get('response_format'):
            completed = next(m['content'] for m in kwargs['messages'] if m['content'].startswith('completed_narrative\n'))
            corrected = policy252_selection['correction_replacement'] in completed
            payload = (calendar_payload(app.state.repository, policy252_selection['save'], corrected=corrected) if calendar_case else
                       chronology_payload(app.state.repository, policy252_selection['save'],policy252_selection['event_id'],5 if corrected else 1))
            yield json.dumps(payload,ensure_ascii=False)
        else:
            yield policy252_selection['narrative'].replace(policy252_selection['correction_original'], policy252_selection['correction_replacement']) if policy252_selection.get('corrected') else policy252_selection['narrative']
        return
    if berezovsk_followup and kwargs.get('model') == 'berezovsk-followup-test':
        if kwargs.get('response_format'):
            answers = berezovsk_followup['responses']
            raw = answers[min(berezovsk_followup['attempt'], len(answers)-1)]
            berezovsk_followup['attempt'] += 1
            yield json.dumps(raw, ensure_ascii=False)
        else:
            yield berezovsk_followup['data']['narrative']
        return
    if kwargs.get('model') == 'lta250-test':
        yield '{}' if kwargs.get('response_format') else 'NPC занимается своим делом.'
        return
    if agency249 and kwargs.get('model') == 'agency249-test':
        from copy import deepcopy
        raw=deepcopy(agency249['raw'])
        if agency249['mode']=='missing':raw['player_agency'].pop('narrative_audit')
        if agency249['mode']=='invalid':raw['final_scene']['location_id']='unknown'
        if agency249['mode']=='uncertain':raw['player_agency']['status']='uncertain'
        yield json.dumps(raw,ensure_ascii=False) if kwargs.get('response_format') else agency249['narrative']
        return
    if integrated247_case and kwargs.get('model') == 'integrated-test':
        from test_integrated_repair247 import archived, corrected
        if integrated247_live:
            from test_live248_recovery import live as archived, control as corrected
        data = archived(integrated247_case)
        if kwargs.get('response_format'):
            integrated247_extractions += 1
            raw = data['responses'][0]['payload'] if integrated247_extractions == 1 or integrated247_repeat else corrected(data)
            if integrated247_live and integrated247_case=='family':raw=corrected(data)
            from copy import deepcopy
            raw=deepcopy(raw)
            review=raw.get('player_agency')
            if review:
                review['narrative_audit']=[dict(narrative_evidence=data['narrative'][:160],
                    classification='authorized',player_action_id=a['id']) for a in review['actions']]
                for action in review['actions']:action.setdefault('target_mode','interaction')
            yield json.dumps(raw, ensure_ascii=False)
        else:
            yield data['narrative']
        return
    if due240_responses is not None:
        from test_due_scene import SIGNS
        if kwargs.get('response_format'):
            raw = due240_responses.pop(0)
            if not due240_responses: due240_responses = None
            yield json.dumps(raw, ensure_ascii=False)
        else:
            yield SIGNS
        return
    if birth231_response is not None:
        narrative, raw = birth231_response
        if kwargs.get('response_format'):
            birth231_response = None
            yield json.dumps(raw, ensure_ascii=False)
        else:
            yield narrative
        return
    if idea190_provider is not None and idea190_provider.matches(kwargs):
        yield from idea190_provider.stream(kwargs);return
    if story168_payload is not None:
        from story_notifications_fixture import TEXT
        if kwargs.get('response_format'):
            if story168_gate is not None and not story168_gate.wait(30): raise RuntimeError('Story168 gate timed out')
            yield json.dumps(story168_payload,ensure_ascii=False)
            story168_payload=None
        else:
            yield TEXT
        return
    if npc_review_start_payload is not None:
        if kwargs.get('response_format') and runtime_v3_request(kwargs['messages']):
            yield json.dumps(npc_review_start_payload,ensure_ascii=False)
            npc_review_start_payload=None
            return
        if not kwargs.get('response_format'):
            yield 'Лада пришла и рассказала об открытой мастерской. Она обещала показать её герою. Следом вошёл Александр Константинович Волконский.'
            return
    if any('TEST_CONTACT_FREE_WORLD' in message['content'] for message in kwargs['messages']):
        phone_mode = 'silent'
    if phone_mode in ('group152', 'digital_style'):
        if group_semantic_fail_once and kwargs['messages'][0]['content'].startswith('Remote semantic extraction/'):
            group_semantic_fail_once=False
            raise RuntimeError('Deterministic group Extraction outage')
        if phone_mode == 'digital_style':
            from digital_style_provider import response
        else:
            from group152_provider import response
        yield response(kwargs['messages'], bool(kwargs.get('response_format')))
        return
    if phone_mode == 'letter130':
        from unittest.mock import MagicMock, patch
        client = MagicMock()
        client.chat.completions.create.side_effect = letter130_provider.create
        with patch('llm.OpenAI', return_value=client):
            yield from provider_chat_stream(**kwargs)
        if kwargs.get('response_format'):
            letter130_provider.artifacts=[]
            letter130_provider.rows=[]
        return
    if kwargs['messages'][0]['content'].startswith('Адресная коррекция творческого предложения'):
        payload=json.loads(kwargs['messages'][1]['content'])
        kwargs['on_usage']({'prompt_tokens':100,'completion_tokens':20})
        kwargs['on_finish']('stop')
        if payload['proposal']['changes'][-1].get('path')=='/sections/relationships':
            yield json.dumps(dict(proposal_hash=payload['proposal_hash'],patches=[],drop_indices=[15]))
        else:
            yield json.dumps(dict(proposal_hash=payload['proposal_hash'],patches=[dict(path='/changes/3/value/actor_id',value='craftswoman')],drop_indices=[]))
        return
    from backend.services.draft_editor import MARKER as EDITOR_MARKER
    if kwargs['messages'][0]['content'].startswith(EDITOR_MARKER):
        editor173_control['calls']+=1
        if not editor173_control['gate'].wait(45):raise RuntimeError('Editor gate timed out')
        kwargs['on_usage']({'prompt_tokens':100,'completion_tokens':40})
        kwargs['on_finish']('stop')
        if editor173_control.get('fail') and editor173_control['calls']==1:
            yield '';return
        from test_draft_creative import additions,change
        payload=json.loads(kwargs['messages'][1]['content'])
        state=payload['candidate'];instruction=json.loads(payload['author_context'])['current_instruction']
        if instruction in ('Создай сестру Ильи','Создай сестру Ильи — Олю'):
            filename='ilya_sister_olya.json' if instruction.endswith('Олю') else 'ilya_sister.json'
            fixture=json.loads((Path(__file__).parent/'fixtures/draft_editor'/filename).read_text())
            proposal=json.loads(fixture['reply']);proposal['candidate_hash']=payload['candidate_hash']
            yield json.dumps(proposal,ensure_ascii=False);return
        if instruction=='WORKSHOP188 пакет':
            changes=[change('/campaign/description','Новая редакция мира для следующего прохождения.','replace')]
        elif instruction=='DELETE184_LOCATION':
            changes=[change('/locations/1',state['locations'][1],'remove')]
        elif instruction=='DELETE184_HISTORY':
            index=next(i for i,c in enumerate(state['characters']) if c['id']=='archive184')
            changes=[change('/characters/'+str(index),state['characters'][index],'remove'),
                     change('/world/characters/archive184',state['world']['characters']['archive184'],'remove')]
        else:
            changes=additions(state)
            changes.append(change('/world/organizations/apex/name','Новая история организации','replace'))
        yield json.dumps(dict(candidate_hash=payload['candidate_hash'],rationale='Меняется только описание мира; начатая игра сохранена.' if instruction=='WORKSHOP188 пакет' else 'Вера возвращается в город. Её прошлое связано с мастерской и друзьями.',changes=changes),ensure_ascii=False)
        return
    if kwargs['messages'][0]['content'].startswith('Ты создаёшь полноценный живой RPG-мир') and 'EDITOR173' in kwargs['messages'][1]['content']:
        from test_initial_draft_v4 import rich
        yield json.dumps(rich(),ensure_ascii=False);return
    from draft_provider_fixture import CREATIVE_MARKER, creative_noop
    if kwargs["messages"][0]["content"].startswith(CREATIVE_MARKER):
        if creative172_control and 'CREATIVE172' in kwargs['messages'][1]['content']:
            creative172_control['calls']+=1
            if not creative172_control['gate'].wait(30):raise RuntimeError('Creative gate timed out')
            if creative172_control.get('http_error') and creative172_control['calls']==1:
                # Exercise real SDK error conversion before any stream/usage.
                from test_draft_creative_http import CreativeHTTP
                from unittest.mock import patch
                http=CreativeHTTP(('opaque refusal','messages'))
                with patch('llm.OpenAI',side_effect=http.client):
                    yield from provider_chat_stream(**kwargs)
                return
            kwargs['on_usage']({'prompt_tokens':100,'completion_tokens':20})
            kwargs['on_finish']('stop')
            if creative172_control['fail'] and creative172_control['calls']==1:
                yield '';return
            from test_draft_creative import additions
            payload=json.loads(kwargs['messages'][1]['content'])
            changes=additions(payload['candidate'])
            if creative172_control.get('invalid'):changes[3]['value']['actor_id']='missing'
            yield json.dumps(dict(candidate_hash=payload['candidate_hash'],rationale='Восстановление мастерской связывает персонажей.',changes=changes),ensure_ascii=False)
            return
        yield creative_noop(kwargs["messages"]);return
    if creative172_control and kwargs['messages'][0]['content'].startswith('Ты создаёшь полноценный живой RPG-мир') and 'CREATIVE172' in kwargs['messages'][1]['content']:
        from test_initial_draft_v4 import rich
        yield json.dumps(rich(),ensure_ascii=False);return
    from backend.services.draft_completeness import MARKER
    if kwargs['messages'][0]['content'].startswith(MARKER):
        request=json.loads(kwargs['messages'][1]['content'])
        source=request.get('author_context','')
        if review170_control and review170_control['source'] in source:
            assert kwargs['thinking']=='off'
            review170_control['calls']+=1
            if not review170_control['gate'].wait(30):raise RuntimeError('Test review gate timed out')
            failed=review170_control['fail'] and (not review170_control['transient'] or review170_control['calls']==1)
            truncated=failed and not review170_control['transient']
            kwargs['on_usage']({'prompt_tokens':24032,'completion_tokens':10,'completion_tokens_details':{'reasoning_tokens':10 if truncated else 0}})
            kwargs['on_finish']('length' if truncated else 'stop')
            yield '' if failed else '{"issues":[]}'
            return
        from draft_provider_fixture import protocol_review
        controlled=protocol_review(request)
        if controlled is not None:
            yield controlled;return
        yield '{"issues":[]}'
        return
    if kwargs['messages'][0]['content'].startswith('Remote semantic extraction/'):
        if phone_mode=='semantic_error_once':
            phone_mode='answer'
            raise RuntimeError('Controlled semantic outage')
        from phone_semantic_fixture import extract
        data=json.loads(kwargs['messages'][1]['content']);value=extract(data)
        if phone_mode=='agency_missing_once' and 'repair' not in data and value.get('scheduled_event_changes'):
            value['scheduled_event_changes'][0].pop('player_assertion')
        if phone_mode=='unknown_place' and value.get('scheduled_event_changes'):
            value['scheduled_event_changes'][0]['location_id']='missing-place'
        yield json.dumps(value,ensure_ascii=False);return
    full='\n'.join(m['content'] for m in kwargs['messages'])
    if handoff_provider is not None and 'ilya_cabinet' in full:
        from test_runtime_handoff import NARRATIVE as entry,provider_payload
        if kwargs.get('response_format'):
            handoff_provider['extractions']+=1
            raw=provider_payload(kwargs)
            raw['choices']=[dict(action='Ждать ответа',speech='')]
            scenario=handoff_provider.get('scenario','retry')
            if scenario=='doorway':
                raw['movements']=[]
                # The shared arrival control now includes its source Event.
                # This observed-only scene establishes no arrival at all.
                raw['events']=[]
                raw['final_scene'].update(present_character_ids=['ilya'],observed_character_ids=['viktoria_solovyova'])
            if scenario in ('retry','semantic-retry') and handoff_provider['extractions']<=2:
                raw['final_scene']['location_id']='unknown-room'
                if scenario=='semantic-retry':raw['life_changes']=[dict(id='viktoria_solovyova',life_status='dead')]
            if scenario=='optional-annotation':
                raw['events'].append(dict(id='greeting',text='Виктория приветствует Илью.',participants=['ilya','viktoria_solovyova'],witnesses=['ilya'],medium='conversation'))
                raw['scene_actions']=[dict(actor_id='viktoria_solovyova',target_ids=['ilya'],source_event_id='greeting',phase='start',modality='speech',knowledge_ids=['missing'])]
            yield json.dumps(raw,ensure_ascii=False)
        else:
            handoff_provider['narratives']+=1
            if handoff_provider.get('scenario')=='doorway':entry='Виктория стоит в проёме, не заходя.'
            elif handoff_provider.get('scenario') in ('entry','optional-annotation','semantic-retry'):entry='Виктория вошла внутрь и подошла к столу.'
            yield entry if handoff_provider['narratives']==1 else 'Виктория Соловьёва отвечает: «Скоро закончу».'
        return
    if kwargs['messages'][0]['content'].startswith('Один необязательный пакет') and 'TEST_RELEASE_QUALITY' in full:
        yield '{"patches":[],"preserved_unknown":null}';return
    observer='Тип хода: background' in full or 'Режим observer:' in full or 'mode=observer' in full
    if kwargs['messages'][0]['content'].startswith('Group communication reaction/'):
        # Same deterministic phone modes, new group wire contract. Do not fall
        # through to Narrative JSON: a silent reaction is a completed job.
        if phone_mode in ('silent','read_only','narrative138'):
            yield '{"messages":[]}';return
        from test_communication_cycle import decision
        yield decision(kwargs['messages'])
        return
    if kwargs['messages'][0]['content'].startswith('Select at most ONE optional grounded autonomous remote action.'):
        options=json.loads(kwargs['messages'][1]['content'])['options']
        if phone_mode in ('silent','narrative138') or not options:
            yield '{"action":null}';return
        time.sleep(0.15)
        o=options[0];action=o['actions'][0]
        if phone_mode=='read_only' and action=='send':
            yield '{"action":null}';return
        if phone_mode=='error_once' and action=='send':
            phone_mode='answer'
            raise RuntimeError('Deterministic phone provider outage')
        if phone_mode=='malformed_once':
            phone_mode='answer'
            yield '{"action":"answer"}';return
        if phone_mode=='decline' and action=='answer':action='decline'
        p=dict(actor_id=o['actor_id'],action=action,basis_ids=o['basis_ids'])
        if 'event_id' in o:p['event_id']=o['event_id']
        if action=='send':p.update(route_index=0,content='Да, договорились, в кафе «Липа».' if phone_mode=='new_place' else 'Да, договорились.' if phone_mode in ('meeting','unknown_place') else 'Привет. Ещё в офисе, разгребаю бумаги. А что, есть планы?' if phone_mode=='greeting' else 'Да, увидимся завтра. Напиши, когда освободишься.')
        if action=='identify':p.update(speaker_name='Дежурный оператор')
        yield json.dumps(dict(action=p),ensure_ascii=False)
        return
    current_message=next((m['content'] for m in kwargs['messages'] if m['content'].startswith('Текущее состояние / GM-only\n')),None)
    current_phone=json.loads(current_message.split('\n',1)[1]) if current_message else {}
    task_message=next((m['content'] for m in kwargs['messages'] if m['content'].startswith('Текущий ввод\n')),None)
    current_task=json.loads(task_message.split('\n',1)[1]) if task_message else {}
    quiet_start=(current_task.get('kind')=='start' and not observer
                 and current_phone.get('camera',{}).get('location_id') is not None
                 and len(current_phone['camera']['present_character_ids'])==1)
    if current_message and phone_mode == 'departure223':
        from copy import deepcopy
        case = json.loads((Path(__file__).parent / 'fixtures/movement/phone001.json').read_text())
        turn = next((m['content'] for m in kwargs['messages'] if m['content'].startswith('Текущий ввод\n')), None)
        if turn and json.loads(turn.split('\n', 1)[1]).get('player_input') == case['player_input']:
            raw = deepcopy(case['payload'])
            # Human-reviewed departure-only interpretation; the original
            # synthetic #223 negative payload on disk remains unchanged.
            raw['movements'] = [dict(actor_id='qa_timur',
                from_location_id=current_phone['camera']['location_id'],
                to_location_id=None, assertion='departure', source_event_id='departure',
                evidence='Тимур прощается и уходит.', order=0)]
            raw['events'][0]['order'] = 0
            # This synthetic browser provider emits the current protocol; the
            # historical fixture on disk remains unchanged.
            review = raw['player_agency']
            review['narrative_audit'] = [dict(narrative_evidence='Кирилл остаётся за столом с фотографиями.',
                classification='authorized', player_action_id=a['id']) for a in review['actions']]
            for action in review['actions']:action['target_mode'] = 'reference'
            for event in raw.get('events', []):
                event.pop('minute', None)  # Fixture clock differs from historical live job.
            yield json.dumps(raw, ensure_ascii=False) if kwargs.get('response_format') else case['narrative']
            return
    from pregnancy_boundary_fixture import REACTION, DELIVERY, delivery_claim
    if current_message and REACTION in full:
        turn = next((m['content'] for m in kwargs['messages'] if m['content'].startswith('Текущий ввод\n')), None)
        if turn and json.loads(turn.split('\n', 1)[1]).get('player_input') == REACTION:
            if kwargs.get('response_format'):
                process = next(p for p in current_phone['pregnancies'] if p['status'] == 'due')
                camera = current_phone['camera']
                yield json.dumps(dict(final_scene=dict(location_id=camera['location_id'],
                    present_character_ids=camera['present_character_ids'], elapsed_minutes=1),
                    **delivery_claim(process, camera)), ensure_ascii=False)
            else:
                yield DELIVERY
            return
    if current_phone.get('communication') and phone_mode=='narrative138':
        from narrative_phone138_fixture import response
        task=json.loads(next(m['content'].split('\n',1)[1] for m in kwargs['messages'] if m['content'].startswith('Текущий ввод\n')))
        value=response(current_phone,task,bool(kwargs.get('response_format')))
        yield json.dumps(value,ensure_ascii=False) if isinstance(value,dict) else value
        return
    if current_phone.get('communication'):
        camera=current_phone['camera']
        voice=current_phone['communication'].get('focus')=='call'
        # AI-editor fixtures reset the optional phone scenario between tests.
        if (phone_mode or '').startswith('office'):
            from call_continuity_fixture import response,BEFORE,AFTER,OFFER
            task=json.loads(next(m['content'].split('\n',1)[1] for m in kwargs['messages'] if m['content'].startswith('Текущий ввод\n')))
            if voice:
                value=response(current_phone,task['player_input'],'complete' if kwargs.get('response_format') else None)
                if isinstance(value,dict) and phone_mode=='office' and task['player_input']==OFFER:
                    value['choices'].extend([
                        dict(action='Уточнить место встречи',speech='Где встретимся?',interaction_channel='call',grounding=dict(fact_ids=[],from_scene=True)),
                        dict(action='Спросить кое-что лично',speech='',interaction_channel='call',grounding=dict(fact_ids=[],from_scene=True)),
                    ])
                if isinstance(value,dict) and phone_mode=='office-recovery':
                    value.pop('physical_projections',None)
                    value['choices']=[]
                if isinstance(value,dict) and phone_mode=='office-rejected' and value.get('events'):
                    value['events'][0]['participants']=['missing-actor']

            else:
                text=AFTER if 'Виктория' in camera.get('situation','') and 'ответ' in camera.get('situation','') else BEFORE
                value=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=0),choices=[dict(action='Посмотреть на часы',speech='')]) if kwargs.get('response_format') else text
                if phone_mode=='office-authority136':
                    doorway=task['player_input'] in ('Подождать у двери.','Продолжить после звонка.')
                    returning=current_phone['characters'].get('qa_marina',{}).get('location_id') != camera['location_id']
                    text=('Виктория вернулась к дому и отвечает Илье из проёма.' if returning else 'Виктория стоит в проёме и отвечает Илье, не заходя.') if doorway else 'Виктория вошла внутрь и отвечает Илье.'
                    present=[cid for cid in camera['present_character_ids'] if cid!='qa_marina']
                    if not doorway: present.append('qa_marina')
                    value=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=present,
                        observed_character_ids=['qa_marina'] if doorway else [],elapsed_minutes=0),
                        events=[dict(id='dialogue',text=text,participants=[camera['controlled_actor_id'],'qa_marina'],witnesses=[camera['controlled_actor_id']],medium='conversation')]) if kwargs.get('response_format') else text
                    if isinstance(value,dict) and returning:
                        from runtime_v3_fixture import arrival_sources
                        value['movements']=[dict(actor_id='qa_marina',to_location_id=camera['location_id'],evidence=text)]
                        arrival_sources(value)
            if isinstance(value,dict):yield json.dumps(value,ensure_ascii=False)
            else:
                for i in range(0,len(value),20):
                    yield value[i:i+20];time.sleep(0.05)
            return
        text='Вера отвечает по телефону: «Да, слышу тебя. Давай встретимся завтра».' if voice else 'В комнате тихо. За окном шелестят листья.'
        if kwargs.get('response_format'):
            events=[dict(id='phone-dialogue',text=text,evidence=text,participants=current_phone['communication']['participants'],witnesses=current_phone['communication']['participants'],medium='conversation',interaction_channel='call')] if voice else []
            yield json.dumps(dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=0),events=events,choices=[dict(action='Посмотреть в окно',speech='',interaction_channel='physical')]),ensure_ascii=False)
        else: yield text
        return
    from rejected_meeting_fixture import CONSENT, QUESTION, meeting_reply
    turn_input = next((m['content'] for m in kwargs['messages'] if m['content'].startswith('Текущий ввод\n')), '')
    action = json.loads(turn_input.split('\n', 1)[1]).get('player_input') if turn_input else None
    if provenance238_case:
        from test_action_provenance_repair import archived, corrected
        data = archived(provenance238_case)
        if action == data['player_input']:
            if kwargs.get('response_format'):
                provenance238_extractions += 1
                raw = data['responses']['extraction'] if provenance238_extractions == 1 or provenance238_repeat else corrected(data, provenance238_case)
                from copy import deepcopy
                raw=deepcopy(raw)
                review=raw['player_agency']
                review['narrative_audit']=[dict(narrative_evidence=data['narrative'][:160],
                    classification='authorized',player_action_id=a['id']) for a in review['actions']]
                for action in review['actions']:action.setdefault('target_mode','interaction')
                yield json.dumps(raw, ensure_ascii=False)
            else:
                yield data['narrative']
            return
    from test_player_action_targets import ACTION as AGENCY_ACTION, BAD_TEXT, ATTEMPT, payload as agency_payload, claim as agency_claim
    if action == AGENCY_ACTION:
        if agency237_mode:
            from test_player_action_completion import absent
            if not kwargs.get('response_format'):
                agency232_attempts += 1
                yield ATTEMPT
            else:
                agency237_extractions += 1
                raw = absent(current_phone, outcome='completed' if agency232_attempts == 1 else 'attempted')
                if agency237_extractions == 1:
                    raw['events'][0]['participants'].append('qa_vera')
                yield json.dumps(raw, ensure_ascii=False)
            return
        if not kwargs.get('response_format'):
            agency232_attempts += 1
            yield BAD_TEXT if agency232_attempts == 1 else ATTEMPT
        else:
            bad = agency232_attempts == 1
            raw = agency_payload(current_phone, [agency_claim(['qa_vera'], actual=['qa_marina'] if bad else ['qa_vera'],
                                  outcome='completed' if bad else 'attempted')], completed=bad)
            if bad:
                # This scripted prose really substitutes Marina for Vera. A mere
                # preserved-meaning target-set mismatch now permits repair (#251).
                raw['player_agency']['actions'][0]['meaning'] = 'changed'
            yield json.dumps(raw, ensure_ascii=False)
        return
    if action in (QUESTION, CONSENT):
        value = (json.dumps(meeting_reply(action, current_phone['camera']), ensure_ascii=False)
                 if kwargs.get('response_format') else meeting_reply(action))
    elif 'qa_meeting' in full:
        current=json.loads(next(m['content'] for m in kwargs['messages'] if m['content'].startswith('Текущее состояние / GM-only\n')).split('\n',1)[1])
        task=json.loads(next(m['content'] for m in kwargs['messages'] if m['content'].startswith('Текущий ввод\n')).split('\n',1)[1])
        depart=task['player_input']=='Разойтись.'
        alone='qa_vera' not in current['camera']['present_character_ids']
        text='Илья и Соня попрощались и разошлись.' if depart else 'Илья смотрит на улицу.' if alone else 'Илья и Соня встретились в «Гвозде» и поговорили.'
        if kwargs.get('response_format'):
            camera=current['camera']
            payload=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=['qa_kirill'] if depart else camera['present_character_ids'],elapsed_minutes=1),
                events=[dict(id='meeting',text=text,evidence=text,participants=['qa_kirill','qa_vera'] if not alone else ['qa_kirill'],witnesses=['qa_kirill','qa_vera'] if not alone else ['qa_kirill'],medium='conversation')],
                choices=[dict(action='Посмотреть вокруг',speech='',kind='decision',basis_ids=['qa_meeting']),dict(action='Осмотреться',speech='',kind='decision',basis_ids=['qa_meeting'])])
            if not alone:payload['scene_transitions']=[dict(source_event_id='meeting',phase='ended' if depart else 'started',actor_ids=['qa_kirill','qa_vera'],thread_ids=['qa_meeting'],evidence=text)]
            value=json.dumps(payload,ensure_ascii=False)
        else:value=text
    elif 'провести вечер вдвоём' in full and 'qa_vera' in full:
        current=json.loads(next(m['content'] for m in kwargs['messages'] if m['content'].startswith('Текущее состояние / GM-only\n')).split('\n',1)[1])
        task=json.loads(next(m['content'] for m in kwargs['messages'] if m['content'].startswith('Текущий ввод\n')).split('\n',1)[1])
        refused='Нет, сегодня не хочу.' in task['player_input']
        text='Вера кивает и заканчивает разговор: «Хорошо, тогда в другой раз».' if refused else 'Вера протягивает ладонь: «Побудем вечером вдвоём?» — и ждёт ответа.'
        if kwargs.get('response_format'):
            camera=current['camera'];external=camera['controlled_actor_id']
            payload=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=1),
                events=[dict(id='initiative',text=text,evidence=text,participants=['qa_vera','qa_kirill'],witnesses=camera['present_character_ids'],medium='conversation')],
                scene_actions=[dict(actor_id='qa_vera',target_ids=['qa_kirill'],source_event_id='initiative',phase='end' if refused else 'offer',modality='speech',adult=True,interruptible=not refused,response='player_supplied' if refused else 'open',player_evidence=task['player_input'] if refused else '',evidence=text)],
                choices=[dict(action='Отказаться',speech='Нет, сегодня не хочу.')])
            if refused:
                # A player refusal answers this invitation, not every open beat.
                pending=current.get('continuity', {}).get('pending_response_ids', [])
                assert len(pending)==1, pending
                payload['scene_actions'][0]['response_event_id']=pending[0]
            value=json.dumps(payload,ensure_ascii=False)
        else: value=text
    elif 'Ты редактор черновика Character' in full:
        task=json.loads(kwargs['messages'][-1]['content'])
        value='Новая сцена у двери.'
        if task['path']=='whole_draft':
            value=task['draft'];value['card']['name']='Сгенерированная героиня'
            value['character']['location_id']=task['context']['locations'][0]['id']
            value['starting_scene']='У входа в дом.'
        value=json.dumps({'value':value},ensure_ascii=False)
    elif 'TEST_CANDIDATE_RECOVERY' in full and 'patches' in kwargs['messages'][0]['content']:
        value='{"patches":[]}'
    elif 'Каноническая JSON Schema WorldState' in full:
        from test_draft_world import fixture
        candidate=fixture()
        if 'TEST_CONTACT_FREE_WORLD' in full:
            candidate['world'].pop('contacts',None)
            candidate['world']['communication']={'text_message':True,'voice_call':True,'presentation':'phone'}
        if 'TEST_MOTIVATION_OBJECTS' in full:
            from test_draft_motivations import motivated
            candidate,_=motivated()
        for card in candidate['characters']:
            for field,text in {'Характер':'Спокоен, внимателен к деталям.','Сильные стороны':'Помнит детали разговора.','Слабости':'Неохотно просит о помощи.','Биография':'Давно живёт в районе и знает соседей.','Внешность':'Короткие волосы, серая куртка.','Стиль общения':'Говорит короткими фразами, уточняет детали.','Привычки':'Записывает договорённости в блокнот.'}.items():
                if card.get('fields',{}).get(field,'').strip().lower() in ('','неизвестно','не указано','—'):card['fields'][field]=text
        if 'TEST_RELEASE_QUALITY' in full:candidate['characters'][1]['fields']['Внешность']='неизвестно'
        if 'TEST_CANDIDATE_RECOVERY' in full:candidate['protagonist_id']='missing'
        candidate['world'].pop('contacts',None)  # Model output omits legacy phonebook defaults.
        value=json.dumps(candidate,ensure_ascii=False)
        if 'TEST_FRAGMENT_RECOVERY' in full:
            key=kwargs['messages'][1]['content'];count=fragment_attempts.get(key,0);fragment_attempts[key]=count+1
            cut=value.index('"world":')+len('"world":')
            if count<2:
                from llm import OutputLimitReached
                yield value[:cut] if count==0 else 'INVALID CONTINUATION'
                if kwargs.get('on_finish'):kwargs['on_finish']('length')
                raise OutputLimitReached()
            value=value[cut:]
        if 'TEST_JSON_CONTINUATION' in full:
            cut=len(value)//2
            if not any(m['role']=='assistant' for m in kwargs['messages']):
                from llm import OutputLimitReached
                yield value[:cut]
                if kwargs.get('on_finish'):kwargs['on_finish']('length')
                raise OutputLimitReached()
            value=value[cut:]
    elif 'Ты редактор RPG' in full:
        payload=json.loads(kwargs['messages'][-1]['content'])
        if payload['instruction'].startswith('WORKSHOP188'):
            assert payload['entity']['id']==payload['card']['id']=='maxim'
            assert payload['current_value']==payload['card']['fields']['Внешность']
            edited={'unexpected':'not a literary value'} if 'invalid' in payload['instruction'] else payload['current_value'].replace('тёмной стрижкой','светлой стрижкой')
            value=json.dumps({'value':edited},ensure_ascii=False)
        else:value=json.dumps({'value':'Обновлённая внешность'},ensure_ascii=False)
    elif kwargs.get('response_format') and runtime_v3_request(kwargs['messages']):
        block=next(m['content'] for m in kwargs['messages'] if m['content'].startswith('Текущее состояние / GM-only'))
        state=json.loads(block.split('\n',1)[1]);camera=state['camera']
        observer=camera['mode']=='observer'
        task=json.loads(next(m['content'] for m in kwargs['messages'] if m['content'].startswith('Текущий ввод')).split('\n',1)[1])
        present=camera['present_character_ids']
        location_id=camera['location_id'];locations=[]
        # QA worlds have authored IDs/locations; generic character_1/2 belong
        # only to the original small transport fixture.
        if location_id is None and (task['kind']=='start' or observer) and 'qa_kirill' not in state['characters']:
            from backend.runtime_v3.models import identity
            place='Подвал' if observer else 'Кухня'
            location_id=identity('location',place.casefold())
            present=['character_3','character_4'] if observer and 'character_3' in present else present if observer else ['character_1','character_2']
            if location_id not in state['locations']:locations=[dict(id=location_id,name=place,evidence=SECRET if observer else NARRATIVE)]
        payload=dict(locations=locations,final_scene=dict(location_id=location_id,
            present_character_ids=present,situation='Тайная встреча.' if observer else 'Разговор на кухне.',elapsed_minutes=1),
            choices=[] if observer else [dict(action='Действие '+str(i),speech='Реплика '+str(i)) for i in range(6)])
        evidence=SECRET if observer else 'Садись, поговорим'
        fid='key_'+sha256(full.encode()).hexdigest()[:12]
        payload['events']=[dict(id='event',text='Передача ключа.' if observer else 'Собеседник предложил поговорить.',
            participants=present,witnesses=present,fact_ids=[fid] if observer else [],medium='conversation',evidence=evidence)]
        if observer:
            # SECRET explicitly authors the NPC arrivals before the key handover.
            # Supply their sources here, not in the generic protocol adapter.
            from runtime_v3_fixture import arrival_sources
            payload['movements']=[dict(actor_id=cid,to_location_id=location_id,evidence=SECRET)
                for cid in present if state['characters'][cid].get('location_id') != location_id]
            arrival_sources(payload)
            payload['facts']=[dict(id=fid,text='Тайный ключ передан.',character_ids=present,evidence=evidence)]
            payload['knowledge_gained']=[dict(actor_id=cid,fact_id=fid,source_event_id='event',evidence=evidence) for cid in present]
        if quiet_start:payload['events']=[]
        value=json.dumps(payload,ensure_ascii=False)
    elif kwargs.get('response_format'):
        payload=background() if observer else result()
        match=re.search(r'Единое время мира: (День \d+(?: \([А-Яа-я]+\))? \d{2}:\d{2})',full)
        if match and match[1]!='День 1 00:00':payload['scene']['time']=match[1]
        if 'pov' in kwargs['messages'][-1]['content'] or 'Режим observer:' in full:
            block=next(m['content'] for m in kwargs['messages'] if m['content'].startswith('Текущая сцена'))
            scene=json.loads(block.split('\n',1)[1]);payload['scene'].update(scene['scene_meta']);payload['scene']['text']=scene['scene']
            if 'Режим observer:' in full:
                payload['facts']=[];payload['events']=[];payload['relationships']=[]
        payload['events']=[e for e in payload.get('events',[]) if set(e['character_ids'])<=set(payload['scene']['present_ids'])]
        value=json.dumps(canonical(payload,sha256(full.encode()).hexdigest()[:12]),ensure_ascii=False)
    elif observer:
        value = SECRET
    elif quiet_start:
        value = 'Вокруг тихо. Пока ничего не происходит.'
    elif 'шаблон' in kwargs['messages'][-1]['content'].lower():
        value = summary()
    elif 'сценар' in kwargs['messages'][0]['content'].lower():
        value = '# Вечер в общем доме\n\nКомпания друзей собирается на кухне после долгого дня. Современная драмеди: живые разговоры, дружба и открытые линии.'
    else:
        value = NARRATIVE
    # Apply the protocol envelope before fragmenting the scripted JSON stream.
    if kwargs.get('response_format') and runtime_v3_request(kwargs['messages']):
        from runtime_v3_fixture import reviewed
        try:
            parsed = json.loads(value)
        except ValueError:
            pass  # Deliberately malformed/partial fixtures retain their transport.
        else:
            if isinstance(parsed, dict) and 'final_scene' in parsed:
                value = json.dumps(browser_response(parsed, kwargs), ensure_ascii=False)
    if kwargs.get('on_usage'):
        kwargs['on_usage']({'prompt_tokens':1000,'completion_tokens':100,'prompt_cache_hit_tokens':800})
    chunk_size=512 if 'Каноническая JSON Schema WorldState' in full else 60
    for i in range(0, len(value), chunk_size):
        time.sleep(.025)
        if kwargs.get('cancel_event') and kwargs['cancel_event'].is_set():
            raise RuntimeError('Генерация остановлена.')
        yield value[i:i+chunk_size]


def stream(**kwargs):
    global phone_mode
    if kwargs['messages'][0]['content'].startswith(('Dating search/1','Dating character/1','Public social activity/1')):
        from smartphone_provider import response
        if phone_mode in ('app_error_once', 'app_refresh_error_once'):
            time.sleep(2)
            phone_mode = 'app_refresh_slow' if phone_mode == 'app_refresh_error_once' else 'silent'
            raise RuntimeError('Тестовый провайдер прервал ответ.')
        time.sleep(2 if phone_mode == 'app_refresh_slow' else .2)
        yield json.dumps(response(kwargs['messages']),ensure_ascii=False)
        return
    global scene255_attempts
    if kwargs.get('model') == 'blank263-test':
        from backend.services.provider_attempt import identity
        yield '  \n  ' if identity()['stage'] == 'narrative' else '{}'
        return
    if kwargs.get('model') == 'frame263-test':
        from backend.services.provider_attempt import identity
        if identity()['stage'] == 'narrative':
            actions = ['Открыть альбом','Выйти во двор','Позвать хозяйку','Заварить чай','Осмотреть окно','Послушать радио']
            rows = [dict(text=t, speech=None, facts=[]) for t in actions]
            rows[2]['speech'] = 'Анна, можно взглянуть на альбом?'
            yield json.dumps(dict(scene='У окна лежит альбом.', actions=rows), ensure_ascii=False)
        else:
            if identity()['stage'] == 'extraction' and scene264_gate is not None:
                if not scene264_gate.wait(30):
                    raise RuntimeError('Scene interpretation fixture timed out')
            yield '{}'
        return
    if kwargs.get('model') == 'scene263-test':
        conflict = 'Кирилл отказывается от чая.'
        if kwargs.get('response_format'):
            prose = next(json.loads(m['content'].split('\n',1)[1]) for m in kwargs['messages'] if m['content'].startswith('completed_narrative\n'))
            result = dict(scene=dict(elapsed_minutes=1),scene_steps=[],choices=[
                dict(index=i,grounding=dict(fact_ids=[],from_scene=True)) for i in range(4)])
            result['choices'].append(dict(index=4,grounding=dict(fact_ids=['private-missing'],from_scene=False)))
            if conflict in prose:
                result['scene_steps'] = [dict(kind='movement', actor_ids=['missing-actor'], endpoint='missing-place')]
                result['agency_findings'] = [dict(classification='unauthorized_choice',narrative_evidence=conflict)]
            yield json.dumps(result)
        else:
            body = '**В альбоме** лежат старые снимки.\n\n---\n\n' + ('За окном шумит дождь. ' * 65) + conflict
            yield body
            time.sleep(.35)
            yield '\n<action_sug'
            time.sleep(.25)
            yield 'gestions>["Рассмотреть альбом","Спросить о дожде","Налить воды","Подойти к окну","Чужой секрет"]'
        return
    if scene255_mode and kwargs.get('model')=='scene255-test':
        if not kwargs.get('response_format'):
            yield 'Кирилл попрощался и дошёл до парка.'
            return
        scene255_attempts += 1
        current=json.loads(next(m['content'].split('\n',1)[1] for m in kwargs['messages'] if m['content'].startswith('Текущее состояние / GM-only\n')))
        schema=json.loads(next(m['content'].split('\n',1)[1] for m in kwargs['messages'] if m['content'].startswith('JSON Schema\n')))
        actor=current['camera']['controlled_actor_id']
        step=dict(id='walk',kind='movement',actor_id=actor,text='Дошёл до парка.',assertion='completed_arrival',endpoint='park255',input_source=dict(quote='несуществующий ввод' if scene255_attempts<=2 else 'Иду в парк.',meaning='preserved'))
        if extraction_versions.EXTRACTION_VERSION >= 7:
            step['actor_ids']=[step.pop('actor_id')]
        if 'candidate_hash' in schema['properties']:
            reply=dict(candidate_hash=schema['properties']['candidate_hash']['const'],replacements=[step],sections={},reason='Повторная ошибочная интерпретация в authored negative control.')
        else:
            reply=dict(scene=dict(elapsed_minutes=1),scene_steps=[step],locations=[dict(id='park255',name='Парк',evidence='')])
        yield ('```json\n'+json.dumps(reply)+'\n```') if extraction_versions.EXTRACTION_VERSION>=8 else json.dumps(reply)
        return
    # Upgrade old scripted provider fixtures to the mandatory #232 review envelope.
    # Preserve malformed/partial transport output and explicit negative reviews.
    from runtime_v3_fixture import reviewed
    for chunk in scripted_stream(**kwargs):
        if kwargs.get('response_format') and runtime_v3_request(kwargs['messages']):
            try:
                value = json.loads(chunk)
            except (ValueError, TypeError):
                pass
            else:
                if isinstance(value, dict) and 'final_scene' in value:
                    chunk = json.dumps(browser_response(value, kwargs), ensure_ascii=False)
        yield chunk


engine.chat_stream = stream
hold_next_preparation = False

def preparation_stream(**kwargs):
    global hold_next_preparation
    if len(kwargs['messages'])==2 and '"calendar_evidence":' in kwargs['messages'][1]['content']:
        from review_actions_fixture import reply
        kwargs['on_usage']({'prompt_tokens':120,'completion_tokens':60})
        kwargs['on_finish']('stop')
        yield reply(kwargs['messages'])
        return
    hold = hold_next_preparation
    hold_next_preparation = False
    for chunk in stream(**kwargs):
        yield chunk
        if hold:
            # Browser reconnection must observe an in-flight generation, independent
            # of device speed. Only the cancellation test enables this one-shot gate.
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                if kwargs.get('cancel_event') and kwargs['cancel_event'].is_set():
                    raise RuntimeError('Генерация остановлена.')
                time.sleep(.05)
            hold=False

preparation.chat_stream = preparation_stream

# This scenario exercises persisted pre-v6 quality semantics explicitly.
from backend.services import draft_generation
_generation_run = draft_generation.run
def generation_fixture(prep, jid, config, *args):
    source=str(config.get('_draft_source',config.get('_draft_input','')))
    if any(marker in source for marker in ('TEST_RELEASE_QUALITY','TEST_REVIEW_PROTOCOL','TEST_REVIEW_AUTOMATIC','TEST_RELEASE_NESTED')):
        journal = json.loads(prep.repo.preparation_job(jid).get('response_journal') or '{}')
        journal.setdefault('generation_contract', {'version':5} if 'TEST_RELEASE_QUALITY' in source else {'version':6,'portrait_version':2})
        prep.repo.save_response_journal(jid, journal)
    return _generation_run(prep, jid, config, *args)
draft_generation.run = generation_fixture

chat_cancel_next = False
chat_markdown_release = threading.Event()
CHAT_MARKDOWN = '''Лена ставит чашку на стол. За окном шумит дождь. «Кто-то стучал», — говорит она.

---

### Варианты действий

1. **Спросить Лену:** «Ты ждёшь гостей?»
2. **Осмотреть дверь:** проверить замок, не открывая.
3. **Позвать гостя:** «Кто там?»
4. **Подождать:** остаться у стола.

**Свободный ввод:** свой вариант.

---

### Текущая сцена

**Время:** 9 октября, точное время не установлено.

**Место:** комната у маяка.

**Рядом:** Лена, чашка, закрытая дверь; за окном дождь.
'''

def authoring_stream(**kwargs):
    global chat_cancel_next
    if kwargs['messages'][0]['content'].startswith('Выбирай графику по открытой внешности'):
        cards=json.loads(kwargs['messages'][1]['content'])['cards']
        yield json.dumps(dict(version=3,characters={cid:dict(hair='bun',clothing='blouse') for cid,card in cards.items()
                                            if card['description']!='QA_SKIP_PORTRAIT'}))
        kwargs['on_usage'](dict(prompt_tokens=400,completion_tokens=82,prompt_cache_hit_tokens=0))
        kwargs['on_finish']('stop')
        return
    if kwargs.get('model') in ('chat-tools-fixture','chat-tools-summary-fixture'):
        from chat_tools_fixture import memory
        if 'первоначальную авторскую выжимку' in kwargs['messages'][0]['content']:
            text=memory()
        elif kwargs['model']=='chat-tools-summary-fixture':
            text=kwargs['messages'][1]['content'].split('\n',1)[1].replace('· Обязательства / обещания: вернуть книгу.','· Обязательства / обещания: книга возвращена.')
            text+='\nАвторская запись: Лена закрыла дверь. Причина не установлена.\n'
        else:
            text=NARRATIVE*2+'\n\n'+CHAT_MARKDOWN
        kwargs['on_usage']({'prompt_tokens':420,'completion_tokens':180,'prompt_cache_hit_tokens':80})
        for offset in range(0,len(text),90):
            if kwargs['cancel_event'].is_set(): raise RuntimeError('stopped')
            yield text[offset:offset+90];time.sleep(.02)
        kwargs['on_finish']('stop');return
    if kwargs.get('model') == 'chat-markdown-fixture':
        # Hold the external stream after Markdown has arrived, so the browser can
        # assert formatting before the job completes and /markdown is requested.
        chat_markdown_release.clear()
        kwargs['on_usage']({'prompt_tokens':321,'completion_tokens':120,'prompt_cache_hit_tokens':80})
        for offset in range(0,len(CHAT_MARKDOWN),37):
            if kwargs['cancel_event'].is_set(): raise RuntimeError('stopped')
            yield CHAT_MARKDOWN[offset:offset+37]
            time.sleep(.025)
        if not chat_markdown_release.wait(30): raise RuntimeError('fixture: expected Markdown stream release')
        kwargs['on_finish']('stop')
        return
    if kwargs.get('model') in ('chat-fixture', 'chat-summary-fixture', 'chat-mobile-fixture'):
        # Chat production service/context/API/SQLite; substitute external provider IO only.
        from backend.chat.context import TEMPLATE
        text = (TEMPLATE + '\n12 мая 2010 — рождение Лены. Тайну знает только Лена. Обещание выполнено.\nНезавершённый разговор: «Ты хотел сказать…»') if kwargs['model']=='chat-summary-fixture' or 'первоначальную авторскую выжимку' in kwargs['messages'][0]['content'] else ('— Ты хотел сказать? — Лена ставит чашку на стол.\n\n'+NARRATIVE)*3
        if kwargs['model']=='chat-mobile-fixture' and 'первоначальную авторскую выжимку' not in kwargs['messages'][0]['content']:
            text = NARRATIVE*6+'\n\n'+CHAT_MARKDOWN
        kwargs['on_usage']({'prompt_tokens':321,'completion_tokens':120,'prompt_cache_hit_tokens':80})
        if chat_cancel_next:
            chat_cancel_next = False
            yield 'Лена ставит чашку. Незавершённый ответ…'
            if not kwargs['cancel_event'].wait(30): raise RuntimeError('fixture: expected explicit cancellation')
            raise RuntimeError('stopped')
        for offset in range(0,len(text),80):
            if kwargs['cancel_event'].is_set(): raise RuntimeError('stopped')
            yield text[offset:offset+80]
            time.sleep(.025)
        kwargs['on_finish']('stop')
        return
    if kwargs["messages"][0]["content"].startswith("Ты дополняешь предложенную карточку"):
        yield json.dumps({"value":"Выросла у моря. Работала в мастерской, затем открыла своё дело."},ensure_ascii=False)
        return
    yield from stream(**kwargs)

llm.chat_stream = authoring_stream
llm.get_available_models = lambda: ['local-model','chat-fixture','chat-summary-fixture','chat-markdown-fixture','chat-mobile-fixture','chat-tools-fixture','chat-tools-summary-fixture']
# Exercise the same loaded-instance discovery for Chat, game jobs and authoring.
# Values are fixture allocations, shared by metadata and the local transport.
fixture_windows = {
    'local-model': 32768, 'test': 32768, 'test-model': 32768,
    'handoff-test': 131072, 'provenance-test': 40960, 'integrated-test': 49152,
    'agency249-test': 49152, 'berezovsk-followup-test': 131072, 'scene255-test': 65536,
    'lta250-test': 49152, 'policy252-test': 65536, 'scene263-test': 65536,
    'frame263-test': 65536, 'blank263-test': 65536,
    'chat-fixture': 65536, 'chat-summary-fixture': 65536, 'chat-small-fixture': 8192,
    'chat-markdown-fixture': 65536, 'chat-mobile-fixture': 65536,
    'chat-tools-fixture': 524288, 'chat-tools-summary-fixture': 524288,
}
llm.get_models_info = lambda: {'models': [
    {'key': name, 'loaded_instances': [{'id': name, 'config': {'context_length': window}}]}
    for name, window in fixture_windows.items()
]}
llm.get_deepseek_models = lambda _: ['deepseek-flash','deepseek-v4-pro']
llm.load_model = lambda **_: {}
llm.unload_all_models = lambda: 1

if __name__ == '__main__':
    path = os.getenv('E2E_DB_PATH') or str(Path(tempfile.mkdtemp())/'e2e.sqlite3')
    app = create_app(path)
    # Approved prototype snapshot is test-only. No simulator is mounted in production.
    import zipfile
    from starlette.staticfiles import StaticFiles
    from starlette.routing import Mount
    reference_dir=Path(tempfile.mkdtemp(prefix='idea190-reference-'))
    with zipfile.ZipFile(Path(__file__).parent/'fixtures/idea190-reference.zip') as archive:
        archive.extractall(reference_dir)
    import shutil
    shutil.copyfile(Path(__file__).parents[1]/'frontend/src/assets/idea-folio.webp',reference_dir/'folio.webp')
    app.router.routes.insert(0, Mount('/test/idea190/reference',app=StaticFiles(directory=reference_dir)))
    workshop_reference_dir=Path(tempfile.mkdtemp(prefix='workshop175-reference-'))
    with zipfile.ZipFile(Path(__file__).parent/'fixtures/workshop175-reference.zip') as archive:
        import hashlib
        reference=archive.read('world-workshop.html')
        assert hashlib.sha256(reference).hexdigest()=='4122bcf37cbfd4c979e264e655896cc8d8783d51899a2aa9d170bd9f5c3e82e1'
        (workshop_reference_dir/'world-workshop.html').write_bytes(reference)
    app.router.routes.insert(0, Mount('/test/workshop175/reference',app=StaticFiles(directory=workshop_reference_dir)))
    @app.post('/test/review-actions')
    def review_actions_seed(scenario: str = ''):
        from review_actions_fixture import seed, seed_family, seed_legacy_family
        if scenario=='legacy-family':
            return seed_legacy_family(app.state.repository)
        if scenario in ('family','direct-family'):
            return seed_family(app.state.repository,scenario=scenario)
        return seed(app.state.repository,scenario)

    @app.post('/test/generation266')
    def generation266_seed():
        from generation266_fixture import seed
        return seed(app.state.repository)

    @app.post('/test/scene255-reset')
    def scene255_reset():
        global scene255_mode
        scene255_mode=False
        extraction_versions.EXTRACTION_VERSION=5
        return {'ok':True}

    @app.post('/test/scene255-seed')
    def scene255_seed():
        global scene255_mode, scene255_attempts
        from test_integrated_repair247 import seed, archived
        extraction_versions.EXTRACTION_VERSION=5
        scene255_mode=False
        result=seed(app.state.repository,archived('knowledge'))
        extraction_versions.EXTRACTION_VERSION=6
        scene255_mode=True;scene255_attempts=0
        return result

    @app.post('/test/scene256-seed')
    def scene256_seed():
        result=scene255_seed()
        extraction_versions.EXTRACTION_VERSION=7
        return result

    @app.post('/test/scene263-seed')
    def scene263_seed(delay_interpretation: bool = False):
        global scene264_gate
        from threading import Event
        scene264_gate = Event() if delay_interpretation else None
        result = scene255_seed()
        extraction_versions.EXTRACTION_VERSION = CURRENT_SCENE_VERSION
        return result

    @app.post('/test/scene264-release')
    def scene264_release():
        scene264_gate.set()
        return {'ok': True}

    @app.post('/test/scene258-seed')
    def scene258_seed():
        result=scene255_seed()
        extraction_versions.EXTRACTION_VERSION=8
        return result

    @app.post('/test/editor173')
    def seed_editor173(body:dict):
        global editor173_control,phone_mode,creative172_control
        from threading import Event
        phone_mode=None;creative172_control=None
        editor173_control=dict(gate=Event(),calls=0,fail=body.get('fail',False))
        return app.state.repository.create_workspace('AI-редактор')

    @app.post('/test/editor173/release')
    def release_editor173():
        editor173_control['gate'].set()
        return dict(calls=editor173_control['calls'])

    @app.post('/test/creative185-rejected')
    def seed_creative185_rejected():
        from fastapi.testclient import TestClient
        from creative185_fixture import seed_rejected
        return seed_rejected(TestClient(app))

    @app.post('/test/idea190')
    def configure_idea190(body:dict):
        global idea190_provider
        from idea190_provider import IdeaProvider
        idea190_provider=IdeaProvider(body.get('fail_review',False),body.get('custom_calendar',False),transport_stream=provider_chat_stream)
        if body.get('release'):idea190_provider.gate.set()
        if body.get('scenario'):
            repo=app.state.repository
            workspace=repo.create_workspace('Сценарий Валлора')
            with repo.connect() as db:
                db.execute('UPDATE preparation_workspaces SET idea=? WHERE id=?',('ATELIER190. Сохранённый сценарий о друзьях.',workspace['id']))
            return workspace
        return {'ready':True}

    @app.post('/test/idea190/release')
    def release_idea190():
        idea190_provider.gate.set()
        return {'world_calls':idea190_provider.world_calls,'review_calls':idea190_provider.review_calls}

    @app.post('/test/creative172')
    def seed_creative172(body:dict):
        global creative172_control, phone_mode
        from threading import Event
        phone_mode=None
        creative172_control=dict(gate=Event(),calls=0,fail=body.get('fail',False),invalid=body.get('invalid',False),http_error=body.get('http_error',False))
        return app.state.repository.create_workspace('Творческое развитие')

    @app.post('/test/creative172/saves/{sid}/canonical')
    def creative172_canonical(sid:int):
        # Test-only read from a reopened repository, never a production API.
        # POST follows fixture routes; the production SPA owns GET fallbacks.
        from backend.repositories.preparation import Repository
        from backend.runtime_v3.repository import read_history
        repo=Repository(app.state.repository.path)
        snapshot=repo.get_snapshot(sid)
        with repo.connect() as db:
            history,warnings=read_history(db,snapshot.get('history_head'))
        return dict(world_state=snapshot['world_state'],events=history['events'],warnings=warnings)

    @app.post('/test/creative172/release')
    def release_creative172():
        creative172_control['gate'].set()
        return dict(calls=creative172_control['calls'])

    @app.post('/test/review170')
    def seed_review170(body:dict):
        global review170_control, phone_mode
        phone_mode='silent'
        from threading import Event
        from review170_fixture import restore,exported
        wid,jid=restore(app.state.repository)
        review170_control=dict(source=exported()['author_input']['source_text'],gate=Event(),fail=body.get('fail',False),transient=body.get('transient',False),calls=0)
        return dict(workspace=wid,job=jid)

    @app.post('/test/review170/release')
    def release_review170():
        review170_control['gate'].set()
        return dict(calls=review170_control['calls'])

    @app.post('/test/runtime-handoff-provider')
    def runtime_handoff_provider(enabled: bool=True, scenario: str="retry"):
        global handoff_provider
        previous=handoff_provider
        handoff_provider={'narratives':0,'extractions':0,'scenario':scenario} if enabled else None
        return previous or {}

    @app.post('/test/calendar-policy-e5')
    def calendar_policy_e5():
        from test_calendar_start_policy import evidence
        from test_api import REMOTE
        j=evidence();s=j['candidate_snapshot'];repo=app.state.repository
        w=repo.create_workspace('E5 calendar policy')
        jid=repo.begin_preparation(w['id'],'draft_world',j['author_input']['text'],dict(REMOTE,_draft_task='world',_draft_input=j['author_input']['text']),0)
        journal={k:v for k,v in j.items() if k not in ('requests','recovery','binding','candidate_snapshot','candidate_version','current_diagnostics','current_start_block_reason','author_input')}
        journal.update(recovery_epoch=0,candidate_text=json.dumps(s,ensure_ascii=False))
        repo.save_response_journal(jid,journal)
        repo.save_draft_candidate(jid,s,[],review=j['recovery']['review'])
        repo.preparation_progress(jid,'','stopped')
        return {'id':w['id']}

    @app.post('/test/hold-preparation')
    def hold_preparation():
        global hold_next_preparation
        hold_next_preparation=True
        return {'held':True}

    @app.post('/test/appearance-seed')
    def appearance_seed():
        from devtools.narrative_test_world import load_fixture
        result=load_fixture(app.state.repository,'appearance')
        return {'world':result['world'],'save':result['save']}

    @app.post('/test/long-term-seed')
    def long_term_seed(pregnancy: bool = False):
        from devtools.narrative_test_world import load_fixture
        result=load_fixture(app.state.repository,'pregnancy' if pregnancy else 'long-term')
        return {'world':result['world'],'save':result['save']}

    @app.post('/test/newborn-seed')
    def newborn_seed():
        from devtools.narrative_test_world import load_fixture
        result=load_fixture(app.state.repository,'newborn-twins')
        return {'world':result['world'],'save':result['save']}

    @app.post('/test/choices-seed')
    def choices_seed():
        from devtools.narrative_test_world import load_fixture
        result=load_fixture(app.state.repository,'choices')
        return {'world':result['world'],'save':result['save']}

    @app.post('/test/continuity-seed')
    def continuity_seed():
        from devtools.narrative_test_world import load_fixture
        from test_narrative_test_world import CONFIG
        result=load_fixture(app.state.repository,'continuity')
        job=app.state.repository.begin_job(result['save'],'','start',CONFIG)
        engine.run_job(app.state.repository.path,job,engine.Worker())
        assert app.state.repository.get_job(job)['status']=='saved'
        return {'world':result['world'],'save':result['save']}

    @app.post('/test/letter130-seed')
    def letter130_seed():
        global phone_mode, letter130_provider
        phone_mode='letter130'
        from test_historical_correspondence130 import HTTPProvider
        from devtools.narrative_test_world import load_fixture
        letter130_provider=HTTPProvider()
        letter130_provider.delay=0.05
        repo=app.state.repository
        seed=load_fixture(repo,'phone')
        with repo.connect() as db:
            snap=json.loads(db.execute('SELECT state_json FROM saves WHERE id=?',(seed['save'],)).fetchone()[0])
            snap['world_state']['meta']['communication'].update(letter=True,delivery_minutes={'letter':10})
            db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snap),seed['save']))
        return {'world':seed['world'],'save':seed['save']}

    @app.post('/test/letter130-arm')
    def letter130_arm(size: int = 0):
        from test_historical_correspondence130 import artifact, extracted, long_letter
        import threading
        letter130_provider.finish_gate=threading.Event()
        a=artifact('qa_vera','qa_kirill')
        if size:
            a['content']=long_letter(size)
            letter130_provider.chunk_size=1000
            letter130_provider.delay=0.01
        letter130_provider.artifacts=[a]
        letter130_provider.rows=[extracted(a)]
        return {'ready':True, 'content':a['content']}

    @app.post('/test/letter130-release')
    def letter130_release():
        letter130_provider.finish_gate.set()
        return {'ready':True}

    @app.post('/test/letter130-reset')
    def letter130_reset():
        global phone_mode, letter130_provider
        if letter130_provider and letter130_provider.finish_gate:
            letter130_provider.finish_gate.set()
        phone_mode='silent'
        letter130_provider=None
        return {'ready':True}

    @app.post('/test/group152-seed')
    def group152_seed(fail_semantic: bool = False, digital_style: bool = False):
        global phone_mode, group_semantic_fail_once
        phone_mode='digital_style' if digital_style else 'group152'
        group_semantic_fail_once=fail_semantic
        from devtools.narrative_test_world import load_fixture
        seed=load_fixture(app.state.repository,'phone')
        return {'world':seed['world'],'save':seed['save']}

    @app.post('/test/narrative-phone138-seed')
    def narrative_phone138_seed():
        global phone_mode
        phone_mode='narrative138'
        from devtools.narrative_test_world import load_fixture
        seed=load_fixture(app.state.repository,'phone-office')
        return {'world':seed['world'],'save':seed['save']}

    @app.post('/test/phone-seed')
    def phone_seed(smartphone: bool = False, unread: bool = False, incoming: bool = True, decision: str = "silent", polish: bool = False, hidden: bool = False, strangers: bool = False, legacy_portraits: bool = False):
        global phone_mode
        phone_mode=decision
        from devtools.narrative_test_world import load_fixture
        from test_narrative_test_world import CONFIG
        from backend.runtime_v3.remote import apply
        from backend.runtime_v3.repository import append_history
        result=load_fixture(app.state.repository,'phone-office' if decision.startswith('office') else 'ui-portrait-polish' if polish else 'phone')
        repo=app.state.repository;sid=result['save']
        job=repo.begin_job(sid,'','start',CONFIG)
        engine.run_job(repo.path,job,engine.Worker())
        assert repo.get_job(job)['status']=='saved', repo.get_job(job)['error']
        snap=repo.get_snapshot(sid)
        from backend.runtime_v3.models import WorldHistoryV3
        batch=WorldHistoryV3().to_dict()
        if smartphone:
            snap['world_state']['meta']['communication'].update(social=True,dating=True)
        if legacy_portraits:
            # Explicit pre-175 save fixture: preserve coverage of the old fallback.
            for actor in snap['world_state']['characters'].values():
                actor.pop('procedural_portrait', None)
                actor.pop('portrait_mode', None)
        if strangers:
            snap['world_state']['contacts'] = {}
        if polish:
            if hidden:
                for contact in snap['world_state']['contacts'].values():
                    if contact['owner_id']=='qa_kirill' and contact['character_id']=='qa_timur':
                        contact['identity_visible']=False
            for index, (author, extra) in enumerate([
                ('qa_kirill', {'contact_id':'phone-qa_kirill-qa-vera'}),
                ('qa_vera', {'contact_id':'phone-qa_vera-qa-kirill'}),
                *[(a, {'conversation_id':'qa-group'}) for a in ('qa_kirill','qa_vera','qa_timur')],
            ]):
                snap, message_batch = apply(snap, dict(action='send', operation_id=f'polish-{index}',
                    content=f'Сообщение {index + 1}: встречаемся у архива.', **extra), actor_id=author, autonomous=author!='qa_kirill')
                for section, rows in message_batch.items():
                    batch.setdefault(section, []).extend(rows)
        if incoming:
            snap,batch=apply(snap,dict(action='call',operation_id='qa-incoming-call',contact_id='phone-qa_vera-qa-kirill'),actor_id='qa_vera',autonomous=True)
        if unread:
            snap, message_batch = apply(snap, dict(action='send', operation_id='qa-incoming-message', contact_id='phone-qa_vera-qa-kirill', content='Прочти, когда будет удобно.'), actor_id='qa_vera', autonomous=True)
            for section, rows in message_batch.items():
                batch.setdefault(section, []).extend(rows)
        with repo.connect() as db:
            snap['history_head']=append_history(db,snap.get('history_head'),batch)
            db.execute('UPDATE saves SET state_json=?,revision=revision+1 WHERE id=?',(json.dumps(snap,ensure_ascii=False),sid))
        return {'world':result['world'],'save':sid}

    @app.post('/test/dossier-authoring')
    def dossier_authoring():
        from devtools.narrative_test_world import build_fixture
        return build_fixture('ui-canonical-personal')

    @app.post('/test/secret183-candidate/{wid}')
    def secret183_candidate(wid: str, semantic: bool = False):
        from secret183_fixture import stage
        stage(app.state.repository, wid, semantic)
        return {'ok': True}

    @app.post('/test/secret181-candidate/{wid}')
    def secret181_candidate(wid: str):
        from secret_handoff181_fixture import stage
        stage(app.state.repository, wid, own=True)
        return {'ready': True}

    @app.post('/test/secret181-prepare/{sid}')
    def secret181_prepare(sid: int, reveal: bool = True):
        global story168_payload
        from secret_handoff181_fixture import payload
        story168_payload = payload(app.state.repository.get_snapshot(sid), reveal)
        return {'ready': True}

    @app.post('/test/story168-seed')
    def story168_seed():
        from story_notifications_fixture import seed
        return seed(app.state.repository)

    @app.post('/test/story168-prepare/{sid}')
    def story168_prepare(sid: int, delayed: bool = False, reveal: bool = True, target_turn_id: int | None = None):
        global story168_payload, story168_gate
        from threading import Event
        story168_gate = Event() if delayed else None
        from story_notifications_fixture import payload
        snap=app.state.repository.get_snapshot(sid)
        if target_turn_id is not None:
            with app.state.repository.connect() as db:
                snap=json.loads(db.execute('SELECT before_json FROM turns WHERE id=? AND save_id=?',(target_turn_id,sid)).fetchone()[0])
        story168_payload=payload(snap,reveal)
        return {'ready': True}

    @app.post('/test/story168-release')
    def story168_release():
        if story168_gate is not None: story168_gate.set()
        return {'released': True}

    @app.post('/test/story-secrets178-seed')
    def story_secrets178_seed():
        from story_secrets_fixture import seed
        return seed(app.state.repository)

    @app.post('/test/ui-completion-seed')
    def ui_completion_seed(checkpoint: str = 'ui-calendar'):
        from devtools.narrative_test_world import load_fixture
        from test_narrative_test_world import ordinary_job
        if checkpoint not in ('ui-calendar','ui-calendar-custom','ui-family','ui-family-dense','ui-public-directory','ui-dossier','ui-inspector','ui-personal'):
            raise ValueError('Unknown UI checkpoint')
        result=load_fixture(app.state.repository,checkpoint)
        if checkpoint.startswith('ui-family') or checkpoint=='ui-public-directory':
            ordinary_job(app.state.repository,result['save'],'start')
        return {'world':result['world'],'save':result['save']}

    @app.post('/test/birth231-seed')
    def birth231_seed():
        from birth_sex_fixture import due_save
        repo, sid = due_save(app.state.repository.path)
        return {'world':repo.get_save(sid)['world_id'], 'save':sid}

    @app.post('/test/birth231-response')
    def birth231_set_response(sid: int, wrong: bool = False):
        global birth231_response
        from birth_sex_fixture import payload
        state = app.state.repository.get_snapshot(sid)['world_state']
        birth231_response = payload(state, sexes=['female' if wrong else 'male'])
        return {'ready':True}

    @app.post('/test/due240-response')
    def due240_set_response(sid: int, mode: str = 'repair'):
        global due240_responses
        from test_due_boundary_repair import ongoing
        state = app.state.repository.get_snapshot(sid)['world_state']
        if mode == 'zero':
            due240_responses = [ongoing(state)]
        elif mode in ('repair', 'repeat'):
            due240_responses = [ongoing(state, 2), ongoing(state,
                2 if mode == 'repeat' else 0, assessed=True)]
        else:
            raise ValueError('Unknown due boundary response')
        return {'ready':True}

    @app.post('/test/initiative-seed')
    def initiative_seed():
        from devtools.narrative_test_world import load_fixture
        from test_narrative_test_world import CONFIG
        result=load_fixture(app.state.repository,'initiative')
        job=app.state.repository.begin_job(result['save'],'','start',CONFIG)
        engine.run_job(app.state.repository.path,job,engine.Worker())
        assert app.state.repository.get_job(job)['status']=='saved'
        return {'world':result['world'],'save':result['save']}

    @app.post('/test/protagonist-seed')
    def protagonist_seed():
        from devtools.narrative_test_world import load_fixture
        result=load_fixture(app.state.repository,'protagonist')
        return {'world':result['world'],'save':result['save']}

    @app.post('/test/berezovsk-followup-seed')
    def berezovsk_followup_seed(case: str = '002'):
        global berezovsk_followup
        from copy import deepcopy
        from test_berezovsk_followup248 import DATA, LTA, grounded_control, compound_control
        from test_integrated_repair247 import seed
        if case not in ('002','005'): raise ValueError('Unknown replay')
        data=deepcopy(DATA[case]); result=seed(app.state.repository,data)
        snapshot=deepcopy(LTA['snapshot'])
        snapshot['world_state']=data['before']
        snapshot['history_head']=app.state.repository.get_snapshot(result['save'])['history_head']
        with app.state.repository.connect() as db:
            db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snapshot),result['save']))
        responses=([grounded_control(data)] if case=='002' else
            [json.loads(raw) for raw in data['responses']['D']] + [compound_control(data)])
        berezovsk_followup=dict(data=data,responses=responses,attempt=0)
        return dict(world=result['world'],save=result['save'],action=data['player_input'])

    @app.post('/test/policy252-seed')
    def policy252_seed(calendar: bool = False):
        global policy252_selection
        from test_policy252 import seed_chronology
        if calendar:
            from test_acceptance254 import seed_calendar
            policy252_selection = seed_calendar(app.state.repository)
        else:
            policy252_selection = seed_chronology(app.state.repository)
        policy252_selection.update(calendar_case=calendar,
            correction_original='Неверный день.' if calendar else 'Вчера Вера встретилась с Тимуром.',
            correction_replacement='Верный день.' if calendar else 'Пять дней назад Вера встретилась с Тимуром.')
        return policy252_selection

    @app.post('/test/playability251-seed')
    def playability251_seed(case: str = '002'):
        global berezovsk_followup
        from test_playability251 import DATA, seed, payload, control
        if case not in ('002','008','016','020'):
            raise ValueError('Unknown replay')
        result = seed(app.state.repository, case)
        responses = [payload(case)] if case in ('002','020') else [payload(case),payload(case),control(case)]
        berezovsk_followup = dict(data=DATA[case], responses=responses, attempt=0)
        return result

    @app.post('/test/agency249-seed')
    def agency249_seed(mode: str = 'saved'):
        global agency249
        from test_extraction_semantics248 import final_live
        from test_integrated_repair247 import seed
        data=final_live('phone');selection=seed(app.state.repository,data)
        state=app.state.repository.get_snapshot(selection['save'])['world_state']
        action='Продолжаю сортировать фотографии.'
        narrative='Кирилл переворачивает снимок, читает дату на обороте и кладёт его в стопку.'
        audit=[dict(narrative_evidence=narrative,classification='execution_detail',player_action_id='sort')]
        if mode=='reauthor':
            narrative+=' Вера предлагает подвезти его. Кирилл кивает, соглашаясь.'
            audit.append(dict(narrative_evidence='Кирилл кивает, соглашаясь.',classification='unauthorized_choice',player_action_id=None))
        raw=dict(final_scene=dict(location_id=state['camera']['location_id'],
            present_character_ids=state['camera']['present_character_ids'],elapsed_minutes=1),
            player_agency=dict(actions=[dict(id='sort',player_evidence=action,target_ids=[],
                narrative_target_ids=[],target_mode='reference',outcome='completed',meaning='preserved')],
                narrative_audit=audit,status='preserved'),
            choices=[dict(action='Посмотреть в окно.',speech=''),dict(action='Продолжить работу.',speech='')])
        agency249=dict(raw=raw,narrative=narrative,mode=mode)
        return dict(world=selection['world'],save=selection['save'],action=action)

    @app.post('/test/agency249-allow')
    def agency249_allow():
        agency249['mode']='saved'
        return {'ok':True}

    @app.post('/test/integrated247-seed')
    def integrated247_seed(case: str = 'knowledge', repeat: bool = False, live: bool = False):
        global integrated247_case, integrated247_repeat, integrated247_extractions, integrated247_live
        from test_integrated_repair247 import seed, archived
        if live:
            from test_live248_recovery import live as archived
        if case not in ('knowledge', 'family', 'phone', 'crisis', 'social'):
            raise ValueError('Unknown replay')
        result = seed(app.state.repository, archived(case))
        integrated247_case, integrated247_repeat, integrated247_extractions = case, repeat, 0
        integrated247_live = live
        return dict(world=result['world'], save=result['save'], action=archived(case)['player_input'])

    @app.post('/test/integrated247-allow-repair')
    def integrated247_allow_repair():
        global integrated247_repeat
        integrated247_repeat = False
        return {'ok': True}

    @app.post('/test/provenance238-seed')
    def provenance238_seed(case: str = 'social', repeat: bool = False):
        global provenance238_case, provenance238_repeat, provenance238_extractions
        from test_action_provenance_repair import seed_archived
        if case not in ('social', 'knowledge', 'campaign'):
            raise ValueError('Unknown replay')
        result = seed_archived(app.state.repository, case)
        provenance238_case, provenance238_repeat, provenance238_extractions = case, repeat, 0
        return {'world': result['world'], 'save': result['save']}

    @app.post('/test/agency232-seed')
    def agency232_seed(completion: bool = False):
        global agency232_attempts, agency237_mode, agency237_extractions
        agency232_attempts = 0
        agency237_mode = completion
        agency237_extractions = 0
        from devtools.narrative_test_world import load_fixture
        from test_narrative_test_world import ordinary_job
        repo = app.state.repository
        seed = load_fixture(repo)
        sid = seed['save']
        ordinary_job(repo, sid, 'start')
        repo.transition_protagonist(sid, repo.get_save(sid)['revision'], 'agency232-nina', 'permanent', 'qa_nina')
        return {'world': seed['world'], 'save': sid}

    @app.post('/test/departure223-seed')
    def departure223_seed():
        global phone_mode
        from devtools.narrative_test_world import load_fixture
        from test_narrative_test_world import ordinary_job
        repo = app.state.repository
        seed = load_fixture(repo, 'phone')
        ordinary_job(repo, seed['save'], 'start')
        phone_mode = 'departure223'
        return {'world': seed['world'], 'save': seed['save']}

    @app.post('/test/knowledge-seed')
    def knowledge_seed():
        from devtools.narrative_test_world import load_fixture, knowledge_correction
        from test_narrative_test_world import CONFIG
        from runtime_v3_fixture import execute
        repo=app.state.repository;result=load_fixture(repo,'knowledge');sid=result['save']
        text,payload=knowledge_correction(repo.get_snapshot(sid))
        jid=repo.begin_job(sid,'Читаю сообщение Олега.','turn',CONFIG)
        execute(repo,jid,payload,text)
        assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
        return {'world':result['world'],'save':sid}

    @app.post('/test/goals-seed')
    def goals_seed():
        from devtools.narrative_test_world import load_fixture
        from test_goals_values import completion, MEET
        from test_narrative_test_world import CONFIG
        from runtime_v3_fixture import execute
        repo=app.state.repository;result=load_fixture(repo,'goals')
        sid=result['save'];state=repo.get_snapshot(sid)['world_state']
        jid=repo.begin_job(sid,'Иду навстречу.','turn',CONFIG)
        execute(repo,jid,completion(state,'qa_ilya'),MEET)
        assert repo.get_job(jid)['status']=='saved'
        return {'world':result['world'],'save':sid}

    @app.post('/test/personality-seed')
    def personality_seed():
        from devtools.narrative_test_world import load_fixture
        repo=app.state.repository
        result=load_fixture(repo,'personality')
        repo.switch_actor(result['save'],'qa_asya',repo.get_save(result['save'])['revision'])
        return {'world':result['world'],'save':result['save']}

    @app.post('/test/residence-seed')
    def residence_seed():
        from devtools.narrative_test_world import load_fixture
        from test_narrative_test_world import ordinary_job
        repo=app.state.repository
        result=load_fixture(repo,'residence-roles')
        ordinary_job(repo,result['save'],'start')
        return {'world':result['world'],'save':result['save']}

    @app.post('/test/family-seed')
    def family_seed(checkpoint: str = 'family', dead: bool = False, current: bool = False):
        from devtools.narrative_test_world import load_fixture
        from test_narrative_test_world import ordinary_job
        repo=app.state.repository
        if checkpoint not in ('family','family-incapacitated'): raise ValueError('Unknown test checkpoint')
        result=load_fixture(repo,checkpoint)
        ordinary_job(repo,result['save'],'start',expected_choices=0 if checkpoint=='family-incapacitated' else 6)
        if current:
            extraction_versions.EXTRACTION_VERSION = CURRENT_SCENE_VERSION
        if dead:
            snap=repo.get_snapshot(result['save']);state=snap['world_state'];cid=state['meta']['current_protagonist_id']
            state['characters'][cid]['life_status']='dead';state['meta']['protagonist_required']=True
            for rel in state['objective_relations'].values():
                if rel['status']=='active' and cid in (rel['source_id'],rel['target_id']) and rel['kind'] in ('spouse','partner','engaged'):
                    rel.update(status='closed',until=state['meta']['world_time'],outcome='widowed' if rel['kind']=='spouse' else 'ended')
            state['camera']['controlled_actor_id']=None;state['camera']['mode']='observer'
            state['camera']['present_character_ids']=[x for x in state['camera']['present_character_ids'] if x!=cid]
            with repo.connect() as db:db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snap),result['save']))
        return {'world':result['world'],'save':result['save']}

    @app.post('/test/commitments-seed')
    def commitments_seed():
        from devtools.narrative_test_world import load_fixture
        from test_narrative_test_world import ordinary_job
        repo = app.state.repository
        result = load_fixture(repo, 'commitments')
        ordinary_job(repo,result['save'],'start')
        return {'world':result['world'],'save':result['save']}

    @app.post('/test/calendar-seed')
    def calendar_seed():
        from devtools.narrative_test_world import load_fixture
        from test_narrative_test_world import ordinary_job
        repo = app.state.repository
        result = load_fixture(repo, 'calendar-evening')
        ordinary_job(repo,result['save'],'start')
        return {'world':result['world'],'save':result['save']}

    @app.post('/test/npc-review-seed')
    def npc_review_seed(start_game:bool=True):
        global npc_review_start_payload
        from test_runtime_v3_engine import run
        from test_npc_review import promoted
        from test_engine import CONFIG
        repo=app.state.repository
        wid=repo.save_world('Новые лица',summary());sid=repo.create_save(wid,'Проверка NPC')
        raw=promoted(repo.get_snapshot(sid))
        raw['promotions'][0]['character']=dict(biological_sex='female',life_status='alive',developmental_stage='adult',physical_state='Устала после дороги')
        raw['promotions'].append(dict(id='second_npc',name='Александр Константинович Волконский',fields={},character=dict(biological_sex='male'),evidence='Пришёл.'))
        raw['final_scene']['present_character_ids'].append('second_npc')
        if not start_game:
            # The actual UI start command has no authored player feelings.
            raw['relationship_changes'][0] = {k:v for k,v in raw['relationship_changes'][0].items()
                if k not in ('dimensions','player_assertion','player_evidence')}
            npc_review_start_payload=raw
            return dict(world=wid,save=sid)
        jid=repo.begin_job(sid,'Я доверяю Ладе.','start',CONFIG);run(repo,jid,raw)
        if repo.get_job(jid)['status']!='saved':raise ValueError(repo.get_job(jid)['error'])
        return dict(world=wid,save=sid)

    @app.post('/test/npc-review-evolve/{sid}')
    def npc_review_evolve(sid:int):
        from test_npc_review_revision import evolve
        evolve(app.state.repository,sid)
        return app.state.repository.get_save(sid)

    @app.post('/test/chat-cancel-window')
    def chat_cancel_window():
        global chat_cancel_next
        chat_cancel_next = True
        return {'armed':True}

    @app.post('/test/chat-markdown-release')
    def release_chat_markdown():
        chat_markdown_release.set()
        return {'released':True}

    @app.post('/test/chat-history')
    def chat_history():
        # Synthetic storage/rendering fixture, not 1000 played turns.
        from backend.chat.models import Create, Settings, Generate, Confirm
        from backend.chat.context import RP_PROMPT, TEMPLATE
        from uuid import uuid4
        r=app.state.chat.repo
        settings=Settings(prompt=RP_PROMPT)
        settings.reply.model='chat-fixture';settings.summary.model='chat-summary-fixture'
        settings.reply.auto_context=False;settings.reply.auto_output=False
        settings.summary.auto_context=False;settings.summary.auto_output=False
        settings.summary.context_length=65536
        cid=r.create(Create(token=uuid4().hex,name='Архив 1000 сообщений',memory=TEMPLATE,settings=settings).model_dump())
        for chapter in range(4):
            with r.transaction() as db:
                b=r.branch(db,cid)
                for i in range(250):
                    r.add_message(db,cid,b,'user' if i%2==0 else 'assistant',f'Глава {chapter+1}, сообщение {i+1}.')
            c=r.state(cid)
            job=app.state.chat.start(cid,Generate(revision=c['revision'],token=uuid4().hex,kind='summary',next_chapter=True).model_dump())
            for _ in range(1000):
                job=r.job(cid,job['id'])
                if job['status']!='running':break
                time.sleep(.01)
            if job['status']!='complete':raise ValueError('Synthetic summary did not complete')
            c=r.state(cid)
            r.confirm(cid,job['output_id'],Confirm(revision=c['revision'],token=uuid4().hex,text=job['response'],next_chapter=True).model_dump())
        return r.state(cid)

    @app.post('/test/chat-tools-history')
    def chat_tools_history():
        from chat_tools_fixture import memory
        from uuid import uuid4
        r=app.state.chat.repo;c=chat_history();cid=c['id']
        settings=c['settings']
        for stage,model in [('reply','chat-tools-fixture'),('summary','chat-tools-summary-fixture')]:
            settings[stage].update(model=model,context_length=524288)
        r.configure(cid,dict(revision=c['revision'],token=uuid4().hex,settings=settings))
        c=r.state(cid)
        d=r.manual_memory(cid,dict(revision=c['revision'],token=uuid4().hex,text=memory(95)))
        c=r.state(cid)
        r.confirm(cid,d['draft'],dict(revision=c['revision'],token=uuid4().hex,text=memory(95),next_chapter=False,accept_partial=False))
        with r.transaction() as db:
            b=r.branch(db,cid);messages=r.messages(db,b['id'])
            for index in range(0,1000,11):
                db.execute('INSERT INTO chat_bookmarks(campaign_id,message_id,note,priority) VALUES(?,?,?,?)',
                           (cid,messages[index]['id'],f'Закладка {index:04d} — важный разговор у маяка',1))
            for i in range(50):r.add_message(db,cid,b,'assistant',f'Продолжение в главе 5, сообщение {i+1}.\n\n'+CHAT_MARKDOWN)
        return dict(campaign=r.state(cid),target=messages[11]['id'])

    @app.post('/test/seed')
    def seed():
        global phone_mode
        phone_mode = 'silent'
        repo = app.state.repository
        wid = repo.save_world('Тест вариантов и памяти',summary())
        sid = repo.create_save(wid,'Тестовое прохождение')
        return {'world':wid,'save':sid}
    # Playwright's API pool can reuse an idle socket exactly as Uvicorn closes it
    # (CI #387: GET 5000.6 ms after the previous response). End fixture connections
    # explicitly after each response, including completed streams; no request retries.
    uvicorn.run(app, host='127.0.0.1', port=int(os.getenv('E2E_PORT','8011')),
                log_level='warning', headers=[('Connection', 'close')])
