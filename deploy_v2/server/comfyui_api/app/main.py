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
    LTXAudioRequest,
    LTXHDRRequest,
    LTXIngredientsRequest,
    LTXInpaintRequest,
    LTXLipdubRequest,
    LTXMotionTrackRequest,
    LTXOutpaintRequest,
    LTXPixelUpscaleRequest,
    LTXUnionControlRequest,
    LTXVideoRequest,
    LTXVideoToVideoRequest,
    MiniMaxH3Ref2VARequest,
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
MINIMAX_H3_REFERENCE_IMAGE_NODES = (
    "137",
    "139",
    "201",
    "202",
    "203",
    "204",
    "205",
    "206",
    "207",
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


def output_values(
    files: list[dict],
    file_type: str,
    node_id: str | None = None,
) -> list[str]:
    values = [
        item["base64"]
        for item in files
        if item["type"] == file_type
        and (node_id is None or item["node_id"] == node_id)
    ]
    if not values:
        raise HTTPException(status_code=502, detail=f"ComfyUI 未返回{file_type}")
    return values


def set_ltx_prompts(workflow: dict, prompt: str, negative_prompt: str) -> None:
    workflow["2483"]["inputs"]["text"] = prompt
    workflow["2612"]["inputs"]["text"] = negative_prompt


def request_seed(seed: int | None) -> int:
    return seed if seed is not None else random.randrange(1, 2**63 - 2)


def set_ltx_seeds(workflow: dict, node_ids: tuple[str, ...], seed: int | None) -> int:
    value = request_seed(seed)
    for offset, node_id in enumerate(node_ids):
        workflow[node_id]["inputs"]["noise_seed"] = value + offset
    return value


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


def minimax_h3_frame_count(duration: float) -> int:
    frames = max(5, round(duration * 24))
    return frames + (5 - frames % 17) % 17


def set_minimax_h3_ref2va_parameters(
    workflow: dict,
    req: MiniMaxH3Ref2VARequest,
    filenames: list[str],
) -> int:
    conditioning_inputs = workflow["136"]["inputs"]
    for index, node_id in enumerate(MINIMAX_H3_REFERENCE_IMAGE_NODES):
        socket_name = f"ref_images.ref_image_{index}"
        if index < len(filenames):
            workflow[node_id]["inputs"]["image"] = filenames[index]
        else:
            conditioning_inputs.pop(socket_name, None)
            workflow.pop(node_id, None)

    conditioning_inputs.update(
        prompt=req.prompt,
        width=req.width,
        height=req.height,
        length=minimax_h3_frame_count(req.duration),
        ref_image_size=req.ref_image_size,
    )
    workflow["124"]["inputs"].update(
        scheduler=req.scheduler,
        steps=req.steps,
    )
    seed = request_seed(req.seed)
    workflow["129"]["inputs"]["noise_seed"] = seed
    return seed


async def run_minimax_h3_ref2va(
    req: MiniMaxH3Ref2VARequest,
    request: Request,
    workflow_name: str,
    profile: str,
) -> dict:
    comfyui = client(request)
    filenames = [await comfyui.upload_image(image) for image in req.images]
    workflow = load_workflow(workflow_name)
    seed = set_minimax_h3_ref2va_parameters(workflow, req, filenames)
    files = await comfyui.run_workflow(workflow)
    return {
        "model": "minimax-h3-ref2va",
        "profile": profile,
        "input_count": len(req.images),
        "seed": seed,
        "width": req.width,
        "height": req.height,
        "frames": minimax_h3_frame_count(req.duration),
        "fps": 24,
        "videos": output_values(files, "video", "92"),
    }


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


@app.post("/v1/videos/ltx_2d3_t2v_i2v_two_stage_distilled")
async def ltx_2d3_t2v_i2v_two_stage_distilled(
    req: LTXVideoRequest,
    request: Request,
):
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


@app.post("/v1/videos/minimax_h3_ref2va_bf16")
async def minimax_h3_ref2va_bf16(
    req: MiniMaxH3Ref2VARequest,
    request: Request,
):
    return await run_minimax_h3_ref2va(
        req,
        request,
        "minimax-h3-ref2va-bf16",
        "bf16",
    )


@app.post("/v1/videos/minimax_h3_ref2va_quantized")
async def minimax_h3_ref2va_quantized(
    req: MiniMaxH3Ref2VARequest,
    request: Request,
):
    return await run_minimax_h3_ref2va(
        req,
        request,
        "minimax-h3-ref2va-quantized",
        "pruned-int8-nvfp4",
    )


@app.post("/v1/audio/ltx_2d3_t2a_single_stage_distilled")
async def ltx_2d3_t2a_single_stage_distilled(
    req: LTXAudioRequest,
    request: Request,
):
    workflow = load_workflow("ltx-2.3-t2a-single-stage-distilled")
    set_ltx_prompts(workflow, req.prompt, req.negative_prompt)
    workflow["4988"]["inputs"]["value"] = req.frames
    workflow["4989"]["inputs"]["value"] = req.fps
    set_ltx_seeds(workflow, ("4832",), req.seed)
    files = await client(request).run_workflow(workflow)
    return {
        "model": "ltx-2.3",
        "profile": "text-to-audio-single-stage-distilled",
        "audio": output_values(files, "audio", "9012"),
    }


@app.post("/v1/videos/ltx_2d3_t2v_i2v_single_stage_distilled_full")
async def ltx_2d3_t2v_i2v_single_stage_distilled_full(
    req: LTXVideoRequest,
    request: Request,
):
    comfyui = client(request)
    workflow = load_workflow("ltx-2.3-t2v-i2v-single-stage-distilled-full")
    set_ltx_prompts(workflow, req.prompt, req.negative_prompt)
    workflow["3059"]["inputs"].update(width=req.width, height=req.height)
    workflow["4979"]["inputs"]["value"] = req.frames
    workflow["4978"]["inputs"]["value"] = req.fps
    set_ltx_seeds(workflow, ("4814", "4832"), req.seed)
    if req.image:
        workflow["2004"]["inputs"]["image"] = await comfyui.upload_image(req.image)
        workflow["4977"]["inputs"]["value"] = False
    else:
        workflow["4977"]["inputs"]["value"] = True
    files = await comfyui.run_workflow(workflow)
    return {
        "model": "ltx-2.3",
        "profile": "single-stage-distilled-full",
        "distilled_videos": output_values(files, "video", "4852"),
        "full_videos": output_values(files, "video", "4823"),
    }


@app.post("/v1/videos/ltx_2d3_iclora_hdr_distilled")
async def ltx_2d3_iclora_hdr_distilled(req: LTXHDRRequest, request: Request):
    comfyui = client(request)
    workflow = load_workflow("ltx-2.3-iclora-hdr-distilled")
    set_ltx_prompts(workflow, req.prompt, req.negative_prompt)
    workflow["5106"]["inputs"]["file"] = await comfyui.upload_video(req.video)
    workflow["5114"]["inputs"].update(
        exposure=req.exposure,
        save_exr=req.save_exr,
    )
    set_ltx_seeds(workflow, ("4832",), req.seed)
    files = await comfyui.run_workflow(workflow)
    return {
        "model": "ltx-2.3",
        "profile": "iclora-hdr-distilled",
        "videos": output_values(files, "video", "5109"),
    }


@app.post("/v1/videos/ltx_2d3_iclora_ingredients_single_stage_distilled")
async def ltx_2d3_iclora_ingredients_single_stage_distilled(
    req: LTXIngredientsRequest,
    request: Request,
):
    comfyui = client(request)
    workflow = load_workflow("ltx-2.3-iclora-ingredients-single-stage-distilled")
    set_ltx_prompts(workflow, req.prompt, req.negative_prompt)
    workflow["2004"]["inputs"]["image"] = await comfyui.upload_image(req.image)
    workflow["5072"]["inputs"]["value"] = req.frames
    workflow["5098"]["inputs"]["value"] = req.fps
    set_ltx_seeds(workflow, ("4832",), req.seed)
    files = await comfyui.run_workflow(workflow)
    return {
        "model": "ltx-2.3",
        "profile": "iclora-ingredients-single-stage-distilled",
        "videos": output_values(files, "video", "4852"),
    }


@app.post("/v1/videos/ltx_2d3_iclora_inpaint_two_stage_distilled")
async def ltx_2d3_iclora_inpaint_two_stage_distilled(
    req: LTXInpaintRequest,
    request: Request,
):
    comfyui = client(request)
    workflow = load_workflow("ltx-2.3-iclora-inpaint-two-stage-distilled")
    set_ltx_prompts(workflow, req.prompt, req.negative_prompt)
    workflow["5368"]["inputs"]["file"] = await comfyui.upload_video(req.video)
    workflow["5375"]["inputs"]["file"] = await comfyui.upload_video(req.mask_video)
    workflow["5400"]["inputs"]["value"] = req.mask_dilation
    set_ltx_seeds(workflow, ("5210", "4832"), req.seed)
    files = await comfyui.run_workflow(workflow)
    return {
        "model": "ltx-2.3",
        "profile": "iclora-inpaint-two-stage-distilled",
        "videos": output_values(files, "video", "5228"),
    }


@app.post("/v1/videos/ltx_2d3_iclora_lipdub_two_stage_distilled")
async def ltx_2d3_iclora_lipdub_two_stage_distilled(
    req: LTXLipdubRequest,
    request: Request,
):
    comfyui = client(request)
    workflow = load_workflow("ltx-2.3-iclora-lipdub-two-stage-distilled")
    set_ltx_prompts(workflow, req.prompt, req.negative_prompt)
    workflow["5002"]["inputs"]["file"] = await comfyui.upload_video(req.video)
    set_ltx_seeds(workflow, ("4967", "4832"), req.seed)
    files = await comfyui.run_workflow(workflow)
    return {
        "model": "ltx-2.3",
        "profile": "iclora-lipdub-two-stage-distilled",
        "videos": output_values(files, "video", "4852"),
    }


@app.post("/v1/videos/ltx_2d3_iclora_motion_track_distilled")
async def ltx_2d3_iclora_motion_track_distilled(
    req: LTXMotionTrackRequest,
    request: Request,
):
    comfyui = client(request)
    workflow = load_workflow("ltx-2.3-iclora-motion-track-distilled")
    set_ltx_prompts(workflow, req.prompt, req.negative_prompt)
    workflow["2004"]["inputs"]["image"] = await comfyui.upload_image(req.image)
    workflow["5044"]["inputs"]["value"] = req.frames
    workflow["5045"]["inputs"]["value"] = req.fps
    workflow["5040"]["inputs"].update(
        points_store=json.dumps(
            [[point.model_dump() for point in track] for track in req.tracks]
        ),
        coordinates="[]",
    )
    set_ltx_seeds(workflow, ("4832",), req.seed)
    files = await comfyui.run_workflow(workflow)
    return {
        "model": "ltx-2.3",
        "profile": "iclora-motion-track-distilled",
        "videos": output_values(files, "video", "4852"),
        "track_previews": output_values(files, "video", "5052"),
    }


@app.post("/v1/videos/ltx_2d3_iclora_outpaint_two_stage_distilled")
async def ltx_2d3_iclora_outpaint_two_stage_distilled(
    req: LTXOutpaintRequest,
    request: Request,
):
    comfyui = client(request)
    workflow = load_workflow("ltx-2.3-iclora-outpaint-two-stage-distilled")
    set_ltx_prompts(workflow, req.prompt, req.negative_prompt)
    workflow["5368"]["inputs"]["file"] = await comfyui.upload_video(req.video)
    workflow["5363"]["inputs"].update(
        target_width=req.width,
        target_height=req.height,
    )
    set_ltx_seeds(workflow, ("5210", "4832"), req.seed)
    files = await comfyui.run_workflow(workflow)
    return {
        "model": "ltx-2.3",
        "profile": "iclora-outpaint-two-stage-distilled",
        "videos": output_values(files, "video", "5228"),
    }


@app.post("/v1/videos/ltx_2d3_iclora_pixel_spatial_upscaler_distilled")
async def ltx_2d3_iclora_pixel_spatial_upscaler_distilled(
    req: LTXPixelUpscaleRequest,
    request: Request,
):
    comfyui = client(request)
    workflow = load_workflow("ltx-2.3-iclora-pixel-spatial-upscaler-distilled")
    set_ltx_prompts(workflow, req.prompt, req.negative_prompt)
    workflow["5022"]["inputs"]["file"] = await comfyui.upload_video(req.video)
    set_ltx_seeds(workflow, ("4967",), req.seed)
    files = await comfyui.run_workflow(workflow)
    return {
        "model": "ltx-2.3",
        "profile": "iclora-pixel-spatial-upscaler-distilled",
        "videos": output_values(files, "video", "5014"),
    }


@app.post("/v1/videos/ltx_2d3_iclora_union_control_distilled")
async def ltx_2d3_iclora_union_control_distilled(
    req: LTXUnionControlRequest,
    request: Request,
):
    comfyui = client(request)
    workflow = load_workflow("ltx-2.3-iclora-union-control-distilled")
    set_ltx_prompts(workflow, req.prompt, req.negative_prompt)
    workflow["5001"]["inputs"]["file"] = await comfyui.upload_video(req.video)
    control_nodes = {
        "canny": ["4991", 0],
        "depth": ["5062", 0],
        "pose": ["4986", 0],
    }
    workflow["5028"]["inputs"]["input"] = control_nodes[req.control]
    set_ltx_seeds(workflow, ("4832",), req.seed)
    files = await comfyui.run_workflow(workflow)
    return {
        "model": "ltx-2.3",
        "profile": f"iclora-union-control-{req.control}-distilled",
        "videos": output_values(files, "video", "4852"),
    }


@app.post("/v1/videos/ltx_2d3_v2v_iclora_single_stage_distilled")
async def ltx_2d3_v2v_iclora_single_stage_distilled(
    req: LTXVideoToVideoRequest,
    request: Request,
):
    comfyui = client(request)
    workflow = load_workflow("ltx-2.3-v2v-iclora-single-stage-distilled")
    set_ltx_prompts(workflow, req.prompt, req.negative_prompt)
    workflow["5102"]["inputs"]["file"] = await comfyui.upload_video(req.video)
    set_ltx_seeds(workflow, ("4832",), req.seed)
    files = await comfyui.run_workflow(workflow)
    return {
        "model": "ltx-2.3",
        "profile": "v2v-iclora-single-stage-distilled",
        "videos": output_values(files, "video", "4852"),
    }
