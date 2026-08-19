# AIGC 部署 v2

一个对外 Gateway，多个独立模型服务。客户端只访问 Gateway `:8000`，内部服务各自使用独立进程、端口和 Python venv。

当前包含：

- Qwen-Image-2512 文生图
- Qwen-Image-Edit-2511 图片编辑
- LTX-2.3 官方 ComfyUI 视频、音频和 IC-LoRA 工作流
- MiniMax H3 官方 REF2VA BF16 满血版与量化版参考生视频

## 架构

```text
客户端
   └── Gateway :8000
          ├── /v1/audio/* ───┐
          ├── /v1/images/* ───┤
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
    /v1/audio: comfyui_api
    /v1/images: comfyui_api
    /v1/videos: comfyui_api

services:
  comfyui_api:
    base_url: http://127.0.0.1:8100
    host: 127.0.0.1
    port: 8100
    comfyui_url: http://127.0.0.1:8188
    poll_interval: 1
    workflow_timeout: 3600
```

`gateway.host` 设为 `0.0.0.0` 供外部访问；内部模型服务保持 `127.0.0.1`，不直接暴露公网。所有服务统一读取这一份 `config.yaml`。

## 部署

要求 Python 3.10 或更高版本。

在 AutoDL 实例中执行：

```bash
cd /root/autodl-tmp/aigc/deploy_v2/server
chmod +x start.sh
./start.sh
```

`start.sh` 会自动完成：

1. 检查 Python 版本、ComfyUI 目录、ComfyUI venv、存储目录和 `extra_model_paths.yaml`。
2. 为 ComfyUI API 和 Gateway 创建独立的 `.venv`。
3. 仅在 `requirements.txt` 变化时重新安装依赖。
4. 后台依次启动 ComfyUI `:8188`、ComfyUI API `:8100` 和 Gateway `:8000`。
5. 等待每个服务通过健康检查，再启动下一个服务。
6. 将 PID 和日志写入 `deploy_v2/.runtime/`。

脚本可以重复执行；如果对应健康检查已经可用，不会重复启动服务。检查整体状态：

```bash
curl http://127.0.0.1:8000/health
```

查看日志：

```bash
tail -f /root/autodl-tmp/aigc/deploy_v2/.runtime/logs/comfyui.log
tail -f /root/autodl-tmp/aigc/deploy_v2/.runtime/logs/comfyui-api.log
tail -f /root/autodl-tmp/aigc/deploy_v2/.runtime/logs/gateway.log
```

默认路径和启动参数可以通过环境变量覆盖：

```bash
COMFYUI_DIR=/root/autodl-tmp/ComfyUI \
PYTHON_BIN=python3 \
OMP_NUM_THREADS=8 \
STARTUP_TIMEOUT=300 \
./start.sh
```

默认不依赖 `/root/autodl-fs`，输入、输出和临时文件分别写入：

```text
/root/autodl-tmp/comfyui/input
/root/autodl-tmp/comfyui/output
/root/autodl-tmp/comfyui/temp
```

如需切换到 AutoDL 文件存储，再通过 `COMFYUI_FILE_STORAGE_ROOT` 覆盖。

对公网开放时，建议在 Gateway 前放置 Nginx/Caddy，添加 HTTPS 和鉴权。

### LTX-2.3 官方工作流模型

原有 `ltx-2.3-t2v-i2v-two-stage-distilled_api.json` 已经使用的基础 checkpoint、distilled LoRA、x2 latent upscaler 和 Gemma 文本编码器不会重复下载。先在 Hugging Face 接受 Lightricks 模型许可并登录，然后执行：

```bash
python3 -m pip install -U huggingface_hub
hf auth login

cd /root/autodl-tmp/aigc/deploy_v2/server
COMFYUI_DIR=/root/autodl-tmp/ComfyUI \
  ./download_ltx_2_3_official_models.sh
```

脚本会下载 8 个新增 IC-LoRA 到 `ComfyUI/models/loras/`，并把 Union Control 的 Video Depth Anything 和 DWPose 权重放到对应的模型目录。

这些官方工作流还要求较新的 ComfyUI，以及下列自定义节点：

```bash
cd /root/autodl-tmp/ComfyUI/custom_nodes
git clone https://github.com/Lightricks/ComfyUI-LTXVideo.git
git clone https://github.com/kijai/ComfyUI-KJNodes.git
git clone https://github.com/Fannovel16/comfyui_controlnet_aux.git
git clone https://github.com/yuvraj108c/ComfyUI-Video-Depth-Anything.git
git clone https://github.com/ClownsharkBatwing/RES4LYF.git
git clone https://github.com/cubiq/ComfyUI_essentials.git
```

已存在的目录不要重复 `git clone`，进入目录执行 `git pull` 即可。安装或更新后，按各仓库的 `requirements.txt` 安装依赖并重启 ComfyUI。

### MiniMax H3 REF2VA 官方工作流

服务内置两个 API 格式工作流，推理拓扑来自 ComfyUI 官方
`video_minimax_h3_r2v.json`，都使用原生 `MiniMaxH3ReferenceToVideo`、
`res_multistep`、视频/音频双 VAE 解码和原生双声道输出。两者默认 20 步，
不加载 Turbo LoRA；区别仅在模型精度：

| 模式 | API JSON | Diffusion model | Text encoder |
|---|---|---|---|
| BF16 满血版 | `minimax-h3-ref2va-bf16_api.json` | `minimax_h3_ref2va_bf16.safetensors` | `qwen3vl_32b_minimax_h3_bf16.safetensors` |
| 官方量化版 | `minimax-h3-ref2va-quantized_api.json` | `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` |

