"""Dimension definitions for report bucketing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SignalMetricsDimensions:
    """Dimension keys for SignalMetrics bucketing."""

    strategy_name: str = "strategy_name"
    strategy_version: str = "strategy_version"
    symbol: str = "symbol"
    direction: str = "direction"
    reason_code: str = "reason_code"
    year: str = "year"
    month: str = "month"


@dataclass(frozen=True, slots=True)
class ReportDimensions:
    """Top-level report dimension registry."""

    signal_metrics: SignalMetricsDimensions = SignalMetricsDimensions()
