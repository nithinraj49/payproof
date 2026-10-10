"""Offline comparison of three change-signal estimators (no Gemini calls).

Tests on:
  Set 1: 20 histories × 20 trips/period  — from eval/histories/
  Set 2: 20 histories × 50 trips/period  — generated here (ASSUMPTION: N=50)

Three estimators:
  (a) Mean of per-trip net_payout_per_km  [current implementation]
  (b) Ratio of sums (total_net_payout / total_km) with bootstrap over trips
  (c) OLS slope of net_payout ~ distance_km per period, bootstrap over trips
"""
import json
import random
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from eval import sim_config as cfg

ROOT = Path(__file__).resolve().parent.parent
HISTORIES_DIR = ROOT / "eval" / "histories"

_BOOTSTRAP_N = 10_000
_BOOTSTRAP_SEED = 20261006
_MIN_TRIPS = 15
_THRESHOLD = 0.05


# ---------------------------------------------------------------------------
# Trip helpers
# ---------------------------------------------------------------------------

def _net_payout(t: dict) -> float:
    return (
        (t.get("base_pay") or 0.0)
        + (t.get("incentive") or 0.0)
        + (t.get("tip") or 0.0)
        - sum(d["amount"] for d in t.get("deductions", []) if isinstance(d, dict))
    )


def _ratios(trips):
    return [
        _net_payout(t) / t["distance_km"]
        for t in trips
        if t.get("distance_km") and t["distance_km"] > 0
    ]


def _pairs(trips):
    return [
        (_net_payout(t), t["distance_km"])
        for t in trips
        if t.get("distance_km") and t["distance_km"] > 0
    ]


# ---------------------------------------------------------------------------
# Estimator (a): mean of per-trip ratios  [current engine]
# ---------------------------------------------------------------------------

def est_a(baseline, recent):
    bv = _ratios(baseline)
    rv = _ratios(recent)
    if len(bv) < _MIN_TRIPS or len(rv) < _MIN_TRIPS:
        return "insufficient_data"
    bmean, rmean = np.mean(bv), np.mean(rv)
    if bmean == 0:
        return "insufficient_data"
    rel = (rmean - bmean) / abs(bmean)
    rng = random.Random(_BOOTSTRAP_SEED)
    diffs = sorted(
        np.mean([rng.choice(rv) for _ in range(len(rv))]) -
        np.mean([rng.choice(bv) for _ in range(len(bv))])
        for _ in range(_BOOTSTRAP_N)
    )
    lo, hi = diffs[int(0.025 * _BOOTSTRAP_N)], diffs[int(0.975 * _BOOTSTRAP_N) - 1]
    ci_excl = hi < 0 or lo > 0
    return "possible_change" if ci_excl and abs(rel) >= _THRESHOLD else "no_clear_change"


# ---------------------------------------------------------------------------
# Estimator (b): ratio of sums with bootstrap over trips
# ---------------------------------------------------------------------------

def _ros(pairs):
    sp = sum(p for p, _ in pairs)
    sd = sum(d for _, d in pairs)
    return sp / sd if sd > 0 else None


def est_b(baseline, recent):
    bp = _pairs(baseline)
    rp = _pairs(recent)
    if len(bp) < _MIN_TRIPS or len(rp) < _MIN_TRIPS:
        return "insufficient_data"
    bm, rm = _ros(bp), _ros(rp)
    if bm is None or bm == 0:
        return "insufficient_data"
    rel = (rm - bm) / abs(bm)
    rng = random.Random(_BOOTSTRAP_SEED)
    diffs = []
    for _ in range(_BOOTSTRAP_N):
        sb = [rng.choice(bp) for _ in range(len(bp))]
        sr = [rng.choice(rp) for _ in range(len(rp))]
        rb, rr = _ros(sb), _ros(sr)
        if rb and rr:
            diffs.append(rr - rb)
    diffs.sort()
    n = len(diffs)
    lo, hi = diffs[int(0.025 * n)], diffs[int(0.975 * n) - 1]
    ci_excl = hi < 0 or lo > 0
    return "possible_change" if ci_excl and abs(rel) >= _THRESHOLD else "no_clear_change"


# ---------------------------------------------------------------------------
# Estimator (c): OLS slope of net_payout ~ distance_km, bootstrap over trips
# ---------------------------------------------------------------------------

def _slope(pairs):
    x = np.array([p[0] for p in pairs])
    y = np.array([p[1] for p in pairs])
    if len(x) < 2 or np.std(x) == 0:
        return None
    return float(np.polyfit(x, y, 1)[0])


