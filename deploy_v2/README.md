# AIGC 部署 v2

本目录提供一个统一的 AIGC HTTP 服务：客户端只访问 Gateway，Gateway 再把请求转发给 ComfyUI API，最后由 ComfyUI 执行工作流。

```text
客户端 → Gateway :8000 → ComfyUI API :8100 → ComfyUI :8188
```

适用环境：AutoDL Ubuntu、NVIDIA GPU、Python 3.10 及以上。本文默认目录为：

```text
/root/autodl-tmp/aigc/deploy_v2
/root/autodl-tmp/ComfyUI
/root/autodl-tmp/models
```

## 1. 第一次部署

### 1.1 安装基础环境

建议直接选择 AutoDL 的 PyTorch 镜像。确认部署代码已经放在 `/root/autodl-tmp/aigc/deploy_v2`，然后执行：

```bash
apt-get update
apt-get install -y git curl python3-venv

cd /root/autodl-tmp
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI
python3 -m venv .venv
./.venv/bin/pip install -U pip
./.venv/bin/pip install -r requirements.txt
```

如果 ComfyUI 已存在，只需更新依赖：

```bash
cd /root/autodl-tmp/ComfyUI
git pull
./.venv/bin/pip install -r requirements.txt
```

### 1.2 安装 ComfyUI 自定义节点

LTX 工作流需要以下节点。只在第一次部署时执行：

```bash
cd /root/autodl-tmp/ComfyUI/custom_nodes
git clone https://github.com/Lightricks/ComfyUI-LTXVideo.git
git clone https://github.com/kijai/ComfyUI-KJNodes.git
git clone https://github.com/Fannovel16/comfyui_controlnet_aux.git
git clone https://github.com/yuvraj108c/ComfyUI-Video-Depth-Anything.git
git clone https://github.com/ClownsharkBatwing/RES4LYF.git
git clone https://github.com/cubiq/ComfyUI_essentials.git
```

安装节点依赖：

```bash
cd /root/autodl-tmp/ComfyUI/custom_nodes
for node in ComfyUI-LTXVideo ComfyUI-KJNodes comfyui_controlnet_aux ComfyUI-Video-Depth-Anything RES4LYF ComfyUI_essentials; do
  test ! -f "$node/requirements.txt" || ../.venv/bin/pip install -r "$node/requirements.txt"
done
```

如果暂时只使用 Qwen 文生图，可以先跳过本步骤。

### 1.3 准备模型

模型可以放在 ComfyUI 默认的 `models/` 下，也可以统一放在 `/root/autodl-tmp/models`。`start.sh` 要求 `/root/autodl-tmp/ComfyUI/extra_model_paths.yaml` 存在：

- 使用 ComfyUI 默认模型目录时，文件内容写成 `{}`。
- 使用独立模型目录时，文件内容如下：

```yaml
aigc_models:
  base_path: /root/autodl-tmp/models
  diffusion_models: diffusion_models
  text_encoders: text_encoders
  vae: vae
  loras: loras
  latent_upscale_models: latent_upscale_models
```

至少放好准备使用的工作流所需模型。冒烟测试使用 Qwen 文生图，需要：

```text
models/diffusion_models/qwen_image_2512_bf16.safetensors
models/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors
models/vae/qwen_image_vae.safetensors
```

其他模型的准确文件名以 `server/comfyui_api/app/workflows/*.json` 为准；缺少模型或自定义节点时，ComfyUI 日志会直接给出名称。

如需 LTX-2.3 IC-LoRA 工作流，先接受 Hugging Face 模型许可并登录，再下载补充模型：

```bash
python3 -m pip install -U huggingface_hub
hf auth login

cd /root/autodl-tmp/aigc/deploy_v2/server
./download_ltx_2_3_official_models.sh
```

### 1.4 首次启动

```bash
cd /root/autodl-tmp/aigc/deploy_v2/server
chmod +x start.sh stop.sh smoke_test.sh download_ltx_2_3_official_models.sh
./start.sh
```

`start.sh` 会自动完成以下工作：

1. 检查 Python、ComfyUI、模型路径配置和存储目录。
2. 创建 Gateway 和 ComfyUI API 各自的 `.venv` 并安装依赖。
3. 依次启动 ComfyUI、ComfyUI API 和 Gateway。
4. 等待健康检查通过，并把 PID、日志写入 `server/.runtime/`。

首次安装依赖会稍慢；以后重复执行不会重复启动已经正常运行的服务。

## 2. 一键启动和停止

启动全部服务：

```bash
cd /root/autodl-tmp/aigc/deploy_v2/server
./start.sh
```

停止由 `start.sh` 启动的全部服务：

```bash
cd /root/autodl-tmp/aigc/deploy_v2/server
./stop.sh
```

修改 `config.yaml` 或更新代码后，执行一次停止再启动即可：

