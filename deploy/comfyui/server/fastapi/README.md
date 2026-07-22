# ComfyUI FastAPI 服务

通过 FastAPI 调用 ComfyUI。

当前支持：

- qwen-image-2512
- qwen-image-edit-2511
- ltx-2.3

## 目录结构

```text
aigc/
└── deploy/
    └── comfyui/
        └── server/
            └── fastapi/
                ├── README.md
                ├── requirements.txt
                └── app/
                    ├── __init__.py
                    ├── main.py
                    ├── comfyui_client.py
                    └── workflows/
                        ├── qwen-image-2512_api.json
                        ├── qwen-image-edit-2511_api.json
                        └── ltx-2.3-t2v-i2v-two-stage-distilled_api.json
```

## 创建 FastAPI 虚拟环境

`.venv` 不上传 GitHub。

首次部署时，根据 `requirements.txt` 创建虚拟环境：

```bash
cd /root/autodl-tmp/aigc/deploy/comfyui/server/fastapi

python -m venv .venv

source .venv/bin/activate

pip install -U pip

pip install -r requirements.txt
```

以后启动 FastAPI 时，只需要激活虚拟环境：

```bash
cd /root/autodl-tmp/aigc/deploy/comfyui/server/fastapi

source .venv/bin/activate
```

## 启动 ComfyUI

ComfyUI 目录：

```text
/root/autodl-tmp/ComfyUI
```

启动命令：

```bash
cd /root/autodl-tmp/ComfyUI

source .venv/bin/activate
export OMP_NUM_THREADS=8

python main.py \
  --listen 127.0.0.1 \
  --port 8188 \
  --extra-model-paths-config /root/autodl-tmp/ComfyUI/extra_model_paths.yaml
```

ComfyUI 地址：

```text
http://127.0.0.1:8188
```

## 启动 FastAPI

```bash
cd /root/autodl-tmp/aigc/deploy/comfyui/server/fastapi

source .venv/bin/activate

uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000
```

FastAPI 地址：

```text
http://127.0.0.1:8000
```

Swagger：

```text
http://127.0.0.1:8000/docs
```

健康检查：

```text
GET /health
```

## Qwen-Image-2512

文生图接口：

```text
POST /v1/images/qwen-image-2512/generate
```

请求示例：

```json
{
  "prompt": "A cinematic portrait of a woman in Tokyo at night",
  "width": 720,
  "height": 1280,
  "steps": 8,
  "cfg": 1
}
```

返回：

```json
{
  "model": "qwen-image-2512",
  "images": [
    "base64..."
  ]
}
```

## Qwen-Image-Edit-2511

图片编辑接口：

```text
POST /v1/images/qwen-image-edit-2511/edit
```

请求示例：

```json
{
  "image": "base64...",
  "prompt": "Change the background to a Tokyo street at night",
  "width": 864,
  "height": 1536,
  "steps": 4
}
```

返回：

```json
{
  "model": "qwen-image-edit-2511",
  "images": [
    "base64..."
  ]
}
```

## LTX-2.3

视频生成接口：

```text
POST /v1/videos/ltx-2.3/generate
```

支持：

```text
T2V：不传 image
I2V：传入 image
```

### T2V 请求示例

```json
{
  "prompt": "A cinematic shot of a woman walking through Tokyo at night",
  "width": 960,
  "height": 544,
  "frames": 121,
  "fps": 24
}
```

### I2V 请求示例

```json
{
  "image": "base64...",
  "prompt": "The woman slowly walks forward while the camera pushes in",
  "width": 960,
  "height": 544,
  "frames": 121,
  "fps": 24
}
```

返回：

```json
{
  "model": "ltx-2.3",
  "videos": [
    "base64..."
  ]
}
```

LTX-2.3 使用的 ComfyUI API workflow：

```text
ltx-2.3-t2v-i2v-two-stage-distilled_api.json
```

## 调用流程

```text
客户端
  ↓
FastAPI :8000
  ↓
comfyui_client.py
  ↓
ComfyUI :8188
  ↓
模型生成
  ↓
Base64 返回
```

当前接口采用同步等待方式。