二者共用：

```text
models/vae/minimax_h3_video_vae_fp16.safetensors
models/vae/minimax_h3_audio_vae_fp32.safetensors
```

如果模型独立存放在 `/root/autodl-tmp/models`，请确认 ComfyUI 的
`extra_model_paths.yaml` 包含：

```yaml
aigc_models:
  base_path: /root/autodl-tmp/models
  diffusion_models: diffusion_models
  text_encoders: text_encoders
  vae: vae
  loras: loras
```

MiniMax H3 是近期加入的原生节点，部署前需要把 ComfyUI 更新到包含
`MiniMaxH3ReferenceToVideo` 的版本并重新安装其 `requirements.txt`：

```bash
cd /root/autodl-tmp/ComfyUI
git pull
./.venv/bin/pip install -r requirements.txt
```

接口当前接收 1～9 张 Base64 参考图片。图片按照数组顺序映射为
`<Picture 1>`～`<Picture 9>`；提示词必须使用完全相同的标签。输出固定为
24fps，并同时生成画面和原生音频。`duration` 接受 5～15 秒，服务会向上
对齐到 H3 的 `17k+5` 合法帧数；例如 5 秒对应 124 帧。

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
cd aigc/deploy_v2/client
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

### MiniMax H3 REF2VA API

BF16 满血版：

```bash
cd aigc/deploy_v2/client
./.venv/bin/python - <<'PY'
import base64
from pathlib import Path

import requests


def image_base64(path):
    return base64.b64encode(Path(path).read_bytes()).decode()


response = requests.post(
    "http://127.0.0.1:8002/v1/videos/minimax_h3_ref2va_bf16",
    json={
        "images": [
            image_base64("character.png"),
            image_base64("style.png"),
        ],
        "prompt": (
            "Use <Picture 1> as the character identity and <Picture 2> as the "
            "visual style. The character walks through a rainy neon street. "
            "Camera slowly pushes in. Audio: rain, footsteps and distant traffic."
        ),
        "width": 1344,
        "height": 768,
        "duration": 5,
        "steps": 20,
        "scheduler": "simple",
        "ref_image_size": "match",
        "seed": 42,
    },
    timeout=None,
)
response.raise_for_status()
result = response.json()
Path("minimax-h3-ref2va-bf16.mp4").write_bytes(
    base64.b64decode(result["videos"][0])
)
print({key: value for key, value in result.items() if key != "videos"})
PY
```

量化版请求体完全一致，只需更换接口：

```text
POST /v1/videos/minimax_h3_ref2va_quantized
```

可调参数：

| 字段 | 默认值 | 约束/说明 |
|---|---:|---|
| `images` | 必填 | 1～9 张 Base64 图片，顺序对应 `<Picture N>` |
| `prompt` | 必填 | 必须准确引用所需的 `<Picture N>` 标签 |
| `width` | `1344` | 32～1344，且必须为 32 的倍数 |
| `height` | `768` | 32～1344，且必须为 32 的倍数 |
| `duration` | `5` | 5～15 秒，自动对齐合法帧数 |
| `steps` | `20` | 官方完整采样默认 20 步 |
| `scheduler` | `simple` | `simple`、`normal` 或 `beta` |
| `ref_image_size` | `match` | `match` 较快；`max` 保留更高参考图细节但更慢 |
| `seed` | 随机 | 可选非负整数；响应会返回实际 seed |

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
| LTX 文/图生视频 | `POST /v1/videos/ltx_2d3_t2v_i2v_two_stage_distilled` |
| LTX 文生音频 | `POST /v1/audio/ltx_2d3_t2a_single_stage_distilled` |
| LTX 单阶段文/图生视频（distilled + full） | `POST /v1/videos/ltx_2d3_t2v_i2v_single_stage_distilled_full` |
| LTX HDR | `POST /v1/videos/ltx_2d3_iclora_hdr_distilled` |
| LTX Ingredients | `POST /v1/videos/ltx_2d3_iclora_ingredients_single_stage_distilled` |
| LTX Inpaint | `POST /v1/videos/ltx_2d3_iclora_inpaint_two_stage_distilled` |
| LTX LipDub / DubIt | `POST /v1/videos/ltx_2d3_iclora_lipdub_two_stage_distilled` |
| LTX Motion Track | `POST /v1/videos/ltx_2d3_iclora_motion_track_distilled` |
| LTX Outpaint | `POST /v1/videos/ltx_2d3_iclora_outpaint_two_stage_distilled` |
| LTX Pixel x4 Upscale | `POST /v1/videos/ltx_2d3_iclora_pixel_spatial_upscaler_distilled` |
| LTX Union Control | `POST /v1/videos/ltx_2d3_iclora_union_control_distilled` |
| LTX V2V IC-LoRA | `POST /v1/videos/ltx_2d3_v2v_iclora_single_stage_distilled` |
| MiniMax H3 REF2VA BF16 满血版 | `POST /v1/videos/minimax_h3_ref2va_bf16` |
| MiniMax H3 REF2VA 官方量化版 | `POST /v1/videos/minimax_h3_ref2va_quantized` |

当前为了保持代码简单，请求会等待 workflow 完成，结果以 Base64 返回。如果后续需要高并发或大视频，再增加任务队列和文件 URL。
