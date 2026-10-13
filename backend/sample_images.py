"""Server-side allow-list of the curated sample images (frontend/samples/).

A client-sent `is_sample` flag must never be trusted to decide usage-limit
or cache behaviour: anyone could set it on an arbitrary image to skip their
daily extraction limit (and the global cap) and to write arbitrary content
into the shared sample cache. Instead, POST /api/extract (backend/main.py)
computes the SHA-256 of the *prepared* image (resized + re-encoded exactly
as extraction/image_prep.prepare_image produces, at the server's own
IMAGE_MAX_SIDE_PX/IMAGE_JPEG_QUALITY settings -- never the raw upload bytes)
and only takes the sample path if that hash is in SAMPLE_IMAGE_HASHES below.

Regenerate this list with `python -m backend.compute_sample_hashes` whenever
frontend/samples/*.jpg changes, or IMAGE_MAX_SIDE_PX / IMAGE_JPEG_QUALITY
change, or the Pillow version changes (all three change the prepared bytes,
and therefore the hash). tests/test_sample_images.py recomputes these
hashes from the real files on every test run and fails loudly if this list
goes stale, so a silent mismatch can't ship unnoticed.

Computed 13 Oct 2026 against IMAGE_MAX_SIDE_PX=1280, IMAGE_JPEG_QUALITY=85
(current defaults in backend/config.py, .env.example and deploy/env.yaml).
"""
SAMPLE_IMAGE_HASHES = frozenset({
    "6f271d5a62e23e91211ec53a5318d15995c9e50dd128eca2ead924cb2fbe499e",  # frontend/samples/trip.jpg
    "a8bfe1d23588c1cb9d35e8f7de61f73c7e38a8ad5e0a7631ff096cd3aa161e12",  # frontend/samples/weekly.jpg
    "75ef8a4f304faf1ef55fd49f2bf7e3e0d72568b3314d16ceeaa782ebd80d72f9",  # frontend/samples/order_offer.jpg
})
