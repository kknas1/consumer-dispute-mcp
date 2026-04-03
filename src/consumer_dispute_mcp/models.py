"""소비자분쟁해결기준 데이터 모델."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Meta(BaseModel):
    """법령 메타데이터."""

    version: str
    law_name: str = "소비자분쟁해결기준"
    announcement_no: str = ""
    fetched_at: datetime


class DamageType(BaseModel):
    """피해유형별 보상기준."""

    condition: str
    remedy: list[str]


class DisputeItem(BaseModel):
    """품목별 분쟁해결기준."""

    industry: str
    category: str
    item: str
    damage_types: list[DamageType]
    warranty_period: str = ""
    parts_retention_period: str = ""


class DisputeData(BaseModel):
    """전체 분쟁해결기준 데이터."""

    meta: Meta
    items: list[DisputeItem]
