from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ThemeMode
from app.schemas.folders import FolderEntry


class AuthUser(BaseModel):
    id: str
    username: str
    email: str | None = None
    created_at: datetime


class AuthLoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=255)


class AuthRegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    email: str | None = Field(default=None, max_length=255)
    password: str = Field(min_length=8, max_length=255)


class AuthSessionResponse(BaseModel):
    token: str
    user: AuthUser


class WorkspaceBootstrapResponse(BaseModel):
    workspace_name: str = "OneRadar"
    single_user_mode: bool = False
    ui_locale: str = "zh-CN"
    theme_mode: ThemeMode = ThemeMode.system
    supported_theme_modes: list[ThemeMode] = Field(
        default_factory=lambda: [ThemeMode.system, ThemeMode.light, ThemeMode.dark]
    )
    default_inbox_folder: FolderEntry
    primary_user: AuthUser
    requires_login: bool = True
    capabilities: list[str] = Field(
        default_factory=lambda: ["items", "folders", "providers", "tasks", "settings"]
    )
