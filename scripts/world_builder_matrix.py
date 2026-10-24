"""Regenerate the review inventory from the same schema served to the UI."""
from pathlib import Path
import sys
import json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.services.world_builder import schema, READ_ONLY


def rows():
    spec=schema()
    def walk(node,path,required=False,inherited=False):
        if '$ref' in node:node=spec['$defs'][node['$ref'].split('/')[-1]]
        readonly=inherited or path.split('.')[-1] in READ_ONLY
        if 'anyOf' in node:
            branch=next((v for v in node['anyOf'] if v.get('type')!='null'),{})
            yield from walk({**branch,**{k:v for k,v in node.items() if k!='anyOf'}},path,False,readonly)
        elif node.get('properties'):
            for key,child in node['properties'].items():
                yield from walk(child,path+'.'+key,key in node.get('required',[]),readonly)
        elif node.get('type')=='array':
            yield from walk(node.get('items',{}),path+'[]',False,readonly)
        elif isinstance(node.get('additionalProperties'),dict):
            yield from walk(node['additionalProperties'],path+'.*',False,readonly)
        else:
            default=json.dumps(node.get('default','—'),ensure_ascii=False)
            mandatory='имя карточки' if path=='characters.*.display_name' else 'в заполненной записи' if required and 'default' not in node and not readonly else 'нет'
            validation='enum: '+', '.join(map(str,node['enum'])) if 'enum' in node else node.get('type','union')
            bounds={k:node[k] for k in ('minimum','maximum','minLength','maxLength','pattern') if k in node}
            if bounds:validation+=' '+json.dumps(bounds,ensure_ascii=False)
            yield [path,path.split('.')[0],mandatory,default,validation,'служебное / read-only' if readonly else 'форма']
    for key,node in spec['properties'].items():yield from walk(node,key)

if __name__=='__main__':
    out=Path(__file__).resolve().parents[1]/'docs/world-builder-field-matrix.md'
    header='''# Матрица полей конструктора (#117)

Источник: `WorldStateV3.model_json_schema()` — текущая модель эволюции Runtime v4.
Обновление: `python scripts/world_builder_matrix.py`. `*` — запись словаря, `[]` — элемент списка.

Формы используют эту же схему в `/api/world-builder/schema`; отдельной модели мира нет.
Обязательные поля вложенной записи требуются только когда автор добавил эту запись.
Числовые/enum/default значения заполняются программно; имя созданного персонажа вводит автор.
Пустой observer-мир разрешён Runtime; для actor-режима обязательны выбранный управляемый персонаж,
его присутствие и согласованные местоположения. Красная звёздочка не означает, что весь раздел обязателен.

Каждая строка дополнительно проверяется итоговыми canonical invariants: life, geography/residence,
reproduction, Knowledge, relationships, remote communication, календарь и камера.
Первый этап — строгий Pydantic, до runtime read-boundary salvage. История до игры использует
`WorldHistoryV3.events` и поля existing extraction schema; при старте один batch добавляется
в существующий immutable History DAG. Это staging истории, не второй Runtime.

Campaign title/setting/era/genre/tone/description/rules редактируются в «Обзор мира»;
биографии и роль — в существующих character_cards. IDs, ревизии, receipts и счётчики не вводятся вручную.
Portrait asset references обслуживает существующий менеджер портретов после начала игры;
конструктор не создаёт ссылки на несуществующие файлы. У Gregorian-даты weekday вычисляет Calendar.

| Поле Runtime | Раздел / вложенная форма | Обязательность | Default модели | Проверка | Ручное изменение |
|---|---|---|---|---|---|
'''
    def escape(v):return str(v).replace('|','\\|').replace('\n',' ')
    out.write_text(header+''.join('| '+' | '.join(escape(v) for v in row)+' |\n' for row in rows()),encoding='utf-8')
