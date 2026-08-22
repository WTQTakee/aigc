#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COMFYUI_DIR="${COMFYUI_DIR:-/root/autodl-tmp/ComfyUI}"
RUNTIME_DIR="${AIGC_RUNTIME_DIR:-${SCRIPT_DIR}/.runtime}"
PID_DIR="${RUNTIME_DIR}/pids"
STOP_TIMEOUT="${STOP_TIMEOUT:-30}"

log() {
  printf '[stop] %s\n' "$*"
}

process_running() {
  local pid="$1" state
  kill -0 "$pid" 2>/dev/null || return 1
  state="$(ps -o stat= -p "$pid" 2>/dev/null || true)"
  state="${state//[[:space:]]/}"
  [[ "$state" != Z* ]]
}

process_matches() {
  local pid="$1" expected="$2" command
  command="$(ps -o command= -p "$pid" 2>/dev/null || true)"
  [[ "$command" == *"$expected"* ]]
}

stop_service() {
  local name="$1" expected="$2"
  local pidfile="${PID_DIR}/${name}.pid"
  local pid elapsed=0

  if [[ ! -f "$pidfile" ]]; then
    log "$name 未记录 PID，跳过"
    return
  fi
  pid="$(<"$pidfile")"
  if [[ ! "$pid" =~ ^[0-9]+$ ]] || ! process_running "$pid"; then
    log "$name 已停止，清理旧 PID"
    rm -f "$pidfile"
    return
  fi
  if ! process_matches "$pid" "$expected"; then
    log "$name 的 PID $pid 已被其他进程占用，只清理 PID 文件"
    rm -f "$pidfile"
    return
  fi

  log "停止 ${name}（PID ${pid}）"
  kill "$pid"
  while process_running "$pid"; do
    if (( elapsed >= STOP_TIMEOUT )); then
      log "$name 未在 ${STOP_TIMEOUT}s 内退出，强制停止"
      kill -KILL "$pid" 2>/dev/null || true
      break
    fi
    sleep 1
    ((elapsed += 1))
  done
  rm -f "$pidfile"
}

stop_service fastapi "${SCRIPT_DIR}/.venv/bin/python"
stop_service comfyui "${COMFYUI_DIR}/.venv/bin/python"
log "FastAPI 和 ComfyUI 已停止"
