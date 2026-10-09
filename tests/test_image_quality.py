"""Tests for the deterministic image-quality gate (extraction/image_quality.py).
Pure PIL code, no Gemini calls, no network."""
import io

from PIL import Image

from extraction.image_quality import check_image_quality

THRESHOLDS = dict(min_short_side_px=300, min_sharpness=3.9, min_contrast=10.0, min_brightness=15.0, max_brightness=254.0)


def make_jpeg(size=(480, 960), color=(128, 128, 128), noise_pattern=False) -> bytes:
    image = Image.new("RGB", size, color)
    if noise_pattern:
        pixels = image.load()
        for x in range(0, size[0], 4):
            for y in range(0, size[1], 4):
                pixels[x, y] = (255, 255, 255) if (x + y) % 8 == 0 else (0, 0, 0)
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def test_sharp_normal_image_passes():
    raw = make_jpeg(noise_pattern=True, color=(130, 130, 130))
    result = check_image_quality(raw, **THRESHOLDS)
    assert result.passed is True


def test_too_small_image_fails():
    raw = make_jpeg(size=(100, 150), noise_pattern=True)
    result = check_image_quality(raw, **THRESHOLDS)
    assert result.passed is False
    assert result.reason == "too_small"


def test_uniform_flat_image_fails_on_blur_or_contrast():
    # A perfectly flat color image has zero edges and zero contrast: must fail.
    raw = make_jpeg(color=(128, 128, 128), noise_pattern=False)
    result = check_image_quality(raw, **THRESHOLDS)
    assert result.passed is False
    assert result.reason in ("too_blurry", "low_contrast")


def test_too_dark_image_fails():
    raw = make_jpeg(color=(2, 2, 2), noise_pattern=True)
    result = check_image_quality(raw, **THRESHOLDS)
    assert result.passed is False
    assert result.reason in ("too_dark", "too_blurry", "low_contrast")


def test_too_bright_image_fails():
    raw = make_jpeg(color=(255, 255, 255), noise_pattern=False)
    result = check_image_quality(raw, **THRESHOLDS)
    assert result.passed is False
    assert result.reason in ("too_bright", "too_blurry", "low_contrast")
