"""Author contract orchestration on the existing durable Preparation journal."""
import json
from copy import deepcopy
from context_builder import estimate
from backend.services import world_authoring as a
from backend.services.initial_world_v2 import _check
from backend.services.world_authoring_compiler import compile_document, CompileError
from backend.services.world_creation_settings import CreationSettings

MAX_SOURCE_BYTES = 120_000
MAX_RECORDS = 3000
SCHEMAS = {'author_brief': a.AuthorBrief, 'author_plan': a.Plan,
           'author_document': a.Document, 'author_batch': a.Sections}


def capture(brief, config):
    if len(brief.encode('utf-8')) > MAX_SOURCE_BYTES:
        raise ValueError('author/brief: максимум 120000 байт UTF-8; сократите замысел до запроса провайдера.')
    # Do not spend an analysis request on an input that cannot reach the planner.
    # The live tokenizer remains provider-owned; this conservative admission
    # bound explicitly includes source, schemas, response and analysis reserve.
    schema_bytes=len(json.dumps(a.Plan.model_json_schema(),ensure_ascii=False).encode('utf-8'))
    required=(len(brief.encode('utf-8'))+schema_bytes)//2+config['max_tokens']+8192
    if required>config['context_length']:
        raise ValueError('author/brief: замысел не помещается в поддерживаемый контекст планирования с резервом ответа; увеличьте контекст или сократите вход. Платные запросы не отправлены.')
    return dict(brief=brief, constraint_revision=1, creation=config.get('_creation', {}),
        prompt=dict(version=a.VERSION, rules=a.AUTHOR_RULES, interpretation=a.ANALYSIS_RULES,
                    schemas={k: model.model_json_schema() for k, model in SCHEMAS.items()}))


def fits(system, data, context, output):
    return estimate([dict(content=system), dict(content=json.dumps(data, ensure_ascii=False))]) + output + 512 <= context


def source_sections(brief, context, output, schema):
    """Lossless only-when-needed splitting; every section gets a checkpoint."""
    system = a.ANALYSIS_RULES + json.dumps(schema, ensure_ascii=False)
    # Reserve room for previously registered keys and ordinary response framing.
    capacity = context - output - 4096
    if capacity <= estimate([dict(content=system)]):
        raise ValueError('author/analysis: контекст не вмещает схему и резерв ответа; увеличьте контекст.')
    if fits(system, {'source': brief}, context - 4096, output):
        return [brief]
    sections = []
    remaining = brief
    while remaining:
        lo, hi = 0, len(remaining)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if fits(system, {'source': remaining[:mid]}, context - 4096, output):
                lo = mid
            else:
                hi = mid - 1
        if not lo:
            raise ValueError('author/analysis: недостаточно контекста для раздела исходного текста.')
        boundary = remaining.rfind('\n', 0, lo)
        cut = boundary + 1 if boundary > lo // 2 else lo
        sections.append(remaining[:cut]); remaining = remaining[cut:]
    assert ''.join(sections) == brief
    return sections


def combine_briefs(parts):
    result = dict(entities=[], observations=[], ambiguities=[])
    known = {}
    for part in parts:
        for row in part['entities']:
            if row['key'] in known and known[row['key']] != row:
                raise CompileError('author_brief/entities/' + row['key'], 'Разделы противоречат друг другу в определении сущности.')
            known[row['key']] = row
        result['observations'].extend(part['observations'])
        result['ambiguities'].extend(part['ambiguities'])
    result['entities'] = list(known.values())
    return _check(a.AuthorBrief, result, 'author_brief').model_dump()


