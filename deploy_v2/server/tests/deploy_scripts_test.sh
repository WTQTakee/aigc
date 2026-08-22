#!/usr/bin/env bash

set -Eeuo pipefail

SERVER_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_DIR="$(mktemp -d)"
RUNTIME_DIR="${TEST_DIR}/runtime"
PID_DIR="${RUNTIME_DIR}/pids"
STOP_SERVER_DIR="${TEST_DIR}/server"
TEST_COMFYUI_DIR="${TEST_DIR}/ComfyUI"
STOP_SCRIPT="${STOP_SERVER_DIR}/stop.sh"
MOCK_PORT_FILE="${TEST_DIR}/mock-port"
MOCK_SERVER="${TEST_DIR}/mock-server.py"
MOCK_PID=""
TEST_PIDS=()
SPAWNED_PID=""

cleanup() {
  local pid
  for pid in "${TEST_PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  for pid in "${TEST_PIDS[@]:-}"; do
    wait "$pid" 2>/dev/null || true
  done
  if [[ -n "$MOCK_PID" ]]; then
    kill "$MOCK_PID" 2>/dev/null || true
    wait "$MOCK_PID" 2>/dev/null || true
  fi
  rm -rf "$TEST_DIR"
}
trap cleanup EXIT

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

assert_process_stopped() {
  local pid="$1"
  if kill -0 "$pid" 2>/dev/null; then
    fail "进程仍在运行: $pid"
  fi
}

assert_process_running() {
  local pid="$1"
  kill -0 "$pid" 2>/dev/null || fail "无关进程被停止: $pid"
}

spawn_named_sleep() {
  local process_marker="$1"
  python3 -c 'import time; time.sleep(300)' "$process_marker" </dev/null >/dev/null 2>&1 &
  SPAWNED_PID=$!
}

test_stop_script() {
  local name pid executable
  mkdir -p "$PID_DIR"
  mkdir -p "$STOP_SERVER_DIR"
  ln -s "$SERVER_DIR/stop.sh" "$STOP_SCRIPT"

  for name in comfyui comfyui-api gateway; do
    case "$name" in
      comfyui) executable="${TEST_COMFYUI_DIR}/.venv/bin/python" ;;
      comfyui-api) executable="${STOP_SERVER_DIR}/comfyui_api/.venv/bin/python" ;;
      gateway) executable="${STOP_SERVER_DIR}/gateway/.venv/bin/python" ;;
    esac
    spawn_named_sleep "$executable"
    pid="$SPAWNED_PID"
    TEST_PIDS+=("$pid")
    printf '%s\n' "$pid" > "${PID_DIR}/${name}.pid"
    assert_process_running "$pid"
  done

  AIGC_RUNTIME_DIR="$RUNTIME_DIR" COMFYUI_DIR="$TEST_COMFYUI_DIR" "$STOP_SCRIPT"

  for pid in "${TEST_PIDS[@]}"; do
    wait "$pid" 2>/dev/null || true
    assert_process_stopped "$pid"
  done
  [[ -z "$(find "$PID_DIR" -type f -name '*.pid' -print -quit)" ]] \
    || fail "停止后仍残留 PID 文件"
}

test_stop_script_ignores_reused_pid() {
  local pid executable="${TEST_DIR}/unrelated/sleep"
  spawn_named_sleep "$executable"
  pid="$SPAWNED_PID"
  TEST_PIDS+=("$pid")
  printf '%s\n' "$pid" > "${PID_DIR}/gateway.pid"

  AIGC_RUNTIME_DIR="$RUNTIME_DIR" COMFYUI_DIR="$TEST_COMFYUI_DIR" "$STOP_SCRIPT"

  assert_process_running "$pid"
  [[ ! -f "${PID_DIR}/gateway.pid" ]] || fail "复用 PID 文件未清理"
  kill "$pid"
  wait "$pid" 2>/dev/null || true
}

test_smoke_script() {
  local port output_file="${TEST_DIR}/smoke-test.png"

  python3 - "$MOCK_PORT_FILE" <<'PY' &
import base64
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):
        return

    def send_json(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/health":
            self.send_error(404)
            return
        self.send_json({"status": "ok", "services": {"comfyui_api": True}})

    def do_POST(self):
        if self.path != "/v1/images/qwen-image-2512/generate":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        if not payload.get("prompt"):
            self.send_error(422)
            return
        self.send_json({
            "model": "qwen-image-2512",
            "images": [base64.b64encode(b"smoke-image").decode()],
        })


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
with open(sys.argv[1], "w", encoding="utf-8") as file:
    file.write(str(server.server_port))
server.serve_forever()
PY
  MOCK_PID=$!

  for _ in {1..50}; do
    [[ -s "$MOCK_PORT_FILE" ]] && break
    sleep 0.1
  done
  [[ -s "$MOCK_PORT_FILE" ]] || fail "模拟 Gateway 未启动"
  port="$(<"$MOCK_PORT_FILE")"

  GATEWAY_URL="http://127.0.0.1:${port}" \
    SMOKE_OUTPUT="$output_file" \
    "${SERVER_DIR}/smoke_test.sh"

  [[ "$(<"$output_file")" == "smoke-image" ]] \
    || fail "冒烟测试没有保存服务返回内容"
}

test_stop_script
test_stop_script_ignores_reused_pid
test_smoke_script
printf 'PASS: deploy scripts\n'
