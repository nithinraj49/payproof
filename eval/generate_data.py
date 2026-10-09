"""Simulated earnings-screen generator (REQUIREMENTS.md sections 3, 4.1, 12).

"Simulate" means we invent the trip or week first, then draw a screen for it
ourselves, so the right answer is known in advance. Fictional platforms only;
no real app's logo, colours, wording or layout is copied. No Gemini calls.

Layouts (Phase 2 step A, per ROADMAP.md Solo overrides): L1 trip detail,
L3 weekly payout, N1 order offer (must be rejected). L2 and N2 are not built
yet.

Usage (PowerShell):
    python -m eval.generate_data
"""
import io
import json
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from eval import sim_config as cfg
from extraction.schema import Deduction, ExtractionResult, PayoutLine, PayoutSummary, Trip

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "eval" / "generated"
IMAGES_DIR = OUT_DIR / "images"
GROUND_TRUTH_DIR = OUT_DIR / "ground_truth"

REFERENCE_DATE = date(2026, 10, 1)

LIGHT_BG = (255, 255, 255)
LIGHT_FG = (20, 20, 20)
LIGHT_MUTED = (110, 110, 110)
DARK_BG = (24, 24, 27)
DARK_FG = (235, 235, 235)
DARK_MUTED = (160, 160, 160)
ACCENT = (0, 122, 86)
NEGATIVE = (178, 34, 34)


def check_deny_list(text: str) -> None:
    """Raise if text matches any real platform name (CLAUDE.md hard rule 4)."""
    lowered = text.lower()
    for banned in cfg.REAL_PLATFORM_DENY_LIST:
        if banned in lowered:
            raise ValueError(f"Refusing to use {text!r}: matches real platform deny list ({banned!r})")


def fonts(size_title: int = 26, size_body: int = 18, size_small: int = 14):
    return {
        "title": ImageFont.truetype(str(ROOT / cfg.FONT_BOLD), size_title),
        "body": ImageFont.truetype(str(ROOT / cfg.FONT_REGULAR), size_body),
        "body_bold": ImageFont.truetype(str(ROOT / cfg.FONT_BOLD), size_body),
        "small": ImageFont.truetype(str(ROOT / cfg.FONT_REGULAR), size_small),
    }


def money(amount: float) -> str:
    return f"₹{amount:,.2f}"


@dataclass
class Palette:
    bg: tuple
    fg: tuple
    muted: tuple


def palette(dark: bool) -> Palette:
    if dark:
        return Palette(DARK_BG, DARK_FG, DARK_MUTED)
    return Palette(LIGHT_BG, LIGHT_FG, LIGHT_MUTED)


def new_canvas(dark: bool):
    pal = palette(dark)
    image = Image.new("RGB", cfg.IMAGE_SIZE, pal.bg)
    draw = ImageDraw.Draw(image)
    return image, draw, pal


def draw_header(draw, pal: Palette, f, app_name: str, title: str):
    draw.rectangle([(0, 0), (cfg.IMAGE_SIZE[0], 70)], fill=ACCENT)
    draw.text((20, 14), app_name, font=f["title"], fill=(255, 255, 255))
    draw.text((20, 44), title, font=f["small"], fill=(230, 245, 240))


def draw_row(draw, pal: Palette, f, y: int, label: str, value: str, bold: bool = False, color=None):
    font = f["body_bold"] if bold else f["body"]
    draw.text((20, y), label, font=f["body"], fill=pal.muted)
    text_color = color if color is not None else pal.fg
    w = draw.textlength(value, font=font)
    draw.text((cfg.IMAGE_SIZE[0] - 20 - w, y), value, font=font, fill=text_color)


def draw_divider(draw, pal: Palette, y: int):
    draw.line([(20, y), (cfg.IMAGE_SIZE[0] - 20, y)], fill=pal.muted, width=1)


# --- L1: trip detail ---

