"""Caches extraction results by image hash for the current process/session
(REQUIREMENTS.md section 19 rule 5). In memory only, never the image itself —
only its hash and the already-computed ExtractionResult. A bounded FIFO so a
long-running instance can't grow this without limit.
"""
import hashlib
from collections import OrderedDict

from extraction.schema import ExtractionResult

_MAX_ENTRIES = 500
_cache: "OrderedDict[str, ExtractionResult]" = OrderedDict()


def hash_image(jpeg_bytes: bytes) -> str:
    return hashlib.sha256(jpeg_bytes).hexdigest()


def get_cached(image_hash: str) -> ExtractionResult | None:
    return _cache.get(image_hash)


def set_cached(image_hash: str, result: ExtractionResult) -> None:
    _cache[image_hash] = result
    _cache.move_to_end(image_hash)
    while len(_cache) > _MAX_ENTRIES:
        _cache.popitem(last=False)
