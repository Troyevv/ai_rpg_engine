"""Bounded current truth and history, with no provenance join for POV knowledge."""
from pathlib import Path
import json
import re
from backend.runtime_v3.raw import extraction_schema
from backend.services.player_agency import PLAYER_AGENCY_CONTRACT

PROMPTS=Path(__file__).resolve().parents[2]/'prompts'


def build_context(snapshot, turns, user_text, kind, context_length, reserve, extraction_text=None,
                  validation_feedback=None,recent_turns=6,prompts=None,world_history=None):
    from context_builder import estimate
    from backend.services.pov import visible,actor_view
    state=snapshot['world_state'];camera=state['camera'];actor=camera['controlled_actor_id']
    main=snapshot.get('campaign',{}).get('protagonist_id')
    def block(name,value):return dict(role='user',content=name+'\n'+json.dumps(value,ensure_ascii=False,separators=(',',':')))
    name='game_system_prompt.md' if kind!='background' else 'background_prompt.md'
    if extraction_text is None:
        rules=(prompts or {}).get(name,{}).get('content') or (PROMPTS/name).read_text(encoding='utf-8')
    else:
        saved=(prompts or {}).get('state_update_prompt.md',{}).get('content') or (PROMPTS/'state_update_prompt.md').read_text(encoding='utf-8')
        rules=saved+'\nАКТУАЛЬНЫЙ КОНТРАКТ RUNTIME V3 заменяет старый формат extraction в сохранённых инструкциях.\n'+('Извлеки только подтверждённые изменения завершённого хода как RawTurnResult v3. '
            'Не продолжай повествование. Final_scene задаёт конечную камеру; elapsed_minutes — длительность. '
            'Не создавай scene_id, last_event_id, from_location или StatePatch. '
            'Location_id должен ссылаться на существующее место или новую запись locations с evidence. '
            'Events — история, не обязательная реконструкция всех перемещений. '
            'Knowledge_gained разрешён только через Fact → Event этого ответа → Witness → Knowledge; '
            'actor_id входит в witnesses, fact_id входит в fact_ids, medium observation/conversation/message/testimony/discovery. '
            'Нет цепочки — опусти acquisition. '
            'Relationship dimensions закрыты схемой. Другой смысл запиши в context. '
            'Не превращай мимолётного человека в постоянного NPC; promotions только для значимой повторяющейся роли. '
            'Необязательные неизвестные поля опускай. Все изменённые записи, кроме явно заданных игроком внутренних полей, требуют точную цитату evidence.\n'
            +PLAYER_AGENCY_CONTRACT+'\nJSON Schema:\n'+json.dumps(extraction_schema(),ensure_ascii=False))
    rules+=f'\nRuntime v3. controlled_actor_id={actor}; mode={camera["mode"]}; world_time={state["meta"]["world_time"]} минут. '
    rules+='Не назначай controlled_actor действия, слова, решения или чувства. Карточки и внутренние состояния NPC — GM-only; не пересказывай психологию, используй индивидуальный стиль речи. При написании диалогов используй «Стиль общения» каждого персонажа: лексику, длину фраз, юмор и реакцию на конфликт. '
    rules+='Предлагай 6 choices объектов action/speech для controlled_actor; для observer choices=[].'
    if validation_feedback:rules+='\nИсправь структурную ошибку, верни полный JSON:\n'+validation_feedback
    present=set(camera['present_character_ids'])
    for card in snapshot['character_cards']:
        if any(re.search(r'(?<!\w)'+re.escape(alias)+r'(?!\w)',user_text,re.I) for alias in [card['name'],*card.get('aliases',[])] if alias):present.add(card['id'])
    relevant_facts={k['fact_id'] for k in state['knowledge'].values() if k['actor_id'] in present and k['status']!='unknown'}
    relevant_facts.update(fid for fid,f in state['facts'].items() if set(f['character_ids']) & present)
    current=dict(meta=state['meta'],camera=camera,locations=state['locations'],
        characters={cid:c for cid,c in state['characters'].items() if cid in present},
        facts={fid:state['facts'][fid] for fid in sorted(relevant_facts)},
        knowledge=[k for k in state['knowledge'].values() if k['actor_id'] in present],
        relationships=[r for r in state['relationships'].values() if r['source_id'] in present or r['target_id'] in present],
        threads=[t for t in state['threads'].values() if t['status']!='resolved' and (not t['character_ids'] or set(t['character_ids']) & present)],
        scheduled_events=[e for e in state['scheduled_events'].values() if e['status']=='pending'])
    campaign=snapshot.get('campaign',{})
    # Static campaign material only: old import sections also contain duplicate
    # character cards and runtime tables, which are not a second context source.
    campaign_context=dict(campaign=campaign.get('campaign',{}),story_notes=campaign.get('story_notes',''),
        tone=campaign.get('sections',{}).get('tone',''),initial_knowledge=campaign.get('sections',{}).get('knowledge',''))
    messages=[dict(role='system',content='Постоянные правила\n'+rules),
        block('Кампания / GM-only',campaign_context),
        block('Текущее состояние / GM-only',current),
        block('Карточки присутствующих / GM-only',[c for c in snapshot['character_cards'] if c['id'] in present]),
        block('Индекс персонажей',[dict(id=c['id'],name=c['name']) for c in snapshot['character_cards']]),
        block('Знания POV',[dict(k,text=state['facts'][k['fact_id']]['text']) for k in state['knowledge'].values() if k['actor_id']==actor and k['status']!='unknown'])]
    memory=snapshot.get('memory',{})
    scoped=memory if kind=='background' else memory.get('per_actor',{}).get(actor,memory if actor==main and not memory.get('per_actor') else {})
    messages.append(block('Память',scoped))
    from backend.runtime_v3.director import plan
    recent_history=[e for e in (world_history or {}).get('events',[]) if isinstance(e,dict) and isinstance(e.get('text'),str) and isinstance(e.get('participants'),list) and any(isinstance(cid,str) and cid in present for cid in e['participants'])][-12:]
    messages.append(block('Недавняя история / GM-only',recent_history))
    messages.append(block('Director / GM-only',plan(state,kind,world_history)))
    historical=[]
    for turn in turns[-recent_turns:]:
        if kind=='background' or visible(turn,actor,main):
            view=turn if kind=='background' else actor_view(turn,actor,main)
            historical.extend([dict(role='user',content=view['user_text'] or 'Продолжить.'),dict(role='assistant',content=view['assistant_text'])])
    tail=[block('Текущий ввод',dict(kind=kind,player_input=user_text))]
    if extraction_text is not None:tail.append(block('completed_narrative',extraction_text))
    # Drop oldest history first; never silently truncate the current player input.
    while historical and estimate(messages+historical+tail)>context_length-reserve-256:del historical[:2]
    budget=context_length-reserve-256
    # Trim optional current material deterministically. Removing a Fact also
    # removes its context-only Knowledge rows; canonical state is untouched.
    def refresh():
        messages[2]=block('Текущее состояние / GM-only',current)
        messages[5]=block('Знания POV',[dict(k,text=current['facts'][k['fact_id']]['text'])
            for k in current['knowledge'] if k['actor_id']==actor and k['status']!='unknown' and k['fact_id'] in current['facts']])
        messages[7]=block('Недавняя история / GM-only',recent_history)
    def priority(item):
        ids=set(item.get('character_ids',[]))
        score=20*bool(ids & present)+30*bool(actor and actor in ids)
        text=' '.join(str(item.get(k,'')) for k in ('text','description','context'))
        if any(word in text.casefold() for word in re.findall(r'\w{4,}',user_text.casefold())):score+=40
        if item.get('status') in ('active','developing'):score+=10
        if item.get('due_minute') is not None and item['due_minute']<=state['meta']['world_time']:score+=40
        return score
    while estimate(messages+historical+tail)>budget:
        options=[]
        for fid,fact in current['facts'].items():options.append((priority(fact),'facts',fid))
        for section in ('threads','scheduled_events','relationships'):
            for index,item in enumerate(current[section]):options.append((priority(item),section,index))
        used_locations={camera['location_id']}|{c['location_id'] for c in current['characters'].values()}
        for lid in current['locations']:
            if lid not in used_locations:options.append((0,'locations',lid))
        if recent_history:options.append((0,'history',0))
        if not options:break
        _,section,key=min(options,key=lambda entry:(entry[0],entry[1],str(entry[2])))
        if section=='history':recent_history.pop(0)
        elif section=='facts':
            del current['facts'][key]
            current['knowledge']=[k for k in current['knowledge'] if k['fact_id']!=key]
        elif section=='locations':
            # Current locations initially share a read reference: copy before edit.
            current['locations']=dict(current['locations']);del current['locations'][key]
        else:current[section].pop(key)
        refresh()
    if estimate(messages+historical+tail)>budget:
        raise ValueError('Контекст v3 не помещается в выбранную модель. Увеличь контекст или уменьши лимит ответа.')
    return messages+historical+tail