def build_trip(rng: random.Random, omit_distance: bool, omit_minutes: bool):
    distance_km = round(rng.uniform(*cfg.DISTANCE_KM_RANGE), 1)
    duration_min = round(distance_km * cfg.MIN_PER_KM + rng.uniform(*cfg.WAITING_MIN_RANGE))
    base_pay = round(cfg.BASE_PAY_FIXED + distance_km * rng.uniform(*cfg.BASE_PAY_PER_KM_RANGE), 2)
    incentive = round(rng.uniform(*cfg.INCENTIVE_RANGE), 2) if rng.random() < cfg.INCENTIVE_CHANCE else None
    tip = round(rng.uniform(*cfg.TIP_RANGE), 2) if rng.random() < cfg.TIP_CHANCE else None
    deductions = []
    if rng.random() < cfg.DEDUCTION_CHANCE:
        deductions.append(Deduction(label=rng.choice(cfg.DEDUCTION_LABELS), amount=round(rng.uniform(*cfg.DEDUCTION_RANGE), 2)))
    gross = base_pay + (incentive or 0) + (tip or 0)
    total_payout = round(gross - sum(d.amount for d in deductions), 2)
    trip_date = REFERENCE_DATE - timedelta(days=rng.randint(0, 29))
    order_id = f"ORD-{rng.randint(10000, 99999)}"
    order_type = rng.choice(["Food delivery", "Parcel delivery", "Passenger ride"])

    trip = Trip(
        trip_date=trip_date.isoformat(),
        order_id=order_id,
        order_type=order_type,
        base_pay=base_pay,
        incentive=incentive,
        tip=tip,
        deductions=deductions,
        total_payout=total_payout,
        distance_km=None if omit_distance else distance_km,
        duration_min=None if omit_minutes else duration_min,
        low_confidence_fields=[],
    )
    return trip


def render_trip_detail(rng: random.Random, dark: bool):
    platform = rng.choice(cfg.FICTIONAL_PLATFORMS)
    check_deny_list(platform)
    omit_distance = rng.random() < cfg.OMIT_DISTANCE_SHARE
    omit_minutes = rng.random() < cfg.OMIT_MINUTES_SHARE
    trip = build_trip(rng, omit_distance, omit_minutes)

    image, draw, pal = new_canvas(dark)
    f = fonts()
    draw_header(draw, pal, f, platform, "Trip complete")

    y = 100
    draw_row(draw, pal, f, y, "Date", trip.trip_date); y += 30
    draw_row(draw, pal, f, y, "Order", f"{trip.order_type} · {trip.order_id}"); y += 40
    draw_divider(draw, pal, y); y += 20

    draw_row(draw, pal, f, y, "Base pay", money(trip.base_pay)); y += 30
    if trip.incentive is not None:
        draw_row(draw, pal, f, y, "Incentive", money(trip.incentive)); y += 30
    if trip.tip is not None:
        draw_row(draw, pal, f, y, "Tip", money(trip.tip)); y += 30
    for d in trip.deductions:
        draw_row(draw, pal, f, y, d.label, f"-{money(d.amount)}", color=NEGATIVE); y += 30

    y += 10
    draw_divider(draw, pal, y); y += 20
    draw_row(draw, pal, f, y, "Total payout", money(trip.total_payout), bold=True); y += 50

    if trip.distance_km is not None or trip.duration_min is not None:
        parts = []
        if trip.distance_km is not None:
            parts.append(f"{trip.distance_km:g} km")
        if trip.duration_min is not None:
            parts.append(f"{trip.duration_min:g} min")
        draw.text((20, y), " · ".join(parts), font=f["small"], fill=pal.muted)

    ground_truth = ExtractionResult(
        platform_label=platform,
        currency=cfg.CURRENCY,
        language_detected="en",
        screen_type="trip_detail",
        trips=[trip],
        payout_summary=None,
        needs_review=False,
        notes=None,
    )
    meta = {"layout": "L1", "omit_distance": omit_distance, "omit_minutes": omit_minutes}
    return image, ground_truth, meta


