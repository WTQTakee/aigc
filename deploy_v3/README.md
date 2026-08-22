# MiniMax H3 Ref2VA FastAPI 服务

这是一套个人单机部署的最小服务：

```text
客户端 → FastAPI :8000 → ComfyUI :8188 → 带原生音频的 MP4
```

FastAPI 通过 ComfyUI API 上传参考素材、提交 workflow、轮询结果并返回视频 Base64。实现基于 [ComfyUI 官方 MiniMax H3 Ref2VA 工作流](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/video_minimax_h3_r2v.json) 和 [ComfyUI 官方 MiniMax H3 节点](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_extras/nodes_minimax_h3.py)。

## 1. 首次部署

适用环境：AutoDL Ubuntu、NVIDIA GPU、Python 3.10 及以上。本文默认目录：

```text
/root/autodl-tmp/aigc/deploy_v3
/root/autodl-tmp/ComfyUI
/root/autodl-tmp/models
```

### 1.1 安装系统依赖

建议使用 AutoDL 的 PyTorch 镜像。首次执行：

```bash
apt-get update
apt-get install -y git curl ffmpeg python3-venv
```

### 1.2 安装 ComfyUI

MiniMax H3 是 ComfyUI 核心节点，不需要额外自定义节点，但必须使用包含 `MiniMaxH3ReferenceToVideo`、`LoadVideo` 和 `GetVideoComponents` 的新版 ComfyUI。

新安装：

```bash
cd /root/autodl-tmp
git clone https://github.com/Comfy-Org/ComfyUI.git
cd /root/autodl-tmp/ComfyUI
python3 -m venv .venv
./.venv/bin/python -m pip install -U pip
./.venv/bin/python -m pip install -r requirements.txt
```

已安装时更新：

```bash
cd /root/autodl-tmp/ComfyUI
git pull
./.venv/bin/python -m pip install -r requirements.txt
```

### 1.3 准备模型

服务自带 `server/extra_model_paths.yaml`，将 `/root/autodl-tmp/models` 映射为 ComfyUI 模型目录。按以下结构放置文件：

```text
/root/autodl-tmp/models/
├── diffusion_models/
│   ├── minimax_h3_ref2va_bf16.safetensors
│   ├── minimax_h3_ref2va_int8_convrot.safetensors
│   ├── minimax_h3_ref2va_pruned_bf16.safetensors
│   ├── minimax_h3_ref2va_pruned_fp8_scaled.safetensors
│   └── minimax_h3_ref2va_pruned_int8_convrot.safetensors
├── text_encoders/
│   ├── qwen3vl_32b_minimax_h3_bf16.safetensors
│   ├── qwen3vl_32b_minimax_h3_int8_convrot.safetensors
│   └── qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors
├── vae/
│   ├── minimax_h3_video_vae_fp16.safetensors
│   └── minimax_h3_audio_vae_fp32.safetensors
└── loras/
    └── minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors
```

只需要存在当次请求选择的 diffusion model 和 text encoder。两个 VAE 始终需要；只有 `enable_lora=true` 时才需要 LoRA 文件。

## 2. 启动、停止和状态

第一次启动：

```bash
cd /root/autodl-tmp/aigc/deploy_v3/server
chmod +x start.sh stop.sh smoke_test.sh tests/deploy_scripts_test.sh
./start.sh
```

`start.sh` 会：

1. 检查 Python、ComfyUI、ComfyUI 虚拟环境和模型目录。
2. 自动创建 `server/.venv` 并安装 FastAPI 依赖。
3. 启动 ComfyUI `8188` 和 FastAPI `8000`。
4. 等待两个服务健康检查通过。

查看状态：

```bash
curl -sS http://127.0.0.1:8000/health
```

正常返回：

```json
{"status":"ok","comfyui":true}
```

停止 FastAPI 和由 v3 启动的 ComfyUI：

```bash
cd /root/autodl-tmp/aigc/deploy_v3/server
./stop.sh
```

修改代码或环境变量后重启：

```bash
./stop.sh
./start.sh
```

## 3. 日志

```bash
cd /root/autodl-tmp/aigc/deploy_v3/server
tail -f .runtime/logs/comfyui.log
tail -f .runtime/logs/fastapi.log
```

PID 文件位于 `.runtime/pids/`。`stop.sh` 会校验 PID 对应的命令行，不会误杀复用了旧 PID 的其他进程。

## 4. API

生成接口：

```text
POST /v1/videos/minimax-h3-ref2va/generate
Content-Type: application/json
```

| 字段 | 默认值 | 说明 |
|---|---:|---|
| `prompt` | 无 | 必填，使用 `<Picture 1>`、`<Video 1>`、`<Audio 1>` 引用素材 |
| `images` | `[]` | 0–9 个 Base64 或 Data URL |
| `videos` | `[]` | 0–3 个 Base64 或 Data URL，自动拆帧并提取内嵌音轨 |
| `audios` | `[]` | 0–3 个独立音频 Base64 或 Data URL |
| `diffusion_model` | pruned INT8 | 上述 5 个文件名之一 |
| `text_encoder` | NVFP4 AWQ | 上述 3 个文件名之一 |
| `enable_lora` | `false` | 开启 Turbo LoRA 后强度固定 1.0、采样步数强制为 4 |
| `duration` | `5.0` | 5–15 秒，按 24 fps 向上对齐到 `17k+5` 帧 |
| `width` | `1344` | 32 的倍数 |
| `height` | `768` | 32 的倍数，宽×高不超过 `768×1344` |
| `seed` | 随机 | 0 到 `2^63-1`，响应会返回实际 seed |
| `steps` | `20` | 1–100，只在关闭 LoRA 时有效 |
| `scheduler` | `simple` | `simple`、`normal` 或 `beta` |
| `ref_image_size` | `match` | `match` 更快；`max` 保留更高参考图精度，显著增加耗时 |

