import asyncio
import base64
import uuid

import httpx


COMFYUI_URL = "http://127.0.0.1:8188"


async def upload_image(image_base64: str) -> str:
    # 兼容 data:image/png;base64,... 格式
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
                )
            },
            data={
                "overwrite": "true"
            },
        )
        response.raise_for_status()

    return filename


async def run_workflow(workflow: dict) -> list[str]:
    async with httpx.AsyncClient(timeout=None) as client:
        # 1. 提交任务
        response = await client.post(
            f"{COMFYUI_URL}/prompt",
            json={"prompt": workflow},
        )
        response.raise_for_status()

        prompt_id = response.json()["prompt_id"]

        # 2. 同步等待任务完成
        while True:
            response = await client.get(
                f"{COMFYUI_URL}/history/{prompt_id}"
            )
            response.raise_for_status()

            history = response.json()

            if prompt_id in history:
                break

            await asyncio.sleep(1)

        # 3. 获取输出图片并转成 base64
        images = []

        for output in history[prompt_id]["outputs"].values():
            for image in output.get("images", []):
                response = await client.get(
                    f"{COMFYUI_URL}/view",
                    params={
                        "filename": image["filename"],
                        "subfolder": image.get("subfolder", ""),
                        "type": image.get("type", "output"),
                    },
                )
                response.raise_for_status()

                images.append(
                    base64.b64encode(response.content).decode("utf-8")
                )

        return images