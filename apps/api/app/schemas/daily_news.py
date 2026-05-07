from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DailyNewsEntry(BaseModel):
    id: str
    title: str
    link: str
    summary: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    source_url: str
    source_title: str


class DailyNewsItem(BaseModel):
    title: str
    summary: str
    entry_id: str | None = None
    entry: DailyNewsEntry | None = None


class DailyNewsLead(DailyNewsItem):
    pass


class DailyNewsSection(BaseModel):
    title: str
    summary: str
    items: list[DailyNewsItem] = Field(default_factory=list)


class DailyNewsReportResponse(BaseModel):
    report_date: str
    status: str
    headline: str | None = None
    lead: DailyNewsLead | None = None
    sections: list[DailyNewsSection] = Field(default_factory=list)
    generated_at: datetime | None = None
    provider_name: str | None = None
    model_name: str | None = None
    entry_count: int = 0
    freshness_hours: int = 24
    error_message: str | None = None


class DailyNewsGenerateRequest(BaseModel):
    date: str | None = None
    force: bool = False
