import json
import random
from pathlib import Path

from app.schemas import MiniMaxH3Request


WORKFLOW_PATH = (
    Path(__file__).parent / "workflows" / "minimax-h3-ref2va_api.json"
)


def frame_count(duration: float) -> int:
    frames = max(5, round(duration * 24))
    return frames + (5 - frames % 17) % 17


def load_base_workflow() -> dict:
    with WORKFLOW_PATH.open(encoding="utf-8") as file:
        return json.load(file)


def build_workflow(
    req: MiniMaxH3Request,
    image_files: list[str],
    video_files: list[str],
    audio_files: list[str],
) -> tuple[dict, int, int]:
    expected = (len(req.images), len(req.videos), len(req.audios))
    actual = (len(image_files), len(video_files), len(audio_files))
    if actual != expected:
        raise ValueError("已上传媒体数量与请求数量不一致")

    workflow = load_base_workflow()
    conditioning = workflow["136"]["inputs"]

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

    frames = frame_count(req.duration)
    seed = req.seed if req.seed is not None else random.randrange(0, 2**63)
    conditioning.update(
        prompt=req.prompt,
        width=req.width,
        height=req.height,
        length=frames,
        ref_image_size=req.ref_image_size,
    )
    workflow["127"]["inputs"]["unet_name"] = req.diffusion_model
    workflow["128"]["inputs"]["clip_name"] = req.text_encoder
    workflow["129"]["inputs"]["noise_seed"] = seed
    workflow["124"]["inputs"].update(
        scheduler=req.scheduler,
        steps=req.effective_steps(),
    )

    active_model = ["127", 0]
    if req.enable_lora:
        active_model = ["145", 0]
    else:
        workflow.pop("145")
    workflow["124"]["inputs"]["model"] = active_model
    workflow["126"]["inputs"]["model"] = active_model

    return workflow, seed, frames
