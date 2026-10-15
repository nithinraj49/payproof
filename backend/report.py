"""Evidence pack: a plain, self-contained HTML page (REQUIREMENTS.md section
8). No external resources (no CSS/JS files, no fonts, no images) -- opens
and prints correctly offline, even with no network. Every piece of text the
worker (or Gemini, copying from a screenshot) supplied -- a deduction or
payout line label -- is HTML-escaped before being placed in the page. No
names, phone numbers or addresses appear here because none are ever
extracted or stored (REQUIREMENTS.md section 11).

Every figure uses the same currency symbol and the same plain-language label
as the Q&A (backend.qa.GLOSSARY, backend.qa.DEFAULT_CURRENCY) -- found
necessary after a live deploy check showed the report's numbers were bare
(no currency, no unit) while the Q&A's answers already said "₹192.00 per
engaged hour". There is nowhere yet to store a worker's own currency (trips/
costs carry no currency field), so this defaults to the same DEFAULT_CURRENCY
as the Q&A -- not a per-user choice.
"""
import datetime
import html as html_lib
from typing import Any, Dict, List, Optional

from backend.qa import CURRENCY_SYMBOLS, DEFAULT_CURRENCY, GLOSSARY
from engine.earnings import _RECONCILIATION_TOLERANCE
from engine.models import TripReconciliation, TripSummary, WeeklySummary

_CURRENCY_SYMBOL = CURRENCY_SYMBOLS[DEFAULT_CURRENCY]

_STYLE = """
body { font-family: system-ui, -apple-system, sans-serif; max-width: 640px; margin: 2rem auto; padding: 0 1rem; color: #111; line-height: 1.5; }
h1 { font-size: 1.4rem; margin-bottom: 0.25rem; }
h2 { font-size: 1.1rem; margin-top: 1.5rem; }
table { width: 100%; border-collapse: collapse; margin: 0.5rem 0 1rem; }
th, td { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #ddd; }
th { font-weight: 600; width: 60%; }
.notes { font-size: 0.9rem; color: #333; }
.recon-warning { font-weight: 700; color: #8a3d00; background: #fff4c2; border: 1px solid #e0a800; border-radius: 6px; padding: 0.6rem 0.75rem; margin: 0 0 1rem; }
.limits { font-size: 0.85rem; color: #333; border-top: 1px solid #ccc; padding-top: 0.75rem; margin-top: 2rem; }
@media print {
  body { margin: 0; max-width: none; color: #000; }
  table { page-break-inside: avoid; }
  h2 { page-break-after: avoid; }
}
"""


def _esc(value: Any) -> str:
    return html_lib.escape(str(value))


def _label(field: str, fallback: str) -> str:
    """The exact plain-language label backend.qa's system prompt and
    _label_violation() use for this field, so the evidence pack and a Q&A
    answer about the same number never disagree on what to call it. Falls
    back to a report-only label for fields the glossary doesn't cover
    (trip/engine internals never shown in an answer, e.g. a reconciliation
    gap or a raw distance/duration total)."""
    text = GLOSSARY.get(field, fallback)
    return text[0].upper() + text[1:]


def _indian_grouped_integer(digits: str) -> str:
    """"123456" -> "1,23,456": last 3 digits form one group, every group
    before that is 2 digits (Indian digit grouping, REQUIREMENTS.md section
    7.2's "1,23,456" example) -- not the Western 3-3-3 grouping."""
    if len(digits) <= 3:
        return digits
    last3 = digits[-3:]
    rest = digits[:-3]
    groups = []
    while len(rest) > 2:
        groups.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        groups.insert(0, rest)
    return ",".join(groups) + "," + last3


def _format_amount(value: float) -> str:
    integer_part, _, decimal_part = f"{value:.2f}".partition(".")
    return f"{_indian_grouped_integer(integer_part)}.{decimal_part}"


def _money(value: Optional[float]) -> str:
    if value is None:
        return "not available"
    sign = "-" if value < 0 else ""
    return f"{sign}{_CURRENCY_SYMBOL}{_format_amount(abs(value))}"


def _rate(value: Optional[float], unit: str) -> str:
    if value is None:
        return "not available"
    return f"{_CURRENCY_SYMBOL}{_format_amount(value)} {unit}"