# --- H1: trip detail, "hard" tier (small font, heavy blur, low resolution, a
# number partly cropped off) — generation only; REQUIREMENTS.md section 13's
# own evaluation gate still applies before any Gemini call is made on these. ---

def render_trip_detail_hard(rng: random.Random, dark: bool):
    platform = rng.choice(cfg.FICTIONAL_PLATFORMS)
    check_deny_list(platform)
    omit_distance = rng.random() < cfg.OMIT_DISTANCE_SHARE
    omit_minutes = rng.random() < cfg.OMIT_MINUTES_SHARE
    trip = build_trip(rng, omit_distance, omit_minutes)

    image, draw, pal = new_canvas(dark)
    f = fonts(size_title=18, size_body=11, size_small=9)  # small font
    draw_header(draw, pal, f, platform, "Trip complete")

    y = 90
    draw_row(draw, pal, f, y, "Date", trip.trip_date); y += 20
    draw_row(draw, pal, f, y, "Order", f"{trip.order_type} · {trip.order_id}"); y += 26
    draw_divider(draw, pal, y); y += 14

    draw_row(draw, pal, f, y, "Base pay", money(trip.base_pay)); y += 20
    if trip.incentive is not None:
        draw_row(draw, pal, f, y, "Incentive", money(trip.incentive)); y += 20
    if trip.tip is not None:
        draw_row(draw, pal, f, y, "Tip", money(trip.tip)); y += 20
    for d in trip.deductions:
        draw_row(draw, pal, f, y, d.label, f"-{money(d.amount)}", color=NEGATIVE); y += 20

    y += 6
    draw_divider(draw, pal, y); y += 14
    total_row_y = y  # remembered so the crop step can cut exactly through this number
    draw_row(draw, pal, f, y, "Total payout", money(trip.total_payout), bold=True); y += 32

    if trip.distance_km is not None or trip.duration_min is not None:
        parts = []
        if trip.distance_km is not None:
            parts.append(f"{trip.distance_km:g} km")
        if trip.duration_min is not None:
            parts.append(f"{trip.duration_min:g} min")
        draw.text((20, y), " · ".join(parts), font=f["small"], fill=pal.muted)

    ground_truth = ExtractionResult(
        platform_label=platform,
        currency=cfg.CURRENCY,
        language_detected="en",
        screen_type="trip_detail",
        trips=[trip],
        payout_summary=None,
        needs_review=False,
        notes=None,
    )
    meta = {"layout": "H1", "omit_distance": omit_distance, "omit_minutes": omit_minutes, "total_row_y": total_row_y}
    return image, ground_truth, meta


