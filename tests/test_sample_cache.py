"""Tests for backend/sample_cache.py. Firestore is a fake in-memory stand-in;
no network calls."""
from backend.sample_cache import get_cached_sample, set_cached_sample
from extraction.schema import ExtractionResult


class _FakeDoc:
    def __init__(self, data=None):
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return self._data


class _FakeDocRef:
    def __init__(self, store, key):
        self._store = store
        self._key = key

    def get(self):
        return _FakeDoc(self._store.get(self._key))

    def set(self, data):
        self._store[self._key] = data


class _FakeCollection:
    def __init__(self, store):
        self._store = store

    def document(self, key):
        return _FakeDocRef(self._store, key)


class _FakeDb:
    def __init__(self):
        self._collections = {}

    def collection(self, name):
        return _FakeCollection(self._collections.setdefault(name, {}))


def test_cache_miss_returns_none():
    db = _FakeDb()
    assert get_cached_sample("somehash", db=db) is None


def test_set_then_get_round_trips():
    db = _FakeDb()
    result = ExtractionResult(screen_type="trip_detail", needs_review=False)
    set_cached_sample("abc123", result, db=db)
    cached = get_cached_sample("abc123", db=db)
    assert cached is not None
    assert cached.screen_type == "trip_detail"
    assert cached.needs_review is False


def test_different_hashes_are_independent():
    db = _FakeDb()
    r1 = ExtractionResult(screen_type="trip_detail", needs_review=False)
    r2 = ExtractionResult(screen_type="payout_summary", needs_review=True)
    set_cached_sample("hash1", r1, db=db)
    set_cached_sample("hash2", r2, db=db)
    assert get_cached_sample("hash1", db=db).screen_type == "trip_detail"
    assert get_cached_sample("hash2", db=db).screen_type == "payout_summary"
