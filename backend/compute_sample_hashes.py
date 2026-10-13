"""Run `python -m backend.compute_sample_hashes` whenever frontend/samples/*.jpg
changes, or IMAGE_MAX_SIDE_PX / IMAGE_JPEG_QUALITY change, or the Pillow
version changes -- all three change the prepared image bytes, and therefore
the SHA-256 that backend/sample_images.py's allow-list checks against.

Prints the hashes; paste them into SAMPLE_IMAGE_HASHES by hand. Kept as an
explicit, reviewable constant rather than something computed from files at
request time, since frontend/ is not copied into the Cloud Run container
(see Dockerfile) and a server-computed allow-list from untrusted input would
defeat the point of an allow-list.
"""
import pathlib

from backend.config import get_settings
from backend.extraction_cache import hash_image
from extraction.image_prep import prepare_image

SAMPLES_DIR = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "samples"


def main() -> None:
    settings = get_settings()
    print(f"IMAGE_MAX_SIDE_PX={settings.image_max_side_px} IMAGE_JPEG_QUALITY={settings.image_jpeg_quality}")
    for path in sorted(SAMPLES_DIR.glob("*.jpg")):
        prepared = prepare_image(path.read_bytes(), settings.image_max_side_px, settings.image_jpeg_quality)
        print(path.name, hash_image(prepared))


if __name__ == "__main__":
    main()
