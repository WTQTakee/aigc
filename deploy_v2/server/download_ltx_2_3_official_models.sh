#!/usr/bin/env bash

set -Eeuo pipefail

COMFYUI_DIR="${COMFYUI_DIR:-/root/autodl-tmp/ComfyUI}"
CONTROLNET_AUX_DIR="${CONTROLNET_AUX_DIR:-${COMFYUI_DIR}/custom_nodes/comfyui_controlnet_aux}"
LORA_DIR="${COMFYUI_DIR}/models/loras"
VIDEO_DEPTH_DIR="${COMFYUI_DIR}/models/videodepthanything"
DWPose_DIR="${CONTROLNET_AUX_DIR}/ckpts/yzd-v/DWPose"
DWPose_TS_DIR="${CONTROLNET_AUX_DIR}/ckpts/hr16/DWPose-TorchScript-BatchSize5"

command -v hf >/dev/null 2>&1 || {
  printf '缺少 hf 命令，请先执行: python3 -m pip install -U huggingface_hub\n' >&2
  exit 1
}

mkdir -p "$LORA_DIR" "$VIDEO_DEPTH_DIR" "$DWPose_DIR" "$DWPose_TS_DIR"

# The base checkpoint, distilled LoRA, x2 latent upscaler and Gemma encoder are
# intentionally omitted: the existing two-stage API workflow already uses them.
hf download Lightricks/LTX-2.3-22b-IC-LoRA-HDR \
  ltx-2.3-22b-ic-lora-hdr-0.9.safetensors --local-dir "$LORA_DIR"
hf download Lightricks/LTX-2.3-22b-IC-LoRA-Ingredients \
  ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors --local-dir "$LORA_DIR"
hf download Lightricks/LTX-2.3-22b-IC-LoRA-In-Outpainting \
  ltx-2.3-22b-ic-lora-in-outpainting-0.9.safetensors --local-dir "$LORA_DIR"
hf download Lightricks/LTX-2.3-22b-IC-LoRA-DubIt \
  ltx-2.3-22b-ic-lora-dubit-0.9.safetensors --local-dir "$LORA_DIR"
hf download Lightricks/LTX-2.3-22b-IC-LoRA-Motion-Track-Control \
  ltx-2.3-22b-ic-lora-motion-track-control-ref0.5.safetensors --local-dir "$LORA_DIR"
hf download Lightricks/LTX-2.3-22b-IC-LoRA-Pixel-Spatial-Upscaler \
  ltx-2.3-22b-ic-lora-pixel-spatial-upscaler-x4-0.9.safetensors --local-dir "$LORA_DIR"
hf download Lightricks/LTX-2.3-22b-IC-LoRA-Union-Control \
  ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors --local-dir "$LORA_DIR"
hf download Lightricks/LTX-2.3-22b-IC-LoRA-Instant-Shave \
  ltx-2.3-22b-ic-lora-instant-shave-0.9.safetensors --local-dir "$LORA_DIR"

# Union Control's depth and pose preprocessors use these auxiliary weights.
hf download depth-anything/Video-Depth-Anything-Small \
  video_depth_anything_vits.pth --local-dir "$VIDEO_DEPTH_DIR"
hf download yzd-v/DWPose yolox_l.onnx --local-dir "$DWPose_DIR"
hf download hr16/DWPose-TorchScript-BatchSize5 \
  dw-ll_ucoco_384_bs5.torchscript.pt --local-dir "$DWPose_TS_DIR"

printf 'LTX-2.3 官方工作流缺失模型下载完成。\n'
