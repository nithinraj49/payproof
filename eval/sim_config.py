"""Fixed values for the simulator (REQUIREMENTS.md section 12). Changing any of
these changes every generated image and ground-truth file, so keep them here,
not scattered through generate_data.py.
"""

SEED = 20261006  # fixed seed: everything the simulator produces is repeatable
HARD_SEED = 20261007  # separate fixed seed for the "hard" tier, so it never disturbs the original 30 images

IMAGE_SIZE = (480, 960)  # a plausible phone-screenshot canvas, portrait

FONT_REGULAR = "eval/assets/fonts/NotoSans-Regular.ttf"
FONT_BOLD = "eval/assets/fonts/NotoSans-Bold.ttf"

# Fictional platform names only (CLAUDE.md hard rule 4). Checked against
# REAL_PLATFORM_DENY_LIST before any file is written.
FICTIONAL_PLATFORMS = ["ZipGo", "TownHop", "QuickDash", "RideWave", "GoFleet"]

# Real gig/rider platform names (and close variants) that must never appear in
# any generated brand, label or filename.
REAL_PLATFORM_DENY_LIST = [
    "uber", "ola", "olacabs", "rapido", "swiggy", "zomato", "dunzo", "porter",
    "indrive", "blusmart", "meru", "zepto", "blinkit", "lyft", "doordash",
    "grab", "gojek", "careem", "didi", "bolt", "shadowfax", "delhivery",
    "amazon flex", "instamart", "bigbasket", "urban company",
]

CURRENCY = "INR"

# --- Value ranges (section 12) ---
DISTANCE_KM_RANGE = (0.5, 12.0)
WAITING_MIN_RANGE = (1.0, 6.0)  # added on top of distance-derived minutes
MIN_PER_KM = 3.0  # rough minutes-per-km before the waiting term, for plausible durations

BASE_PAY_FIXED = 25.0  # flat component of base pay
BASE_PAY_PER_KM_RANGE = (8.0, 14.0)  # per-km rate with random variation

TIP_CHANCE = 0.3
TIP_RANGE = (10.0, 40.0)

INCENTIVE_CHANCE = 0.35
INCENTIVE_RANGE = (10.0, 60.0)

DEDUCTION_CHANCE = 0.4
DEDUCTION_RANGE = (5.0, 20.0)
DEDUCTION_LABELS = ["Platform fee", "Cancellation fee", "Convenience fee"]

OMIT_DISTANCE_SHARE = 0.2  # share of trip_detail images that omit distance_km
OMIT_MINUTES_SHARE = 0.2  # share of trip_detail images that omit duration_min

# --- Weekly payout (L3) ranges ---
WEEKLY_LINE_LABELS = ["Order earnings", "Daily incentive", "Peak hour bonus"]
WEEKLY_LINE_AMOUNT_RANGE = (1500.0, 9000.0)
WEEKLY_LINES_COUNT_RANGE = (1, 3)
WEEKLY_DEDUCTION_CHANCE = 0.5
WEEKLY_DEDUCTION_RANGE = (100.0, 500.0)

# --- Order offer (N1) ranges, rejected: expected earning is not pay ---
EXPECTED_EARNING_RANGE = (40.0, 150.0)
PICKUP_DISTANCE_KM_RANGE = (0.5, 4.0)
DROP_DISTANCE_KM_RANGE = (1.0, 10.0)
FICTIONAL_STREETS = [
    "12 Lotus Avenue", "45 Riverside Block", "8 Maple Court", "21 Harbor Lane",
    "33 Willow Terrace", "5 Cedar Crossing",
]

# --- Noise profiles applied after rendering ---
NOISE_PROFILES = ["none", "blur", "tilt", "crop", "jpeg_low", "low_brightness"]
DARK_MODE_SHARE = 0.25

JPEG_QUALITY_NORMAL = 90
JPEG_QUALITY_LOW = 40
