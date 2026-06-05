"""
ATRBA Resources Hub — Supabase Storage Service
Handles all file upload, download URL generation, and deletion.
"""

import os
import uuid
import mimetypes
from typing import Optional, Tuple
from fastapi import UploadFile, HTTPException
import asyncio
import httpx
# Injected at startup from main.py
_supabase = None
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
def init_storage(supabase_client):
    global _supabase
    _supabase = supabase_client

def get_client():
    if _supabase is None:
        raise RuntimeError("Storage service not initialised — call init_storage() first")
    return _supabase


# ─── Constants ────────────────────────────────────────────────────────────────

RESOURCE_BUCKET    = "resources"
THUMBNAIL_BUCKET   = "resource-thumbnails"
MAX_FILE_SIZE      = 50 * 1024 * 1024   # 50 MB
MAX_THUMB_SIZE     = 5  * 1024 * 1024   # 5 MB
SIGNED_URL_EXPIRY  = 3600               # 1 hour for download links

ALLOWED_FILE_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/zip",
    "application/x-zip-compressed",
}

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}

MIME_TO_EXT = {
    "application/pdf":   "pdf",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/zip": "zip",
    "application/x-zip-compressed": "zip",
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _detect_mime(file: UploadFile) -> str:
    """Detect MIME from content_type header, fallback to filename extension."""
    ct = (file.content_type or "").split(";")[0].strip().lower()
    if ct and ct != "application/octet-stream":
        return ct
    guessed, _ = mimetypes.guess_type(file.filename or "")
    return guessed or "application/octet-stream"


def _safe_filename(original: str) -> str:
    """Strip path traversal attempts from filenames."""
    name = os.path.basename(original or "file")
    name = "".join(c for c in name if c.isalnum() or c in "._- ")
    return name.strip() or "file"


# ─── File upload ──────────────────────────────────────────────────────────────

async def upload_resource_file(file: UploadFile) -> dict:
    """
    Upload a resource file to Supabase Storage.
    Returns metadata dict with path, url, extension, size, etc.
    Raises HTTPException on validation failure.
    """
    mime = _detect_mime(file)
    if mime not in ALLOWED_FILE_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"File type '{mime}' not allowed. Accepted: PDF, DOCX, XLSX, PPTX, ZIP"
        )

    contents = await file.read()
    await file.seek(0)
    size = len(contents)
    if size == 0:
        raise HTTPException(status_code=422, detail="Uploaded file is empty")
    if size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=422,
            detail=f"File too large ({size / 1024 / 1024:.1f} MB). Maximum is 50 MB"
        )

    ext = MIME_TO_EXT.get(mime, "bin")
    safe_name = _safe_filename(file.filename or f"file.{ext}")
    storage_path = f"{uuid.uuid4().hex}/{safe_name}"

    try:
        get_client().storage.from_(RESOURCE_BUCKET).upload(
    storage_path,
    contents,
    {
        "content-type": mime,
        "upsert": "false"
    }
)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Storage upload failed: {exc}")

    return {
        "file_path":       storage_path,
        "file_name":       safe_name,
        "file_type":       mime,
        "file_extension":  ext,
        "file_size_bytes": size,
        "file_url":        storage_path,  # stored as path; URL generated on request
    }
async def upload_thumbnail(file: UploadFile) -> dict:
    mime = _detect_mime(file)

    if mime not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=422, detail="Invalid image type")

    contents = await file.read()

    ext = mime.split("/")[-1].replace("jpeg", "jpg")
    path = f"{uuid.uuid4().hex}/thumb.{ext}"

    url = f"{SUPABASE_URL}/storage/v1/object/{THUMBNAIL_BUCKET}/{path}"

    headers = {
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": mime,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(url, content=contents, headers=headers)

    if res.status_code >= 300:
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {res.text}"
        )

    public_url = f"{SUPABASE_URL}/storage/v1/object/public/{THUMBNAIL_BUCKET}/{path}"

    return {
        "thumbnail_path": path,
        "thumbnail_url": public_url
    }
# ─── Signed download URL ──────────────────────────────────────────────────────

def create_signed_download_url(file_path: str, file_name: str) -> str:
    """
    Generate a time-limited signed URL for a private resource file.
    Expires after SIGNED_URL_EXPIRY seconds (default 1 hour).
    """
    try:
        resp = get_client().storage.from_(RESOURCE_BUCKET).create_signed_url(
            path=file_path,
            expires_in=SIGNED_URL_EXPIRY,
            options={"download": file_name},  # Forces browser download with correct filename
        )
        return resp.get("signedURL") or resp.get("signed_url") or resp["signedUrl"]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not generate download URL: {exc}")


# ─── Deletion ─────────────────────────────────────────────────────────────────

def delete_resource_file(file_path: str) -> None:
    """Delete a file from the resources bucket. Fails silently if not found."""
    try:
        get_client().storage.from_(RESOURCE_BUCKET).remove([file_path])
    except Exception:
        pass  # Log in production but don't fail the delete operation


def delete_thumbnail(thumbnail_path: str) -> None:
    """Delete a thumbnail from the thumbnails bucket."""
    try:
        get_client().storage.from_(THUMBNAIL_BUCKET).remove([thumbnail_path])
    except Exception:
        pass