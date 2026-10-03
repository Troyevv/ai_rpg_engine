"""Actual request stages, scoped by game/request; no estimated completion percentages."""

from collections import OrderedDict
from functools import wraps
from threading import Lock


class RequestProgress:
    def __init__(self):
        self.lock = Lock()
        self.values = OrderedDict()

    def set(self, gid, request_id, stage):
        with self.lock:
            key = (gid, request_id)
            self.values[key] = stage
            self.values.move_to_end(key)
            while len(self.values) > 512:
                self.values.popitem(last=False)

    def get(self, gid, request_id):
        with self.lock:
            return {"stage": self.values.get((gid, request_id), "waiting")}

    def tracked(self, fn):
        @wraps(fn)
        def wrapped(gid, body):
            self.set(gid, body.request_id, "validation")
            try:
                result = fn(gid, body)
                self.set(gid, body.request_id, "complete")
                return result
            except Exception:
                self.set(gid, body.request_id, "failed")
                raise

        return wrapped
