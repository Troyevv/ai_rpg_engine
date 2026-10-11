"""Local, rebuildable relevance only. Never owns or mutates canonical records."""
from collections import OrderedDict, Counter
from dataclasses import dataclass, field
from hashlib import sha256
import logging
import os
from threading import RLock
from time import perf_counter, monotonic

BASELINE_MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
DEFAULT_MODEL = 'intfloat/multilingual-e5-small'
LIMITS = {'facts': 12, 'threads': 4, 'history_events': 8, 'locations': 3, 'characters': 6, 'scheduled_events': 4}
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Document:
    entity_type: str
    entity_id: str
    text: str

    @property
    def key(self):
        return self.entity_type, self.entity_id, sha256(self.text.encode()).hexdigest()


@dataclass
class Retrieval:
    scores: dict = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)


def documents(snapshot, history=None):
    state = snapshot['world_state']
    for kind, fields in {'facts': ('text',), 'threads': ('description', 'state'),
                         'locations': ('name', 'description'),
                         'scheduled_events': ('description', 'condition')}.items():
        for eid, row in sorted(state[kind].items()):
            yield Document(kind, eid, '\n'.join(str(row.get(k, '')) for k in fields))
    for card in sorted(snapshot['character_cards'], key=lambda c: c['id']):
        from backend.runtime_v3.personality import project_card
        card = project_card(card, state['characters'][card['id']])
        fields = card.get('fields', {})
        text = '\n'.join([card['name'], *card.get('aliases', []),
                          *(fields.get(k, '') for k in ('Роль', 'Характер', 'Стиль общения'))])
        yield Document('characters', card['id'], text)
    for row in (history or {}).get('events', []):
        if isinstance(row, dict) and isinstance(row.get('id'), str) and isinstance(row.get('text'), str):
            yield Document('history_events', row['id'], row['text'])


class SemanticRetriever:
    """Lazy CPU encoder + bounded process cache; active index is the supplied documents.

    Deleted/rolled-back entries are immediately inactive. Content-addressed LRU rows
    may be reused after rollback, but can never become candidates on their own.
    All model/cache access is locked so concurrent saves cannot corrupt the cache.
    """
    def __init__(self, model_name=None, encoder=None, threshold=None, capacity=30000):
        self.model_name = model_name or os.getenv('RPG_EMBEDDING_MODEL', DEFAULT_MODEL)
        self.encoder = encoder
        self.threshold = float(os.getenv('RPG_SEMANTIC_THRESHOLD', '0.785' if 'multilingual-e5' in self.model_name else '0.30')) if threshold is None else threshold
        self.capacity = capacity
        self.cache = OrderedDict()
        self.lock = RLock()
        self.retry_after = 0
        self.failure = None

    def _model(self):
        if self.encoder is None:
            import torch
            torch.set_num_threads(max(1, int(os.getenv('RPG_EMBEDDING_THREADS', '2'))))
            from sentence_transformers import SentenceTransformer
            self.encoder = SentenceTransformer(self.model_name, device='cpu', local_files_only=True,
                                               trust_remote_code=False)
        return self.encoder

    def _encode(self, encoder, texts, query=False):
        # E5's documented asymmetric prefixes apply equally to Russian text.
        default = ('query: ' if query else 'passage: ') if 'multilingual-e5' in self.model_name else ''
        prefix = os.getenv('RPG_EMBEDDING_QUERY_PREFIX' if query else 'RPG_EMBEDDING_DOCUMENT_PREFIX', default)
        return encoder.encode([prefix+t for t in texts], normalize_embeddings=True,
                              convert_to_numpy=True, show_progress_bar=False)

    def search(self, docs, query):
        start = perf_counter()
        docs = list(docs)
        stats = dict(model=self.model_name, threshold=self.threshold, indexed_documents=len(docs), cache_hits=0,
                     cache_misses=0, rebuilt_embeddings=0, candidate_counts={}, build_ms=0, query_ms=0)
        with self.lock:
            if monotonic() < self.retry_after:
                return Retrieval(diagnostics=dict(stats, status='fallback', error=self.failure))
            try:
                if not docs or not query.strip():
                    return Retrieval(diagnostics=dict(stats, status='empty'))
                import numpy as np
                encoder = self._model()
                missing = [d for d in docs if d.key not in self.cache]
                stats.update(cache_hits=len(docs)-len(missing), cache_misses=len(missing))
                vectors = {}
                # Batch explicitly; do not build an unbounded intermediate tensor.
                for offset in range(0, len(missing), 64):
                    batch = missing[offset:offset+64]
                    values = self._encode(encoder, [d.text for d in batch])
                    for doc, vector in zip(batch, values):
                        vectors[doc.key] = vector
                rows = [vectors.get(d.key) if d.key in vectors else self.cache[d.key] for d in docs]
                matrix = np.asarray(rows, dtype=np.float32)
                if matrix.ndim != 2 or len(matrix) != len(docs) or not np.isfinite(matrix).all():
                    raise ValueError('invalid document embeddings')
                for doc, vector in zip(docs, rows):
                    self.cache[doc.key] = vector
                    self.cache.move_to_end(doc.key)
                while len(self.cache) > self.capacity: self.cache.popitem(last=False)
                stats['rebuilt_embeddings'] = len(missing)
                stats['build_ms'] = round((perf_counter()-start)*1000, 3)
                query_start = perf_counter()
                q = np.asarray(self._encode(encoder, [query], query=True), dtype=np.float32)[0]
                scores = matrix @ q
                if not np.isfinite(scores).all(): raise ValueError('invalid query embedding')
                gap = float(os.getenv('RPG_SEMANTIC_MAX_GAP', '0.06' if 'multilingual-e5' in self.model_name else '0.20'))
                effective_threshold = max(self.threshold, float(scores.max())-gap)
                stats['effective_threshold'] = round(effective_threshold, 6)
                found, counts = {}, Counter()
                for i in sorted(range(len(docs)), key=lambda i: (-float(scores[i]), docs[i].entity_type, docs[i].entity_id)):
                    doc = docs[i]; score = float(scores[i])
                    if score < effective_threshold or counts[doc.entity_type] >= LIMITS.get(doc.entity_type, 0): continue
                    found[(doc.entity_type, doc.entity_id)] = round(score, 6)
                    counts[doc.entity_type] += 1
                stats.update(status='ok', query_ms=round((perf_counter()-query_start)*1000, 3),
                             total_ms=round((perf_counter()-start)*1000, 3), candidate_counts=dict(counts))
                return Retrieval(found, stats)
            except Exception as exc:
                # No text, embeddings or credentials in error diagnostics.
                self.failure = type(exc).__name__
                self.retry_after = monotonic()+60
                log.warning('Semantic retrieval unavailable (%s); structural fallback', self.failure)
                return Retrieval(diagnostics=dict(stats, status='fallback', error=self.failure,
                                                   total_ms=round((perf_counter()-start)*1000, 3)))


_service = None
_service_lock = RLock()


def retrieve(snapshot, history, query):
    if os.getenv('RPG_SEMANTIC_ENABLED', '1') == '0':
        return Retrieval(diagnostics=dict(status='disabled', indexed_documents=0))
    global _service
    with _service_lock:
        if _service is None: _service = SemanticRetriever()
    return _service.search(documents(snapshot, history), query)
