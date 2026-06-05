"""
ATRBA Resources Hub — Public Routes
No authentication required. Read-only resource access + download tracking.
"""

from fastapi import APIRouter, Query, Request, HTTPException
from typing import Optional

import resources_db as db
import storage as storage

router = APIRouter(prefix="/resources", tags=["Resources - Public"])


# ─────────────────────────────────────────────────────────────────────────────
# LIST
# ─────────────────────────────────────────────────────────────────────────────
@router.get("")
def list_resources(
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=50),
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None, max_length=100),
    tag: Optional[str] = Query(None),
):
    return db.get_published_resources(
        page=page,
        per_page=per_page,
        category=category,
        search=search,
        tag=tag,
    )


# ─────────────────────────────────────────────────────────────────────────────
# FEATURED
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/featured")
def get_featured(limit: int = Query(6, ge=1, le=12)):
    return db.get_published_resources(per_page=limit, featured_only=True)


# ─────────────────────────────────────────────────────────────────────────────
# CATEGORIES
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/categories")
def get_categories():
    return [
        {"value": "all", "label": "All Resources"},
        {"value": "strategy", "label": "Strategy"},
        {"value": "operations", "label": "Operations"},
        {"value": "ai-technology", "label": "AI & Technology"},
        {"value": "africa-diaspora", "label": "Africa & Diaspora"},
        {"value": "finance", "label": "Finance"},
        {"value": "leadership", "label": "Leadership"},
        {"value": "marketing", "label": "Marketing"},
        {"value": "general", "label": "General"},
    ]


# ─────────────────────────────────────────────────────────────────────────────
# SINGLE RESOURCE
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/{slug}")
def get_resource(slug: str):
    return db.get_resource_by_slug(slug)


# ─────────────────────────────────────────────────────────────────────────────
# DOWNLOAD
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/{resource_id}/download")
def download_resource(resource_id: str, request: Request):

    resource = db.get_resource_by_id(resource_id)

    ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")
    referrer = request.headers.get("referer", "")

    db.record_download(resource_id, ip, user_agent, referrer)

    if not resource.get("file_path"):
        raise HTTPException(status_code=500, detail="Missing file_path")

    signed_url = storage.create_signed_download_url(
        file_path=resource["file_path"],
        file_name=resource["file_name"],
    )

    return {
        "download_url": signed_url,
        "file_name": resource["file_name"],
        "expires_in_seconds": storage.SIGNED_URL_EXPIRY,
    }