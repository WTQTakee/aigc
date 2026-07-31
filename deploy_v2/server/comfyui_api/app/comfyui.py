import asyncio
import base64
import binascii
import time
import uuid
from pathlib import Path

import httpx


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".gif"}


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
        if "," in image_base64:
            image_base64 = image_base64.split(",", 1)[1]

        try:
            image_bytes = base64.b64decode(image_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("image 不是有效的 Base64 数据") from exc

        filename = f"{uuid.uuid4().hex}.png"
        response = await self.http.post(
            f"{self.base_url}/upload/image",
            files={"image": (filename, image_bytes, "image/png")},
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
    if any(word in output_key.lower() for word in ("video", "gif")):
        return "video"
    if "image" in output_key.lower():
        return "image"
    return "file"
