import json
import random
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

from app.comfyui_client import run_workflow, upload_image


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


class QwenImage2512Request(BaseModel):
    prompt: str
    negative_prompt: str = (
        "low quality, bad anatomy, extra digits, missing digits, "
        "extra limbs, missing limbs"
    )
    width: int = 864
    height: int = 1536
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

    workflow["67"]["inputs"]["text"] = req.prompt
    workflow["71"]["inputs"]["text"] = req.negative_prompt

    workflow["68"]["inputs"]["width"] = req.width
    workflow["68"]["inputs"]["height"] = req.height

    workflow["70"]["inputs"]["steps"] = req.steps
    workflow["70"]["inputs"]["cfg"] = req.cfg
    workflow["70"]["inputs"]["seed"] = (
        req.seed
        if req.seed is not None
        else random.randint(1, 2**63 - 1)
    )

    images = await run_workflow(workflow)

    return {
        "model": "qwen-image-2512",
        "images": images,
    }


@app.post("/v1/images/qwen-image-edit-2511/edit")
async def qwen_image_edit_2511_edit(
    req: QwenImageEdit2511Request,
):
    filename = await upload_image(req.image)

    with open(
        QWEN_IMAGE_EDIT_2511_WORKFLOW_PATH,
        "r",
        encoding="utf-8",
    ) as f:
        workflow = json.load(f)

    workflow["21"]["inputs"]["image"] = filename
    workflow["20"]["inputs"]["prompt"] = req.prompt

    workflow["17"]["inputs"]["width"] = req.width
    workflow["17"]["inputs"]["height"] = req.height

    workflow["11"]["inputs"]["steps"] = req.steps

    workflow["7"]["inputs"]["noise_seed"] = (
        req.seed
        if req.seed is not None
        else random.randint(1, 2**63 - 1)
    )

    images = await run_workflow(workflow)

    return {
        "model": "qwen-image-edit-2511",
        "images": images,
    }