import asyncio
import base64
import uuid
from pathlib import Path

import httpx


COMFYUI_URL = "http://127.0.0.1:8188"

IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
}

VIDEO_EXTENSIONS = {
    ".mp4",
    ".webm",
    ".mov",
    ".mkv",
    ".avi",
    ".gif",
}


async def upload_image(image_base64: str) -> str:
    if "," in image_base64:
        image_base64 = image_base64.split(",", 1)[1]

    image_bytes = base64.b64decode(image_base64)
    filename = f"{uuid.uuid4().hex}.png"

    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(
            f"{COMFYUI_URL}/upload/image",
            files={
                "image": (
                    filename,
                    image_bytes,
                    "image/png",
                ),
            },
            data={
                "overwrite": "true",
            },
        )

        response.raise_for_status()

        result = response.json()

    return result.get("name", filename)


def get_file_type(
    filename: str,
    output_key: str,
) -> str:
    extension = Path(filename).suffix.lower()

    if extension in IMAGE_EXTENSIONS:
        return "image"

    if extension in VIDEO_EXTENSIONS:
        return "video"

    output_key = output_key.lower()

    if "video" in output_key:
        return "video"

    if "gif" in output_key:
        return "video"

    if "image" in output_key:
        return "image"

    return "file"


async def run_workflow(workflow: dict) -> list[dict]:
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(
            f"{COMFYUI_URL}/prompt",
            json={
                "prompt": workflow,
            },
        )

        if not response.is_success:
            raise RuntimeError(
                "ComfyUI 提交 workflow 失败: "
                f"{response.status_code} {response.text}"
            )

        prompt_id = response.json()["prompt_id"]

        while True:
            response = await client.get(
                f"{COMFYUI_URL}/history/{prompt_id}",
            )

            response.raise_for_status()

            history = response.json()

            if prompt_id in history:
                break

            await asyncio.sleep(1)

        prompt_result = history[prompt_id]

        status = prompt_result.get("status", {})

        if status.get("status_str") == "error":
            raise RuntimeError(
                f"ComfyUI 执行失败: {status}"
            )

        outputs = prompt_result.get(
            "outputs",
            {},
        )

        files = []

        for node_id, output in outputs.items():
            if not isinstance(output, dict):
                continue

            for output_key, items in output.items():
                if not isinstance(items, list):
                    continue

                for item in items:
                    if not isinstance(item, dict):
                        continue

                    filename = item.get("filename")

                    if not filename:
                        continue

                    response = await client.get(
                        f"{COMFYUI_URL}/view",
                        params={
                            "filename": filename,
                            "subfolder": item.get(
                                "subfolder",
                                "",
                            ),
                            "type": item.get(
                                "type",
                                "output",
                            ),
                        },
                    )

                    response.raise_for_status()

                    file_type = get_file_type(
                        filename,
                        output_key,
                    )

                    files.append(
                        {
                            "type": file_type,
                            "filename": filename,
                            "node_id": node_id,
                            "base64": base64.b64encode(
                                response.content
                            ).decode("utf-8"),
                        }
                    )

        return files