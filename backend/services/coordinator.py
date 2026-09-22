"""Process-local resource scheduling, shared by game, preparation and model management."""
import threading
from contextlib import contextmanager

LOCAL_MODEL_LOCK = threading.Lock()

@contextmanager
def model_lease(provider):
    if provider == 'local':
        with LOCAL_MODEL_LOCK:
            yield
    else:
        yield
