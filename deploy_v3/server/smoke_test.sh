#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${AIGC_RUNTIME_DIR:-${SCRIPT_DIR}/.runtime}"
API_URL="${API_URL:-http://127.0.0.1:8000}"
SMOKE_OUTPUT="${SMOKE_OUTPUT:-${RUNTIME_DIR}/smoke-test.mp4}"
SMOKE_TIMEOUT="${SMOKE_TIMEOUT:-3600}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

[[ -n "${SMOKE_IMAGE:-}" ]] || {
  printf '[smoke] ERROR: 请通过 SMOKE_IMAGE 指定参考图\n' >&2
  exit 1
}
[[ -r "$SMOKE_IMAGE" ]] || {
  printf '[smoke] ERROR: 参考图不可读: %s\n' "$SMOKE_IMAGE" >&2
  exit 1
}
command -v "$PYTHON_BIN" >/dev/null 2>&1 || {
  printf '[smoke] ERROR: 找不到 Python: %s\n' "$PYTHON_BIN" >&2
  exit 1
}

"$PYTHON_BIN" - \
  "$API_URL" \
  "$SMOKE_IMAGE" \
  "$SMOKE_OUTPUT" \
  "$SMOKE_TIMEOUT" <<'PY'
import base64
import json
import mimetypes
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen


base_url, image_path, output_path, timeout = sys.argv[1:]
base_url = base_url.rstrip("/")

with urlopen(f"{base_url}/health", timeout=10) as response:
    health = json.load(response)
if health.get("status") != "ok":
    raise SystemExit(f"[smoke] ERROR: 服务未就绪: {health}")
print(f"[smoke] 健康检查通过: {health}")

mime_type = mimetypes.guess_type(image_path)[0] or "image/png"
encoded = base64.b64encode(Path(image_path).read_bytes()).decode()
payload = {
    "prompt": os.environ.get(
        "SMOKE_PROMPT",
        "Use <Picture 1> as the character reference in a short cinematic shot.",
    ),
    "images": [f"data:{mime_type};base64,{encoded}"],
    "diffusion_model": os.environ.get(
        "SMOKE_DIFFUSION_MODEL",
        "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
    ),
    "text_encoder": os.environ.get(
        "SMOKE_TEXT_ENCODER",
        "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    ),
    "enable_lora": True,
    "duration": 5,
    "width": 768,
    "height": 448,
    "seed": 1,
}
request = Request(
    f"{base_url}/v1/videos/minimax-h3-ref2va/generate",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urlopen(request, timeout=float(timeout)) as response:
    result = json.load(response)

videos = result.get("videos") or []
if not videos:
    raise SystemExit(f"[smoke] ERROR: 服务未返回视频: {result}")
video = base64.b64decode(videos[0], validate=True)
if not video:
    raise SystemExit("[smoke] ERROR: 服务返回了空视频")
output = Path(output_path)
output.parent.mkdir(parents=True, exist_ok=True)
output.write_bytes(video)
print(f"[smoke] MiniMax H3 Ref2VA 端到端通过: {output}")
PY
