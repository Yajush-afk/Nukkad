"""Bounded process-local memoisation; callers always receive independent values."""

from collections import OrderedDict
from copy import deepcopy
from threading import RLock


class RevisionCache:
    def __init__(self, capacity=8):
        self.capacity = capacity
        self.values = OrderedDict()
        self.lock = RLock()

    def get(self, namespace, revision, build):
        key = (namespace, revision)
        with self.lock:
            if key not in self.values:
                self.values[key] = build()
                while len(self.values) > self.capacity:
                    self.values.popitem(last=False)
            self.values.move_to_end(key)
            return deepcopy(self.values[key])
