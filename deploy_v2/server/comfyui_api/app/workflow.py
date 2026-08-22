import json
import random
from pathlib import Path

from app.schemas import MiniMaxH3Ref2VARequest, QwenImageEditRequest, QwenImageRequest


WORKFLOW_DIR = Path(__file__).parent / "workflows"
MINIMAX_WORKFLOW = WORKFLOW_DIR / "minimax-h3-ref2va_api.json"
QWEN_IMAGE_WORKFLOW = WORKFLOW_DIR / "qwen-image-2512_api.json"
QWEN_EDIT_WORKFLOW = WORKFLOW_DIR / "qwen-image-edit-2511_api.json"
MINIMAX_IMAGE_NODE_IDS = ("137", "139", "201", "202", "203", "204", "205", "206", "207")
MINIMAX_LORA = "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors"


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def _seed(value: int | None) -> int:
    return value if value is not None else random.randrange(0, 2**63)


def minimax_frame_count(duration: float) -> int:
    frames = max(5, round(duration * 24))
    return frames + (5 - frames % 17) % 17


def build_minimax_workflow(
    request: MiniMaxH3Ref2VARequest,
    image_files: list[str],
    video_files: list[str],
    audio_files: list[str],
) -> tuple[dict, int, int]:
    expected = (len(request.images), len(request.videos), len(request.audios))
    actual = (len(image_files), len(video_files), len(audio_files))
    if actual != expected:
        raise ValueError("已上传媒体数量与请求数量不一致")

    workflow = _load(MINIMAX_WORKFLOW)
    conditioning = workflow["136"]["inputs"]
    for node_id in MINIMAX_IMAGE_NODE_IDS:
        workflow.pop(node_id, None)
    for name in tuple(conditioning):
        if name.startswith(("ref_images.", "ref_videos.", "ref_video_audios.", "ref_audios.")):
            conditioning.pop(name)

    for index, filename in enumerate(image_files):
        node_id = str(1000 + index)
        workflow[node_id] = {
            "class_type": "LoadImage",
            "inputs": {"image": filename},
        }
        conditioning[f"ref_images.ref_image_{index}"] = [node_id, 0]

    for index, filename in enumerate(video_files):
        load_id = str(1100 + index)
        components_id = str(1200 + index)
        workflow[load_id] = {
            "class_type": "LoadVideo",
            "inputs": {"file": filename},
        }
        workflow[components_id] = {
            "class_type": "GetVideoComponents",
            "inputs": {"video": [load_id, 0]},
        }
        conditioning[f"ref_videos.ref_video_{index}"] = [components_id, 0]
        conditioning[f"ref_video_audios.ref_video_audio_{index}"] = [
            components_id,
            1,
        ]

    for index, filename in enumerate(audio_files):
        node_id = str(1300 + index)
        workflow[node_id] = {
            "class_type": "LoadAudio",
            "inputs": {"audio": filename},
        }
        conditioning[f"ref_audios.ref_audio_{index}"] = [node_id, 0]

    frames = minimax_frame_count(request.duration)
    seed = _seed(request.seed)
    conditioning.update(
        prompt=request.prompt,
        width=request.width,
        height=request.height,
        length=frames,
        ref_image_size="match",
    )
    workflow["127"]["inputs"]["unet_name"] = request.diffusion_model
    workflow["128"]["inputs"]["clip_name"] = request.text_encoder
    workflow["129"]["inputs"]["noise_seed"] = seed
    workflow["124"]["inputs"].update(scheduler="simple", steps=request.effective_steps())

    active_model = ["127", 0]
    if request.enable_lora:
        workflow["145"] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": ["127", 0],
                "lora_name": MINIMAX_LORA,
                "strength_model": 1.0,
            },
        }
        active_model = ["145", 0]
    else:
        workflow.pop("145", None)
    workflow["124"]["inputs"]["model"] = active_model
    workflow["126"]["inputs"]["model"] = active_model
    workflow["92"]["inputs"]["filename_prefix"] = "video/minimax_h3_ref2va_api"
    return workflow, seed, frames


def build_qwen_image_workflow(request: QwenImageRequest) -> tuple[dict, int]:
    workflow = _load(QWEN_IMAGE_WORKFLOW)
    seed = _seed(request.seed)
    workflow["66"]["inputs"].update(
        unet_name="qwen_image_2512_bf16.safetensors",
        weight_dtype="default",
    )
    workflow["62"]["inputs"].update(
        clip_name="qwen_2.5_vl_7b_fp8_scaled.safetensors",
        type="qwen_image",
        device="default",
    )
    workflow["63"]["inputs"]["vae_name"] = "qwen_image_vae.safetensors"
    workflow["67"]["inputs"]["text"] = request.prompt
    workflow["71"]["inputs"]["text"] = request.negative_prompt
    workflow["68"]["inputs"].update(width=request.width, height=request.height)
    workflow["70"]["inputs"].update(
        seed=seed,
        steps=request.steps,
        cfg=request.cfg,
    )
    return workflow, seed


def build_qwen_edit_workflow(
    request: QwenImageEditRequest,
    image_files: list[str],
) -> tuple[dict, int]:
    if len(image_files) != len(request.images):
        raise ValueError("已上传图片数量与请求数量不一致")

    workflow = _load(QWEN_EDIT_WORKFLOW)
    image_nodes = (("6", "image1"), ("16", "image2"), ("17", "image3"))
    for index, (node_id, input_name) in enumerate(image_nodes):
        if index < len(image_files):
            workflow[node_id]["inputs"]["image"] = image_files[index]
        else:
            workflow.pop(node_id, None)
            workflow["8"]["inputs"].pop(input_name, None)
            workflow["9"]["inputs"].pop(input_name, None)

    workflow["1"]["inputs"]["unet_name"] = "qwen_image_edit_2511_bf16.safetensors"
    workflow["4"]["inputs"]["clip_name"] = "qwen_2.5_vl_7b_fp8_scaled.safetensors"
    workflow["5"]["inputs"]["vae_name"] = "qwen_image_vae.safetensors"
    workflow["7"] = {
        "class_type": "ImageScale",
        "inputs": {
            "image": ["6", 0],
            "upscale_method": "lanczos",
            "width": request.width,
            "height": request.height,
            "crop": "center",
        },
    }
    workflow["8"]["inputs"]["prompt"] = request.prompt
    workflow["9"]["inputs"]["prompt"] = request.negative_prompt
    seed = _seed(request.seed)
    workflow["13"]["inputs"].update(
        seed=seed,
        steps=request.steps,
        cfg=request.cfg,
    )
    return workflow, seed
