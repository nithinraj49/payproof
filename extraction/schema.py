"""Data contract for Gemini extraction output (REQUIREMENTS.md section 4.1).

Gemini never does arithmetic: this schema only ever holds copied-from-screen
values plus the needs_review/low_confidence_fields flags. engine/ computes
everything else.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

ScreenType = Literal["trip_detail", "trip_list", "payout_summary", "order_offer", "other"]

# Constrained to the actual Trip/PayoutSummary field names (added after the Phase 2
# hard-tier evaluation found the model sometimes wrote human labels like "Base pay"
# or "Date" here instead of the schema field name). response_schema enforcement means
# Gemini can no longer emit anything outside this list; extraction/extract.py's
# normalizer is a backstop for any output produced before this change, or any model
# that still doesn't comply.
TripField = Literal[
    "trip_date", "order_id", "order_type", "base_pay", "incentive", "tip",
    "total_payout", "distance_km", "duration_min",
]
PayoutField = Literal["period_label", "period_start", "period_end", "total_credited", "credited_on"]


class Deduction(BaseModel):
    label: str = Field(description="Deduction name exactly as shown")
    amount: float = Field(ge=0, description="Positive number")


class Trip(BaseModel):
    trip_date: Optional[str] = Field(None, description="YYYY-MM-DD only if fully visible")
    order_id: Optional[str] = None
    order_type: Optional[str] = None
    base_pay: Optional[float] = Field(None, ge=0)
    incentive: Optional[float] = Field(None, ge=0)
    tip: Optional[float] = Field(None, ge=0)
    deductions: List[Deduction] = []
    total_payout: Optional[float] = Field(None, ge=0)
    distance_km: Optional[float] = Field(None, ge=0)
    duration_min: Optional[float] = Field(None, ge=0)
    low_confidence_fields: List[TripField] = []


class PayoutLine(BaseModel):
    label: str = Field(description="Earning or incentive name exactly as shown")
    amount: float = Field(ge=0)


class PayoutSummary(BaseModel):
    period_label: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    lines: List[PayoutLine] = []
    deductions: List[Deduction] = []
    total_credited: Optional[float] = Field(None, ge=0)
    credited_on: Optional[str] = None
    low_confidence_fields: List[PayoutField] = []


class ExtractionResult(BaseModel):
    platform_label: Optional[str] = None
    currency: Optional[str] = None
    language_detected: Optional[str] = None
    screen_type: ScreenType
    trips: List[Trip] = []
    payout_summary: Optional[PayoutSummary] = None
    needs_review: bool
    notes: Optional[str] = Field(None, description="Short reason when the screen is rejected")
