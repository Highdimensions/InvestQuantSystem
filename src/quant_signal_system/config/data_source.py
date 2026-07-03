"""Data source profiles for provider isolation and auditability."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ProviderTier(StrEnum):
    """Planned provider role in the first A-share data-source rollout."""

    EXPLORATION = "tier0_exploration"
    RESEARCH_BASELINE = "tier1_research_baseline"
    STABLE_SHADOW_CANDIDATE = "tier2_stable_shadow_candidate"
    BROKER_TERMINAL = "tier3_broker_terminal"


@dataclass(frozen=True, slots=True)
class DataSourceProfile:
    """Versioned profile for one external market data source.

    The profile is intentionally separate from any vendor SDK so strategies only
    see normalized contracts and reproducible data version keys.
    """

    provider: str
    market: str
    frequency: str
    adjustment: str
    permission_level: str
    data_source_version: str
    as_of_version: str
    tier: ProviderTier
    license_notes: str
    retention_policy: str
    can_store_raw: bool = False
    supports_realtime: bool = False
    supports_history: bool = True

    def validate(self) -> None:
        required = {
            "provider": self.provider,
            "market": self.market,
            "frequency": self.frequency,
            "adjustment": self.adjustment,
            "permission_level": self.permission_level,
            "data_source_version": self.data_source_version,
            "as_of_version": self.as_of_version,
            "license_notes": self.license_notes,
            "retention_policy": self.retention_policy,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"DataSourceProfile missing required fields: {joined}")

        if self.market != "CN_A_SHARE":
            raise ValueError("First version supports only CN_A_SHARE profiles")


def akshare_exploration_profile(
    *,
    frequency: str = "1m",
    adjustment: str = "none",
    data_source_version: str = "akshare-exploration-v1",
    as_of_version: str = "asof-research-v1",
) -> DataSourceProfile:
    return DataSourceProfile(
        provider="AKShare",
        market="CN_A_SHARE",
        frequency=frequency,
        adjustment=adjustment,
        permission_level="public_research",
        data_source_version=data_source_version,
        as_of_version=as_of_version,
        tier=ProviderTier.EXPLORATION,
        license_notes="用于探索和交叉验证；不得作为唯一评价价格来源。",
        retention_policy="仅保存标准化研究样本；原始数据保存取决于授权。",
        can_store_raw=False,
        supports_realtime=True,
        supports_history=True,
    )


def tushare_research_profile(
    *,
    frequency: str = "1m",
    adjustment: str = "none",
    data_source_version: str = "tushare-research-v1",
    as_of_version: str = "asof-research-v1",
) -> DataSourceProfile:
    return DataSourceProfile(
        provider="Tushare",
        market="CN_A_SHARE",
        frequency=frequency,
        adjustment=adjustment,
        permission_level="requires_minute_permission",
        data_source_version=data_source_version,
        as_of_version=as_of_version,
        tier=ProviderTier.RESEARCH_BASELINE,
        license_notes="分钟数据权限和商业用途限制需单独确认。",
        retention_policy="优先保存标准化 Bar；原始数据保存需按授权决策。",
        can_store_raw=False,
        supports_realtime=False,
        supports_history=True,
    )


def stable_shadow_candidate_profile(
    *,
    provider: str,
    frequency: str = "1m",
    adjustment: str = "none",
    data_source_version: str,
    as_of_version: str = "asof-shadow-candidate-v1",
) -> DataSourceProfile:
    return DataSourceProfile(
        provider=provider,
        market="CN_A_SHARE",
        frequency=frequency,
        adjustment=adjustment,
        permission_level="paid_or_trial_required",
        data_source_version=data_source_version,
        as_of_version=as_of_version,
        tier=ProviderTier.STABLE_SHADOW_CANDIDATE,
        license_notes="进入长期影子运行前需确认个人授权、保存限制和展示限制。",
        retention_policy="按授权保存标准化 Bar、tick 或引用摘要。",
        can_store_raw=False,
        supports_realtime=True,
        supports_history=True,
    )

