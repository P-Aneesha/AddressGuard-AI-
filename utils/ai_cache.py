"""Small in-process cache for successful LLM responses.

LLM output can vary between calls even at temperature 0. Caching the first
successful response per input keeps repeated validations of the same address
consistent for the lifetime of the server process. Failures are never cached,
so a temporary outage is retried on the next request.
"""
import copy
from collections import OrderedDict
from threading import Lock


class ResultCache:
    def __init__(self, max_items=256):
        self._items = OrderedDict()
        self._max = max_items
        self._lock = Lock()

    def get(self, key):
        with self._lock:
            if key not in self._items:
                return None
            self._items.move_to_end(key)
            return copy.deepcopy(self._items[key])

    def put(self, key, value):
        with self._lock:
            self._items[key] = copy.deepcopy(value)
            self._items.move_to_end(key)
            while len(self._items) > self._max:
                self._items.popitem(last=False)

    def clear(self):
        with self._lock:
            self._items.clear()
