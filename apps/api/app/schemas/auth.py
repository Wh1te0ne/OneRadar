from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ThemeMode
from app.schemas.folders import FolderEntry


class AuthUser(BaseModel):
    id: str
    username: str
    created_at: datetime


class WorkspaceBootstrapResponse(BaseModel):
    workspace_name: str = "OneRadar"
    single_user_mode: bool = True
    ui_locale: str = "zh-CN"
    theme_mode: ThemeMode = ThemeMode.system
    supported_theme_modes: list[ThemeMode] = Field(
        default_factory=lambda: [ThemeMode.system, ThemeMode.light, ThemeMode.dark]
    )
    default_inbox_folder: FolderEntry
    primary_user: AuthUser
    requires_login: bool = False
    capabilities: list[str] = Field(
        default_factory=lambda: ["items", "folders", "providers", "tasks", "settings"]
    )
