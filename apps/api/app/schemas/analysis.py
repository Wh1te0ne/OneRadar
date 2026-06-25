from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class UrlAnalysisRequest(BaseModel):
    url: str = Field(min_length=1)
    platform_hint: str | None = None


class SourceMaterial(BaseModel):
    kind: str
    text: str
    markdown: str
    segments: list[dict[str, object]] = Field(default_factory=list)
    assets: list[dict[str, object]] = Field(default_factory=list)
    completeness: str
    warnings: list[str] = Field(default_factory=list)


class AnalysisSummary(BaseModel):
    summary: str
    markdown: str
    key_points: list[str] = Field(default_factory=list)
    provider: str = "extractive"
    model_name: str | None = None


class UrlAnalysisResponse(BaseModel):
    source_url: str
    final_url: str | None = None
    platform: str
    content_type: str
    title: str
    source_name: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    original_text: str
    source_text_kind: str
    summary: str
    source_material: SourceMaterial
    ai_summary: AnalysisSummary
    source_markdown: str
    summary_markdown: str
    summary_provider: str = "extractive"
    model_name: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    fetched_at: datetime
    persisted: bool = False
