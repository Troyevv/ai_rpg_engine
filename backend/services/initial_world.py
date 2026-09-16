"""Import explicit preparation metadata. Never guess holders of legacy prose secrets."""
import re
from backend.services.timeline import parse_time


def seed(world, state, now):
    from backend.services.world import identity
    aliases={re.sub(r'\s*\(ГГ\)', '', c['name']).strip().casefold():c['id'] for c in state['characters']}
    aliases.update({c['name'].casefold():c['id'] for c in state['characters']})
    def people(value):
        if value.strip().casefold()=='все':return list(world['characters'])
        return sorted({aliases[n.strip().casefold()] for n in value.split(',') if n.strip().casefold() in aliases})
    for c in state['characters']:
        target=world['characters'][c['id']];fields=c['fields']
        if not target['scene_id'] and fields.get('Место'):
            target['location']=fields['Место']
            target['minute']=parse_time(fields.get('Время',''),now)
            if target['minute'] is None:target['minute']=now
        for field,key in [('Намерения','intentions'),('Обязательства','obligations')]:
            if fields.get(field):target[key]=[fields[field]]
    secret=False
    for line in state['sections'].get('knowledge','').splitlines():
        if line.startswith('#'):
            secret='ТАЙНЫ' in line.upper() or '🔴' in line
        if not re.match(r'^\s*[-·*]\s+',line) or '| Знают:' not in line:continue
        parts=line.split('|')
        text=re.sub(r'^\s*[-·*]\s+','',parts[0]).strip()
        fields={k.strip():v.strip() for p in parts[1:] if ':' in p for k,v in [p.split(':',1)]}
        fid=identity('initial_fact',text)
        known=people(fields.get('Знают',''));suspected=people(fields.get('Подозревают',''))
        evidence=fields.get('Основание','')
        world['facts'][fid]=dict(id=fid,text=text,secret=secret,character_ids=sorted(set(known+suspected)),evidence=[evidence] if evidence else [])
        for status,ids in [('suspected',suspected),('known',known)]:
            for cid in ids:
                world['knowledge'][cid+':'+fid]=dict(actor_id=cid,fact_id=fid,status=status,source_event_id=None,initial=True)
