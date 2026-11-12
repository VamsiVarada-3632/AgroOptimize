"""Small TTL cache for repository reads (official data changes at most daily)."""
from __future__ import annotations
import functools, time
from typing import Callable

_REGISTRY: list = []

def ttl_cache(seconds: float = 3600.0) -> Callable:
    def deco(fn):
        store: dict = {}
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            key = (a, tuple(sorted(kw.items())))
            hit = store.get(key)
            now = time.monotonic()
            if hit and now - hit[0] < seconds:
                return hit[1]
            val = fn(*a, **kw)
            store[key] = (now, val)
            return val
        wrapper.cache_clear = store.clear
        _REGISTRY.append(wrapper)
        return wrapper
    return deco

def clear_all() -> None:
    for w in _REGISTRY:
        w.cache_clear()
