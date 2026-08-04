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
ssh -p 39402 root@connect.bjb1.seetacloud.com
```

然后在本地终端建立 SSH 隧道，将本地 `8000` 端口转发到 AutoDL 实例的 Gateway：

```bash
ssh -N -L 8002:127.0.0.1:8000 \
  -p 39402 root@connect.bjb1.seetacloud.com
```

请将示例中的 SSH 地址和端口替换为自己实例页面显示的值，并保持这个终端运行。隧道建立后，以下客户端命令统一使用：

```bash
--base-url http://127.0.0.1:8002
```

文生图：

```bash
./.venv/bin/python example.py text-to-image \
  --base-url http://127.0.0.1:8002 \
  --prompt "A cinematic portrait in Tokyo at night"
```

图片编辑：

```bash
./.venv/bin/python example.py edit-image \
  --base-url http://127.0.0.1:8002 \
  --input input.png \
  --prompt "Change the background to a Tokyo street"
```

上面的 `edit-image` 默认调用单图满血版。Qwen-Image-Edit-2511 当前提供四种 API：

| 模式 | 工作流 | Gateway 接口 |
|---|---|---|
| 单图满血版 | `qwen-image-edit-2511_api.json` | `POST /v1/images/qwen-image-edit-2511/edit` |
| 单图 Lightning 4 步 | `qwen-image-edit-2511_lightning-4step_api.json` | `POST /v1/images/qwen-image-edit-2511/edit-lightning-4step` |
| 1～3 图满血版 | `qwen-image-edit-2511-multi_api.json` | `POST /v1/images/qwen-image-edit-2511/edit-multi` |
| 1～3 图 Lightning 4 步 | `qwen-image-edit-2511-multi-lightning-4step_api.json` | `POST /v1/images/qwen-image-edit-2511/edit-multi-lightning-4step` |

满血版默认使用 40 步、CFG 4，不加载 Lightning LoRA；输出尺寸跟随经过 `FluxKontextImageScale` 处理后的主图。可传入 `negative_prompt`、`steps`、`cfg` 和 `seed`。

Lightning 版固定使用 4 步 LoRA；可传入 `width`、`height` 和 `seed`，默认尺寸为 `864x1536`。

多图接口的 `images` 数组接受 1～3 张 Base64 图片，第一张是主图，其余为可选参考图。未提供的参考图节点会在提交 ComfyUI 前自动移除。下面是满血多图版调用示例：

```bash
./.venv/bin/python - <<'PY'
import base64
from pathlib import Path

import requests


def image_base64(path):
    return base64.b64encode(Path(path).read_bytes()).decode()


response = requests.post(
    "http://127.0.0.1:8002/v1/images/qwen-image-edit-2511/edit-multi",
    json={
        "images": [
            image_base64("input-1.png"),
            image_base64("input-2.png"),
            image_base64("input-3.png"),
        ],
        "prompt": "Use image 1 as the main scene, image 2 as the character reference, and image 3 as the clothing reference.",
        "steps": 40,
        "cfg": 4,
    },
    timeout=None,
)
response.raise_for_status()
Path("qwen-image-edit-2511-multi.png").write_bytes(
    base64.b64decode(response.json()["images"][0])
)
PY
```

将 URL 改为下面的地址即可调用多图 Lightning 4 步版：

```text
http://127.0.0.1:8002/v1/images/qwen-image-edit-2511/edit-multi-lightning-4step
```

### 直接调用 ComfyUI 三图工作流（Lightning 4 步，调试用）

工作流文件：

```text
server/comfyui_api/app/workflows/qwen-image-edit-2511-multi-lightning-4step_api.json
```

该工作流使用原生 `TextEncodeQwenImageEditPlus`，固定接收三张图片：

| 图片 | `LoadImage` 节点 | 用途 |
|---|---:|---|
| `image1` | `21` | 主图 |
| `image2` | `23` | 参考图 |
| `image3` | `24` | 参考图 |

它默认加载以下模型：

```text
models/diffusion_models/qwen_image_edit_2511_bf16.safetensors
models/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors
models/vae/qwen_image_vae.safetensors
models/loras/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors
```

如需绕过 Gateway 和 `comfyui_api` 调试原始工作流，可以在 AutoDL 实例内直接调用 ComfyUI API。先把三张图片上传到 ComfyUI：

```bash
curl -sS -X POST http://127.0.0.1:8188/upload/image \
  -F 'image=@/root/autodl-tmp/input-1.png' \
  -F 'overwrite=true'

curl -sS -X POST http://127.0.0.1:8188/upload/image \
  -F 'image=@/root/autodl-tmp/input-2.png' \
  -F 'overwrite=true'

curl -sS -X POST http://127.0.0.1:8188/upload/image \
  -F 'image=@/root/autodl-tmp/input-3.png' \
  -F 'overwrite=true'
```

上传接口会返回图片的 `name`。如果返回的名称不是 `input-1.png`、`input-2.png` 和 `input-3.png`，请在下面命令中使用实际返回值。提交工作流：

```bash
cd /root/autodl-tmp/aigc/deploy_v2/server/comfyui_api

jq --arg prompt \
  'Use image 1 as the main image. Put the person from image 2 in the scene, using image 3 as the clothing reference.' \
  '."21".inputs.image = "input-1.png"
   | ."23".inputs.image = "input-2.png"
   | ."24".inputs.image = "input-3.png"
   | ."20".inputs.prompt = $prompt
   | {prompt: .}' \
  app/workflows/qwen-image-edit-2511-multi-lightning-4step_api.json \
  | curl -sS -X POST http://127.0.0.1:8188/prompt \
      -H 'Content-Type: application/json' \
      --data-binary @-
```

请求成功后会返回 `prompt_id`。生成结果由 `SaveImage` 节点写入：

```text
/root/autodl-tmp/ComfyUI/output/
```

该工作流默认输出尺寸为 `864x1536`，采样步数为 `4`。可在提交前通过 `jq` 修改节点 `17` 的 `width`、`height`，以及节点 `7` 的 `noise_seed`。

文生视频：

```bash
./.venv/bin/python example.py text-to-video \
  --base-url http://127.0.0.1:8002 \
  --prompt "A woman walks through a neon street"
```

图生视频：

```bash
./.venv/bin/python example.py image-to-video \
  --base-url http://127.0.0.1:8002 \
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
| Qwen 单图满血编辑 | `POST /v1/images/qwen-image-edit-2511/edit` |
| Qwen 单图 Lightning 4 步编辑 | `POST /v1/images/qwen-image-edit-2511/edit-lightning-4step` |
| Qwen 1～3 图满血编辑 | `POST /v1/images/qwen-image-edit-2511/edit-multi` |
| Qwen 1～3 图 Lightning 4 步编辑 | `POST /v1/images/qwen-image-edit-2511/edit-multi-lightning-4step` |
| LTX 文/图生视频 | `POST /v1/videos/ltx-2.3/generate` |

当前为了保持代码简单，请求会等待 workflow 完成，结果以 Base64 返回。如果后续需要高并发或大视频，再增加任务队列和文件 URL。
