# FastAPI 服务

通过 FastAPI 调用 ComfyUI。

当前支持：

* qwen-image-2512
* qwen-image-edit-2511

## 目录结构

```text
server/fastapi/
├── README.md
├── requirements.txt
└── app/
    ├── main.py
    └── backends/
        └── comfyui/
            ├── client.py
            └── workflows/
                ├── qwen-image-2512_api.json
                └── qwen-image-edit-2511_api.json
```

`.venv` 虚拟环境不上传 GitHub。

首次部署或 clone 项目后，在当前目录根据 `requirements.txt` 创建环境：

```bash
cd /root/autodl-tmp/aigc/server/fastapi

python -m venv .venv

source .venv/bin/activate

pip install -U pip

pip install -r requirements.txt
```

以后启动服务时只需要激活环境：

```bash
cd /root/autodl-tmp/aigc/server/fastapi

source .venv/bin/activate
```

## 启动 FastAPI

确保 ComfyUI 已运行在：

```text
127.0.0.1:8188
```

启动 FastAPI：

```bash
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000
```

健康检查：

```text
GET /health
```

## Qwen-Image-2512

文生图：

```text
POST /v1/images/qwen-image-2512/generate
```

请求：

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
  "images": ["base64..."]
}
```

## Qwen-Image-Edit-2511

图片编辑：

```text
POST /v1/images/qwen-image-edit-2511/edit
```

请求：

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
  "images": ["base64..."]
}
```

## 调用流程

```text
客户端
  ↓
FastAPI :8000
  ↓
ComfyUI :8188
  ↓
模型生成
  ↓
Base64 返回
```

当前接口采用同步等待方式。
