from __future__ import annotations

import asyncio
from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.core.errors import AppError


class ObjectStorageProvider(Protocol):
    async def put(self, *, key: str, content: bytes, content_type: str) -> None: ...

    async def read(self, *, key: str) -> bytes: ...

    async def delete(self, *, key: str) -> None: ...

    async def exists(self, *, key: str) -> bool: ...

    async def ensure_available(self) -> None: ...


def _validate_object_key(key: str) -> str:
    path = PurePosixPath(key)
    if (
        not key
        or key.startswith("/")
        or "\\" in key
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError("Invalid object storage key")
    return key


def _storage_error(*, retryable: bool = True) -> AppError:
    return AppError(
        "OBJECT_STORAGE_UNAVAILABLE",
        "El almacenamiento de archivos no está disponible. Inténtalo nuevamente.",
        status_code=503,
        retryable=retryable,
    )


class DisabledObjectStorageProvider:
    """Explicit provider for environments where file persistence is unavailable."""

    async def put(self, *, key: str, content: bytes, content_type: str) -> None:
        del key, content, content_type
        raise AppError(
            "OBJECT_STORAGE_DISABLED",
            "El almacenamiento de archivos no está habilitado en este entorno.",
            status_code=503,
        )

    async def read(self, *, key: str) -> bytes:
        del key
        raise AppError(
            "OBJECT_STORAGE_DISABLED",
            "El almacenamiento de archivos no está habilitado en este entorno.",
            status_code=503,
        )

    async def delete(self, *, key: str) -> None:
        del key

    async def exists(self, *, key: str) -> bool:
        del key
        return False

    async def ensure_available(self) -> None:
        return None


class LocalObjectStorageProvider:
    """Filesystem adapter for local development; keys are server-generated opaque paths."""

    def __init__(self, root: str) -> None:
        self._root = Path(root).expanduser().resolve()

    def _path_for(self, key: str) -> Path:
        validated_key = _validate_object_key(key)
        path = (self._root / validated_key).resolve()
        if self._root not in path.parents:
            raise ValueError("Invalid object storage key")
        return path

    async def put(self, *, key: str, content: bytes, content_type: str) -> None:
        del content_type
        path = self._path_for(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, content)

    async def read(self, *, key: str) -> bytes:
        path = self._path_for(key)
        try:
            return await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError as exc:
            raise AppError(
                "ASSET_UNAVAILABLE", "El activo ya no está disponible.", status_code=404
            ) from exc

    async def delete(self, *, key: str) -> None:
        path = self._path_for(key)
        await asyncio.to_thread(path.unlink, missing_ok=True)

    async def exists(self, *, key: str) -> bool:
        return await asyncio.to_thread(self._path_for(key).is_file)

    async def ensure_available(self) -> None:
        try:
            await asyncio.to_thread(self._root.mkdir, parents=True, exist_ok=True)
        except OSError as exc:
            raise _storage_error() from exc


class S3ObjectStorageProvider:
    """Existing S3-compatible adapter kept for MinIO and compatible object stores."""

    def __init__(self, *, endpoint: str, access_key: str, secret_key: str, bucket: str) -> None:
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - dependency configuration error
            raise _storage_error() from exc
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    async def put(self, *, key: str, content: bytes, content_type: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.put_object,
                Bucket=self._bucket,
                Key=_validate_object_key(key),
                Body=content,
                ContentType=content_type,
            )
        except Exception as exc:
            raise _storage_error() from exc

    async def read(self, *, key: str) -> bytes:
        try:
            response = await asyncio.to_thread(
                self._client.get_object, Bucket=self._bucket, Key=_validate_object_key(key)
            )
            return await asyncio.to_thread(response["Body"].read)
        except Exception as exc:  # Provider-specific exceptions stay outside the domain.
            raise AppError(
                "ASSET_UNAVAILABLE", "El activo ya no está disponible.", status_code=404
            ) from exc

    async def delete(self, *, key: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.delete_object, Bucket=self._bucket, Key=_validate_object_key(key)
            )
        except Exception as exc:
            raise _storage_error() from exc

    async def exists(self, *, key: str) -> bool:
        try:
            await asyncio.to_thread(
                self._client.head_object, Bucket=self._bucket, Key=_validate_object_key(key)
            )
            return True
        except Exception:
            return False

    async def ensure_available(self) -> None:
        try:
            await asyncio.to_thread(self._client.head_bucket, Bucket=self._bucket)
        except Exception as exc:
            raise _storage_error() from exc


class SupabaseStorageProvider:
    """Private Supabase Storage adapter using server-only service-role credentials."""

    def __init__(
        self,
        *,
        base_url: str,
        service_role_key: str,
        bucket: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._service_role_key = service_role_key
        self._bucket = bucket
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def _object_url(self, key: str) -> str:
        return (
            f"{self._base_url}/storage/v1/object/{quote(self._bucket, safe='')}/"
            f"{quote(_validate_object_key(key), safe='/')}"
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._service_role_key}",
            "apikey": self._service_role_key,
        }

    async def _request(
        self,
        method: str,
        url: str,
        *,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        json: dict[str, object] | None = None,
    ) -> httpx.Response:
        request_headers = self._headers()
        if headers:
            request_headers.update(headers)
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                return await client.request(
                    method,
                    url,
                    content=content,
                    headers=request_headers,
                    json=json,
                )
        except httpx.HTTPError as exc:
            raise _storage_error() from exc

    async def put(self, *, key: str, content: bytes, content_type: str) -> None:
        response = await self._request(
            "POST",
            self._object_url(key),
            content=content,
            headers={"Content-Type": content_type, "x-upsert": "false"},
        )
        if response.is_error:
            raise _storage_error(retryable=response.status_code >= 500)

    async def read(self, *, key: str) -> bytes:
        response = await self._request("GET", self._object_url(key))
        if response.status_code == 404:
            raise AppError("ASSET_UNAVAILABLE", "El activo ya no está disponible.", status_code=404)
        if response.is_error:
            raise _storage_error(retryable=response.status_code >= 500)
        return response.content

    async def delete(self, *, key: str) -> None:
        response = await self._request(
            "DELETE",
            f"{self._base_url}/storage/v1/object/{quote(self._bucket, safe='')}",
            json={"prefixes": [_validate_object_key(key)]},
        )
        if response.is_error:
            raise _storage_error(retryable=response.status_code >= 500)

    async def exists(self, *, key: str) -> bool:
        response = await self._request("HEAD", self._object_url(key))
        if response.status_code == 404:
            return False
        if response.is_error:
            raise _storage_error(retryable=response.status_code >= 500)
        return True

    async def ensure_available(self) -> None:
        # Bucket access is checked on file operations. Health must not disclose bucket metadata.
        if not self._base_url or not self._service_role_key or not self._bucket:
            raise _storage_error(retryable=False)


def get_object_storage_provider() -> ObjectStorageProvider:
    if settings.object_storage_provider == "disabled":
        return DisabledObjectStorageProvider()
    if settings.object_storage_provider == "local":
        return LocalObjectStorageProvider(settings.object_storage_local_dir)
    if settings.object_storage_provider == "s3":
        if not all(
            [
                settings.object_storage_endpoint,
                settings.object_storage_access_key,
                settings.object_storage_secret_key,
                settings.object_storage_bucket,
            ]
        ):
            raise _storage_error(retryable=False)
        return S3ObjectStorageProvider(
            endpoint=settings.object_storage_endpoint,
            access_key=settings.object_storage_access_key,
            secret_key=settings.object_storage_secret_key,
            bucket=settings.object_storage_bucket,
        )
    if settings.object_storage_provider == "supabase":
        return SupabaseStorageProvider(
            base_url=settings.supabase_url,
            service_role_key=settings.supabase_service_role_key,
            bucket=settings.supabase_storage_bucket,
            timeout_seconds=settings.storage_timeout_seconds,
        )
    raise _storage_error(retryable=False)
