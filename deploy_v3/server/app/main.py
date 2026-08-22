import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.comfyui import ComfyUIClient
from app.schemas import MiniMaxH3Request
from app.workflow import build_workflow


COMFYUI_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "1"))
WORKFLOW_TIMEOUT = float(os.getenv("WORKFLOW_TIMEOUT", "3600"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.comfyui = ComfyUIClient(
        COMFYUI_URL,
        poll_interval=POLL_INTERVAL,
        workflow_timeout=WORKFLOW_TIMEOUT,
    )
    try:
        yield
    finally:
        await app.state.comfyui.close()


app = FastAPI(
    title="MiniMax H3 Ref2VA API",
    version="3.0.0",
    lifespan=lifespan,
)


def comfyui_client(request: Request) -> ComfyUIClient:
    return request.app.state.comfyui


def error_response(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


@app.exception_handler(httpx.HTTPError)
async def handle_comfyui_http_error(_request: Request, exc: httpx.HTTPError):
    return error_response(502, f"ComfyUI 连接失败: {exc}")


@app.exception_handler(TimeoutError)
async def handle_timeout(_request: Request, exc: TimeoutError):
    return error_response(504, str(exc))


@app.exception_handler(RuntimeError)
async def handle_runtime_error(_request: Request, exc: RuntimeError):
    return error_response(502, str(exc))


@app.exception_handler(ValueError)
async def handle_value_error(_request: Request, exc: ValueError):
    return error_response(422, str(exc))


@app.get("/health")
async def health(request: Request):
    available = await comfyui_client(request).health()
    return {
        "status": "ok" if available else "degraded",
        "comfyui": available,
    }


@app.post("/v1/videos/minimax-h3-ref2va/generate")
async def generate(req: MiniMaxH3Request, request: Request):
    comfyui = comfyui_client(request)
    image_files = [
        await comfyui.upload_media(encoded, "image")
        for encoded in req.images
    ]
    video_files = [
        await comfyui.upload_media(encoded, "video")
        for encoded in req.videos
    ]
    audio_files = [
        await comfyui.upload_media(encoded, "audio")
        for encoded in req.audios
    ]
    workflow, seed, frames = build_workflow(
        req,
        image_files,
        video_files,
        audio_files,
    )
    files = await comfyui.run_workflow(workflow)
    videos = [
        item["base64"]
        for item in files
        if item["type"] == "video" and item["node_id"] == "92"
    ]
    if not videos:
        raise HTTPException(status_code=502, detail="ComfyUI 未返回视频")

    return {
        "model": "minimax-h3-ref2va",
        "diffusion_model": req.diffusion_model,
        "text_encoder": req.text_encoder,
        "enable_lora": req.enable_lora,
        "steps": req.effective_steps(),
        "scheduler": req.scheduler,
        "input_count": {
            "images": len(req.images),
            "videos": len(req.videos),
            "audios": len(req.audios),
        },
        "seed": seed,
        "width": req.width,
        "height": req.height,
        "frames": frames,
        "fps": 24,
        "actual_duration": frames / 24,
        "videos": videos,
    }
