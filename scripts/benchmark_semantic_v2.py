"""Russian retrieval benchmark, local CPU. --download explicitly provisions weights."""
import argparse
import json
import os
from pathlib import Path
import resource
import statistics
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.runtime_v3.semantic import SemanticRetriever, Document, DEFAULT_MODEL

DOCS = [
    Document('facts','fact_sonya_serious_intent','Соня прямо сказала Илье, что ей с ним хорошо и она не хочет делать вид, будто они просто гуляют.'),
    Document('threads','thread_sonya_ilya','Соня и Илья сближаются. Их связь перестаёт быть случайными встречами и становится устойчивой парой.'),
    Document('facts','fact_cottage_agreed','Друзья договорились провести выходные в загородном доме у озера.'),
    Document('facts','fact_cottage_booked','Бронь коттеджа на субботу подтверждена, предоплата внесена.'),
    Document('scheduled_events','scheduled_cottage_trip','В субботу утром компания выезжает на дачу. Проверить бронь и распределить машины.'),
    Document('facts','fact_katya_jealous','Катя из квартиры напротив обиделась, увидев Илью с Соней, и стала холодно с ним здороваться.'),
    Document('history_events','event_katya_jealous','Соседка Катя устроила Илье сцену из-за его внимания к другой девушке.'),
    Document('characters','katya','Катя, соседка Ильи. Ревнивая, ранимая, скрывает свою привязанность.'),
    Document('facts','negative_lab','В лабораторию доставили новый спектрометр; Тимур проверил калибровку прибора.'),
    Document('facts','negative_weather','В городе всю ночь шёл сильный дождь, утром дороги покрылись лужами.'),
    Document('locations','negative_station','Вокзал. Зал ожидания с кассами и табло поездов.'),
    Document('threads','negative_report','Юра должен подготовить отчёт о ядерном реакторе к понедельнику.'),
    Document('scheduled_events','negative_delivery','В среду в офис доставят бумагу для принтера.'),
]
CASES = [
    ('serious', 'Вспоминаю момент, когда Соня дала понять, что считает наши отношения серьёзными.', ['fact_sonya_serious_intent','thread_sonya_ilya']),
    ('cottage', 'Надо бы разобраться с нашей поездкой за город.', ['fact_cottage_agreed','fact_cottage_booked','scheduled_cottage_trip']),
    ('jealous', 'Что там было с ревностью соседки?', ['fact_katya_jealous','event_katya_jealous','katya']),
    ('negative', 'Как устроен двигатель межпланетного космического аппарата?', []),
]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--model', default=DEFAULT_MODEL)
    parser.add_argument('--threshold', type=float, default=None)
    parser.add_argument('--download', action='store_true')
    args=parser.parse_args()
    import torch
    torch.set_num_threads(int(os.getenv('RPG_EMBEDDING_THREADS','2')))
    from sentence_transformers import SentenceTransformer
    start=time.perf_counter()
    model=SentenceTransformer(args.model,device='cpu',local_files_only=not args.download,trust_remote_code=False)
    load_ms=(time.perf_counter()-start)*1000
    service=SemanticRetriever(model_name=args.model,encoder=model,threshold=args.threshold)
    rows=[]
    for name, query, expected in CASES:
        result=service.search(DOCS,query)
        found={eid for _,eid in result.scores}
        rows.append(dict(case=name, query=query, expected=expected, found=[dict(entity_type=t,entity_id=eid,similarity=score) for (t,eid),score in result.scores.items()],
            recall=None if not expected else len(found & set(expected))/len(expected),
            precision=None if not found else len(found & set(expected))/len(found),
            extra_matches=sorted(found-set(expected)),
            negative_matches=len(found) if not expected else len([eid for eid in found if eid.startswith('negative_')]),
            performance=result.diagnostics))
    warm=[service.search(DOCS,CASES[0][1]).diagnostics['query_ms'] for _ in range(5)]
    from huggingface_hub import snapshot_download
    folder=Path(snapshot_download(args.model,local_files_only=True))
    model_bytes=sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())
    print(json.dumps(dict(model=args.model,device='cpu',threads=torch.get_num_threads(),load_ms=round(load_ms,2),
        warm_query_median_ms=statistics.median(warm),peak_rss_mib=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,2),
        cached_model_mib=round(model_bytes/1024**2,2),cases=rows),ensure_ascii=False,indent=2))


if __name__=='__main__': main()
