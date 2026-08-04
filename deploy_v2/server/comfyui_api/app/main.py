import json
import random
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.comfyui import ComfyUIClient
from app.config import load_config
from app.schemas import (
    LTXVideoRequest,
    QwenImageEditRequest,
    QwenImageEditLightningRequest,
    QwenImageMultiEditRequest,
    QwenImageMultiEditLightningRequest,
    QwenImageRequest,
)


WORKFLOW_DIR = Path(__file__).parent / "workflows"
CONFIG = load_config()["services"]["comfyui_api"]
WORKFLOW_FILES = CONFIG["workflows"]
FULL_MULTI_IMAGE_NODES = (
    ("6", "image1"),
    ("16", "image2"),
    ("17", "image3"),
)
LIGHTNING_MULTI_IMAGE_NODES = (
    ("21", "image1"),
    ("23", "image2"),
    ("24", "image3"),
)


def load_workflow(name: str) -> dict:
    with (WORKFLOW_DIR / WORKFLOW_FILES[name]).open(encoding="utf-8") as file:
        return json.load(file)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.comfyui = ComfyUIClient(
        base_url=CONFIG["comfyui_url"],
        poll_interval=CONFIG["poll_interval"],
        workflow_timeout=CONFIG["workflow_timeout"],
    )
    try:
        yield
    finally:
        await app.state.comfyui.close()


app = FastAPI(title="AIGC ComfyUI API", version="2.0.0", lifespan=lifespan)


def client(request: Request) -> ComfyUIClient:
    return request.app.state.comfyui


@app.exception_handler(httpx.HTTPError)
async def handle_comfyui_http_error(_request: Request, exc: httpx.HTTPError):
    return _error_response(502, f"ComfyUI 连接失败: {exc}")


@app.exception_handler(TimeoutError)
async def handle_timeout(_request: Request, exc: TimeoutError):
    return _error_response(504, str(exc))


@app.exception_handler(RuntimeError)
async def handle_runtime_error(_request: Request, exc: RuntimeError):
    return _error_response(502, str(exc))


@app.exception_handler(ValueError)
async def handle_value_error(_request: Request, exc: ValueError):
    return _error_response(422, str(exc))


def _error_response(status_code: int, detail: str):
    return JSONResponse(status_code=status_code, content={"detail": detail})


def output_values(files: list[dict], file_type: str) -> list[str]:
    values = [item["base64"] for item in files if item["type"] == file_type]
    if not values:
        raise HTTPException(status_code=502, detail=f"ComfyUI 未返回{file_type}")
    return values


def set_multi_image_inputs(
    workflow: dict,
    filenames: list[str],
    image_nodes: tuple[tuple[str, str], ...],
    encoder_nodes: tuple[str, ...],
) -> None:
    for index, (node_id, input_name) in enumerate(image_nodes):
        if index < len(filenames):
            workflow[node_id]["inputs"]["image"] = filenames[index]
        else:
            for encoder_node in encoder_nodes:
                workflow[encoder_node]["inputs"].pop(input_name, None)
            workflow.pop(node_id, None)


def set_full_edit_parameters(
    workflow: dict,
    prompt: str,
    negative_prompt: str,
    steps: int,
    cfg: float,
    seed: int | None,
) -> None:
    workflow["8"]["inputs"]["prompt"] = prompt
    workflow["9"]["inputs"]["prompt"] = negative_prompt
    workflow["13"]["inputs"].update(
        steps=steps,
        cfg=cfg,
        seed=seed if seed is not None else random.randrange(1, 2**63),
    )


def set_lightning_edit_parameters(
    workflow: dict,
    prompt: str,
    width: int,
    height: int,
    seed: int | None,
) -> None:
    workflow["20"]["inputs"]["prompt"] = prompt
    workflow["17"]["inputs"].update(width=width, height=height)
    workflow["7"]["inputs"]["noise_seed"] = (
        seed if seed is not None else random.randrange(1, 2**63)
    )


@app.get("/health")
async def health(request: Request):
    available = await client(request).health()
    return {"status": "ok" if available else "degraded", "comfyui": available}


@app.post("/v1/images/qwen-image-2512/generate")
async def generate_qwen_image(req: QwenImageRequest, request: Request):
    workflow = load_workflow("qwen-image-2512")
    workflow["67"]["inputs"]["text"] = req.prompt
    workflow["71"]["inputs"]["text"] = req.negative_prompt
    workflow["68"]["inputs"].update(width=req.width, height=req.height)
    workflow["70"]["inputs"].update(
        steps=req.steps,
        cfg=req.cfg,
        seed=req.seed if req.seed is not None else random.randrange(1, 2**63),
    )
    files = await client(request).run_workflow(workflow)
    return {
        "model": "qwen-image-2512",
        "images": output_values(files, "image"),
    }