```bash
./stop.sh
./start.sh
```

检查状态：

```bash
curl -sS http://127.0.0.1:8000/health
```

正常结果类似：

```json
{"status":"ok","services":{"comfyui_api":true}}
```

## 3. 冒烟测试

服务启动后执行：

```bash
cd /root/autodl-tmp/aigc/deploy_v2/server
./smoke_test.sh
```

脚本会依次：

1. 检查 Gateway、ComfyUI API 和 ComfyUI 是否正常。
2. 调用 Qwen 文生图接口完成一次真实推理。
3. 将结果保存到 `server/.runtime/smoke-test.png`。

看到下面两行即表示服务链路已跑通：

```text
[smoke] 健康检查通过: ...
[smoke] 端到端文生图通过: .../smoke-test.png
```

可自定义提示词和输出路径：

```bash
SMOKE_PROMPT="A cat sitting by the window" \
SMOKE_OUTPUT=/root/autodl-tmp/smoke.png \
./smoke_test.sh
```

## 4. 配置和目录

主要配置文件是 `server/config.yaml`：

```yaml
gateway:
  host: 0.0.0.0
  port: 8000

services:
  comfyui_api:
    host: 127.0.0.1
    port: 8100
    comfyui_url: http://127.0.0.1:8188
```

- `8000`：对外 Gateway。
- `8100`：内部 ComfyUI API，不需要开放公网。
- `8188`：内部 ComfyUI，不需要开放公网。
- ComfyUI 输入、输出和临时文件默认位于 `/root/autodl-tmp/comfyui/`。

常用环境变量：

```bash
COMFYUI_DIR=/root/autodl-tmp/ComfyUI \
COMFYUI_FILE_STORAGE_ROOT=/root/autodl-tmp \
STARTUP_TIMEOUT=300 \
./start.sh
```

## 5. 日志和常见问题

查看日志：

```bash
tail -f /root/autodl-tmp/aigc/deploy_v2/server/.runtime/logs/comfyui.log
tail -f /root/autodl-tmp/aigc/deploy_v2/server/.runtime/logs/comfyui-api.log
tail -f /root/autodl-tmp/aigc/deploy_v2/server/.runtime/logs/gateway.log
```

常见问题：

- `找不到 extra_model_paths.yaml`：按“准备模型”一节创建该文件。
- `端口已被占用`：先执行 `./stop.sh`，再用 `ss -lntp | grep -E '8000|8100|8188'` 检查残留进程。
- `ComfyUI workflow 执行失败`：优先查看 `comfyui.log`，通常是缺少模型或自定义节点。
- 启动等待超时：使用 `STARTUP_TIMEOUT=300 ./start.sh`，并同步查看日志。
- Gateway 健康状态为 `degraded`：说明 Gateway 已启动，但 ComfyUI API 或 ComfyUI 未就绪。

## 6. 从本地访问 AutoDL

AutoDL 通常不直接开放 `8000` 端口，可在本地建立 SSH 隧道：

```bash
ssh -N -L 8002:127.0.0.1:8000 \
  -p <AutoDL SSH端口> root@<AutoDL SSH地址>
```

然后在本地使用 `http://127.0.0.1:8002`：

```bash
cd aigc/deploy_v2/client
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python example.py text-to-image \
  --base-url http://127.0.0.1:8002 \
  --prompt "A cinematic portrait at night"
```

## 7. 主要 API

| 能力 | 接口 |
|---|---|
| 健康检查 | `GET /health` |
| Qwen 文生图 | `POST /v1/images/qwen-image-2512/generate` |
| Qwen 单图编辑 | `POST /v1/images/qwen-image-edit-2511/edit` |
| Qwen 单图 Lightning 编辑 | `POST /v1/images/qwen-image-edit-2511/edit-lightning-4step` |
| Qwen 多图编辑 | `POST /v1/images/qwen-image-edit-2511/edit-multi` |
| Qwen 多图 Lightning 编辑 | `POST /v1/images/qwen-image-edit-2511/edit-multi-lightning-4step` |
| LTX 文/图生视频 | `POST /v1/videos/ltx_2d3_t2v_i2v_two_stage_distilled` |
| LTX 文生音频 | `POST /v1/audio/ltx_2d3_t2a_single_stage_distilled` |
| MiniMax H3 BF16 | `POST /v1/videos/minimax_h3_ref2va_bf16` |
| MiniMax H3 量化版 | `POST /v1/videos/minimax_h3_ref2va_quantized` |

全部接口和参数可在 AutoDL 实例内查看 ComfyUI API 的在线文档：

```text
http://127.0.0.1:8100/docs
```

当前请求会一直等待 ComfyUI 工作流完成，并以 Base64 返回结果。它适合单机部署和低并发调用；高并发场景需要另行增加任务队列和对象存储。
