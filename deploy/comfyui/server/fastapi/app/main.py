import json
import random
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

from app.comfyui_client import (
    run_workflow,
    upload_image,
)


app = FastAPI()


QWEN_IMAGE_2512_WORKFLOW_PATH = (
    Path(__file__).parent
    / "workflows"
    / "qwen-image-2512_api.json"
)

QWEN_IMAGE_EDIT_2511_WORKFLOW_PATH = (
    Path(__file__).parent
    / "workflows"
    / "qwen-image-edit-2511_api.json"
)

LTX_23_WORKFLOW_PATH = (
    Path(__file__).parent
    / "workflows"
    / "ltx-2.3-t2v-i2v-two-stage-distilled_api.json"
)


class QwenImage2512Request(BaseModel):
    prompt: str

    negative_prompt: str = (
        "low quality, bad anatomy, extra digits, missing digits, "
        "extra limbs, missing limbs"
    )

    width: int = 720
    height: int = 1280

    steps: int = 8
    cfg: float = 1.0

    seed: int | None = None


class QwenImageEdit2511Request(BaseModel):
    image: str
    prompt: str

    width: int = 864
    height: int = 1536

    steps: int = 4
    seed: int | None = None


class LTX23Request(BaseModel):
    prompt: str

    negative_prompt: str = (
        "pc game, console game, video game, "
        "cartoon, childish, ugly"
    )

    # 不传 image -> T2V
    # 传 image -> I2V
    image: str | None = None

    width: int = 960
    height: int = 544

    frames: int = 121
    fps: float = 24

    seed: int | None = None


@app.get("/health")
async def health():
    return {
        "status": "ok",
    }


@app.post("/v1/images/qwen-image-2512/generate")
async def qwen_image_2512_generate(
    req: QwenImage2512Request,
):
    with open(
        QWEN_IMAGE_2512_WORKFLOW_PATH,
        "r",
        encoding="utf-8",
    ) as f:
        workflow = json.load(f)

    # Prompt
    workflow["67"]["inputs"]["text"] = req.prompt

    # Negative prompt
    workflow["71"]["inputs"]["text"] = req.negative_prompt

    # Width / height
    workflow["68"]["inputs"]["width"] = req.width
    workflow["68"]["inputs"]["height"] = req.height

    # Sampling
    workflow["70"]["inputs"]["steps"] = req.steps
    workflow["70"]["inputs"]["cfg"] = req.cfg

    workflow["70"]["inputs"]["seed"] = (
        req.seed
        if req.seed is not None
        else random.randint(1, 2**63 - 1)
    )

    files = await run_workflow(workflow)

    images = [
        file["base64"]
        for file in files
        if file["type"] == "image"
    ]

    return {
        "model": "qwen-image-2512",
        "images": images,
    }


@app.post("/v1/images/qwen-image-edit-2511/edit")
async def qwen_image_edit_2511_edit(
    req: QwenImageEdit2511Request,
):
    # Base64 图片上传到 ComfyUI
    filename = await upload_image(req.image)

    with open(
        QWEN_IMAGE_EDIT_2511_WORKFLOW_PATH,
        "r",
        encoding="utf-8",
    ) as f:
        workflow = json.load(f)

    # LoadImage
    workflow["21"]["inputs"]["image"] = filename

    # Prompt
    workflow["20"]["inputs"]["prompt"] = req.prompt

    # Width / height
    workflow["17"]["inputs"]["width"] = req.width
    workflow["17"]["inputs"]["height"] = req.height

    # Steps
    workflow["11"]["inputs"]["steps"] = req.steps

    # Seed
    workflow["7"]["inputs"]["noise_seed"] = (
        req.seed
        if req.seed is not None
        else random.randint(1, 2**63 - 1)
    )

    files = await run_workflow(workflow)

    images = [
        file["base64"]
        for file in files
        if file["type"] == "image"
    ]

    return {
        "model": "qwen-image-edit-2511",
        "images": images,
    }


@app.post("/v1/videos/ltx-2.3/generate")
async def ltx_23_generate(
    req: LTX23Request,
):
    with open(
        LTX_23_WORKFLOW_PATH,
        "r",
        encoding="utf-8",
    ) as f:
        workflow = json.load(f)

    # Prompt
    workflow["2483"]["inputs"]["text"] = req.prompt

    # Negative prompt
    workflow["2612"]["inputs"]["text"] = (
        req.negative_prompt
    )

    # Width / height
    workflow["3059"]["inputs"]["width"] = req.width
    workflow["3059"]["inputs"]["height"] = req.height

    # Frames
    workflow["4988"]["inputs"]["value"] = req.frames

    # FPS
    workflow["4989"]["inputs"]["value"] = req.fps

    # Seed
    seed = (
        req.seed
        if req.seed is not None
        else random.randint(1, 2**63 - 2)
    )

    # 第一阶段 seed
    workflow["4832"]["inputs"]["noise_seed"] = seed

    # 第二阶段 seed
    workflow["4967"]["inputs"]["noise_seed"] = seed + 1

    # T2V / I2V
    if req.image:
        # I2V
        filename = await upload_image(req.image)

        workflow["2004"]["inputs"]["image"] = filename

        # 使用输入图片
        workflow["4987"]["inputs"]["value"] = False

    else:
        # T2V
        # bypass 输入图片
        workflow["4987"]["inputs"]["value"] = True

    files = await run_workflow(workflow)

    videos = [
        file["base64"]
        for file in files
        if file["type"] in (
            "video",
            "gif",
        )
    ]

    return {
        "model": "ltx-2.3",
        "videos": videos,
    }

