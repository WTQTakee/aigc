import asyncio
import base64
import binascii
import mimetypes
import time
import uuid
from pathlib import Path

import httpx


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".gif"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg"}


class ComfyUIClient:
    def __init__(
        self,
        base_url: str,
        poll_interval: float = 1.0,
        workflow_timeout: float = 1800,
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

    async def upload_image(self, image_base64: str) -> str:
        return await self.upload_media(image_base64, ".png", "image/png")

    async def upload_video(self, video_base64: str) -> str:
        return await self.upload_media(video_base64, ".mp4", "video/mp4")

    async def upload_audio(self, audio_base64: str) -> str:
        return await self.upload_media(audio_base64, ".wav", "audio/wav")

    async def upload_media(
        self,
        encoded: str,
        default_suffix: str,
        default_mime_type: str,
    ) -> str:
        mime_type = default_mime_type
        if encoded.startswith("data:") and "," in encoded:
            header, encoded = encoded.split(",", 1)
            declared_type = header[5:].split(";", 1)[0]
            if declared_type:
                mime_type = declared_type

        try:
            media_bytes = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("媒体内容不是有效的 Base64 数据") from exc

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
            response = await self.http.get(f"{self.base_url}/history/{prompt_id}")
            response.raise_for_status()
            history = response.json()
            if prompt_id in history:
                return await self._download_outputs(history[prompt_id])
            await asyncio.sleep(self.poll_interval)

        raise TimeoutError(f"ComfyUI 任务超时: {prompt_id}")

    async def _download_outputs(self, result: dict) -> list[dict]:
        status = result.get("status", {})
        if status.get("status_str") == "error":
            raise RuntimeError("ComfyUI workflow 执行失败")

        files: list[dict] = []
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
                            "type": _file_type(item["filename"], output_key),
                            "filename": item["filename"],
                            "node_id": node_id,
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
    if any(word in output_key.lower() for word in ("video", "gif")):
        return "video"
    if "image" in output_key.lower():
        return "image"
    if "audio" in output_key.lower():
        return "audio"
    return "file"