def _percent(value: Optional[float]) -> str:
    if value is None:
        return "not available"
    return f"{value * 100:.1f}%"


def _distance(value: Optional[float]) -> str:
    if value is None:
        return "not available"
    return f"{value:g} km"


def _duration(value: Optional[float]) -> str:
    if value is None:
        return "not available"
    return f"{value:g} min"


def _count(value: Optional[int]) -> str:
    if value is None:
        return "not available"
    return f"{value:g}"


def _plain(value: Optional[str]) -> str:
    # For a field that is already a complete, human-readable sentence (the
    # per-hour-on-trips-unavailable reason) -- never blank, never a bare number.
    if not value:
        return "not available"
    return value


def _rows_table(rows: List[tuple]) -> str:
    body = "".join(f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>" for k, v in rows)
    return f"<table><tbody>{body}</tbody></table>"


def _label_amount_table(heading: str, items: Dict[str, float]) -> str:
    if not items:
        return ""
    rows = "".join(
        f"<tr><th>{_esc(label)}</th><td>{_esc(_money(round(amount, 2)))}</td></tr>"
        for label, amount in sorted(items.items())
    )
    return f"<h2>{_esc(heading)}</h2><table><tbody>{rows}</tbody></table>"


def _page(title: str, data_source: str, table_html: str, method_html: str, notes_html: str) -> str:
    today = datetime.date.today().isoformat()
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{_esc(title)}</title>
<style>{_STYLE}</style>
</head>
<body>
<h1>PayProof evidence pack</h1>
<p>Generated by PayProof on {today}.<br>Data source: {_esc(data_source)}.</p>
{table_html}
{method_html}
{notes_html}
<div class="limits">
<p>Generated by PayProof. Built only from the screenshots you provided; figures are the worker's own.</p>
<p>PayProof does not verify your identity or your platform account, and does not contact your platform. It reports what you uploaded and the arithmetic performed on it, nothing more.</p>
</div>
</body>
</html>"""


_TRIP_METHOD = """
<h2>Method</h2>
<p>Gross pay is the sum of base pay, incentives and tips across your confirmed trips. Platform deductions are subtracted to get net payout. Your own costs (fuel and maintenance per km, plus any fixed daily cost) are subtracted from net payout to get net earnings. Net earnings is divided by engaged hours (the time you were actually on a trip) and, separately, by logged-in hours (your total time online) to give two different hourly rates, since they measure different things. Net payout is also divided by total distance to give pay per km. Deduction share is platform deductions divided by gross pay.</p>
"""

_WEEKLY_METHOD = """
<h2>Method</h2>
<p>Gross weekly pay is the sum of the earning lines from your weekly payout screenshot. Weekly deductions are subtracted to get net payout. Your own costs (fuel and maintenance per km, plus any fixed daily cost, for the km and days you reported) are subtracted to get net earnings. Net earnings is divided by hours online to give pay per online hour, and net payout is divided by km driven to give pay per km. Pay per trip hour is not available in weekly mode, since a weekly payout screen has no per-trip minutes. Deduction share is weekly deductions divided by gross weekly pay.</p>
"""


def render_trip_report(
    summary: TripSummary,
    trip_rows: List[Dict[str, Any]],
    reconciliation: Optional[List[TripReconciliation]] = None,
) -> str:
    rows = [
        (_label("trip_count", "Trip count"), _count(summary.trip_count)),
        (_label("gross_pay", "Gross pay"), _money(summary.gross_pay)),
        (_label("platform_deductions", "Platform deductions"), _money(summary.platform_deductions)),
        (_label("net_payout", "Net payout"), _money(summary.net_payout)),
        (_label("worker_costs", "Worker costs"), _money(summary.worker_costs)),
        (_label("net_earnings", "Net earnings"), _money(summary.net_earnings)),
        (_label("net_per_engaged_hour", "Net pay per engaged hour"), _rate(summary.net_per_engaged_hour, "per hour on trips")),
        (_label("net_per_logged_in_hour", "Net pay per logged-in hour"), _rate(summary.net_per_logged_in_hour, "per hour online")),
        (_label("net_payout_per_km", "Net pay per km"), _rate(summary.net_payout_per_km, "per km")),
        (_label("deduction_share", "Deduction share"), _percent(summary.deduction_share)),
        ("Total distance", _distance(summary.total_distance_km)),
        ("Total duration", _duration(summary.total_duration_min)),
    ]

    deduction_totals: Dict[str, float] = {}
    for row in trip_rows:
        for d in row.get("deductions") or []:
            label = str(d.get("label") or "Deduction")
            deduction_totals[label] = deduction_totals.get(label, 0.0) + float(d.get("amount") or 0.0)

    notes_html = ""
    if summary.data_quality:
        items = "".join(f"<li>{_esc(n)}</li>" for n in summary.data_quality)
        notes_html = f'<h2>Data-quality notes</h2><ul class="notes">{items}</ul>'

    recon_html = ""
    if reconciliation:
        parts = "".join(
            f"<li>Trip {r.trip_index + 1}: the amounts add up to {_esc(_money(r.computed_total))}, "
            f"but the screenshot says {_esc(_money(r.total_payout))} was paid.</li>"
            for r in reconciliation
        )
        recon_html = (
            '<p class="recon-warning">Some trips do not add up to the total payout shown in the screenshot, '
            f'so figures built from them may be off.</p><ul class="notes">{parts}</ul>'
        )

    table_html = recon_html + _rows_table(rows) + _label_amount_table("Deductions by type", deduction_totals)
    return _page(
        "PayProof evidence pack (trip mode)",
        f"trip mode, {summary.trip_count} confirmed trip(s) you uploaded or entered",
        table_html, _TRIP_METHOD, notes_html,
    )


def render_weekly_report(summary: WeeklySummary, week_row: Dict[str, Any]) -> str:
    rows = [
        (_label("gross_weekly", "Gross weekly pay"), _money(summary.gross_weekly)),
        (_label("deductions_weekly", "Weekly deductions"), _money(summary.deductions_weekly)),
        (_label("net_payout_weekly", "Total credited"), _money(summary.net_payout_weekly)),
        ("Credited total minus the earning lines", _money(summary.reconciliation_gap)),
        (_label("worker_costs_weekly", "Worker costs"), _money(summary.worker_costs_weekly)),
        (_label("net_earnings_weekly", "Net earnings"), _money(summary.net_earnings_weekly)),
        (_label("net_per_online_hour", "Net pay per online hour"), _rate(summary.net_per_online_hour, "per hour online")),
        (_label("net_payout_per_km", "Net pay per km"), _rate(summary.net_payout_per_km, "per km")),
        (_label("deduction_share", "Deduction share"), _percent(summary.deduction_share)),
        ("Net pay per trip hour", _plain(summary.per_hour_on_trips_unavailable)),
    ]

    line_totals: Dict[str, float] = {}
    for line in week_row.get("lines") or []:
        label = str(line.get("label") or "Earning")
        line_totals[label] = line_totals.get(label, 0.0) + float(line.get("amount") or 0.0)

    deduction_totals: Dict[str, float] = {}
    for d in week_row.get("deductions") or []:
        label = str(d.get("label") or "Deduction")
        deduction_totals[label] = deduction_totals.get(label, 0.0) + float(d.get("amount") or 0.0)

    notes_html = ""
    if summary.data_quality:
        items = "".join(f"<li>{_esc(n)}</li>" for n in summary.data_quality)
        notes_html = f'<h2>Data-quality notes</h2><ul class="notes">{items}</ul>'

    recon_html = ""
    if summary.reconciliation_gap is not None and abs(summary.reconciliation_gap) > _RECONCILIATION_TOLERANCE:
        recon_html = (
            f'<p class="recon-warning">Your earning lines do not add up to the credited total: '
            f'net earnings may be understated by about {_esc(_money(abs(summary.reconciliation_gap)))}.</p>'
        )

    table_html = (
        recon_html
        + _rows_table(rows)
        + _label_amount_table("Earning lines", line_totals)
        + _label_amount_table("Deductions by type", deduction_totals)
    )
    period_label = str(week_row.get("period_label") or "your most recently confirmed week")
    return _page(
        "PayProof evidence pack (weekly mode)",
        f"weekly mode, {period_label}",  # _page() escapes the whole data_source string once
        table_html, _WEEKLY_METHOD, notes_html,
    )
