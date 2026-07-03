"""Provider reconciliation for A-share market data quality checks."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from quant_signal_system.contracts.market import MarketBar


@dataclass(frozen=True, slots=True)
class ReconciliationIssue:
    severity: str
    issue_type: str
    symbol: str
    timeframe: str
    market_data_time: str
    detail: str


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    left_provider: str
    right_provider: str
    compared_count: int
    issues: tuple[ReconciliationIssue, ...]

    @property
    def is_clean(self) -> bool:
        return not self.issues


class MarketDataReconciler:
    def compare_bars(
        self,
        *,
        left_provider: str,
        right_provider: str,
        left: list[MarketBar],
        right: list[MarketBar],
        price_tolerance: Decimal = Decimal("0"),
        volume_tolerance: Decimal = Decimal("0"),
    ) -> ReconciliationReport:
        left_by_key = {(bar.symbol, bar.timeframe, bar.market_data_time): bar for bar in left}
        right_by_key = {(bar.symbol, bar.timeframe, bar.market_data_time): bar for bar in right}
        issues: list[ReconciliationIssue] = []

        all_keys = sorted(set(left_by_key) | set(right_by_key), key=lambda key: key[2])
        compared_count = 0
        for key in all_keys:
            lbar = left_by_key.get(key)
            rbar = right_by_key.get(key)
            symbol, timeframe, market_data_time = key
            iso_time = market_data_time.isoformat()
            if lbar is None:
                issues.append(
                    ReconciliationIssue(
                        "ERROR",
                        "MISSING_LEFT",
                        symbol,
                        timeframe,
                        iso_time,
                        f"{left_provider} missing bar",
                    )
                )
                continue
            if rbar is None:
                issues.append(
                    ReconciliationIssue(
                        "ERROR",
                        "MISSING_RIGHT",
                        symbol,
                        timeframe,
                        iso_time,
                        f"{right_provider} missing bar",
                    )
                )
                continue

            compared_count += 1
            self._compare_field(
                issues,
                lbar,
                rbar,
                "open_price",
                price_tolerance,
                left_provider,
                right_provider,
            )
            self._compare_field(
                issues,
                lbar,
                rbar,
                "high_price",
                price_tolerance,
                left_provider,
                right_provider,
            )
            self._compare_field(
                issues,
                lbar,
                rbar,
                "low_price",
                price_tolerance,
                left_provider,
                right_provider,
            )
            self._compare_field(
                issues,
                lbar,
                rbar,
                "close_price",
                price_tolerance,
                left_provider,
                right_provider,
            )
            self._compare_field(
                issues,
                lbar,
                rbar,
                "volume",
                volume_tolerance,
                left_provider,
                right_provider,
            )
            if lbar.timeframe != rbar.timeframe:
                self._add_issue(issues, lbar, "TIMEFRAME_MISMATCH", "timeframe mismatch")

        return ReconciliationReport(
            left_provider=left_provider,
            right_provider=right_provider,
            compared_count=compared_count,
            issues=tuple(issues),
        )

    def _compare_field(
        self,
        issues: list[ReconciliationIssue],
        left: MarketBar,
        right: MarketBar,
        field_name: str,
        tolerance: Decimal,
        left_provider: str,
        right_provider: str,
    ) -> None:
        left_value = getattr(left, field_name)
        right_value = getattr(right, field_name)
        if left_value is None or right_value is None:
            if left_value != right_value:
                self._add_issue(
                    issues,
                    left,
                    f"{field_name.upper()}_MISMATCH",
                    f"{left_provider}={left_value}, {right_provider}={right_value}",
                )
            return

        if abs(left_value - right_value) > tolerance:
            self._add_issue(
                issues,
                left,
                f"{field_name.upper()}_MISMATCH",
                f"{left_provider}={left_value}, {right_provider}={right_value}",
            )

    def _add_issue(
        self,
        issues: list[ReconciliationIssue],
        bar: MarketBar,
        issue_type: str,
        detail: str,
    ) -> None:
        issues.append(
            ReconciliationIssue(
                severity="WARN",
                issue_type=issue_type,
                symbol=bar.symbol,
                timeframe=bar.timeframe,
                market_data_time=bar.market_data_time.isoformat(),
                detail=detail,
            )
        )