三类参考素材的总数必须至少为 1。提示词中的素材顺序固定为图片、视频、独立音频；有内嵌音轨的视频会在对应 `<Video N>` 前占用一个 `<Audio N>` 标签。

### Python 调用示例

```python
import base64
import json
import mimetypes
from pathlib import Path
from urllib.request import Request, urlopen


def data_url(path: str) -> str:
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    encoded = base64.b64encode(Path(path).read_bytes()).decode()
    return f"data:{mime};base64,{encoded}"


payload = {
    "prompt": (
        "Use <Picture 1> for identity, <Video 1> for motion, and "
        "<Audio 2> for the supplied voice. Create a coherent cinematic shot."
    ),
    "images": [data_url("reference.png")],
    "videos": [data_url("motion.mp4")],
    "audios": [data_url("voice.wav")],
    "diffusion_model": "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
    "text_encoder": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    "enable_lora": True,
    "duration": 5,
    "width": 1344,
    "height": 768,
    "seed": 42,
}
request = Request(
    "http://127.0.0.1:8000/v1/videos/minimax-h3-ref2va/generate",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urlopen(request, timeout=3600) as response:
    result = json.load(response)

Path("output.mp4").write_bytes(base64.b64decode(result["videos"][0]))
print({key: value for key, value in result.items() if key != "videos"})
```

上例假设参考视频本身带音轨：它的音轨是 `<Audio 1>`，独立的 `voice.wav` 需要用 `<Audio 2>` 引用。如果参考视频无音轨，独立音频仍是 `<Audio 1>`。

## 5. 冒烟测试

服务启动后，用一张本地参考图运行真实 5 秒、4 步 LoRA 推理：

```bash
cd /root/autodl-tmp/aigc/deploy_v3/server
SMOKE_IMAGE=/root/autodl-tmp/reference.png ./smoke_test.sh
```

默认结果：

```text
/root/autodl-tmp/aigc/deploy_v3/server/.runtime/smoke-test.mp4
```

自定义提示词和输出位置：

```bash
SMOKE_IMAGE=/root/autodl-tmp/reference.png \
SMOKE_PROMPT="Use <Picture 1> as identity, cinematic close-up with dialogue." \
SMOKE_OUTPUT=/root/autodl-tmp/minimax-smoke.mp4 \
./smoke_test.sh
```

## 6. 本地单元测试

FastAPI 虚拟环境已由 `start.sh` 创建后：

```bash
cd /root/autodl-tmp/aigc/deploy_v3/server
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -v
bash tests/deploy_scripts_test.sh
bash -n start.sh stop.sh smoke_test.sh
```

这些测试不加载大模型；`smoke_test.sh` 才是 GPU 端到端测试。

## 7. 环境变量

| 变量 | 默认值 | 用途 |
|---|---|---|
| `COMFYUI_DIR` | `/root/autodl-tmp/ComfyUI` | ComfyUI 代码目录 |
| `MODEL_ROOT` | `/root/autodl-tmp/models` | 启动时检查的模型根目录 |
| `MODEL_PATH_CONFIG` | `server/extra_model_paths.yaml` | ComfyUI 额外模型路径配置 |
| `COMFYUI_PORT` | `8188` | ComfyUI 端口 |
| `API_PORT` | `8000` | FastAPI 端口 |
| `COMFYUI_STORAGE_ROOT` | `/root/autodl-tmp/comfyui` | ComfyUI input/output/temp 根目录 |
| `STARTUP_TIMEOUT` | `300` | 服务启动等待秒数 |
| `WORKFLOW_TIMEOUT` | `3600` | 单次 workflow 超时秒数 |
| `PYTHON_BIN` | `python3` | 创建 FastAPI 虚拟环境的 Python |

如果模型不在默认路径，同时传入匹配的 `MODEL_ROOT` 和自定义 `MODEL_PATH_CONFIG`。

## 8. 常见问题

- `MiniMaxH3ReferenceToVideo` / `LoadVideo` / `GetVideoComponents` 节点不存在：更新 `/root/autodl-tmp/ComfyUI` 并重新安装其 requirements。
- `Value not in list` 或模型文件不存在：检查文件名大小写和 `models/` 子目录。
- CUDA OOM：优先选用 pruned INT8 diffusion model 和 NVFP4 text encoder，使用 `ref_image_size=match`，并减少参考素材。
- 请求超时：使用 `WORKFLOW_TIMEOUT=7200 ./start.sh`，同时检查 `comfyui.log`。
- 结果与参考素材不匹配：确保 prompt 中的 `<Picture N>`、`<Video N>` 和 `<Audio N>` 与输入顺序一致。
- `/health` 返回 `degraded`：查看 `.runtime/logs/comfyui.log`，并直接检查 `curl http://127.0.0.1:8188/system_stats`。
- 端口被占用：先执行 `./stop.sh`，再用 `ss -lntp | grep -E '8000|8188'` 检查残留进程。
