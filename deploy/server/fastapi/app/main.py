import json
import random
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

from app.backends.comfyui.client import (
    run_workflow,
    upload_image,
)


app = FastAPI()


# --------------------------------------------------
# Workflow
# --------------------------------------------------

QWEN_IMAGE_2512_WORKFLOW_PATH = (
    Path(__file__).parent
    / "backends"
    / "comfyui"
    / "workflows"
    / "qwen-image-2512_api.json"
)

QWEN_IMAGE_EDIT_2511_WORKFLOW_PATH = (
    Path(__file__).parent
    / "backends"
    / "comfyui"
    / "workflows"
    / "qwen-image-edit-2511_api.json"
)


# --------------------------------------------------
# Request
# --------------------------------------------------

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


# --------------------------------------------------
# Health
# --------------------------------------------------

@app.get("/health")
async def health():
    return {
        "status": "ok",
    }


# --------------------------------------------------
# Qwen-Image-2512
# --------------------------------------------------

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

    # 同步等待 ComfyUI 完成
    images = await run_workflow(workflow)

    return {
        "model": "qwen-image-2512",
        "images": images,
    }


# --------------------------------------------------
# Qwen-Image-Edit-2511
# --------------------------------------------------

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

    # 同步等待 ComfyUI 完成
    images = await run_workflow(workflow)

    return {
        "model": "qwen-image-edit-2511",
        "images": images,
    }