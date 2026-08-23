# AIGC 部署 v2

个人单机使用的 FastAPI + ComfyUI 服务，提供 MiniMax H3 Ref2VA、Qwen Image 2512 和 Qwen Image Edit 2511 接口。

```text
客户端 → AutoDL 公网映射 → Gateway :6006 → ComfyUI API :8100 → ComfyUI :8188
```

## 部署目录

```text
/root/autodl-tmp/aigc/deploy_v2/comfyui_api
/root/autodl-tmp/ComfyUI
/root/autodl-tmp/models
```

需要 AutoDL Ubuntu、NVIDIA GPU、Python 3.10+ 和较新的 ComfyUI。MiniMax H3 所需的 `MiniMaxH3ReferenceToVideo`、`LoadVideo` 和 `GetVideoComponents` 均为 ComfyUI 核心节点。

## 准备 ComfyUI

```bash
apt-get update
apt-get install -y git curl ffmpeg python3-venv

cd /root/autodl-tmp
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI
python3 -m venv .venv
./.venv/bin/pip install -U pip
./.venv/bin/pip install -r requirements.txt
```

如果已安装 ComfyUI，请先执行 `git pull` 并更新 requirements。

## 模型目录

```text
/root/autodl-tmp/models/
├── diffusion_models/
│   ├── minimax_h3_ref2va_bf16.safetensors
│   ├── minimax_h3_ref2va_int8_convrot.safetensors
│   ├── minimax_h3_ref2va_pruned_bf16.safetensors
│   ├── minimax_h3_ref2va_pruned_fp8_scaled.safetensors
│   ├── minimax_h3_ref2va_pruned_int8_convrot.safetensors
│   ├── qwen_image_2512_bf16.safetensors
│   └── qwen_image_edit_2511_bf16.safetensors
├── text_encoders/
│   ├── qwen3vl_32b_minimax_h3_bf16.safetensors
│   ├── qwen3vl_32b_minimax_h3_int8_convrot.safetensors
│   ├── qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors
│   └── qwen_2.5_vl_7b_fp8_scaled.safetensors
├── vae/
│   ├── minimax_h3_video_vae_fp16.safetensors
│   ├── minimax_h3_audio_vae_fp32.safetensors
│   └── qwen_image_vae.safetensors
└── loras/
    └── minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors
```

`server/extra_model_paths.yaml` 已映射该目录，无需再修改 ComfyUI 配置。

## 启动和停止

```bash
cd /root/autodl-tmp/aigc/deploy_v2/comfyui_api/server
chmod +x start.sh stop.sh smoke_test.sh
./start.sh
curl -sS http://127.0.0.1:6006/health
./stop.sh
```

日志位于 `server/.runtime/logs/`。Gateway 监听 `6006` 端口，AutoDL 会将它映射到以下 HTTPS 公网地址：

```bash
curl -sS https://u743245-6dat-d16e8d25.bjb1.seetacloud.com:8443/health
```

客户端默认可使用该公网地址。AutoDL 实例或端口映射变更后，需要同步修改 `client/example.py` 中的 `--base-url` 默认值。对于 MiniMax H3 这类长时间同步请求，如果公网映射出现 HTML 404、502/504 或中途断开，建议使用下方的 SSH 隧道方案。

## macOS 通过 SSH 隧道同步调用

该方案保持现有同步 API 不变，但不再经过 AutoDL 的公网 HTTP 反向代理：

```text
Mac 本地客户端
  ↓ http://127.0.0.1:16006
SSH 本地端口转发
  ↓
AutoDL 127.0.0.1:6006 Gateway
  ↓
ComfyUI API :8100 → ComfyUI :8188
```

`tmux` 用于避免关闭终端窗口时结束隧道，`caffeinate` 用于允许显示器黑屏但阻止 Mac 因空闲进入系统休眠。

### 1. 准备 Mac 工具

