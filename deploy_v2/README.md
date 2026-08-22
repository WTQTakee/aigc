# AIGC 部署 v2

个人单机使用的 FastAPI + ComfyUI 服务，提供 MiniMax H3 Ref2VA、Qwen Image 2512 和 Qwen Image Edit 2511 接口。

```text
客户端 → Gateway :8000 → ComfyUI API :8100 → ComfyUI :8188
```

## 部署目录

```text
/root/autodl-tmp/aigc/deploy_v2
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
cd /root/autodl-tmp/aigc/deploy_v2/server
chmod +x start.sh stop.sh smoke_test.sh
./start.sh
curl -sS http://127.0.0.1:8000/health
./stop.sh
```

日志位于 `server/.runtime/logs/`。AutoDL 不开放 8000 端口时，可在本地建立 SSH 隧道：

```bash
ssh -N -L 8002:127.0.0.1:8000 -p <SSH端口> root@<SSH地址>
```

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
cd /root/autodl-tmp/aigc/deploy_v2/client
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
cd /root/autodl-tmp/aigc/deploy_v2/server/comfyui_api
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -v

cd /root/autodl-tmp/aigc/deploy_v2/server
bash tests/deploy_scripts_test.sh
./smoke_test.sh
```

`smoke_test.sh` 会通过 Qwen Image 2512 执行一次真实端到端推理。MiniMax H3 可使用上面的客户端命令验证。

官方工作流：

- https://github.com/Comfy-Org/workflow_templates/blob/main/templates/video_minimax_h3_r2v.json
- https://github.com/Comfy-Org/workflow_templates/blob/main/templates/image_qwen_Image_2512.json
- https://github.com/Comfy-Org/workflow_templates/blob/main/templates/image_qwen_image_edit_2511.json
