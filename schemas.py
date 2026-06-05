"""
ATRBA Resources Hub — Pydantic schemas
All request/response models for the resources API.
"""

from pydantic import BaseModel, field_validator, model_validator
from typing import Optional, List
from datetime import datetime
import re


# ─── Shared helpers ───────────────────────────────────────────────────────────

def make_slug(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    return re.sub(r"[-\s]+", "-", slug).strip("-")


VALID_CATEGORIES = {
    "strategy", "operations", "ai-technology", "africa-diaspora",
    "finance", "leadership", "marketing", "general"
}

VALID_EXTENSIONS = {"pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt", "zip"}

MIME_TO_EXT = {
    "application/pdf":                                                       "pdf",
    "application/msword":                                                    "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-excel":                                              "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":    "xlsx",
    "application/vnd.ms-powerpoint":                                         "ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/zip":                                                       "zip",
    "application/x-zip-compressed":                                         "zip",
}


# ─── Resource schemas ─────────────────────────────────────────────────────────

class ResourceCreate(BaseModel):
    title: str
    slug: Optional[str] = None
    description: Optional[str] = None
    category: str = "general"
    tags: List[str] = []
    featured: bool = False
    published: bool = False
    author: str = "ATRBA Team"

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Title is required")
        return v.strip()

    @field_validator("slug", mode="before")
    @classmethod
    def generate_slug(cls, v, info):
        if not v:
            title = info.data.get("title", "")
            return make_slug(title)
        return make_slug(v)

    @field_validator("category")
    @classmethod
    def validate_category(cls, v):
        if v not in VALID_CATEGORIES:
            return "general"
        return v

    @field_validator("tags", mode="before")
    @classmethod
    def clean_tags(cls, v):
        if isinstance(v, str):
            v = [t.strip() for t in v.split(",") if t.strip()]
        return [t.strip().lower() for t in v if t.strip()][:10]  # max 10 tags


class ResourceUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    featured: Optional[bool] = None
    published: Optional[bool] = None
    author: Optional[str] = None

    @field_validator("tags", mode="before")
    @classmethod
    def clean_tags(cls, v):
        if v is None:
            return v
        if isinstance(v, str):
            v = [t.strip() for t in v.split(",") if t.strip()]
        return [t.strip().lower() for t in v if t.strip()][:10]


class ResourceResponse(BaseModel):
    id: str
    title: str
    slug: str
    description: Optional[str]
    category: str
    tags: List[str]
    file_url: str
    file_name: str
    file_type: str
    file_extension: str
    file_size_bytes: int
    thumbnail_url: Optional[str]
    featured: bool
    published: bool
    download_count: int
    author: str
    created_at: str
    updated_at: str

    # Computed display fields
    file_size_display: Optional[str] = None
    file_type_label: Optional[str] = None

    @model_validator(mode="after")
    def compute_display_fields(self):
        # Human-readable file size
        size = self.file_size_bytes
        if size < 1024:
            self.file_size_display = f"{size} B"
        elif size < 1024 ** 2:
            self.file_size_display = f"{size / 1024:.1f} KB"
        else:
            self.file_size_display = f"{size / 1024 ** 2:.1f} MB"

        # Human-readable file type
        labels = {
            "pdf": "PDF Document", "docx": "Word Document", "doc": "Word Document",
            "xlsx": "Excel Spreadsheet", "xls": "Excel Spreadsheet",
            "pptx": "PowerPoint", "ppt": "PowerPoint", "zip": "ZIP Archive",
        }
        self.file_type_label = labels.get(self.file_extension.lower(), self.file_extension.upper())
        return self


class ResourceListResponse(BaseModel):
    items: List[ResourceResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


# ─── Auth schemas ─────────────────────────────────────────────────────────────

class AdminLogin(BaseModel):
    username: str
    password: str

    @field_validator("username", "password")
    @classmethod
    def not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Field is required")
        return v.strip()


class TokenResponse(BaseModel):
    token: str
    expires_at: str
    admin: dict


# ─── Download schema ──────────────────────────────────────────────────────────

class DownloadResponse(BaseModel):
    download_url: str
    file_name: str
    expires_in_seconds: int = 3600