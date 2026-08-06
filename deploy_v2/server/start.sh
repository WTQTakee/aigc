#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COMFYUI_DIR="${COMFYUI_DIR:-/root/autodl-tmp/ComfyUI}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
RUNTIME_DIR="${AIGC_RUNTIME_DIR:-${SCRIPT_DIR}/.runtime}"
EXTRA_MODEL_PATHS_CONFIG="${EXTRA_MODEL_PATHS_CONFIG:-${COMFYUI_DIR}/extra_model_paths.yaml}"
COMFYUI_PORT="${COMFYUI_PORT:-8188}"
STARTUP_TIMEOUT="${STARTUP_TIMEOUT:-180}"

COMFYUI_API_DIR="${SCRIPT_DIR}/comfyui_api"
GATEWAY_DIR="${SCRIPT_DIR}/gateway"
CONFIG_PATH="${SCRIPT_DIR}/config.yaml"
PID_DIR="${RUNTIME_DIR}/pids"
LOG_DIR="${RUNTIME_DIR}/logs"

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

ensure_venv() {
  local service_dir="$1"
  local requirements="${service_dir}/requirements.txt"
  local venv_dir="${service_dir}/.venv"
  local stamp="${venv_dir}/.requirements.sha256"
  local expected_hash
  local installed_hash=""

  require_file "$requirements"
  if [[ ! -x "${venv_dir}/bin/python" ]]; then
    log "创建虚拟环境: $venv_dir"
    "$PYTHON_BIN" -m venv "$venv_dir"
  fi

  expected_hash="$(requirements_hash "$requirements")"
  if [[ -f "$stamp" ]]; then
    installed_hash="$(<"$stamp")"
  fi

  if [[ "$installed_hash" != "$expected_hash" ]]; then
    log "安装依赖: $requirements"
    "${venv_dir}/bin/python" -m pip install -r "$requirements"
    printf '%s\n' "$expected_hash" > "$stamp"
  else
    log "依赖未变化: $service_dir"
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
  local name="$1"
  local health_url="$2"
  local pidfile="$3"
  local logfile="$4"
  local timeout="$5"
  local elapsed=0
  local pid

  while (( elapsed < timeout )); do
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

  printf '[start] ERROR: 等待 %s 超时（%ss），最近日志如下：\n' "$name" "$timeout" >&2
  tail -n 40 "$logfile" >&2 || true
  return 1
}

start_service() {
  local name="$1"
  local workdir="$2"
  local port="$3"
  local health_url="$4"
  shift 4

  local safe_name="${name// /-}"
  local pidfile="${PID_DIR}/${safe_name}.pid"
  local logfile="${LOG_DIR}/${safe_name}.log"
  local pid=""

  if url_ready "$health_url"; then
    log "$name 已在运行: $health_url"
    return 0
  fi

  if [[ -f "$pidfile" ]]; then
    pid="$(<"$pidfile")"
    if kill -0 "$pid" 2>/dev/null; then
      log "$name 进程已存在（PID $pid），等待健康检查"
      wait_for_service "$name" "$health_url" "$pidfile" "$logfile" "$STARTUP_TIMEOUT"
      return
    fi
    rm -f "$pidfile"
  fi

  if port_in_use "$port"; then
    fail "端口 $port 已被其他进程占用，但 $health_url 不可用"
  fi

  log "启动 $name，日志: $logfile"
  (
    cd "$workdir"
    nohup "$@" >> "$logfile" 2>&1 </dev/null &
    printf '%s\n' "$!" > "$pidfile"
  )

  wait_for_service "$name" "$health_url" "$pidfile" "$logfile" "$STARTUP_TIMEOUT"
}

main() {
  command -v curl >/dev/null 2>&1 || fail "缺少 curl"
  check_python
  require_dir "$COMFYUI_DIR"
  require_file "${COMFYUI_DIR}/main.py"
  require_file "$EXTRA_MODEL_PATHS_CONFIG"
  require_file "$CONFIG_PATH"
  [[ -x "${COMFYUI_DIR}/.venv/bin/python" ]] || fail "ComfyUI 虚拟环境不存在: ${COMFYUI_DIR}/.venv"

  mkdir -p "$PID_DIR" "$LOG_DIR"
  ensure_venv "$COMFYUI_API_DIR"
  ensure_venv "$GATEWAY_DIR"

  local api_port
  local gateway_port
  api_port="$("${COMFYUI_API_DIR}/.venv/bin/python" -c '
import sys
import yaml

with open(sys.argv[1], encoding="utf-8") as file:
    print(yaml.safe_load(file)["services"]["comfyui_api"]["port"])
' "$CONFIG_PATH")"
  gateway_port="$("${COMFYUI_API_DIR}/.venv/bin/python" -c '
import sys
import yaml

with open(sys.argv[1], encoding="utf-8") as file:
    print(yaml.safe_load(file)["gateway"]["port"])
' "$CONFIG_PATH")"

  start_service \
    "comfyui" \
    "$COMFYUI_DIR" \
    "$COMFYUI_PORT" \
    "http://127.0.0.1:${COMFYUI_PORT}/system_stats" \
    env OMP_NUM_THREADS="${OMP_NUM_THREADS:-8}" \
    "${COMFYUI_DIR}/.venv/bin/python" main.py \
      --listen 127.0.0.1 \
      --port "$COMFYUI_PORT" \
      --extra-model-paths-config "$EXTRA_MODEL_PATHS_CONFIG"

  start_service \
    "comfyui-api" \
    "$COMFYUI_API_DIR" \
    "$api_port" \
    "http://127.0.0.1:${api_port}/health" \
    "${COMFYUI_API_DIR}/.venv/bin/python" -m app

  start_service \
    "gateway" \
    "$GATEWAY_DIR" \
    "$gateway_port" \
    "http://127.0.0.1:${gateway_port}/health" \
    "${GATEWAY_DIR}/.venv/bin/python" -m app

  log "全部服务启动完成"
  curl --silent --show-error "http://127.0.0.1:${gateway_port}/health"
  printf '\n'
  log "PID 目录: $PID_DIR"
  log "日志目录: $LOG_DIR"
}

main "$@"
