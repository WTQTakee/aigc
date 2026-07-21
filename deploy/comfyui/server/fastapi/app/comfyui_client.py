import asyncio
import base64
import uuid

import httpx


COMFYUI_URL = "http://127.0.0.1:8188"


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

    return filename


async def run_workflow(workflow: dict) -> list[dict]:
    async with httpx.AsyncClient(timeout=None) as client:
        # 提交 workflow
        response = await client.post(
            f"{COMFYUI_URL}/prompt",
            json={
                "prompt": workflow,
            },
        )

        response.raise_for_status()

        prompt_id = response.json()["prompt_id"]

        # 等待任务完成
        while True:
            response = await client.get(
                f"{COMFYUI_URL}/history/{prompt_id}",
            )

            response.raise_for_status()

            history = response.json()

            if prompt_id in history:
                break

            await asyncio.sleep(1)

        outputs = history[prompt_id]["outputs"]

        files = []

        # 获取输出文件
        for output in outputs.values():
            for output_type, items in output.items():
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

                    file_base64 = base64.b64encode(
                        response.content,
                    ).decode("utf-8")

                    files.append(
                        {
                            "type": output_type.rstrip("s"),
                            "filename": filename,
                            "base64": file_base64,
                        }
                    )

        return files
