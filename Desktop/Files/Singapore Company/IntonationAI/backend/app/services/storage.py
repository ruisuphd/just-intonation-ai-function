import asyncio
import base64
import logging
from datetime import timedelta

from google.cloud import storage

from app.core.config import settings

logger = logging.getLogger(__name__)


class CloudStorageService:
    def __init__(self) -> None:
        self._client: storage.Client | None = None
        self._bucket_name: str | None = settings.GCS_BUCKET
        if self._bucket_name:
            try:
                self._client = storage.Client(project=settings.gcp_project)
            except Exception as e:
                logger.warning("Cloud Storage client init failed: %s", e)
        else:
            logger.info("Cloud Storage disabled (no GCS_BUCKET in dev mode)")

    async def upload(
        self,
        data: bytes,
        path: str,
        content_type: str = "audio/mpeg",
    ) -> str:
        if not self._client or not self._bucket_name:
            return self._data_uri_fallback(data, content_type)

        def _upload() -> str:
            bucket = self._client.bucket(self._bucket_name)
            blob = bucket.blob(path)
            blob.upload_from_string(
                data,
                content_type=content_type,
            )
            return blob.generate_signed_url(
                version="v4",
                expiration=timedelta(hours=1),
                method="GET",
            )

        return await asyncio.wait_for(
            asyncio.to_thread(_upload),
            timeout=settings.GCS_OPERATION_TIMEOUT_SEC,
        )

    async def download(self, path: str) -> bytes:
        if not self._client or not self._bucket_name:
            logger.warning("Cloud Storage not configured")
            return b""

        def _download() -> bytes:
            bucket = self._client.bucket(self._bucket_name)
            blob = bucket.blob(path)
            return blob.download_as_bytes()

        return await asyncio.wait_for(
            asyncio.to_thread(_download),
            timeout=settings.GCS_OPERATION_TIMEOUT_SEC,
        )

    async def delete(self, path: str) -> None:
        if not self._client or not self._bucket_name:
            logger.warning("Cloud Storage not configured")
            return

        def _delete() -> None:
            bucket = self._client.bucket(self._bucket_name)
            blob = bucket.blob(path)
            blob.delete()

        await asyncio.wait_for(
            asyncio.to_thread(_delete),
            timeout=settings.GCS_OPERATION_TIMEOUT_SEC,
        )

    async def ping_bucket(self) -> bool:
        if not self._client or not self._bucket_name:
            return True

        def _ping() -> bool:
            b = self._client.bucket(self._bucket_name)
            return b.exists()

        try:
            return await asyncio.wait_for(
                asyncio.to_thread(_ping),
                timeout=min(15.0, settings.GCS_OPERATION_TIMEOUT_SEC),
            )
        except Exception as e:
            logger.warning("GCS bucket ping failed: %s", e)
            return False

    @staticmethod
    def _data_uri_fallback(data: bytes, content_type: str) -> str:
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{content_type};base64,{b64}"


storage_service = CloudStorageService()
