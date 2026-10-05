"""Deterministic long-world data shared by selection tests and before/after benchmark."""
from backend.runtime_v3.models import (Character, Location, Fact, Knowledge, Relationship,
                                      Thread, ScheduledEvent, Motivation, WorldStateV3)


def long_world(scale=1):
    actors = ['a', 'b', 'c'] + [f'npc_{i}' for i in range(32*scale)]
    locations = {'kitchen': Location(id='kitchen', name='Кухня', description='Тёплая кухня с круглым столом.').model_dump()}
    locations.update({f'loc_{i}': Location(id=f'loc_{i}', name=f'Warehouse{i}', description=f'UNRELATED_WAREHOUSE_{i} '+('далёкий склад '*30)).model_dump() for i in range(55*scale)})
    characters = {cid: Character(id=cid, location_id='kitchen' if cid in ('a','b') else 'loc_0').model_dump() for cid in actors}
    characters['a']['goals'] = [Motivation(id='goal_a', text='Разобраться с конвертом').model_dump()]
    state = WorldStateV3(meta=dict(turn_id=1000, world_time=600),
        camera=dict(location_id='kitchen', present_character_ids=['a','b'], controlled_actor_id='a'),
        characters=characters, locations=locations).model_dump()
    cards = [dict(id=cid, name={'a':'Илья','b':'Тимур','c':'Соня'}.get(cid, cid), aliases=[],
        fields={'Роль':'Друг', 'Характер':'Упрямый, заботливый', 'Биография':f'BIO_{cid} '+('подробная биография '*60),
                'Внешность':f'APPEARANCE_{cid}', 'Стиль общения':f'VOICE_{cid}: сухой юмор, короткие фразы',
                'Привычки':'Поправляет рукав', 'Страхи и уязвимости':'Боится потери друзей'}) for cid in actors]
    for i in range(220*scale):
        fid = f'fact_{i}'; cid = actors[3+i%(len(actors)-3)]
        state['facts'][fid] = Fact(id=fid, text=f'UNRELATED_SECRET_{i} '+('архивная деталь '*12), character_ids=[cid], visibility='secret').model_dump()
        for knower in ('a', cid): state['knowledge'][knower+':'+fid] = Knowledge(actor_id=knower, fact_id=fid).model_dump()
    state['facts']['letter'] = Fact(id='letter', text='Конверт пришёл вчера; Соня просила сохранить его.', character_ids=['a','b','c'], visibility='secret').model_dump()
    for cid in ('a','b'):
        state['knowledge'][cid+':letter'] = Knowledge(actor_id=cid, fact_id='letter').model_dump()
    for index, source in enumerate(actors):
        for offset in range(1,5):
            target = actors[(index+offset)%len(actors)]
            state['relationships'][source+':'+target] = Relationship(source_id=source, target_id=target, dimensions={'trust':20.0}, context=f'REL_{source}_{target}').model_dump()
    state['relationships']['b:a'] = Relationship(source_id='b', target_id='a', dimensions={'trust':40.0}, context='Давно знакомы').model_dump()
    for i in range(35*scale):
        tid=f'thread_{i}'
        state['threads'][tid]=Thread(id=tid, description=f'Архивный проект {i}', character_ids=['a',actors[3+i%(len(actors)-3)]]).model_dump()
    state['threads']['letter_thread']=Thread(id='letter_thread',description='Выяснить историю конверта',character_ids=['a','b','c']).model_dump()
    for i in range(55*scale):
        eid=f'scheduled_{i}'
        state['scheduled_events'][eid]=ScheduledEvent(id=eid, description=f'Дальняя поставка {i}', due_minute=11000, character_ids=[actors[3+i%(len(actors)-3)]], location_id='loc_0').model_dump()
    state['scheduled_events']['doorbell']=ScheduledEvent(id='doorbell',description='Доставка конверта',due_minute=610,character_ids=['a'],location_id='kitchen',interrupts=True).model_dump()
    events=[dict(id=f'event_{i}', text=f'Архивная история {i}', participants=['a', actors[3+i%(len(actors)-3)]], location_id='loc_0', turn_id=i, fact_ids=[]) for i in range(550*scale)]
    # Keep unrelated history old at all scales.
    for event in events: event['turn_id']=1
    events.append(dict(id='letter_event', text='Тимур передал Илье конверт.',participants=['a','b'], location_id='kitchen', turn_id=1000, fact_ids=['letter']))
    conversation = [
        'Тимур поставил чашку на край стола, не отпуская ручку. «Ты ведь помнишь, что я обещал?» '
        'За окном стучал дождь. Он говорил тише обычного: сухая шутка так и осталась невысказанной. '
        'На столе лежал конверт, запечатанный неровной полоской скотча. Тимур подвинул его к середине стола. '
        '«Я тебя не предам», — добавил он после паузы, не требуя ответа. Чай в обеих чашках постепенно остывал.',
        '«Откуда он у тебя?» Тимур покосился на конверт. «Из почтового ящика. Удивительная вещь, почта: '
        'иногда в ней даже бывает что-то кроме счетов». Шутка прозвучала привычно, но дальше он замолчал. '
        'Край скотча отстал от бумаги. Тимур заметил это и отодвинул чашку, чтобы случайно не залить письмо. '
        '«Не открывал. Решил, что сначала надо показать тебе». За дверью коротко скрипнула половица.',
        'Тимур поправил рукав и снова посмотрел на конверт. «Если хочешь, подожду в коридоре». '
        'Предложение прозвучало спокойно, без обиды. Потом он всё-таки добавил: «Но ты уже третий раз '
        'спрашиваешь, не читал ли я. Ответ пока не изменился». На кухне повисла пауза. '
        'Тимур не потянулся к письму и не попытался заглянуть через стол; он ждал, держа ладони на коленях.',
        '«Ладно, неудачно сказал», — признал Тимур. Он отодвинул стул на несколько сантиметров. '
        '«Я понимаю, почему ты спрашиваешь. Просто хотелось бы, чтобы мне иногда верили с первого раза». '
        'Теперь в голосе почти не осталось привычной иронии. За окном проехала машина; свет фар скользнул '
        'по потолку и исчез. Конверт оставался между чашками, и никто его пока не вскрыл.',
        'Тимур кивнул, услышав ответ. «Хорошо. Тогда начнём сначала». Он аккуратно повернул конверт '
        'адресом вверх. «Вот что я точно знаю: его принесли вчера. Больше ничего придумывать не буду». '
        'В его голос вернулась сдержанная, знакомая сухость. «Можем даже завести протокол, если поможет». '
        'Он едва улыбнулся, оставляя возможность отшутиться или продолжить разговор всерьёз.',
        '«Про обещание я помню», — сказал Тимур, возвращаясь к началу разговора. «И сейчас не забираю '
        'его обратно». Он замолчал и убрал руку со стола. В коридоре снова послышались шаги, но до двери '
        'пока никто не дошёл. Тимур посмотрел в ту сторону, затем снова на собеседника. '
        '«Разберёмся с письмом вместе или тебе нужно ещё немного времени?» Ответа он не торопил.',
    ]
    turns=[dict(user_text=f'Реплика игрока {i}',assistant_text=f'Художественная сцена {i}: '+conversation[i],pov_actor_id='a',kind='turn') for i in range(6)]
    return dict(schema_version=3, world_state=state, character_cards=cards, campaign={'protagonist_id':'a','sections':{'tone':'Драмеди'}}, history_head=None, memory={}), turns, {'events':events}
