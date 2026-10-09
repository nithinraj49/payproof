"""Deterministic image-quality gate, in plain code, before any Gemini call
(REQUIREMENTS.md section 19). A failing image never reaches Gemini — zero
cost — and returns a needs_review result asking for a retake.

No new dependency: uses only Pillow (already required), via ImageStat and
ImageFilter.FIND_EDGES as a crude edge-energy proxy for sharpness. This is
not a real focus-detection algorithm; it is tuned empirically on the 30
simulated standard images (so none of them are blocked) and is NOT validated
on real screenshots. See PROGRESS.md for what it does and does not catch:
it reliably catches very dark, heavily blurred images (the eval's dark
hard-tier images), but pixelation/JPEG-block artifacts on a bright image can
inflate this sharpness measure, so it does NOT catch every illegible image
(the eval's light hard-tier images pass it despite being unreadable).
"""
import io
from dataclasses import dataclass
from typing import Optional

from PIL import Image, ImageFilter, ImageStat


@dataclass
class QualityCheckResult:
    passed: bool
    reason: Optional[str] = None  # too_small, too_blurry, low_contrast, too_dark, too_bright


def check_image_quality(
    raw_bytes: bytes,
    min_short_side_px: int,
    min_sharpness: float,
    min_contrast: float,
    min_brightness: float,
    max_brightness: float,
) -> QualityCheckResult:
    image = Image.open(io.BytesIO(raw_bytes)).convert("L")
    width, height = image.size
    if min(width, height) < min_short_side_px:
        return QualityCheckResult(False, "too_small")

    edges = image.filter(ImageFilter.FIND_EDGES)
    sharpness = ImageStat.Stat(edges).stddev[0]
    if sharpness < min_sharpness:
        return QualityCheckResult(False, "too_blurry")

    stat = ImageStat.Stat(image)
    brightness = stat.mean[0]
    contrast = stat.stddev[0]

    if contrast < min_contrast:
        return QualityCheckResult(False, "low_contrast")
    if brightness < min_brightness:
        return QualityCheckResult(False, "too_dark")
    if brightness > max_brightness:
        return QualityCheckResult(False, "too_bright")

    return QualityCheckResult(True)


QUALITY_MESSAGES = {
    "too_small": "This image is too small to read. Please retake this screenshot at full size.",
    "too_blurry": "This image looks too blurry to read. Please retake this screenshot in focus.",
    "low_contrast": "This image has too little contrast to read. Please retake this screenshot.",
    "too_dark": "This image is too dark to read. Please retake this screenshot with more light.",
    "too_bright": "This image is too bright/washed out to read. Please retake this screenshot.",
}
