"""Guards against the sample-image allow-list (backend/sample_images.py)
going stale. Reads the real frontend/samples/*.jpg files from disk and
recomputes their prepared-image hash the same way backend/main.py does, so
a changed sample image, a changed IMAGE_MAX_SIDE_PX/IMAGE_JPEG_QUALITY, or a
Pillow version bump that shifts JPEG re-encoding output is caught here
instead of silently falling back to being treated as an unknown (non-sample)
upload in production. No network calls.
"""
import pathlib

from backend.config import get_settings
from backend.extraction_cache import hash_image
from backend.sample_images import SAMPLE_IMAGE_HASHES
from extraction.image_prep import prepare_image

SAMPLES_DIR = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "samples"


def test_every_curated_sample_image_hash_is_allow_listed():
    settings = get_settings()
    image_paths = sorted(SAMPLES_DIR.glob("*.jpg"))
    assert len(image_paths) > 0, "expected curated sample images under frontend/samples/"

    for path in image_paths:
        prepared = prepare_image(path.read_bytes(), settings.image_max_side_px, settings.image_jpeg_quality)
        actual_hash = hash_image(prepared)
        assert actual_hash in SAMPLE_IMAGE_HASHES, (
            f"{path.name}'s prepared-image hash is not in backend.sample_images.SAMPLE_IMAGE_HASHES -- "
            "regenerate with `python -m backend.compute_sample_hashes` and update that file."
        )


def test_allow_list_has_no_unused_hashes():
    settings = get_settings()
    real_hashes = {
        hash_image(prepare_image(path.read_bytes(), settings.image_max_side_px, settings.image_jpeg_quality))
        for path in SAMPLES_DIR.glob("*.jpg")
    }
    assert SAMPLE_IMAGE_HASHES == real_hashes, (
        "backend.sample_images.SAMPLE_IMAGE_HASHES contains a hash that doesn't match any current "
        "file in frontend/samples/ -- remove stale entries (an old sample image's hash left behind "
        "after it was replaced would still be treated as a valid sample)."
    )