def run(repo, jid, token, inputs, config, context, request, execute):
    def unit(uid, stage, dependencies, outputs):
        return dict(id=uid, stage=stage, inputs=dependencies, outputs=outputs)
    def get(key):
        return repo.generation_resources(jid, [key])[key]
    brief = inputs['brief']
    parts = source_sections(brief, context, config['max_tokens'], inputs['prompt']['schemas']['author_brief'])
    part_keys = ['author_source_' + str(i) for i in range(len(parts))]
    repo.plan_generation_units(jid, token, [
        *[unit(key, 'author_brief', ['brief', 'prompt', *part_keys[:i]], {key: ''}) for i, key in enumerate(part_keys)],
        unit('author_brief', 'author_brief', part_keys, {'author_brief': ''})])
    accepted = []
    for i, key in enumerate(part_keys):
        known = {r['key']: r for p in accepted for r in p['entities']}
        execute(key, lambda: request('author_brief', dict(source=parts[i], known_entities=list(known.values())), a.AuthorBrief),
                lambda raw: _check(a.AuthorBrief, raw, key).model_dump())
        accepted.append(get(key))
    execute('author_brief', lambda: combine_briefs(accepted), lambda value: value)
    analysis = get('author_brief')
    def validate_document(raw):
        value=_check(a.Document,raw,'author_document').model_dump()
        for entity in analysis['entities']:
            section={'character':'characters','location':'locations','organization':'organizations'}[entity['kind']]
            row=next((r for r in value[section] if r['key']==entity['key']),None)
            if row is None:raise CompileError('author_document/'+section+'/'+entity['key'],'Пропущена сущность, заданная автором.')
            if row['name']!=entity['name']:raise CompileError('author_document/'+section+'/'+entity['key'],'Изменено заданное автором имя.')
        return value
    data = dict(original_source=brief, author_brief=analysis)
    targets = CreationSettings.model_validate(inputs['creation']).cast_targets(analysis['entities'])
    # Output estimate includes substantive prose, sparse ties and schema overhead;
    # it is planning, not an assertion about actual tokenizer usage.
    expected = (1 + targets['core']) * 1600 + targets['secondary'] * 700 + len(brief.encode('utf-8')) // 2 + 2500
    system = inputs['prompt']['rules'] + json.dumps(inputs['prompt']['schemas']['author_document'], ensure_ascii=False)
    compact = expected <= config['max_tokens'] and fits(system, data, context, expected)
    if compact:
        repo.plan_generation_units(jid, token, [unit('author_document', 'author_document',
            ['brief', 'author_brief', 'creation', 'prompt'], {'author_document': ''})])
        execute('author_document', lambda: request('author_document', data, a.Document),
            validate_document)
    else:
        repo.plan_generation_units(jid, token, [unit('author_plan', 'author_plan',
            ['brief', 'author_brief', 'creation', 'prompt'], {'author_plan': ''})])
        execute('author_plan', lambda: request('author_plan', {**data,
            'instruction': 'Plan the entire registry and only meaningful relations/events/circumstances. Each record has a section/key and explicit references. Do not write full biographies. Preserve all author entities and mandatory ties.'}, a.Plan),
            lambda raw: _check(a.Plan, raw, 'author_plan').model_dump())
        plan = get('author_plan')
        batches = []
        current, budget = [], 0
        for record in plan['records']:
            cost = 1800 if record['section'] == 'characters' else 650
            if cost > config['max_tokens']:
                raise CompileError('author_plan/' + record['key'], 'Резерв ответа слишком мал для содержательной записи.')
            if current and budget + cost > config['max_tokens'] * .7:
                batches.append(current); current, budget = [], 0
            current.append(record); budget += cost
        if current:
            batches.append(current)
        keys = ['author_batch_' + str(i) for i in range(len(batches))]
        owner={r['section']+'/'+r['key']:i for i,batch in enumerate(batches) for r in batch}
        dependencies={i:sorted({owner[ref] for r in batch for ref in r['references'] if owner[ref]<i}) for i,batch in enumerate(batches)}
        definitions = [unit(key, 'author_batch', ['brief', 'author_brief', 'author_plan', 'prompt', 'creation',*[keys[j] for j in dependencies[i]]], {key: ''}) for i,key in enumerate(keys)]
        definitions += [unit('author_document', 'author_document', ['author_plan', *keys], {'author_document': ''})]
        repo.plan_generation_units(jid, token, definitions)
        for i, key in enumerate(keys):
            assigned = batches[i]
            def validate(raw):
                value = _check(a.Sections, raw, key).model_dump()
                actual = {section + '/' + r['key'] for section, rows in value.items() for r in rows}
                wanted = {r['section'] + '/' + r['key'] for r in assigned}
                if actual != wanted:
                    raise CompileError(key, 'Ответ должен содержать только назначенные записи, без пропусков.')
                return value
            execute(key, lambda: request('author_batch', {**data, 'world': plan['world'],
                'opening': plan['opening'], 'registry': plan['records'], 'assigned_records': assigned,
                'accepted_related_sections':{keys[j]:get(keys[j]) for j in dependencies[i]},
                'instruction': 'Expand only assigned records. The plan registry, relations and identities are accepted and cannot change.'}, a.Sections), validate)
        def assemble():
            value = {k: deepcopy(plan[k]) for k in ('world', 'opening', 'uncertainties')}
            value.update({k: [] for k in a.Sections.model_fields})
            for key in keys:
                for section, rows in get(key).items():
                    value[section].extend(rows)
            return validate_document(value)
        execute('author_document', assemble, lambda value: value)
    repo.plan_generation_units(jid, token, [unit('compile', 'compile',
        ['author_document', 'creation', 'brief', 'author_brief'], {'assembled': '/snapshot', 'author_compilation': ''})])
    def compile_current():
        previous = repo.inspect_generation_checkpoint(jid, 'compile', True).get('artifact') or {}
        result = compile_document(get('author_document'), previous.get('id_map'), inputs['creation'])
        snapshot = result.snapshot
        snapshot['campaign']['initial_world'] = dict(version=a.VERSION, brief=brief,
            analysis=analysis, source_document=get('author_document'), id_map=result.id_map,
            compiled_hash=compiled_hash(snapshot), diagnostics=result.diagnostics)
        return dict(snapshot=snapshot, id_map=result.id_map, diagnostics=result.diagnostics,
                    transformations=result.transformations)
    execute('compile', compile_current, lambda value: value)
    if repo.generation_boundary(jid, token):
        repo.publish_generation_draft(jid, token, get('assembled'))