def apply_hard_noise(image: Image.Image, dark: bool, total_row_y: int, rng: random.Random) -> Image.Image:
    """Stacks heavy blur, a low-resolution round-trip, and a crop through the
    total payout row — deliberately harder than any single profile in
    apply_noise(), to avoid the ceiling effect seen on the first 30 images."""
    fill = DARK_BG if dark else LIGHT_BG

    # Low resolution: downscale a lot, then upscale back, baking in blockiness.
    small = image.resize((image.width // 4, image.height // 4), Image.BILINEAR)
    image = small.resize(image.size, Image.NEAREST)

    # Heavy blur on top of the pixelation.
    image = image.filter(ImageFilter.GaussianBlur(radius=rng.uniform(3.0, 5.0)))

    # Partly crop the total payout row: keep only its top half, replace the rest
    # of the screen below it with background so the number is visibly cut off.
    cut_at = total_row_y + rng.randint(8, 14)
    canvas = Image.new(image.mode, image.size, fill)
    canvas.paste(image.crop((0, 0, image.width, cut_at)), (0, 0))
    return canvas


def generate_hard_tier(n: int = 10):
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    GROUND_TRUTH_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(cfg.HARD_SEED)

    manifest_path = OUT_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else []

    new_entries = []
    for i in range(1, n + 1):
        name = f"H1_{i:03d}"
        dark = rng.random() < cfg.DARK_MODE_SHARE
        image, ground_truth, meta = render_trip_detail_hard(rng, dark)
        image = apply_hard_noise(image, dark, meta.pop("total_row_y"), rng)

        image_path = IMAGES_DIR / f"{name}.jpg"
        save_jpeg(image, image_path, cfg.JPEG_QUALITY_NORMAL)
        gt_path = GROUND_TRUTH_DIR / f"{name}.json"
        gt_path.write_text(ground_truth.model_dump_json(indent=2))

        new_entries.append({
            "name": name,
            "image": str(image_path.relative_to(ROOT)).replace("\\", "/"),
            "ground_truth": str(gt_path.relative_to(ROOT)).replace("\\", "/"),
            "dark_mode": dark,
            "noise": "hard",
            **meta,
        })

    manifest = [e for e in manifest if not e["name"].startswith("H1_")] + new_entries
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return new_entries


# --- M1: trip detail, "moderate" tier — one mild degradation each, a human
# should still be able to read every digit. Generation only here; readability
# is confirmed by viewing sample images before any Gemini call (not by code). ---

MODERATE_DEGRADATIONS = ["smaller_font", "light_blur", "mild_jpeg", "partial_crop"]


def render_trip_detail_moderate(rng: random.Random, dark: bool, degradation: str):
    platform = rng.choice(cfg.FICTIONAL_PLATFORMS)
    check_deny_list(platform)
    omit_distance = rng.random() < cfg.OMIT_DISTANCE_SHARE
    omit_minutes = rng.random() < cfg.OMIT_MINUTES_SHARE
    trip = build_trip(rng, omit_distance, omit_minutes)

    image, draw, pal = new_canvas(dark)
    if degradation == "smaller_font":
        f = fonts(size_title=22, size_body=15, size_small=12)
    else:
        f = fonts()
    header_bottom_y = 70  # the header bar's own height; partial_crop cuts into this, never into row data
    draw_header(draw, pal, f, platform, "Trip complete")

    y = 100
    draw_row(draw, pal, f, y, "Date", trip.trip_date); y += 30
    draw_row(draw, pal, f, y, "Order", f"{trip.order_type} · {trip.order_id}"); y += 40
    draw_divider(draw, pal, y); y += 20

    draw_row(draw, pal, f, y, "Base pay", money(trip.base_pay)); y += 30
    if trip.incentive is not None:
        draw_row(draw, pal, f, y, "Incentive", money(trip.incentive)); y += 30
    if trip.tip is not None:
        draw_row(draw, pal, f, y, "Tip", money(trip.tip)); y += 30
    for d in trip.deductions:
        draw_row(draw, pal, f, y, d.label, f"-{money(d.amount)}", color=NEGATIVE); y += 30

    y += 10
    draw_divider(draw, pal, y); y += 20
    draw_row(draw, pal, f, y, "Total payout", money(trip.total_payout), bold=True); y += 50

    if trip.distance_km is not None or trip.duration_min is not None:
        parts = []
        if trip.distance_km is not None:
            parts.append(f"{trip.distance_km:g} km")
        if trip.duration_min is not None:
            parts.append(f"{trip.duration_min:g} min")
        draw.text((20, y), " · ".join(parts), font=f["small"], fill=pal.muted)

    ground_truth = ExtractionResult(
        platform_label=platform,
        currency=cfg.CURRENCY,
        language_detected="en",
        screen_type="trip_detail",
        trips=[trip],
        payout_summary=None,
        needs_review=False,
        notes=None,
    )
    meta = {"layout": "M1", "omit_distance": omit_distance, "omit_minutes": omit_minutes,
            "degradation": degradation, "header_bottom_y": header_bottom_y}
    return image, ground_truth, meta


def apply_moderate_degradation(image: Image.Image, degradation: str, dark: bool, header_bottom_y: int, rng: random.Random) -> tuple:
    """Returns (image, jpeg_quality). Exactly one mild degradation, chosen so
    every number stays fully legible."""
    if degradation == "smaller_font":
        return image, cfg.JPEG_QUALITY_NORMAL
    if degradation == "light_blur":
        return image.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.8, 1.2))), cfg.JPEG_QUALITY_NORMAL
    if degradation == "mild_jpeg":
        return image, 60  # noticeably compressed, well above the "hard" tier's 40
    if degradation == "partial_crop":
        # Crops into the header bar only (platform name/title) -- never into a data
        # row, so every number and label stays fully visible.
        fill = DARK_BG if dark else LIGHT_BG
        cut = rng.randint(15, 30)
        canvas = Image.new(image.mode, image.size, fill)
        canvas.paste(image.crop((0, cut, image.width, image.height)), (0, cut))
        return canvas, cfg.JPEG_QUALITY_NORMAL
    raise ValueError(f"Unknown moderate degradation: {degradation}")


