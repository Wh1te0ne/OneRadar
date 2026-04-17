from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FolderEntry(BaseModel):
    id: str
    name: str
    is_builtin: bool = False
    item_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FolderCreateRequest(BaseModel):
    name: str = Field(min_length=1)


class FolderUpdateRequest(BaseModel):
    name: str = Field(min_length=1)


class FolderListResponse(BaseModel):
    items: list[FolderEntry]


class FolderDeleteResponse(BaseModel):
    id: str
    deleted: bool
    moved_item_count: int = 0


class MoveItemRequest(BaseModel):
    folder_id: str = "inbox"


class MoveItemResponse(BaseModel):
    uid: str
    folder_id: str
    folder_name: str
    is_inbox: bool