macOS 自带 `ssh` 和 `caffeinate`。如未安装 `tmux`，可通过 Homebrew 安装：

```bash
brew install tmux
```

### 2. 确认 AutoDL 内部服务

先登录 AutoDL 并检查三层服务：

```bash
curl --max-time 10 -sS http://127.0.0.1:8188/system_stats
curl --max-time 10 -sS http://127.0.0.1:8100/health
curl --max-time 10 -sS http://127.0.0.1:6006/health
```

如服务未就绪，在 AutoDL 重启：

```bash
cd /root/autodl-tmp/aigc/deploy_v2/comfyui_api/server
./stop.sh
./start.sh
```

### 3. 在 Mac 的 tmux 中建立隧道

在 Mac 终端创建会话：

```bash
tmux new -s autodl-h3
```

在 tmux 中先填入 AutoDL 控制台显示的 SSH 主机和端口，再建立隧道：

```bash
export AUTODL_SSH_HOST="AutoDL-SSH地址"
export AUTODL_SSH_PORT="AutoDL-SSH端口"

caffeinate -i ssh -N \
  -p "$AUTODL_SSH_PORT" \
  -L 16006:127.0.0.1:6006 \
  "root@$AUTODL_SSH_HOST" \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=10 \
  -o TCPKeepAlive=yes \
  -o ExitOnForwardFailure=yes
```

参数说明：

- `16006` 是 Mac 本地端口，可换成其他未被占用的端口。
- `6006` 是 AutoDL 服务器内的 Gateway 端口。
- `ServerAliveInterval` 和 `ServerAliveCountMax` 用于尽快发现已失效的 SSH 连接。
- `caffeinate -i` 只阻止因空闲触发的系统休眠，不阻止显示器熄屏。

隧道运行后，按 `Ctrl+B`，再按 `C` 在同一 tmux 会话中新建一个窗口。

### 4. 检查本地隧道

在新 tmux 窗口执行：

```bash
curl --max-time 15 -sS http://127.0.0.1:16006/health
```

正常结果应包含：

```json
{
  "status": "ok",
  "services": {
    "comfyui_api": true
  }
}
```

如果 `/health` 长时间卡住，不要立即提交生成请求；返回 AutoDL 检查 `8100` 和 `8188` 服务。

### 5. 使用隧道同步调用

所有客户端脚本的 `base_url` 都改为 Mac 本地隧道地址：

```text
http://127.0.0.1:16006
```

例如：

```bash
python3 -B generate_two_15s_videos.py \
  --base-url http://127.0.0.1:16006
```

完整的风油精项目示例：

```bash
cd "/Users/wtq/Desktop/ai短剧"

python3 -B \
  "商业广告/风油精/天宫_v2/generate_two_15s_videos.py" \
  --base-url http://127.0.0.1:16006
```

该调用仍然是同步调用：Mac 会上传参考素材，一直等待 AutoDL 的 ComfyUI 生成完成，再通过同一条 SSH 隧道接收 Base64 视频响应。

### 6. tmux 会话管理

临时退出 tmux 但保持隧道和任务运行：

```text
Ctrl+B，然后按 D
```

查看会话：

```bash
tmux ls
```

重新进入：

```bash
tmux attach -t autodl-h3
```

在 tmux 内部窗口之间切换：

```text
Ctrl+B，然后按 N（下一个窗口）
Ctrl+B，然后按 P（上一个窗口）
```

### 7. 稳定性边界

该方案可以解决或避免：

- AutoDL 公网 HTTP 映射的 HTML 404、502/504 或长请求代理超时。
- Mac 因空闲触发的系统休眠。
- 普通终端窗口被关闭导致 SSH 进程退出。

该方案不能解决：

- 合上 MacBook 屏幕导致的强制休眠。
- Wi-Fi 断开、切换网络或路由器重启。
- AutoDL 实例关机、欠费、被回收或 SSH 服务中断。
- ComfyUI 崩溃、模型缺失、CUDA 显存不足或 Gateway 的 3600 秒内部超时。