def generate_moderate_tier(n: int = 10):
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    GROUND_TRUTH_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(cfg.MODERATE_SEED)

    manifest_path = OUT_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else []

    new_entries = []
    for i in range(1, n + 1):
        name = f"M1_{i:03d}"
        dark = rng.random() < cfg.DARK_MODE_SHARE
        degradation = MODERATE_DEGRADATIONS[(i - 1) % len(MODERATE_DEGRADATIONS)]
        image, ground_truth, meta = render_trip_detail_moderate(rng, dark, degradation)
        image, quality = apply_moderate_degradation(image, degradation, dark, meta.pop("header_bottom_y"), rng)

        image_path = IMAGES_DIR / f"{name}.jpg"
        save_jpeg(image, image_path, quality)
        gt_path = GROUND_TRUTH_DIR / f"{name}.json"
        gt_path.write_text(ground_truth.model_dump_json(indent=2))

        new_entries.append({
            "name": name,
            "image": str(image_path.relative_to(ROOT)).replace("\\", "/"),
            "ground_truth": str(gt_path.relative_to(ROOT)).replace("\\", "/"),
            "dark_mode": dark,
            "noise": "moderate",
            **meta,
        })

    manifest = [e for e in manifest if not e["name"].startswith("M1_")] + new_entries
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return new_entries


# --- L3: weekly payout ---

def render_weekly_payout(rng: random.Random, dark: bool):
    platform = rng.choice(cfg.FICTIONAL_PLATFORMS)
    check_deny_list(platform)

    period_start = REFERENCE_DATE - timedelta(days=rng.randint(0, 5), weeks=rng.randint(0, 3))
    period_end = period_start + timedelta(days=6)
    period_label = f"{period_start:%d %b} - {period_end:%d %b}"

    n_lines = rng.randint(*cfg.WEEKLY_LINES_COUNT_RANGE)
    labels = rng.sample(cfg.WEEKLY_LINE_LABELS, n_lines)
    lines = [PayoutLine(label=label, amount=round(rng.uniform(*cfg.WEEKLY_LINE_AMOUNT_RANGE), 2)) for label in labels]

    deductions = []
    if rng.random() < cfg.WEEKLY_DEDUCTION_CHANCE:
        deductions.append(Deduction(label="Platform charges", amount=round(rng.uniform(*cfg.WEEKLY_DEDUCTION_RANGE), 2)))

    gross = sum(line.amount for line in lines)
    total_credited = round(gross - sum(d.amount for d in deductions), 2)
    credited_on = (period_end + timedelta(days=1)).isoformat()

    image, draw, pal = new_canvas(dark)
    f = fonts()
    draw_header(draw, pal, f, platform, "Weekly payout")

    y = 100
    draw.text((20, y), period_label, font=f["body_bold"], fill=pal.fg); y += 40
    draw_divider(draw, pal, y); y += 20

    for line in lines:
        draw_row(draw, pal, f, y, line.label, money(line.amount)); y += 30
    for d in deductions:
        draw_row(draw, pal, f, y, d.label, f"-{money(d.amount)}", color=NEGATIVE); y += 30

    y += 10
    draw_divider(draw, pal, y); y += 20
    draw_row(draw, pal, f, y, "Total credited", money(total_credited), bold=True); y += 40
    draw.text((20, y), f"Credited on {credited_on}", font=f["small"], fill=pal.muted)

    payout_summary = PayoutSummary(
        period_label=period_label,
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
        lines=lines,
        deductions=deductions,
        total_credited=total_credited,
        credited_on=credited_on,
        low_confidence_fields=[],
    )
    ground_truth = ExtractionResult(
        platform_label=platform,
        currency=cfg.CURRENCY,
        language_detected="en",
        screen_type="payout_summary",
        trips=[],
        payout_summary=payout_summary,
        needs_review=False,
        notes=None,
    )
    meta = {"layout": "L3"}
    return image, ground_truth, meta


