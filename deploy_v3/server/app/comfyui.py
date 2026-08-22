import asyncio
import base64
import binascii
import mimetypes
import time
import uuid
from pathlib import Path

import httpx


MEDIA_DEFAULTS = {
    "image": ("image/png", ".png"),
    "video": ("video/mp4", ".mp4"),
    "audio": ("audio/wav", ".wav"),
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".gif"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg"}


class ComfyUIClient:
    def __init__(
        self,
        base_url: str,
        poll_interval: float = 1.0,
        workflow_timeout: float = 3600,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.poll_interval = poll_interval
        self.workflow_timeout = workflow_timeout
        self.http = httpx.AsyncClient(timeout=60)

    async def close(self) -> None:
        await self.http.aclose()

    async def health(self) -> bool:
        try:
            response = await self.http.get(f"{self.base_url}/system_stats")
            return response.is_success
        except httpx.HTTPError:
            return False

    async def upload_media(self, encoded: str, kind: str) -> str:
        try:
            default_mime, default_suffix = MEDIA_DEFAULTS[kind]
        except KeyError as exc:
            raise ValueError(f"不支持的媒体类型: {kind}") from exc

        mime_type = default_mime
        if encoded.startswith("data:") and "," in encoded:
            header, encoded = encoded.split(",", 1)
            declared_type = header[5:].split(";", 1)[0]
            if declared_type:
                mime_type = declared_type

        try:
            media_bytes = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("媒体内容不是有效的 Base64 数据") from exc
        if not media_bytes:
            raise ValueError("媒体 Base64 内容不能为空")

        suffix = mimetypes.guess_extension(mime_type) or default_suffix
        if suffix == ".jpe":
            suffix = ".jpg"
        filename = f"{uuid.uuid4().hex}{suffix}"
        response = await self.http.post(
            f"{self.base_url}/upload/image",
            files={"image": (filename, media_bytes, mime_type)},
            data={"overwrite": "true"},
        )
        response.raise_for_status()
        return response.json().get("name", filename)

    async def run_workflow(self, workflow: dict) -> list[dict]:
        response = await self.http.post(
            f"{self.base_url}/prompt",
            json={"prompt": workflow},
        )
        response.raise_for_status()
        prompt_id = response.json()["prompt_id"]

        deadline = time.monotonic() + self.workflow_timeout
        while time.monotonic() < deadline:
            response = await self.http.get(
                f"{self.base_url}/history/{prompt_id}",
            )
            response.raise_for_status()
            result = response.json().get(prompt_id)
            if result is not None:
                return await self._download_outputs(result)
            await asyncio.sleep(self.poll_interval)

        raise TimeoutError(f"ComfyUI 任务超时: {prompt_id}")

    async def _download_outputs(self, result: dict) -> list[dict]:
        status = result.get("status", {})
        if status.get("status_str") == "error":
            messages = status.get("messages") or []
            detail = str(messages[-1]) if messages else "未知错误"
            raise RuntimeError(f"ComfyUI workflow 执行失败: {detail}")

        files = []
        for node_id, output in result.get("outputs", {}).items():
            if not isinstance(output, dict):
                continue
            for output_key, items in output.items():
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict) or not item.get("filename"):
                        continue
                    response = await self.http.get(
                        f"{self.base_url}/view",
                        params={
                            "filename": item["filename"],
                            "subfolder": item.get("subfolder", ""),
                            "type": item.get("type", "output"),
                        },
                    )
                    response.raise_for_status()
                    files.append(
                        {
                            "node_id": node_id,
                            "filename": item["filename"],
                            "type": _file_type(item["filename"], output_key),
                            "base64": base64.b64encode(response.content).decode(),
                        }
                    )
        return files


def _file_type(filename: str, output_key: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in VIDEO_EXTENSIONS:
        return "video"
    if extension in AUDIO_EXTENSIONS:
        return "audio"
    key = output_key.lower()
    if "video" in key or "gif" in key:
        return "video"
    if "image" in key:
        return "image"
    if "audio" in key:
        return "audio"
    return "file"
