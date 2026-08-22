#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${AIGC_RUNTIME_DIR:-${SCRIPT_DIR}/.runtime}"
GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:8000}"
SMOKE_OUTPUT="${SMOKE_OUTPUT:-${RUNTIME_DIR}/smoke-test.png}"
SMOKE_PROMPT="${SMOKE_PROMPT:-A small red paper boat on a calm lake, cinematic light}"
SMOKE_TIMEOUT="${SMOKE_TIMEOUT:-3600}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

command -v "$PYTHON_BIN" >/dev/null 2>&1 || {
  printf '[smoke] ERROR: 找不到 Python: %s\n' "$PYTHON_BIN" >&2
  exit 1
}

mkdir -p "$(dirname -- "$SMOKE_OUTPUT")"

"$PYTHON_BIN" - "$GATEWAY_URL" "$SMOKE_OUTPUT" "$SMOKE_PROMPT" "$SMOKE_TIMEOUT" <<'PY'
import base64
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen


base_url, output, prompt, timeout = sys.argv[1:]
base_url = base_url.rstrip("/")

with urlopen(f"{base_url}/health", timeout=10) as response:
    health = json.load(response)
if health.get("status") != "ok":
    raise SystemExit(f"[smoke] ERROR: 服务未就绪: {health}")
print(f"[smoke] 健康检查通过: {health}")

payload = json.dumps(
    {
        "prompt": prompt,
        "width": 512,
        "height": 512,
        "steps": 4,
        "seed": 1,
    }
).encode()
request = Request(
    f"{base_url}/v1/images/qwen-image-2512/generate",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urlopen(request, timeout=float(timeout)) as response:
    result = json.load(response)

images = result.get("images") or []
if not images:
    raise SystemExit(f"[smoke] ERROR: 服务未返回图片: {result}")
image = base64.b64decode(images[0], validate=True)
if not image:
    raise SystemExit("[smoke] ERROR: 服务返回了空图片")
Path(output).write_bytes(image)
print(f"[smoke] 端到端文生图通过: {output}")
PY
