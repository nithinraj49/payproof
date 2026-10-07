"""Image preparation before any Gemini call (REQUIREMENTS.md section 19 rule 3).

Resize to at most IMAGE_MAX_SIDE_PX on the longest side, re-encode as JPEG at
IMAGE_JPEG_QUALITY, and strip metadata. In memory only — never written to disk.
"""
import io

from PIL import Image


def prepare_image(raw_bytes: bytes, max_side_px: int, jpeg_quality: int) -> bytes:
    image = Image.open(io.BytesIO(raw_bytes))
    image = image.convert("RGB")  # drops alpha/ICC profile and any EXIF metadata

    longest_side = max(image.size)
    if longest_side > max_side_px:
        scale = max_side_px / longest_side
        new_size = (round(image.width * scale), round(image.height * scale))
        image = image.resize(new_size, Image.LANCZOS)

    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=jpeg_quality)  # no exif= kwarg: metadata is stripped
    return buf.getvalue()
