# AIGC 部署 v2

一个对外 Gateway，多个独立模型服务。客户端只访问 Gateway `:8000`，内部服务各自使用独立进程、端口和 Python venv。

当前包含：

- Qwen-Image-2512 文生图
- Qwen-Image-Edit-2511 图片编辑
- LTX-2.3 文生视频和图生视频

## 架构

```text
客户端
   └── Gateway :8000
          ├── /v1/images/* ──┐
          └── /v1/videos/* ──┴──> ComfyUI API :8100 ──> ComfyUI :8188
```

```text
deploy_v2/
├── server/
│   ├── config.yaml                  # 所有服务、端口、路由和超时配置
│   ├── gateway/                     # 公网入口，不加载模型
│   │   ├── app/
│   │   └── requirements.txt
│   └── comfyui_api/                 # 内部 ComfyUI 适配服务
│       ├── app/
│       │   ├── main.py
│       │   ├── comfyui.py
│       │   ├── schemas.py
│       │   └── workflows/
│       └── requirements.txt
└── client/
    ├── example.py
    └── requirements.txt
```

## 配置

编辑 `server/config.yaml`：

```yaml
gateway:
  host: 0.0.0.0
  port: 8000
  request_timeout: 3600
  routes:
    /v1/images: comfyui_api
    /v1/videos: comfyui_api

services:
  comfyui_api:
    base_url: http://127.0.0.1:8100
    host: 127.0.0.1
    port: 8100
    comfyui_url: http://127.0.0.1:8188
    poll_interval: 1
    workflow_timeout: 1800
```

`gateway.host` 设为 `0.0.0.0` 供外部访问；内部模型服务保持 `127.0.0.1`，不直接暴露公网。所有服务统一读取这一份 `config.yaml`。

## 部署

要求 Python 3.10 或更高版本。

### 1. 启动 ComfyUI

ComfyUI 继续使用它自己的 venv：

```bash
cd /root/autodl-tmp/ComfyUI
source .venv/bin/activate
export OMP_NUM_THREADS=8
python main.py \
  --listen 127.0.0.1 \
  --port 8188 \
  --extra-model-paths-config /root/autodl-tmp/ComfyUI/extra_model_paths.yaml
```

### 2. 启动 ComfyUI API

```bash
cd /root/autodl-tmp/aigc/deploy_v2/server/comfyui_api
python -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m app
```

该服务默认只监听 `127.0.0.1:8100`。

### 3. 启动 Gateway

```bash
cd /root/autodl-tmp/aigc/deploy_v2/server/gateway
python -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m app
```

Gateway 默认监听 `0.0.0.0:8000`。检查 Gateway 及内部服务：

```bash
curl http://127.0.0.1:8000/health
```

对公网开放时，建议在 Gateway 前放置 Nginx/Caddy，添加 HTTPS 和鉴权。

## 客户端调用

```bash
cd aigc/deploy_v2/client
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

### 通过 SSH 隧道访问 AutoDL Gateway（推荐）

AutoDL 实例通常不能直接从公网访问 `8000` 端口。先在 AutoDL 实例页面复制 SSH 登录命令，例如：

```bash
ssh -p 35394 root@region-1.autodl.com
```

然后在本地终端建立 SSH 隧道，将本地 `8000` 端口转发到 AutoDL 实例的 Gateway：

```bash
ssh -N -L 8000:127.0.0.1:8000 \
  -p 35394 root@region-1.autodl.com
```

请将示例中的 SSH 地址和端口替换为自己实例页面显示的值，并保持这个终端运行。隧道建立后，以下客户端命令统一使用：

```bash
--base-url http://127.0.0.1:8000
```

文生图：

```bash
./.venv/bin/python example.py text-to-image \
  --base-url http://127.0.0.1:8000 \
  --prompt "A cinematic portrait in Tokyo at night"
```

图片编辑：

```bash
./.venv/bin/python example.py edit-image \
  --base-url http://127.0.0.1:8000 \
  --input input.png \
  --prompt "Change the background to a Tokyo street"
```

文生视频：

```bash
./.venv/bin/python example.py text-to-video \
  --base-url http://127.0.0.1:8000 \
  --prompt "A woman walks through a neon street"
```

图生视频：

```bash
./.venv/bin/python example.py image-to-video \
  --base-url http://127.0.0.1:8000 \
  --input input.png \
  --prompt "The camera slowly pushes in"
```

## 新增模型服务

例如新增 `vlm_api`：

1. 创建 `server/vlm_api/app/` 和它自己的 `requirements.txt`、`.venv`。
2. 让 VLM 服务只监听一个内部端口，例如 `127.0.0.1:8200`。
3. 在 `config.yaml` 注册服务和路由：

```yaml
gateway:
  routes:
    /v1/vlm: vlm_api

services:
  vlm_api:
    base_url: http://127.0.0.1:8200
    host: 127.0.0.1
    port: 8200
```

Gateway 会将 `/v1/vlm/*` 转发到 VLM 服务，客户端仍只访问 `:8000`。修改配置后需要重启 Gateway。

## API

| 能力 | Gateway 接口 |
|---|---|
| 健康检查 | `GET /health` |
| Qwen 文生图 | `POST /v1/images/qwen-image-2512/generate` |
| Qwen 图片编辑 | `POST /v1/images/qwen-image-edit-2511/edit` |
| LTX 文/图生视频 | `POST /v1/videos/ltx-2.3/generate` |

当前为了保持代码简单，请求会等待 workflow 完成，结果以 Base64 返回。如果后续需要高并发或大视频，再增加任务队列和文件 URL。
