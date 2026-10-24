"""Synthetic populated author world; never merged into user journals."""
from test_initial_draft_v4 import rich
from backend.services.draft_initial import inspect_candidate
from backend.runtime_v3 import models as m


def presentation_world():
    s=rich();w=s['world'];a,b=[c['id'] for c in s['characters'][:2]];lid=s['locations'][0]['id']
    s['campaign']['title']='Синтетический мир представления'
    s['characters'][0]['name']='Анна';s['characters'][1]['name']='Борис'
    s['locations'][0]['name']='Дом у реки'
    w['residences']={'home_a':m.Residence(id='home_a',actor_id=a,location_id=lid,context='Живёт у реки.').model_dump(),
                     'home_b':m.Residence(id='home_b',actor_id=b,location_id=lid,status='closed',since=0,until=100,context='Прежнее жильё.').model_dump()}
    w['contacts']={'contact_b':m.Contact(id='contact_b',owner_id=a,character_id=b,label='Друг',address='local-b',identity_visible=False,provenance='Введён автором',created_at=0).model_dump()}
    w['conditions']={'condition_a':m.Condition(id='condition_a',actor_id=a,description='Повреждение ноги',effects={'can_move':False},evidence='Указано автором').model_dump()}
    w['possessions']={'watch':m.SignificantPossession(id='watch',name='Старинные часы',kind='heirloom',owner_id=a,holder_id=b,location_id=lid,status='available').model_dump()}
    w['characters'][a].update(life_status='alive',developmental_stage='adult',capabilities={'conscious':True,'can_act':True,'can_perceive':None,'can_move':False,'can_speak':True},
        appearance={'items':{'hair':{'category':'presentation','kind':'hairstyle','text':'Короткие волосы'}}},
        personality={'items':{'habit':{'field':'habits','text':'Смотрит в окно перед ответом'}}})
    out,report=inspect_candidate(s)
    if report['diagnostics']:raise AssertionError(report['diagnostics'])
    return out


def family_world():
    """Separate valid synthetic world exercising pregnancy/name records via Runtime."""
    from test_reproduction import conceive,naming
    from backend.services.world import KINDS
    from backend.services.draft_initial import EXTENSIONS,ACTOR_FIELDS
    first=conceive();second=naming(first.state);canonical=second.state
    s=rich();s['campaign']['title']='Синтетическая семейная история'
    s['characters']=[{'id':cid,'name':name,'fields':{'Возраст':'36','Биография':'Синтетическая биография взрослого персонажа.'},'aliases':[]} for cid,name in zip(canonical['characters'],['Анна','Борис','Вера'])]
    s['locations']=[dict(loc,text='Синтетический семейный дом.') for loc in canonical['locations'].values()];s['controlled_actor_id']=s['protagonist_id']='a'
    s['camera']={'scene_id':'start'};s['world_clock']={'minute':0,'calendar':canonical['meta']['calendar']}
    w={key:{} for key in KINDS};w['version']=2;s['world']=w
    for key in EXTENSIONS:w[key]=canonical[key]
    w['characters']={cid:{'id':cid,'location':'home','situation':'Дома','goals':[],'intentions':[],'obligations':[],**{k:c[k] for k in ACTOR_FIELDS if k in c}} for cid,c in canonical['characters'].items()}
    w['facts']={fid:dict(f,secret=f.get('visibility')=='secret',evidence=[]) for fid,f in canonical['facts'].items()}
    w['knowledge']=canonical['knowledge']
    w['events']={e['id']:dict({k:v for k,v in e.items() if k in ('id','text','participants','witnesses','fact_ids','player_observed','source_sequence')},minute=e['recorded_minute']) for history in [first.history,second.history] for e in history['events']}
    w['scenes']={'start':{'id':'start','location':'home','participants':['a','b'],'text':'Два человека обсуждают выбранное имя.','start_minute':0,'end_minute':0,'status':'active','event_ids':[]}}
    out,report=inspect_candidate(s)
    if report['diagnostics']:raise AssertionError(report['diagnostics'])
    return out
