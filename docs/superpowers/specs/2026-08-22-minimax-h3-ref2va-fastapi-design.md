# MiniMax H3 Ref2VA FastAPI 服务设计

## 目标

在 `deploy_v3` 中建立一套个人单机使用的最小化服务：FastAPI 接收动态数量的参考图片、视频和音频，根据 ComfyUI 官方 MiniMax H3 Ref2VA 工作流构建 API workflow，同步调用同一台 ComfyUI 并返回带原生音频的 MP4 Base64。

不包含 Gateway、鉴权、数据库、任务队列、持久化、管理界面和模型下载器。

## 部署架构

```text
客户端 JSON/Base64
        │
        ▼
FastAPI :8000
  ├─ 请求和模型白名单校验
  ├─ 上传媒体到 ComfyUI input
  ├─ 构建动态 API workflow
  └─ 提交、轮询并下载结果
        │
        ▼
ComfyUI :8188
        │
        ▼
带原生音频的 MP4 Base64
```

`deploy_v3/server/start.sh` 完整启动 FastAPI 和 ComfyUI，不依赖 `deploy_v2` 的进程。ComfyUI 默认目录为 `/root/autodl-tmp/ComfyUI`，模型根目录为 `/root/autodl-tmp/models`。

## API

### 健康检查

`GET /health` 检查 FastAPI 和 ComfyUI `/system_stats` 的连通性。ComfyUI 可用时返回 `status: ok`，否则返回 `status: degraded`。

### 生成接口

`POST /v1/videos/minimax-h3-ref2va/generate`

请求使用 `application/json`：

- `prompt: str`：必填且非空。
- `images: list[str]`：0–9 个 Base64 或 Data URL；纯 Base64 默认按 PNG 处理。
- `videos: list[str]`：0–3 个 Base64 或 Data URL；纯 Base64 默认按 MP4 处理。
- `audios: list[str]`：0–3 个独立音频 Base64 或 Data URL；纯 Base64 默认按 WAV 处理。
- 三类素材的总数必须至少为 1。
- `diffusion_model`：只允许下列文件名：
  - `minimax_h3_ref2va_bf16.safetensors`
  - `minimax_h3_ref2va_int8_convrot.safetensors`
  - `minimax_h3_ref2va_pruned_bf16.safetensors`
  - `minimax_h3_ref2va_pruned_fp8_scaled.safetensors`
  - `minimax_h3_ref2va_pruned_int8_convrot.safetensors`
- `text_encoder`：只允许下列文件名：
  - `qwen3vl_32b_minimax_h3_bf16.safetensors`
  - `qwen3vl_32b_minimax_h3_int8_convrot.safetensors`
  - `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`
- `enable_lora: bool = false`：开启时使用 `minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors`，强度固定为 `1.0`，步数强制为 4。
- `duration: float = 5.0`：范围 5–15 秒。按 24 fps 换算后向上对齐到 `17k+5` 帧；5 秒为 124 帧，15 秒为 362 帧。
- `width: int = 1344` 和 `height: int = 768`：必须为 32 的倍数，且总像素不超过 `768 * 1344`。
- `seed: int | null = null`：未提供时由服务生成并在响应中返回。
- `steps: int = 20`：LoRA 关闭时有效，范围 1–100。
- `scheduler: "simple" | "normal" | "beta" = "simple"`。
- `ref_image_size: "match" | "max" = "match"`。

响应包含 `seed`、模型文件名、LoRA 状态、三类输入数量、`width`、`height`、`frames`、`fps`、`actual_duration` 和 `videos` Base64 数组。

## 工作流构建

执行用工作流来源于 Comfy-Org `workflow_templates/templates/video_minimax_h3_r2v.json`，转为 ComfyUI `/prompt` 所需的 API 格式并只保留推理节点。

基础图固定使用：

- `VAELoader`：`minimax_h3_video_vae_fp16.safetensors`。
- `VAELoader`：`minimax_h3_audio_vae_fp32.safetensors`。
- `UNETLoader`、`CLIPLoader`、`MiniMaxH3ReferenceToVideo`、`KSamplerSelect`、`BasicScheduler`、`RandomNoise`、`BasicGuider`、`SamplerCustomAdvanced`、两个 VAE 解码节点、`CreateVideo` 和 `SaveVideo`。

每次请求深拷贝基础图并进行以下变换：

1. 将白名单中的 diffusion model 和 text encoder 写入加载节点。
2. 每张图片生成一个 `LoadImage`，连接到 `ref_images.ref_image_N`。
3. 每个视频生成 `LoadVideo → GetVideoComponents`；帧批次连接到 `ref_videos.ref_video_N`，拆出的内嵌音轨连接到 `ref_video_audios.ref_video_audio_N`。
4. 每个独立音频生成一个 `LoadAudio`，连接到 `ref_audios.ref_audio_N`。
5. LoRA 开启时在原模型后接入 `LoraLoaderModelOnly`，并将 scheduler 步数设为 4；关闭时直接使用原模型和请求步数。
6. 设置 prompt、尺寸、对齐后帧数、scheduler、seed 和输出前缀。

## ComfyUI 客户端与错误处理

媒体解析 Data URL 中的 MIME type，验证 Base64 后以 UUID 文件名上传到 ComfyUI input。提交 workflow 后轮询 `/history/{prompt_id}`，成功时通过 `/view` 下载 `SaveVideo` 输出并转为 Base64。

- Pydantic 请求错误和无效 Base64：HTTP 422。
- ComfyUI 连接、提交或执行失败：HTTP 502，响应保留可诊断的错误详情。
- 轮询超时：HTTP 504。

## 文件与运维

```text
deploy_v3/
├── README.md
└── server/
    ├── app/
    │   ├── main.py
    │   ├── schemas.py
    │   ├── comfyui.py
    │   ├── workflow.py
    │   └── workflows/minimax-h3-ref2va_api.json
    ├── tests/test_schemas.py
    ├── tests/test_workflow.py
    ├── requirements.txt
    ├── extra_model_paths.yaml
    ├── start.sh
    ├── stop.sh
    └── smoke_test.sh
```

`start.sh` 负责检查 Python 3.10+、ComfyUI 代码与虚拟环境、模型根目录和端口，创建 FastAPI 虚拟环境，安装发生变化的依赖，创建输入/输出/日志/PID 目录，依次启动 ComfyUI 和 FastAPI 并等待健康检查。

`stop.sh` 只停止 PID 文件中记录且命令行与预期可执行文件匹配的 FastAPI 和 ComfyUI 进程。日志和 PID 位于 `server/.runtime/`。

`smoke_test.sh` 从 `SMOKE_IMAGE` 指定的本地图片构建 Data URL，调用默认的 pruned INT8 diffusion model、NVFP4 text encoder 和 4 步 LoRA 完成真实 5 秒推理，并将结果写入 `.runtime/smoke-test.mp4`。

README 包含 AutoDL 首次安装 ComfyUI 与 Python 环境、`/root/autodl-tmp/models` 子目录、启停命令、日志、健康检查、API 示例和真实冒烟测试命令。

## 测试

单元测试仅覆盖最容易影响真实推理的边界：

- 模型和 text encoder 白名单。
- 媒体数量、非空素材、尺寸、时长和 seed 校验。
- `17k+5` 帧数对齐。
- 图片、视频/音轨、独立音频动态节点与点号插槽连接。
- LoRA 开关、强度 1.0 和 4 步规则。
- 工作流中固定的两个 VAE 文件名。

验收命令包括 `pytest`、shell 语法检查、FastAPI 健康检查，以及在已配好 GPU 和模型的 AutoDL 主机上运行 `smoke_test.sh`。
