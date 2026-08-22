#!/usr/bin/env bash

set -Eeuo pipefail

SERVER_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_DIR="$(mktemp -d)"
RUNTIME_DIR="${TEST_DIR}/runtime"
PID_DIR="${RUNTIME_DIR}/pids"
TEST_COMFYUI_DIR="${TEST_DIR}/ComfyUI"
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
  rm -rf "$TEST_DIR"
}
trap cleanup EXIT

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

spawn_named_sleep() {
  local marker="$1"
  python3 -c 'import time; time.sleep(300)' "$marker" \
    </dev/null >/dev/null 2>&1 &
  SPAWNED_PID=$!
  TEST_PIDS+=("$SPAWNED_PID")
}

assert_stopped() {
  ! kill -0 "$1" 2>/dev/null || fail "进程仍在运行: $1"
}

for script in start.sh stop.sh smoke_test.sh; do
  [[ -x "${SERVER_DIR}/${script}" ]] || fail "脚本不存在或不可执行: $script"
  bash -n "${SERVER_DIR}/${script}"
done

mkdir -p "$PID_DIR"

spawn_named_sleep "${SERVER_DIR}/.venv/bin/python"
fastapi_pid="$SPAWNED_PID"
printf '%s\n' "$fastapi_pid" > "${PID_DIR}/fastapi.pid"

spawn_named_sleep "${TEST_COMFYUI_DIR}/.venv/bin/python"
comfyui_pid="$SPAWNED_PID"
printf '%s\n' "$comfyui_pid" > "${PID_DIR}/comfyui.pid"

AIGC_RUNTIME_DIR="$RUNTIME_DIR" \
  COMFYUI_DIR="$TEST_COMFYUI_DIR" \
  STOP_TIMEOUT=2 \
  "${SERVER_DIR}/stop.sh"
wait "$fastapi_pid" 2>/dev/null || true
wait "$comfyui_pid" 2>/dev/null || true
assert_stopped "$fastapi_pid"
assert_stopped "$comfyui_pid"

spawn_named_sleep "${TEST_DIR}/unrelated/python"
unrelated_pid="$SPAWNED_PID"
printf '%s\n' "$unrelated_pid" > "${PID_DIR}/fastapi.pid"

AIGC_RUNTIME_DIR="$RUNTIME_DIR" \
  COMFYUI_DIR="$TEST_COMFYUI_DIR" \
  STOP_TIMEOUT=2 \
  "${SERVER_DIR}/stop.sh"

kill -0 "$unrelated_pid" 2>/dev/null || fail "无关进程被停止"
[[ ! -e "${PID_DIR}/fastapi.pid" ]] || fail "复用 PID 文件未清理"

printf 'PASS: deploy scripts\n'
