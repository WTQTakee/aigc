import json
import random
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.comfyui import ComfyUIClient
from app.config import load_config
from app.schemas import LTXVideoRequest, QwenImageEditRequest, QwenImageRequest


WORKFLOW_DIR = Path(__file__).parent / "workflows"
CONFIG = load_config()["services"]["comfyui_api"]
WORKFLOW_FILES = CONFIG["workflows"]


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
    workflow["21"]["inputs"]["image"] = filename
    workflow["20"]["inputs"]["prompt"] = req.prompt
    workflow["17"]["inputs"].update(width=req.width, height=req.height)
    workflow["11"]["inputs"]["steps"] = req.steps
    workflow["7"]["inputs"]["noise_seed"] = (
        req.seed if req.seed is not None else random.randrange(1, 2**63)
    )
    files = await comfyui.run_workflow(workflow)
    return {
        "model": "qwen-image-edit-2511",
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