def est_c(baseline, recent):
    bp = [(t["distance_km"], _net_payout(t)) for t in baseline
          if t.get("distance_km") and t["distance_km"] > 0]
    rp = [(t["distance_km"], _net_payout(t)) for t in recent
          if t.get("distance_km") and t["distance_km"] > 0]
    if len(bp) < _MIN_TRIPS or len(rp) < _MIN_TRIPS:
        return "insufficient_data"
    bs, rs = _slope(bp), _slope(rp)
    if bs is None or bs == 0:
        return "insufficient_data"
    rel = (rs - bs) / abs(bs)
    rng = random.Random(_BOOTSTRAP_SEED)
    diffs = []
    for _ in range(_BOOTSTRAP_N):
        sb = [rng.choice(bp) for _ in range(len(bp))]
        sr = [rng.choice(rp) for _ in range(len(rp))]
        ss, sr_ = _slope(sb), _slope(sr)
        if ss is not None and sr_ is not None:
            diffs.append(sr_ - ss)
    diffs.sort()
    n = len(diffs)
    lo, hi = diffs[int(0.025 * n)], diffs[int(0.975 * n) - 1]
    ci_excl = hi < 0 or lo > 0
    return "possible_change" if ci_excl and abs(rel) >= _THRESHOLD else "no_clear_change"


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate(histories, label):
    counts = {e: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for e in "abc"}
    for baseline, recent, injected in histories:
        for name, fn in [("a", est_a), ("b", est_b), ("c", est_c)]:
            status = fn(baseline, recent)
            pos = status == "possible_change"
            if injected and pos:
                counts[name]["tp"] += 1
            elif injected and not pos:
                counts[name]["fn"] += 1
            elif not injected and pos:
                counts[name]["fp"] += 1
            else:
                counts[name]["tn"] += 1

    n = len(histories)
    n_pos = sum(1 for _, _, inj in histories if inj)
    n_neg = n - n_pos
    print(f"\n{'=' * 62}")
    print(f"  {label}")
    print(f"  n={n}  ({n_pos} with 10% cut, {n_neg} stable)  [SIMULATED]")
    print(f"{'=' * 62}")
    print(f"  {'Estimator':<16} {'Prec':>6} {'Rec':>6} {'FA':>6}   TP  FP  FN  TN")
    print(f"  {'-' * 58}")
    for name in "abc":
        r = counts[name]
        prec = r["tp"] / (r["tp"] + r["fp"]) if r["tp"] + r["fp"] > 0 else float("nan")
        rec  = r["tp"] / n_pos if n_pos > 0 else float("nan")
        fa   = r["fp"] / n_neg if n_neg > 0 else float("nan")
        desc = {"a": "(a) mean-ratio   ", "b": "(b) sum-ratio    ", "c": "(c) ols-slope   "}[name]
        print(f"  {desc}  {prec:5.3f}  {rec:5.3f}  {fa:5.3f}  {r['tp']:3}{r['fp']:4}{r['fn']:4}{r['tn']:4}")
    return counts


# ---------------------------------------------------------------------------
# Generate set 2: 50 trips/period
# ---------------------------------------------------------------------------

def _make_trip(rng, rate, is_recent, reference):
    km = round(rng.uniform(*cfg.DISTANCE_KM_RANGE), 2)
    base = round(cfg.BASE_PAY_FIXED + km * rate, 2)
    inc = round(rng.uniform(*cfg.INCENTIVE_RANGE), 2) if rng.random() < cfg.INCENTIVE_CHANCE else None
    tip = round(rng.uniform(*cfg.TIP_RANGE), 2) if rng.random() < cfg.TIP_CHANCE else None
    ded = round(rng.uniform(*cfg.DEDUCTION_RANGE), 2) if rng.random() < cfg.DEDUCTION_CHANCE else 0.0
    gross = base + (inc or 0) + (tip or 0)
    payout = round(gross - ded, 2)
    offset = rng.randint(1, 21) if is_recent else rng.randint(22, 42)
    d = (reference - timedelta(days=offset)).isoformat()
    return {
        "trip_date": d, "date_confirmed": True,
        "base_pay": base, "incentive": inc, "tip": tip,
        "deductions": [{"label": "Fee", "amount": ded}] if ded > 0 else [],
        "total_payout": payout, "distance_km": km,
        "duration_min": round(km * cfg.MIN_PER_KM + rng.uniform(*cfg.WAITING_MIN_RANGE)),
    }


def generate_set2(n=20, trips_per_period=50):
    rng = random.Random(20261099)
    baseline_rate = (cfg.BASE_PAY_PER_KM_RANGE[0] + cfg.BASE_PAY_PER_KM_RANGE[1]) / 2
    reference = date(2026, 10, 1)
    histories = []
    for i in range(1, n + 1):
        injected = i > n // 2
        recent_rate = baseline_rate * 0.9 if injected else baseline_rate
        baseline = [_make_trip(rng, baseline_rate, False, reference) for _ in range(trips_per_period)]
        recent   = [_make_trip(rng, recent_rate, True, reference) for _ in range(trips_per_period)]
        histories.append((baseline, recent, injected))
    return histories


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Loading set 1: 20 histories × 20 trips/period (from eval/histories/)")
    index = json.loads((HISTORIES_DIR / "index.json").read_text())
    set1 = []
    for entry in index:
        path = ROOT / entry["path"]
        h = json.loads(path.read_text())
        trips = h["trips"]
        split = h["split_date"]
        injected = h["injected_cut"]
        baseline = [t for t in trips if t["trip_date"] < split and t["date_confirmed"]]
        recent   = [t for t in trips if t["trip_date"] >= split and t["date_confirmed"]]
        set1.append((baseline, recent, injected))
    evaluate(set1, "Set 1: 20 histories × 20 trips/period")

    print("\nGenerating set 2: 20 histories × 50 trips/period (ASSUMPTION: N=50)")
    set2 = generate_set2(n=20, trips_per_period=50)
    evaluate(set2, "Set 2: 20 histories × 50 trips/period  [ASSUMPTION]")
