#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COMFYUI_DIR="${COMFYUI_DIR:-/root/autodl-tmp/ComfyUI}"
MODEL_ROOT="${MODEL_ROOT:-/root/autodl-tmp/models}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
RUNTIME_DIR="${AIGC_RUNTIME_DIR:-${SCRIPT_DIR}/.runtime}"
MODEL_PATH_CONFIG="${MODEL_PATH_CONFIG:-${SCRIPT_DIR}/extra_model_paths.yaml}"
COMFYUI_PORT="${COMFYUI_PORT:-8188}"
API_PORT="${API_PORT:-8000}"
STARTUP_TIMEOUT="${STARTUP_TIMEOUT:-300}"
COMFYUI_STORAGE_ROOT="${COMFYUI_STORAGE_ROOT:-/root/autodl-tmp/comfyui}"
PID_DIR="${RUNTIME_DIR}/pids"
LOG_DIR="${RUNTIME_DIR}/logs"
VENV_DIR="${SCRIPT_DIR}/.venv"

log() {
  printf '[start] %s\n' "$*"
}

fail() {
  printf '[start] ERROR: %s\n' "$*" >&2
  exit 1
}

require_file() {
  [[ -f "$1" ]] || fail "找不到文件: $1"
}

require_dir() {
  [[ -d "$1" ]] || fail "找不到目录: $1"
}

check_python() {
  command -v "$PYTHON_BIN" >/dev/null 2>&1 || fail "找不到 Python: $PYTHON_BIN"
  "$PYTHON_BIN" -c '
import sys
if sys.version_info < (3, 10):
    raise SystemExit(f"需要 Python 3.10+，当前是 {sys.version.split()[0]}")
'
}

requirements_hash() {
  "$PYTHON_BIN" -c '
import hashlib
import pathlib
import sys
print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
' "$1"
}

ensure_api_venv() {
  local requirements="${SCRIPT_DIR}/requirements.txt"
  local stamp="${VENV_DIR}/.requirements.sha256"
  local expected_hash installed_hash=""

  require_file "$requirements"
  if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    log "创建 FastAPI 虚拟环境: $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
  fi

  expected_hash="$(requirements_hash "$requirements")"
  [[ ! -f "$stamp" ]] || installed_hash="$(<"$stamp")"
  if [[ "$installed_hash" != "$expected_hash" ]]; then
    log "安装 FastAPI 依赖"
    "${VENV_DIR}/bin/python" -m pip install -r "$requirements"
    printf '%s\n' "$expected_hash" > "$stamp"
  else
    log "FastAPI 依赖未变化"
  fi
}

url_ready() {
  curl --fail --silent --show-error --max-time 3 "$1" >/dev/null 2>&1
}

port_in_use() {
  "$PYTHON_BIN" -c '
import socket
import sys
with socket.socket() as sock:
    sock.settimeout(1)
    raise SystemExit(0 if sock.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
' "$1"
}

wait_for_service() {
  local name="$1" health_url="$2" pidfile="$3" logfile="$4"
  local elapsed=0 pid

  while (( elapsed < STARTUP_TIMEOUT )); do
    if url_ready "$health_url"; then
      log "$name 已就绪: $health_url"
      return 0
    fi
    if [[ -f "$pidfile" ]]; then
      pid="$(<"$pidfile")"
      if ! kill -0 "$pid" 2>/dev/null; then
        printf '[start] ERROR: %s 启动失败，最近日志如下：\n' "$name" >&2
        tail -n 40 "$logfile" >&2 || true
        return 1
      fi
    fi
    sleep 1
    ((elapsed += 1))
  done

  printf '[start] ERROR: 等待 %s 超时（%ss），最近日志如下：\n' \
    "$name" "$STARTUP_TIMEOUT" >&2
  tail -n 40 "$logfile" >&2 || true
  return 1
}

start_service() {
  local name="$1" workdir="$2" port="$3" health_url="$4"
  shift 4
  local pidfile="${PID_DIR}/${name}.pid"
  local logfile="${LOG_DIR}/${name}.log"
  local pid=""

  if url_ready "$health_url"; then
    log "$name 已在运行: $health_url"
    return 0
  fi
  if [[ -f "$pidfile" ]]; then
    pid="$(<"$pidfile")"
    if kill -0 "$pid" 2>/dev/null; then
      wait_for_service "$name" "$health_url" "$pidfile" "$logfile"
      return
    fi
    rm -f "$pidfile"
  fi
  port_in_use "$port" && fail "端口 $port 已被占用，但 $health_url 不可用"

  log "启动 ${name}，日志: $logfile"
  (
    cd "$workdir"
    nohup "$@" >> "$logfile" 2>&1 </dev/null &
    printf '%s\n' "$!" > "$pidfile"
  )
  wait_for_service "$name" "$health_url" "$pidfile" "$logfile"
}

main() {
  command -v curl >/dev/null 2>&1 || fail "缺少 curl"
  check_python
  require_dir "$COMFYUI_DIR"
  require_file "${COMFYUI_DIR}/main.py"
  require_file "$MODEL_PATH_CONFIG"
  require_dir "$MODEL_ROOT"
  require_dir "${MODEL_ROOT}/diffusion_models"
  require_dir "${MODEL_ROOT}/text_encoders"
  require_dir "${MODEL_ROOT}/vae"
  require_dir "${MODEL_ROOT}/loras"
  [[ -x "${COMFYUI_DIR}/.venv/bin/python" ]] \
    || fail "ComfyUI 虚拟环境不存在: ${COMFYUI_DIR}/.venv"

  mkdir -p \
    "$PID_DIR" \
    "$LOG_DIR" \
    "${COMFYUI_STORAGE_ROOT}/input" \
    "${COMFYUI_STORAGE_ROOT}/output" \
    "${COMFYUI_STORAGE_ROOT}/temp"
  ensure_api_venv

  start_service \
    "comfyui" \
    "$COMFYUI_DIR" \
    "$COMFYUI_PORT" \
    "http://127.0.0.1:${COMFYUI_PORT}/system_stats" \
    env OMP_NUM_THREADS="${OMP_NUM_THREADS:-8}" \
    "${COMFYUI_DIR}/.venv/bin/python" main.py \
      --listen 127.0.0.1 \
      --port "$COMFYUI_PORT" \
      --extra-model-paths-config "$MODEL_PATH_CONFIG" \
      --input-directory "${COMFYUI_STORAGE_ROOT}/input" \
      --output-directory "${COMFYUI_STORAGE_ROOT}/output" \
      --temp-directory "${COMFYUI_STORAGE_ROOT}/temp"

  start_service \
    "fastapi" \
    "$SCRIPT_DIR" \
    "$API_PORT" \
    "http://127.0.0.1:${API_PORT}/health" \
    env \
      COMFYUI_URL="http://127.0.0.1:${COMFYUI_PORT}" \
      WORKFLOW_TIMEOUT="${WORKFLOW_TIMEOUT:-3600}" \
    "${VENV_DIR}/bin/python" -m uvicorn app.main:app \
      --host 0.0.0.0 \
      --port "$API_PORT"

  log "ComfyUI 和 FastAPI 启动完成"
}

main "$@"