# --- N1: order offer (must be rejected) ---

def render_order_offer(rng: random.Random, dark: bool):
    platform = rng.choice(cfg.FICTIONAL_PLATFORMS)
    check_deny_list(platform)
    expected_earning = round(rng.uniform(*cfg.EXPECTED_EARNING_RANGE), 2)
    pickup_km = round(rng.uniform(*cfg.PICKUP_DISTANCE_KM_RANGE), 1)
    drop_km = round(rng.uniform(*cfg.DROP_DISTANCE_KM_RANGE), 1)
    pickup_place = rng.choice(cfg.FICTIONAL_STREETS)
    check_deny_list(pickup_place)
    order_type = rng.choice(["Food delivery", "Parcel delivery", "Passenger ride"])

    image, draw, pal = new_canvas(dark)
    f = fonts()
    draw_header(draw, pal, f, platform, "New order request")

    y = 110
    draw.text((20, y), order_type, font=f["body"], fill=pal.muted); y += 36
    draw.text((20, y), f"Expected earning {money(expected_earning)}", font=f["title"], fill=ACCENT); y += 50
    draw_row(draw, pal, f, y, "Pickup distance", f"{pickup_km:g} km"); y += 30
    draw_row(draw, pal, f, y, "Drop distance", f"{drop_km:g} km"); y += 30
    draw.text((20, y), pickup_place, font=f["body"], fill=pal.fg); y += 60

    button_y = cfg.IMAGE_SIZE[1] - 120
    draw.rectangle([(20, button_y), (220, button_y + 50)], outline=pal.muted, width=2)
    draw.text((85, button_y + 15), "Reject", font=f["body_bold"], fill=pal.fg)
    draw.rectangle([(260, button_y), (cfg.IMAGE_SIZE[0] - 20, button_y + 50)], fill=ACCENT)
    draw.text((320, button_y + 15), "Accept", font=f["body_bold"], fill=(255, 255, 255))

    ground_truth = ExtractionResult(
        platform_label=platform,
        currency=cfg.CURRENCY,
        language_detected="en",
        screen_type="order_offer",
        trips=[],
        payout_summary=None,
        needs_review=False,
        notes="Order offer: an expected earning is a promise, not confirmed pay.",
    )
    meta = {"layout": "N1"}
    return image, ground_truth, meta


# --- Noise ---