@app.post("/v1/images/qwen-image-edit-2511/edit")
async def edit_qwen_image(req: QwenImageEditRequest, request: Request):
    comfyui = client(request)
    filename = await comfyui.upload_image(req.image)
    workflow = load_workflow("qwen-image-edit-2511")
    workflow["6"]["inputs"]["image"] = filename
    set_full_edit_parameters(
        workflow,
        req.prompt,
        req.negative_prompt,
        req.steps,
        req.cfg,
        req.seed,
    )
    files = await comfyui.run_workflow(workflow)
    return {
        "model": "qwen-image-edit-2511",
        "profile": "full",
        "images": output_values(files, "image"),
    }


@app.post("/v1/images/qwen-image-edit-2511/edit-lightning-4step")
async def edit_qwen_image_lightning(
    req: QwenImageEditLightningRequest,
    request: Request,
):
    comfyui = client(request)
    filename = await comfyui.upload_image(req.image)
    workflow = load_workflow("qwen-image-edit-2511-lightning-4step")
    workflow["21"]["inputs"]["image"] = filename
    set_lightning_edit_parameters(
        workflow,
        req.prompt,
        req.width,
        req.height,
        req.seed,
    )
    files = await comfyui.run_workflow(workflow)
    return {
        "model": "qwen-image-edit-2511",
        "profile": "lightning-4step",
        "images": output_values(files, "image"),
    }


@app.post("/v1/images/qwen-image-edit-2511/edit-multi")
async def edit_qwen_image_multi(
    req: QwenImageMultiEditRequest,
    request: Request,
):
    comfyui = client(request)
    filenames = [await comfyui.upload_image(image) for image in req.images]
    workflow = load_workflow("qwen-image-edit-2511-multi")
    set_multi_image_inputs(
        workflow,
        filenames,
        FULL_MULTI_IMAGE_NODES,
        ("8", "9"),
    )
    set_full_edit_parameters(
        workflow,
        req.prompt,
        req.negative_prompt,
        req.steps,
        req.cfg,
        req.seed,
    )
    files = await comfyui.run_workflow(workflow)
    return {
        "model": "qwen-image-edit-2511",
        "profile": "full-multi",
        "input_count": len(req.images),
        "images": output_values(files, "image"),
    }


@app.post("/v1/images/qwen-image-edit-2511/edit-multi-lightning-4step")
async def edit_qwen_image_multi_lightning(
    req: QwenImageMultiEditLightningRequest,
    request: Request,
):
    comfyui = client(request)
    filenames = [await comfyui.upload_image(image) for image in req.images]
    workflow = load_workflow("qwen-image-edit-2511-multi-lightning-4step")
    set_multi_image_inputs(
        workflow,
        filenames,
        LIGHTNING_MULTI_IMAGE_NODES,
        ("20",),
    )
    set_lightning_edit_parameters(
        workflow,
        req.prompt,
        req.width,
        req.height,
        req.seed,
    )
    files = await comfyui.run_workflow(workflow)
    return {
        "model": "qwen-image-edit-2511",
        "profile": "lightning-4step-multi",
        "input_count": len(req.images),
        "images": output_values(files, "image"),
    }


@app.post("/v1/videos/ltx-2.3/generate")
async def generate_ltx_video(req: LTXVideoRequest, request: Request):
    comfyui = client(request)
    workflow = load_workflow("ltx-2.3")
    workflow["2483"]["inputs"]["text"] = req.prompt
    workflow["2612"]["inputs"]["text"] = req.negative_prompt
    workflow["3059"]["inputs"].update(width=req.width, height=req.height)
    workflow["4988"]["inputs"]["value"] = req.frames
    workflow["4989"]["inputs"]["value"] = req.fps

    seed = req.seed if req.seed is not None else random.randrange(1, 2**63 - 1)
    workflow["4832"]["inputs"]["noise_seed"] = seed
    workflow["4967"]["inputs"]["noise_seed"] = seed + 1

    if req.image:
        workflow["2004"]["inputs"]["image"] = await comfyui.upload_image(req.image)
        workflow["4987"]["inputs"]["value"] = False
    else:
        workflow["4987"]["inputs"]["value"] = True

    files = await comfyui.run_workflow(workflow)
    return {"model": "ltx-2.3", "videos": output_values(files, "video")}