def compiled_hash(snapshot):
    from backend.services.initial_world_stages import fingerprint
    from backend.services.initial_world_v2 import normalize
    from backend.services.draft_world import prepare
    snapshot=normalize(prepare(snapshot)).snapshot
    return fingerprint({k:snapshot.get(k) for k in ('world_state','character_cards')})


def mark_author_changes(before, after):
    """Field-level provenance for edits; never relabel untouched generated prose."""
    for section in a.Sections.model_fields:
        old={r['key']:r for r in before.get(section,[])}
        for row in after.get(section,[]):
            prior=old.get(row['key'])
            if prior is None:
                row['origin']='explicit'
            else:
                for field in set(row)-{'key','origin','field_origins'}:
                    if row[field]!=prior.get(field):
                        row.setdefault('field_origins',{})[field]='explicit'
    return after


def patch_author_checkpoint(repo, jid, unit, cp, revision, artifact_version, path, value,
                            *, preview=True, operation='patch', ack=False):
    if cp['stage'] == 'compile':
        raise ValueError('author/edit: сборка вычисляется из авторского документа.')
    if operation == 'unlock':
        return repo.unlock_generation_fields(jid, unit, revision, artifact_version, [path], preview=preview)
    if cp['status'] != 'completed' or cp['artifact_version'] != artifact_version:
        raise ValueError('author/edit: обновите версию этапа.')
    if operation not in ('patch', 'regenerate'):
        raise ValueError('author/edit: неизвестное действие.')
    if cp['stage'] == 'author_brief' and not ack:
        raise ValueError('author/edit: подтвердите изменение анализа; оригинал останется в истории.')
    payload = deepcopy(cp['artifact'])
    if operation == 'patch':
        parts = [p.replace('~1', '/').replace('~0', '~') for p in path.split('/')[1:]] if path.startswith('/') else []
        if not parts or any(p in ('key', 'version') for p in parts):
            raise ValueError('author/edit: выберите содержательное поле; идентификаторы неизменны.')
        target = payload
        try:
            for part in parts[:-1]:
                target = target[int(part)] if isinstance(target, list) else target[part]
            if isinstance(target, list):
                target[int(parts[-1])] = value
            else:
                if parts[-1] not in target:raise KeyError(parts[-1])
                target[parts[-1]] = value
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ValueError('author/edit: поле не найдено.') from exc
    if operation=='patch' and cp['stage'] in ('author_document','author_batch'):
        payload=mark_author_changes(cp['artifact'],payload)
    payload = _check(SCHEMAS[cp['stage']], payload, unit).model_dump()
    # A paused author document may need several local corrections. Schema-valid
    # edits are journaled; only the compile/publication gate can make it playable.
    return repo.revise_generation_checkpoint(jid, unit, payload, revision, artifact_version,
        [path] if operation == 'patch' else [], preview=preview, regenerate=operation == 'regenerate')
