"""Renders the REQUIREMENTS.md section 5.1 worked-example evidence pack to
eval/results/report_example.html, so the owner can open it in a browser.
No Gemini calls, no Firestore -- pure offline rendering from engine output.
"""
from pathlib import Path

from backend.report import render_trip_report
from engine.earnings import compute_trip_summary
from engine.models import CostInputs, TripInput

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "eval" / "results" / "report_example.html"


def main():
    trips = [
        TripInput(base_pay=80.0, incentive=20.0, tip=10.0, deductions=[10.0], total_payout=100.0, distance_km=5.0, duration_min=25.0),
        TripInput(base_pay=60.0, distance_km=3.0, duration_min=15.0),
    ]
    summary = compute_trip_summary(trips, CostInputs(fuel_cost_per_km=3.0, maintenance_cost_per_km=1.0), logged_in_hours=1.5)
    trip_rows = [
        {"deductions": [{"label": "Platform fee", "amount": 10.0}]},
        {"deductions": []},
    ]
    html = render_trip_report(summary, trip_rows)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