def apply_noise(image: Image.Image, profile: str, dark: bool, rng: random.Random):
    if profile == "none":
        return image
    if profile == "blur":
        return image.filter(ImageFilter.GaussianBlur(radius=rng.uniform(1.0, 2.5)))
    if profile == "tilt":
        fill = DARK_BG if dark else LIGHT_BG
        angle = rng.uniform(-6, 6)
        return image.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=fill)
    if profile == "crop":
        fill = DARK_BG if dark else LIGHT_BG
        percent = rng.uniform(0.05, 0.15)
        side = rng.choice(["top", "bottom"])
        h = image.height
        cut = int(h * percent)
        canvas = Image.new(image.mode, image.size, fill)
        if side == "bottom":
            kept = image.crop((0, 0, image.width, h - cut))
            canvas.paste(kept, (0, 0))
        else:
            kept = image.crop((0, cut, image.width, h))
            canvas.paste(kept, (0, cut))
        return canvas
    if profile == "low_brightness":
        return ImageEnhance.Brightness(image).enhance(rng.uniform(0.45, 0.7))
    if profile == "jpeg_low":
        return image  # quality is applied at save time
    raise ValueError(f"Unknown noise profile: {profile}")


def save_jpeg(image: Image.Image, path: Path, quality: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=quality)
    path.write_bytes(buf.getvalue())


def generate(n_l1: int = 15, n_l3: int = 10, n_n1: int = 5):
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    GROUND_TRUTH_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(cfg.SEED)

    manifest = []
    jobs = [("L1", render_trip_detail)] * n_l1 + [("L3", render_weekly_payout)] * n_l3 + [("N1", render_order_offer)] * n_n1
    counters = {"L1": 0, "L3": 0, "N1": 0}

    for layout, renderer in jobs:
        counters[layout] += 1
        name = f"{layout}_{counters[layout]:03d}"

        dark = rng.random() < cfg.DARK_MODE_SHARE
        image, ground_truth, meta = renderer(rng, dark)

        noise_profile = rng.choice(cfg.NOISE_PROFILES)
        image = apply_noise(image, noise_profile, dark, rng)
        quality = cfg.JPEG_QUALITY_LOW if noise_profile == "jpeg_low" else cfg.JPEG_QUALITY_NORMAL

        image_path = IMAGES_DIR / f"{name}.jpg"
        save_jpeg(image, image_path, quality)

        gt_path = GROUND_TRUTH_DIR / f"{name}.json"
        gt_path.write_text(ground_truth.model_dump_json(indent=2))

        manifest.append({
            "name": name,
            "image": str(image_path.relative_to(ROOT)).replace("\\", "/"),
            "ground_truth": str(gt_path.relative_to(ROOT)).replace("\\", "/"),
            "dark_mode": dark,
            "noise": noise_profile,
            **meta,
        })

    manifest_path = OUT_DIR / "manifest.json"
    existing_other_tiers = []
    if manifest_path.exists():
        existing_other_tiers = [e for e in json.loads(manifest_path.read_text()) if e["name"].startswith(("H1_", "M1_"))]
    manifest_path.write_text(json.dumps(manifest + existing_other_tiers, indent=2))
    return manifest


if __name__ == "__main__":
    import sys

    if "--hard" in sys.argv:
        entries = generate_hard_tier()
        print(f"Generated {len(entries)} hard-tier images in {IMAGES_DIR} (names H1_001..H1_{len(entries):03d})")
        for entry in entries:
            print(f"  {entry['name']}: dark={entry['dark_mode']} noise={entry['noise']}")
    elif "--moderate" in sys.argv:
        entries = generate_moderate_tier()
        print(f"Generated {len(entries)} moderate-tier images in {IMAGES_DIR} (names M1_001..M1_{len(entries):03d})")
        for entry in entries:
            print(f"  {entry['name']}: dark={entry['dark_mode']} degradation={entry['degradation']}")
    else:
        manifest = generate()
        print(f"Generated {len(manifest)} images in {IMAGES_DIR} with ground truth in {GROUND_TRUTH_DIR}")
        for entry in manifest[:6]:
            print(f"  {entry['name']}: layout={entry['layout']} dark={entry['dark_mode']} noise={entry['noise']}")
