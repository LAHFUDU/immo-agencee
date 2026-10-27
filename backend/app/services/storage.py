"""File storage abstraction: local disk in development, any S3-compatible bucket in production.

Files are never served from a public static directory: downloads always go through an
authenticated endpoint that checks permissions (except photos of published properties).
"""

import os
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
DOCUMENT_TYPES = {**IMAGE_TYPES, "application/pdf": ".pdf"}

_SIGNATURES = {
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/webp": [b"RIFF"],
    "application/pdf": [b"%PDF-"],
}


def sniff_type(head: bytes) -> str | None:
    for ctype, sigs in _SIGNATURES.items():
        for sig in sigs:
            if head.startswith(sig):
                if ctype == "image/webp" and head[8:12] != b"WEBP":
                    continue
                return ctype
    return None


async def read_validated(upload: UploadFile, allowed: dict[str, str]) -> tuple[bytes, str]:
    """Read an upload, enforce the size limit and verify its real type from magic bytes
    (the client-provided content type and extension are not trusted)."""
    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"Fichier trop volumineux (max {settings.MAX_UPLOAD_MB} Mo).")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Fichier vide.")
    ctype = sniff_type(data[:16])
    if ctype is None or ctype not in allowed:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Type de fichier non autorisé.")
    return data, ctype


def safe_filename(name: str | None) -> str:
    base = os.path.basename(name or "fichier")
    cleaned = "".join(c for c in base if c.isalnum() or c in "._- ").strip() or "fichier"
    return cleaned[:200]


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents:
            raise ValueError("invalid storage key")
        return p

    def save(self, key: str, data: bytes, content_type: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def load(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Fichier introuvable.") from exc

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink()
        except FileNotFoundError:
            pass


class S3Storage:
    def __init__(self):
        import boto3
        from botocore.config import Config

        self.bucket = settings.S3_BUCKET
        # S3-compatible providers (Neon, R2, MinIO...) need path-style URLs and reject the
        # optional checksum headers recent boto3 versions send by default.
        config = Config(
            s3={"addressing_style": "path"} if settings.S3_ENDPOINT_URL else {},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        )
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL or None,
            region_name=settings.S3_REGION or None,
            aws_access_key_id=settings.S3_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY or None,
            config=config,
        )

    def save(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def load(self, key: str) -> bytes:
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except self.client.exceptions.NoSuchKey as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Fichier introuvable.") from exc

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


_storage = None


def get_storage():
    global _storage
    if _storage is None:
        _storage = S3Storage() if settings.STORAGE_BACKEND == "s3" else LocalStorage(settings.UPLOAD_DIR)
    return _storage


def new_key(prefix: str, ext: str) -> str:
    return f"{prefix}/{uuid.uuid4().hex}{ext}"
