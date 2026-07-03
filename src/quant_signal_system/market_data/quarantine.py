"""Quarantine records for invalid, conflicting, or untrusted market data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping


@dataclass(frozen=True, slots=True)
class QuarantineRecord:
    provider: str
    reason_code: str
    reason_detail: str
    raw_payload: Mapping[str, object]
    data_source_version: str
    as_of_version: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