同步 HTTP 请求一旦因 SSH 或网络中断而失败，重建隧道不能恢复原请求。如 ComfyUI 已经收到任务，它可能仍会继续生成，成片可在服务器上查找：

```bash
find /root/autodl-tmp/comfyui/output/video \
  -type f \
  -name 'minimax_h3_ref2va_api*' \
  -printf '%T@ %s %p\n' | sort -nr | head -10
```

在保持同步调用的前提下，建议保持 MacBook 开盖、电源接通和网络稳定，直到客户端已完整保存视频文件。

## API

### MiniMax H3 Ref2VA

`POST /v1/videos/minimax-h3-ref2va/generate`

```json
{
  "prompt": "Use <Picture 1> as the character reference.",
  "images": ["<base64>"],
  "videos": [],
  "audios": [],
  "diffusion_model": "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
  "text_encoder": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
  "enable_lora": false,
  "duration": 5,
  "width": 1344,
  "height": 768,
  "steps": 20,
  "seed": 42
}
```

- `images` 0–9 张，`videos` 0–3 段，`audios` 0–3 段，合计至少一个。
- 参考标签为 `<Picture 1>`、`<Video 1>` 和 `<Audio 1>`。
- 视频内嵌音轨会自动作为对应视频的参考音频。
- LoRA 关闭时 `steps` 可设置，默认 20；LoRA 开启时固定为 4 步。
- 视频固定 24 fps，请求时长会对齐到 MiniMax H3 帧数网格，响应会返回 `frames` 和 `actual_duration`。

### Qwen Image 2512

`POST /v1/images/qwen-image-2512/generate`

```json
{
  "prompt": "A cinematic portrait",
  "negative_prompt": "low quality",
  "width": 1328,
  "height": 1328,
  "steps": 50,
  "cfg": 4,
  "seed": 42
}
```

### Qwen Image Edit 2511

`POST /v1/images/qwen-image-edit-2511/edit`

```json
{
  "images": ["<main-image-base64>", "<reference-base64>"],
  "prompt": "Use the second image as a style reference",
  "negative_prompt": "",
  "width": 1024,
  "height": 1024,
  "steps": 40,
  "cfg": 4,
  "seed": 42
}
```

支持 1–3 张图片，第一张是主编辑图，其余为附加参考图。工作流不使用 LoRA。

三个接口都同步等待 ComfyUI 完成，并以 Base64 数组返回 `images` 或 `videos`。完整参数可查看 `http://127.0.0.1:8100/docs`。

## 客户端示例

```bash
cd /root/autodl-tmp/aigc/deploy_v2/comfyui_api/client
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

./.venv/bin/python example.py qwen-generate \
  --prompt "A cinematic portrait"

./.venv/bin/python example.py qwen-edit \
  --image main.png --image reference.png \
  --prompt "Use the second image as a style reference"

./.venv/bin/python example.py minimax-h3 \
  --image character.png --audio voice.wav \
  --prompt "<Picture 1> speaks with <Audio 1>." \
  --steps 20
```

## 测试

```bash
cd /root/autodl-tmp/aigc/deploy_v2/comfyui_api/server/comfyui_api
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -v

cd /root/autodl-tmp/aigc/deploy_v2/comfyui_api/server
bash tests/deploy_scripts_test.sh
./smoke_test.sh
```

`smoke_test.sh` 会通过 Qwen Image 2512 执行一次真实端到端推理。MiniMax H3 可使用上面的客户端命令验证。

官方工作流：

- https://github.com/Comfy-Org/workflow_templates/blob/main/templates/video_minimax_h3_r2v.json
- https://github.com/Comfy-Org/workflow_templates/blob/main/templates/image_qwen_Image_2512.json
- https://github.com/Comfy-Org/workflow_templates/blob/main/templates/image_qwen_image_edit_2511.json
