from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.comfyui import ComfyUIClient
from app.config import load_config
from app.schemas import MiniMaxH3Ref2VARequest, QwenImageEditRequest, QwenImageRequest
from app.workflow import (
    build_minimax_workflow,
    build_qwen_edit_workflow,
    build_qwen_image_workflow,
)


CONFIG = load_config()["services"]["comfyui_api"]


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


app = FastAPI(title="AIGC ComfyUI API", version="2.1.0", lifespan=lifespan)


def client(request: Request) -> ComfyUIClient:
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
async def generate_qwen_image(request_body: QwenImageRequest, request: Request):
    workflow, seed = build_qwen_image_workflow(request_body)
    files = await client(request).run_workflow(workflow)
    return {
        "model": "qwen-image-2512",
        "seed": seed,
        "width": request_body.width,
        "height": request_body.height,
        "images": output_values(files, "image"),
    }


@app.post("/v1/images/qwen-image-edit-2511/edit")
async def edit_qwen_image(request_body: QwenImageEditRequest, request: Request):
    comfyui = client(request)
    image_files = [await comfyui.upload_image(value) for value in request_body.images]
    workflow, seed = build_qwen_edit_workflow(request_body, image_files)
    files = await comfyui.run_workflow(workflow)
    return {
        "model": "qwen-image-edit-2511",
        "input_count": len(request_body.images),
        "seed": seed,
        "width": request_body.width,
        "height": request_body.height,
        "images": output_values(files, "image"),
    }


@app.post("/v1/videos/minimax-h3-ref2va/generate")
async def generate_minimax_h3(
    request_body: MiniMaxH3Ref2VARequest,
    request: Request,
):
    comfyui = client(request)
    image_files = [await comfyui.upload_image(value) for value in request_body.images]
    video_files = [await comfyui.upload_video(value) for value in request_body.videos]
    audio_files = [await comfyui.upload_audio(value) for value in request_body.audios]
    workflow, seed, frames = build_minimax_workflow(
        request_body,
        image_files,
        video_files,
        audio_files,
    )
    files = await comfyui.run_workflow(workflow)
    return {
        "model": "minimax-h3-ref2va",
        "diffusion_model": request_body.diffusion_model,
        "text_encoder": request_body.text_encoder,
        "enable_lora": request_body.enable_lora,
        "steps": request_body.effective_steps(),
        "input_count": {
            "images": len(request_body.images),
            "videos": len(request_body.videos),
            "audios": len(request_body.audios),
        },
        "seed": seed,
        "width": request_body.width,
        "height": request_body.height,
        "frames": frames,
        "fps": 24,
        "actual_duration": frames / 24,
        "videos": output_values(files, "video"),
    }
