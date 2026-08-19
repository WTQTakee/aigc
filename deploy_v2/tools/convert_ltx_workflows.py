#!/usr/bin/env python3
"""Convert Lightricks ComfyUI LTX-2.3 UI workflows to API prompt JSON."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


# Widget order follows each node's INPUT_TYPES/define_schema declaration. ``None``
# marks a frontend-only widget (upload preview or control-after-generate).
WIDGETS: dict[str, list[str | None]] = {
    "CFGGuider": ["cfg"],
    "CLIPTextEncode": ["text"],
    "CannyEdgePreprocessor": ["low_threshold", "high_threshold", "resolution"],
    "CheckpointLoaderSimple": ["ckpt_name"],
    "ClownSampler_Beta": ["eta", "sampler_name", "seed", None, "bongmath"],
    "ComfyMathExpression": ["expression"],
    "CreateVideo": ["fps"],
    "DWPreprocessor": [
        "detect_hand",
        "detect_body",
        "detect_face",
        "resolution",
        "bbox_detector",
        "pose_estimator",
        "scale_stick_for_xinsr_cn",
    ],
    "EmptyLTXVLatentVideo": ["width", "height", "length", "batch_size"],
    "GuiderParameters": [
        "modality",
        "cfg",
        "stg",
        "perturb_attn",
        "rescale",
        "modality_scale",
        "skip_step",
        "cross_attn",
    ],
    "ImagePadForOutpaintTargetSize": [
        "target_width",
        "target_height",
        "feathering",
        "upscale_method",
    ],
    "ImageToMask": ["channel"],
    "KSamplerSelect": ["sampler_name"],
    "LTXAVTextEncoderLoader": ["text_encoder", "ckpt_name", "device"],
    "LTXAddVideoICLoRAGuide": [
        "frame_idx",
        "strength",
        "latent_downscale_factor",
        "crop",
        "use_tiled_encode",
        "tile_size",
        "tile_overlap",
    ],
    "LTXAddVideoICLoRAGuideAdvanced": [
        "frame_idx",
        "strength",
        "latent_downscale_factor",
        "crop",
        "use_tiled_encode",
        "tile_size",
        "tile_overlap",
        "attention_strength",
    ],
    "LTXFloatToInt": ["a"],
    "LTXICLoRALoaderModelOnly": ["lora_name", "strength_model"],
    "LTXVAudioVAELoader": ["ckpt_name"],
    "LTXVConditioning": ["frame_rate"],
    "LTXVDilateVideoMask": ["spatial_radius", "temporal_radius"],
    "LTXVDrawTracks": ["tracks", "width", "height"],
    "LTXVEmptyLatentAudio": ["frames_number", "frame_rate", "batch_size"],
    "LTXVHDRDecodePostprocess": [
        "exposure",
        "save_exr",
        "output_dir",
        "filename_prefix",
        "half_precision",
    ],
    "LTXVImgToVideoConditionOnly": ["strength", "bypass"],
    "LTXVLaplacianPyramidBlend": ["trim_to_shortest", "mask_low_res_dilation"],
    "LTXVPreprocess": ["img_compression"],
    "LTXVScheduler": ["steps", "max_shift", "base_shift", "stretch", "terminal"],
    "LTXVSparseTrackEditor": [
        "points_store",
        "coordinates",
        "points_to_sample",
        None,
    ],
    "LTXVTiledVAEDecode": [
        "horizontal_tiles",
        "vertical_tiles",
        "overlap",
        "last_frame_fix",
        "working_device",
        "working_dtype",
    ],
    "LatentUpscaleModelLoader": ["model_name"],
    "LoadImage": ["image", None],
    "LoadVideo": ["file", None],
    "LoadVideoDepthAnythingModel": ["model"],
    "LoraLoaderModelOnly": ["lora_name", "strength_model"],
    "ManualSigmas": ["sigmas"],
    "MultimodalGuider": ["skip_blocks"],
    "PrimitiveBoolean": ["value"],
    "PrimitiveFloat": ["value"],
    "PrimitiveInt": ["value", None],
    "RandomNoise": ["noise_seed", None],
    "RepeatImageBatch": ["amount"],
    "SaveVideo": ["filename_prefix", "format", "codec"],
    "SimpleMath+": ["value"],
    "VAEDecodeTiled": ["tile_size", "overlap", "temporal_size", "temporal_overlap"],
    "VAEEncodeTiled": ["tile_size", "overlap", "temporal_size", "temporal_overlap"],
    "VideoDepthAnythingOutput": ["colormap"],
    "VideoDepthAnythingProcess": ["input_size", "max_res", "precision"],
}

NO_WIDGETS = {
    "GetImageSize",
    "GetImageSizeAndCount",
    "GetVideoComponents",
    "LTXVAudioOnlyEmptyVideoLatent",
    "LTXVAudioOnlyModel",
    "LTXVAudioVAEDecode",
    "LTXVAudioVAEEncode",
    "LTXVConcatAVLatent",
    "LTXVCropGuides",
    "LTXVInpaintPreprocess",
    "LTXVLatentUpsampler",
    "LTXVSeparateAVLatent",
    "LTXVSetAudioRefTokens",
    "PreviewAudio",
    "SamplerCustomAdvanced",
    "VAEEncode",
    "VAEEncodeAudio",
}

SKIP_NODE_TYPES = {"Note", "MarkdownNote"}


def api_name(source_name: str) -> str:
    name = source_name.removesuffix(".json")
    name = re.sub(r"^LTX-2\.3_", "ltx-2.3-", name)
    name = name.replace("_", "-").lower()
    return f"{name}_api.json"


def normalize_model_path(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if value == "comfy_gemma_3_12B_it.safetensors":
        return "split_files/text_encoders/gemma_3_12B_it.safetensors"
    if value.endswith("ltx-2.3-22b-ic-lora-lipdub-0.9.safetensors"):
        # The official repository renamed LipDub to DubIt after publishing the
        # workflow; the old filename no longer exists on Hugging Face.
        return "ltx-2.3-22b-ic-lora-dubit-0.9.safetensors"
    if value.startswith("ltxv/ltx2/"):
        return Path(value).name
    return value


def resize_widget_names(values: list[Any]) -> list[str]:
    mode = values[0]
    fields = {
        "match size": ["resize_type", "resize_type.crop", "scale_method"],
        "scale by multiplier": [
            "resize_type",
            "resize_type.multiplier",
            "scale_method",
        ],
        "scale dimensions": [
            "resize_type",
            "resize_type.width",
            "resize_type.height",
            "resize_type.crop",
            "scale_method",
        ],
        "scale longer dimension": [
            "resize_type",
            "resize_type.longer_size",
            "scale_method",
        ],
        "scale shorter dimension": [
            "resize_type",
            "resize_type.shorter_size",
            "scale_method",
        ],
        "scale to multiple": [
            "resize_type",
            "resize_type.multiple",
            "scale_method",
        ],
    }
    try:
        return fields[mode]
    except KeyError as exc:
        raise ValueError(f"Unsupported ResizeImageMaskNode mode: {mode}") from exc


def widget_names(node: dict[str, Any]) -> list[str | None]:
    node_type = node["type"]
    values = node.get("widgets_values")
    if node_type == "ResizeImageMaskNode":
        return resize_widget_names(values)
    if node_type in WIDGETS:
        return WIDGETS[node_type]
    if node_type in NO_WIDGETS and not values:
        return []
    raise ValueError(
        f"No widget schema for active node {node['id']} ({node_type}), values={values!r}"
    )


def link_map(workflow: dict[str, Any]) -> dict[int, list[Any]]:
    raw = {int(link[0]): link for link in workflow["links"]}
    nodes = {int(node["id"]): node for node in workflow["nodes"]}

    def resolve(link_id: int) -> list[Any]:
        link = raw[link_id]
        origin_id, origin_slot = int(link[1]), int(link[2])
        origin = nodes[origin_id]
        if origin.get("mode", 0) == 0:
            return [str(origin_id), origin_slot]
        if origin.get("mode") != 4:
            raise ValueError(f"Unsupported node mode {origin.get('mode')} on {origin_id}")

        output_type = origin["outputs"][origin_slot]["type"]
        candidates = [
            item
            for item in origin.get("inputs", [])
            if item.get("link") is not None and item.get("type") == output_type
        ]
        if len(candidates) != 1:
            raise ValueError(
                f"Cannot bypass node {origin_id} output {origin_slot} ({output_type}); "
                f"found {len(candidates)} compatible inputs"
            )
        return resolve(int(candidates[0]["link"]))

    return {
        link_id: resolve(link_id)
        for link_id, link in raw.items()
        if int(link[3]) in nodes and nodes[int(link[3])].get("mode", 0) == 0
    }


def convert(workflow: dict[str, Any]) -> dict[str, Any]:
    embedded = workflow.get("extra", {}).get("prompt")
    if isinstance(embedded, dict) and embedded:
        prompt = embedded
    else:
        links = link_map(workflow)
        prompt = {}
        for node in workflow["nodes"]:
            if node.get("mode", 0) != 0 or node["type"] in SKIP_NODE_TYPES:
                continue

            inputs: dict[str, Any] = {}
            for source_input in node.get("inputs", []):
                link_id = source_input.get("link")
                if link_id is not None:
                    inputs[source_input["name"]] = links[int(link_id)]

            values = node.get("widgets_values") or []
            names = widget_names(node)
            if len(values) != len(names):
                raise ValueError(
                    f"Widget count mismatch for {node['id']} ({node['type']}): "
                    f"{len(values)} values vs {len(names)} names"
                )
            for name, value in zip(names, values):
                if name is not None and name not in inputs:
                    inputs[name] = value

            if node["type"] in {"LoadVideo", "SaveVideo"}:
                inputs["video-preview"] = ""

            prompt[str(node["id"])] = {
                "inputs": inputs,
                "class_type": node["type"],
                "_meta": {"title": node.get("title", node["type"])},
            }

    for node in prompt.values():
        node["inputs"] = {
            key: normalize_model_path(value) for key, value in node["inputs"].items()
        }
    return prompt


def validate(prompt: dict[str, Any]) -> None:
    node_ids = set(prompt)
    for node_id, node in prompt.items():
        for name, value in node["inputs"].items():
            if (
                isinstance(value, list)
                and len(value) == 2
                and isinstance(value[0], str)
                and value[0] not in node_ids
            ):
                raise ValueError(
                    f"Node {node_id} input {name} points to omitted node {value[0]}"
                )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Official source filename to skip (repeatable)",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for source in sorted(args.source_dir.glob("*.json")):
        if source.name in args.exclude:
            continue
        workflow = json.loads(source.read_text(encoding="utf-8"))
        prompt = convert(workflow)
        validate(prompt)
        output = args.output_dir / api_name(source.name)
        output.write_text(
            json.dumps(prompt, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"{source.name} -> {output.name} ({len(prompt)} nodes)")


if __name__ == "__main__":
    main()
