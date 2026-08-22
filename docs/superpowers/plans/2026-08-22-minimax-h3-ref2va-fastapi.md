# MiniMax H3 Ref2VA FastAPI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a minimal standalone FastAPI service in `deploy_v3` that starts the shared ComfyUI installation, builds the official MiniMax H3 Ref2VA workflow dynamically, and returns generated MP4 data synchronously.

**Architecture:** One FastAPI process on port 8000 talks directly to one ComfyUI process on port 8188. A small request schema validates model filenames and media counts, a workflow builder mutates a bundled API-format official workflow, and an async ComfyUI client uploads Base64 media, submits `/prompt`, polls `/history`, and downloads the `SaveVideo` output.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic 2, HTTPX, Uvicorn, Bash, ComfyUI core nodes

**Spec:** `docs/superpowers/specs/2026-08-22-minimax-h3-ref2va-fastapi-design.md`

## Global Constraints

- Keep the implementation personal-use and minimal: no gateway, authentication, database, queue, persistence, UI, or model downloader.
- Default ComfyUI path is `/root/autodl-tmp/ComfyUI`.
- Default model root is `/root/autodl-tmp/models`.
- FastAPI listens on port 8000 and ComfyUI listens on port 8188.
- Inputs and outputs use JSON Base64/Data URLs and a synchronous request.
- Use only ComfyUI core nodes from the official MiniMax H3 Ref2VA workflow.
- The two VAE filenames and Turbo LoRA filename are fixed exactly as written in the spec.

---

### Task 1: Request schema and parameter rules

**Files:**
- Create: `deploy_v3/server/app/__init__.py`
- Create: `deploy_v3/server/app/schemas.py`
- Create: `deploy_v3/server/tests/test_schemas.py`
- Create: `deploy_v3/server/requirements.txt`

**Interfaces:**
- Produces: `MiniMaxH3Request`, `DIFFUSION_MODELS`, `TEXT_ENCODERS` in `app.schemas`.
- `MiniMaxH3Request.effective_steps() -> int` returns 4 when LoRA is enabled, otherwise `steps`.

- [ ] **Step 1: Write the failing schema tests**

```python
import unittest

from pydantic import ValidationError

from app.schemas import MiniMaxH3Request


class MiniMaxH3RequestTest(unittest.TestCase):
    def valid(self, **changes):
        data = {
            "prompt": "Use <Picture 1> as the character reference.",
            "images": ["aW1hZ2U="],
            "diffusion_model": "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
            "text_encoder": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        }
        data.update(changes)
        return MiniMaxH3Request(**data)

    def test_accepts_each_supported_model(self):
        self.valid(diffusion_model="minimax_h3_ref2va_bf16.safetensors")
        self.valid(text_encoder="qwen3vl_32b_minimax_h3_bf16.safetensors")

    def test_rejects_unknown_model(self):
        with self.assertRaises(ValidationError):
            self.valid(diffusion_model="other.safetensors")

    def test_requires_at_least_one_reference(self):
        with self.assertRaises(ValidationError):
            self.valid(images=[], videos=[], audios=[])

    def test_enforces_reference_limits(self):
        with self.assertRaises(ValidationError):
            self.valid(images=["a"] * 10)
        with self.assertRaises(ValidationError):
            self.valid(videos=["a"] * 4)
        with self.assertRaises(ValidationError):
            self.valid(audios=["a"] * 4)

    def test_enforces_canvas_constraints(self):
        with self.assertRaises(ValidationError):
            self.valid(width=1000)
        with self.assertRaises(ValidationError):
            self.valid(width=1344, height=800)

    def test_lora_forces_four_steps(self):
        self.assertEqual(self.valid(enable_lora=True, steps=20).effective_steps(), 4)
        self.assertEqual(self.valid(enable_lora=False, steps=18).effective_steps(), 18)
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
cd deploy_v3/server
PYTHONPATH=. python3 -m unittest tests.test_schemas -v
```

Expected: import failure because `app.schemas` does not exist.

- [ ] **Step 3: Implement the minimal Pydantic schema**

Use `Literal` for the exact five diffusion models and exact three text encoders. Define list fields with `default_factory=list` and their official maximum lengths. Add one `model_validator(mode="after")` that rejects an empty combined media set and a canvas larger than `768 * 1344`. Width and height use `multiple_of=32`; duration is 5–15; seed is `[0, 2**63)`.

```python
class MiniMaxH3Request(BaseModel):
    images: list[str] = Field(default_factory=list, max_length=9)
    videos: list[str] = Field(default_factory=list, max_length=3)
    audios: list[str] = Field(default_factory=list, max_length=3)
    prompt: str = Field(min_length=1)
    diffusion_model: DiffusionModel = DEFAULT_DIFFUSION_MODEL
    text_encoder: TextEncoder = DEFAULT_TEXT_ENCODER
    enable_lora: bool = False
    duration: float = Field(default=5.0, ge=5.0, le=15.0)
    width: int = Field(default=1344, ge=32, multiple_of=32)
    height: int = Field(default=768, ge=32, multiple_of=32)
    seed: int | None = Field(default=None, ge=0, lt=2**63)
    steps: int = Field(default=20, ge=1, le=100)
    scheduler: Literal["simple", "normal", "beta"] = "simple"
    ref_image_size: Literal["match", "max"] = "match"

    def effective_steps(self) -> int:
        return 4 if self.enable_lora else self.steps
```

Set `requirements.txt` to:

```text
fastapi>=0.115,<1
httpx>=0.27,<1
pydantic>=2.7,<3
uvicorn[standard]>=0.30,<1
```

- [ ] **Step 4: Run the schema tests and verify GREEN**

Run: `PYTHONPATH=. python3 -m unittest tests.test_schemas -v`

Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add deploy_v3/server/app deploy_v3/server/tests/test_schemas.py deploy_v3/server/requirements.txt
git commit -m "feat(deploy-v3): validate minimax h3 requests"
```

---

### Task 2: Official API workflow and dynamic media graph

**Files:**
- Create: `deploy_v3/server/app/workflow.py`
- Create: `deploy_v3/server/app/workflows/minimax-h3-ref2va_api.json`
- Create: `deploy_v3/server/tests/test_workflow.py`

**Interfaces:**
- Consumes: `MiniMaxH3Request` from Task 1 and uploaded filename lists.
- Produces: `frame_count(duration: float) -> int`.
- Produces: `build_workflow(req, image_files, video_files, audio_files) -> tuple[dict, int, int]`; returns workflow, chosen seed, and aligned frame count.

- [ ] **Step 1: Write failing frame and graph tests**

```python
import unittest

from app.schemas import MiniMaxH3Request
from app.workflow import build_workflow, frame_count


class WorkflowTest(unittest.TestCase):
    def request(self, **changes):
        data = {
            "prompt": "Use all references.",
            "images": ["a"],
            "diffusion_model": "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
            "text_encoder": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
            "seed": 42,
        }
        data.update(changes)
        return MiniMaxH3Request(**data)

    def test_frame_count_uses_official_grid(self):
        self.assertEqual(frame_count(5), 124)
        self.assertEqual(frame_count(15), 362)

    def test_builds_dynamic_image_video_audio_nodes(self):
        req = self.request(images=["a", "b"], videos=["c"], audios=["d"])
        graph, seed, frames = build_workflow(
            req, ["one.png", "two.png"], ["clip.mp4"], ["voice.wav"]
        )
        conditioning = graph["136"]["inputs"]
        self.assertEqual(conditioning["ref_images.ref_image_0"], ["1000", 0])
        self.assertEqual(conditioning["ref_images.ref_image_1"], ["1001", 0])
        self.assertEqual(conditioning["ref_videos.ref_video_0"], ["1200", 0])
        self.assertEqual(conditioning["ref_video_audios.ref_video_audio_0"], ["1200", 1])
        self.assertEqual(conditioning["ref_audios.ref_audio_0"], ["1300", 0])
        self.assertEqual(graph["1100"]["class_type"], "LoadVideo")
        self.assertEqual(graph["1200"]["class_type"], "GetVideoComponents")
        self.assertEqual((seed, frames), (42, 124))

    def test_selects_models_and_fixed_vaes(self):
        graph, _, _ = build_workflow(self.request(), ["one.png"], [], [])
        self.assertEqual(graph["127"]["inputs"]["unet_name"], self.request().diffusion_model)
        self.assertEqual(graph["128"]["inputs"]["clip_name"], self.request().text_encoder)
        self.assertEqual(graph["119"]["inputs"]["vae_name"], "minimax_h3_video_vae_fp16.safetensors")
        self.assertEqual(graph["120"]["inputs"]["vae_name"], "minimax_h3_audio_vae_fp32.safetensors")

    def test_lora_switches_model_and_steps(self):
        graph, _, _ = build_workflow(
            self.request(enable_lora=True, steps=20), ["one.png"], [], []
        )
        self.assertEqual(graph["145"]["inputs"]["strength_model"], 1.0)
        self.assertEqual(graph["124"]["inputs"]["model"], ["145", 0])
        self.assertEqual(graph["126"]["inputs"]["model"], ["145", 0])
        self.assertEqual(graph["124"]["inputs"]["steps"], 4)

        graph, _, _ = build_workflow(
            self.request(enable_lora=False, steps=18), ["one.png"], [], []
        )
        self.assertEqual(graph["124"]["inputs"]["model"], ["127", 0])
        self.assertEqual(graph["124"]["inputs"]["steps"], 18)
```

- [ ] **Step 2: Run graph tests and verify RED**

Run: `PYTHONPATH=. python3 -m unittest tests.test_workflow -v`

Expected: import failure because `app.workflow` does not exist.

- [ ] **Step 3: Add the API-format official base workflow**

Convert the execution subgraph of the official `video_minimax_h3_r2v.json` to API format. Keep stable node IDs from the official graph: `92`, `119`–`130`, `136`, and `145`. The graph must contain only:

```text
SaveVideo, two VAELoader nodes, VAEDecodeAudio, VAEDecode,
KSamplerSelect, BasicScheduler, SamplerCustomAdvanced, BasicGuider,
UNETLoader, CLIPLoader, RandomNoise, CreateVideo,
MiniMaxH3ReferenceToVideo, LoraLoaderModelOnly
```

The conditioning node starts without media sockets; the builder inserts only the sockets present in the request. `SaveVideo.filename_prefix` is `video/minimax_h3_ref2va_api`.

- [ ] **Step 4: Implement the minimal workflow builder**

```python
def frame_count(duration: float) -> int:
    frames = max(5, round(duration * 24))
    return frames + (5 - frames % 17) % 17


def build_workflow(req, image_files, video_files, audio_files):
    workflow = load_base_workflow()
    conditioning = workflow["136"]["inputs"]
    for index, filename in enumerate(image_files):
        node_id = str(1000 + index)
        workflow[node_id] = {
            "class_type": "LoadImage",
            "inputs": {"image": filename},
        }
        conditioning[f"ref_images.ref_image_{index}"] = [node_id, 0]
    for index, filename in enumerate(video_files):
        load_id = str(1100 + index)
        components_id = str(1200 + index)
        workflow[load_id] = {
            "class_type": "LoadVideo",
            "inputs": {"file": filename},
        }
        workflow[components_id] = {
            "class_type": "GetVideoComponents",
            "inputs": {"video": [load_id, 0]},
        }
        conditioning[f"ref_videos.ref_video_{index}"] = [components_id, 0]
        conditioning[f"ref_video_audios.ref_video_audio_{index}"] = [components_id, 1]
    for index, filename in enumerate(audio_files):
        node_id = str(1300 + index)
        workflow[node_id] = {
            "class_type": "LoadAudio",
            "inputs": {"audio": filename},
        }
        conditioning[f"ref_audios.ref_audio_{index}"] = [node_id, 0]
```

Complete the same function by setting prompt, width, height, aligned length, `ref_image_size`, scheduler, seed, model filenames, and the active model connection. Verify uploaded filename counts equal request counts before constructing nodes; raise `ValueError` if they differ.

- [ ] **Step 5: Run graph tests and verify GREEN**

Run: `PYTHONPATH=. python3 -m unittest tests.test_workflow -v`

Expected: 4 tests pass.

- [ ] **Step 6: Commit**

```bash
git add deploy_v3/server/app/workflow.py deploy_v3/server/app/workflows deploy_v3/server/tests/test_workflow.py
git commit -m "feat(deploy-v3): build dynamic ref2va workflow"
```

---

### Task 3: ComfyUI client and FastAPI endpoint

**Files:**
- Create: `deploy_v3/server/app/comfyui.py`
- Create: `deploy_v3/server/app/main.py`
- Create: `deploy_v3/server/tests/test_comfyui.py`
- Create: `deploy_v3/server/tests/test_api.py`

**Interfaces:**
- Consumes: `build_workflow()` and `MiniMaxH3Request`.
- Produces: `ComfyUIClient(base_url, poll_interval, workflow_timeout)` with `health`, `upload_media`, `run_workflow`, and `close` async methods.
- Produces: FastAPI `app`, `GET /health`, and `POST /v1/videos/minimax-h3-ref2va/generate`.

- [ ] **Step 1: Write failing media upload tests**

Use `httpx.MockTransport` so the test exercises real Base64 parsing and multipart request construction without a live ComfyUI.

```python
import asyncio
import base64
import unittest

import httpx

from app.comfyui import ComfyUIClient


class ComfyUIClientTest(unittest.TestCase):
    def test_upload_media_accepts_data_url(self):
        async def run():
            async def handler(request):
                self.assertEqual(request.url.path, "/upload/image")
                return httpx.Response(200, json={"name": "uploaded.png"})

            client = ComfyUIClient("http://comfy")
            await client.http.aclose()
            client.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            encoded = "data:image/png;base64," + base64.b64encode(b"image").decode()
            self.assertEqual(await client.upload_media(encoded, "image"), "uploaded.png")
            await client.close()

        asyncio.run(run())

    def test_upload_media_rejects_invalid_base64(self):
        async def run():
            client = ComfyUIClient("http://comfy")
            with self.assertRaisesRegex(ValueError, "Base64"):
                await client.upload_media("not-base64", "image")
            await client.close()

        asyncio.run(run())
```

- [ ] **Step 2: Run the client tests and verify RED**

Run: `PYTHONPATH=. python3 -m unittest tests.test_comfyui -v`

Expected: import failure because `app.comfyui` does not exist.

- [ ] **Step 3: Implement the minimal async ComfyUI client**

Map media kinds to default MIME/suffix values:

```python
MEDIA_DEFAULTS = {
    "image": ("image/png", ".png"),
    "video": ("video/mp4", ".mp4"),
    "audio": ("audio/wav", ".wav"),
}
```

`upload_media` strips a Data URL header, performs strict `base64.b64decode(..., validate=True)`, creates a UUID filename, and posts multipart field `image` to `/upload/image`. `run_workflow` posts `{"prompt": workflow}`, polls `/history/{prompt_id}`, checks `status.status_str`, and downloads output file descriptors through `/view`. Keep only output descriptors that include a filename; classify by file extension and return dictionaries with `node_id`, `filename`, `type`, and `base64`.

- [ ] **Step 4: Run the client tests and verify GREEN**

Run: `PYTHONPATH=. python3 -m unittest tests.test_comfyui -v`

Expected: 2 tests pass.

- [ ] **Step 5: Write the failing endpoint test**

```python
import base64
import unittest
from types import SimpleNamespace

from app.main import generate
from app.schemas import MiniMaxH3Request


class FakeComfyUI:
    def __init__(self):
        self.kinds = []

    async def upload_media(self, encoded, kind):
        self.kinds.append(kind)
        return f"{kind}-{len(self.kinds)}"

    async def run_workflow(self, workflow):
        return [{"node_id": "92", "type": "video", "base64": "bXA0"}]


class ApiTest(unittest.IsolatedAsyncioTestCase):
    async def test_generate_uploads_all_media_and_returns_metadata(self):
        fake = FakeComfyUI()
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(comfyui=fake)))
        body = MiniMaxH3Request(
            prompt="Use all references.",
            images=[base64.b64encode(b"image").decode()],
            videos=[base64.b64encode(b"video").decode()],
            audios=[base64.b64encode(b"audio").decode()],
            seed=42,
        )
        result = await generate(body, request)
        self.assertEqual(fake.kinds, ["image", "video", "audio"])
        self.assertEqual(result["videos"], ["bXA0"])
        self.assertEqual(result["frames"], 124)
        self.assertEqual(result["seed"], 42)
```

- [ ] **Step 6: Run the endpoint test and verify RED**

Run: `PYTHONPATH=. python3 -m unittest tests.test_api -v`

Expected: import failure because `app.main` does not exist.

- [ ] **Step 7: Implement FastAPI lifespan, handlers, and routes**

Read these environment variables at startup:

```python
COMFYUI_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "1"))
WORKFLOW_TIMEOUT = float(os.getenv("WORKFLOW_TIMEOUT", "3600"))
```

The generation route uploads lists in image/video/audio order, calls `build_workflow`, extracts only `type == "video" and node_id == "92"`, and raises HTTP 502 when there is no output. Return `actual_duration = frames / 24` and all metadata defined by the spec. Add small exception handlers mapping `ValueError` to 422, `httpx.HTTPError` and `RuntimeError` to 502, and `TimeoutError` to 504.

- [ ] **Step 8: Run all Python tests and verify GREEN**

Run: `PYTHONPATH=. python3 -m unittest discover -s tests -v`

Expected: all schema, workflow, client, and API tests pass.

- [ ] **Step 9: Commit**

```bash
git add deploy_v3/server/app deploy_v3/server/tests/test_comfyui.py deploy_v3/server/tests/test_api.py
git commit -m "feat(deploy-v3): expose ref2va fastapi endpoint"
```

---

### Task 4: Complete start, stop, and smoke-test scripts

**Files:**
- Create: `deploy_v3/server/extra_model_paths.yaml`
- Create: `deploy_v3/server/start.sh`
- Create: `deploy_v3/server/stop.sh`
- Create: `deploy_v3/server/smoke_test.sh`
- Create: `deploy_v3/server/tests/deploy_scripts_test.sh`
- Create: `deploy_v3/.gitignore`

**Interfaces:**
- `./start.sh` starts ComfyUI and FastAPI and waits for both health checks.
- `./stop.sh` stops only matching recorded processes.
- `SMOKE_IMAGE=/absolute/path/reference.png ./smoke_test.sh` saves an MP4.

- [ ] **Step 1: Write failing shell checks**

Create `tests/deploy_scripts_test.sh` that asserts all three scripts exist and are executable and validates them with `bash -n`. First, start marker sleep processes whose command lines contain the expected ComfyUI and FastAPI virtualenv paths, write their PID files, run `stop.sh`, and assert both stop. Second, start an unrelated marker process, write its PID into `fastapi.pid`, run `stop.sh`, and assert the unrelated process remains alive while the reused PID file is removed.

The central assertions are:

```bash
bash -n "$SERVER_DIR/start.sh"
bash -n "$SERVER_DIR/stop.sh"
bash -n "$SERVER_DIR/smoke_test.sh"
AIGC_RUNTIME_DIR="$RUNTIME_DIR" COMFYUI_DIR="$COMFYUI_DIR" "$SERVER_DIR/stop.sh"
kill -0 "$UNRELATED_PID"
[[ ! -e "$PID_DIR/fastapi.pid" ]]
```

- [ ] **Step 2: Run shell checks and verify RED**

Run: `bash tests/deploy_scripts_test.sh`

Expected: failure because the scripts do not exist.

- [ ] **Step 3: Add the model mapping**

`extra_model_paths.yaml` contains:

```yaml
aigc_models:
  base_path: /root/autodl-tmp/models
  diffusion_models: diffusion_models
  text_encoders: text_encoders
  vae: vae
  loras: loras
```

- [ ] **Step 4: Implement `start.sh`**

Follow the proven PID/log pattern from `deploy_v2/server/start.sh`, reduced to two services. Defaults:

```bash
COMFYUI_DIR="${COMFYUI_DIR:-/root/autodl-tmp/ComfyUI}"
RUNTIME_DIR="${AIGC_RUNTIME_DIR:-${SCRIPT_DIR}/.runtime}"
MODEL_PATH_CONFIG="${MODEL_PATH_CONFIG:-${SCRIPT_DIR}/extra_model_paths.yaml}"
COMFYUI_PORT="${COMFYUI_PORT:-8188}"
API_PORT="${API_PORT:-8000}"
STARTUP_TIMEOUT="${STARTUP_TIMEOUT:-300}"
COMFYUI_STORAGE_ROOT="${COMFYUI_STORAGE_ROOT:-/root/autodl-tmp/comfyui}"
```

Validate Python 3.10+, curl, `${COMFYUI_DIR}/main.py`, `${COMFYUI_DIR}/.venv/bin/python`, the model mapping, and `/root/autodl-tmp/models`. Create the API venv and install requirements only when their SHA-256 changes. Start ComfyUI with:

```bash
"${COMFYUI_DIR}/.venv/bin/python" main.py \
  --listen 127.0.0.1 \
  --port "$COMFYUI_PORT" \
  --extra-model-paths-config "$MODEL_PATH_CONFIG" \
  --input-directory "${COMFYUI_STORAGE_ROOT}/input" \
  --output-directory "${COMFYUI_STORAGE_ROOT}/output" \
  --temp-directory "${COMFYUI_STORAGE_ROOT}/temp"
```

Then start FastAPI with:

```bash
env COMFYUI_URL="http://127.0.0.1:${COMFYUI_PORT}" \
  "${SCRIPT_DIR}/.venv/bin/python" -m uvicorn app.main:app \
  --host 0.0.0.0 --port "$API_PORT"
```

Wait for `/system_stats` and `/health`; fail with the last 40 log lines if either process exits or times out.

- [ ] **Step 5: Implement `stop.sh`**

Reuse the safe behavior from v2: read each PID, confirm it is numeric and running, compare `ps -o command=` with the expected venv executable, send TERM, wait up to `STOP_TIMEOUT=30`, then KILL only that confirmed PID if needed. Stop FastAPI first and ComfyUI second.

- [ ] **Step 6: Implement the real smoke test**

Require a readable `SMOKE_IMAGE`. Use an embedded standard-library Python script to Base64 encode it, POST this body, decode the first video, and save it:

```python
payload = {
    "prompt": os.environ.get(
        "SMOKE_PROMPT",
        "Use <Picture 1> as the character reference in a short cinematic shot.",
    ),
    "images": [base64.b64encode(Path(image_path).read_bytes()).decode()],
    "diffusion_model": os.environ.get(
        "SMOKE_DIFFUSION_MODEL",
        "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
    ),
    "text_encoder": os.environ.get(
        "SMOKE_TEXT_ENCODER",
        "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    ),
    "enable_lora": True,
    "duration": 5,
    "width": 768,
    "height": 448,
    "seed": 1,
}
```

First verify `/health` reports `status == "ok"`. Default output is `.runtime/smoke-test.mp4`; request timeout defaults to 3600 seconds.

- [ ] **Step 7: Add runtime ignores and run shell checks**

Ignore `.runtime/`, `.venv/`, and Python cache files. Mark scripts executable.

Run:

```bash
chmod +x start.sh stop.sh smoke_test.sh tests/deploy_scripts_test.sh
bash tests/deploy_scripts_test.sh
```

Expected: `PASS: deploy scripts`.

- [ ] **Step 8: Commit**

```bash
git add deploy_v3/.gitignore deploy_v3/server/extra_model_paths.yaml deploy_v3/server/*.sh deploy_v3/server/tests/deploy_scripts_test.sh
git commit -m "feat(deploy-v3): add service lifecycle scripts"
```

---

### Task 5: Deployment and usage README

**Files:**
- Create: `deploy_v3/README.md`

**Interfaces:**
- Documents the exact first-install, start, stop, health, API, log, test, and smoke commands.

- [ ] **Step 1: Write the README against the implemented commands**

Include these sections in order:

1. Architecture and requirements: AutoDL Ubuntu, NVIDIA GPU, Python 3.10+.
2. First install: install `git curl ffmpeg python3-venv`, clone/update `/root/autodl-tmp/ComfyUI`, create its `.venv`, and install ComfyUI requirements.
3. Model layout under `/root/autodl-tmp/models`, listing all five diffusion models, all three encoders, both VAEs, and the LoRA.
4. Start/stop/status commands:

```bash
cd /root/autodl-tmp/aigc/deploy_v3/server
chmod +x start.sh stop.sh smoke_test.sh
./start.sh
curl -sS http://127.0.0.1:8000/health
./stop.sh
```

5. Logs:

```bash
tail -f .runtime/logs/comfyui.log
tail -f .runtime/logs/fastapi.log
```

6. API JSON field table and a Python example that Data-URL encodes local image/video/audio files and saves the response MP4.
7. Unit and script tests:

```bash
cd /root/autodl-tmp/aigc/deploy_v3/server
.venv/bin/python -m unittest discover -s tests -v
bash tests/deploy_scripts_test.sh
```

8. Real smoke test:

```bash
SMOKE_IMAGE=/root/autodl-tmp/reference.png ./smoke_test.sh
```

9. Environment overrides: `COMFYUI_DIR`, `COMFYUI_PORT`, `API_PORT`, `COMFYUI_STORAGE_ROOT`, `STARTUP_TIMEOUT`, and `WORKFLOW_TIMEOUT`.
10. Troubleshooting for missing H3 core nodes, missing model files, OOM, timeout, and invalid reference tags.

Link the official sources:

- `https://github.com/Comfy-Org/workflow_templates/blob/main/templates/video_minimax_h3_r2v.json`
- `https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_extras/nodes_minimax_h3.py`

- [ ] **Step 2: Verify every documented command and path exists**

Run:

```bash
test -f README.md
test -x server/start.sh
test -x server/stop.sh
test -x server/smoke_test.sh
test -f server/app/workflows/minimax-h3-ref2va_api.json
rg -n '/root/autodl-tmp/(ComfyUI|models)|start.sh|stop.sh|smoke_test.sh|/health|/v1/videos/minimax-h3-ref2va/generate' README.md
```

Expected: all `test` commands return zero and each required README topic has at least one match.

- [ ] **Step 3: Run the full local verification suite**

Run:

```bash
cd deploy_v3/server
PYTHONPATH=. python3 -m unittest discover -s tests -v
bash tests/deploy_scripts_test.sh
bash -n start.sh stop.sh smoke_test.sh
python3 -m compileall -q app tests
git diff --check
```

Expected: all unit tests and deploy script tests pass, shell syntax and Python compilation succeed, and `git diff --check` reports no errors.

- [ ] **Step 4: Commit**

```bash
git add deploy_v3/README.md
git commit -m "docs(deploy-v3): add minimax h3 deployment guide"
```

---

### Task 6: Final requirements audit

**Files:**
- Verify: `deploy_v3/**`
- Verify: `docs/superpowers/specs/2026-08-22-minimax-h3-ref2va-fastapi-design.md`

**Interfaces:**
- Produces a verified handoff with explicit notice that a real GPU smoke test requires the AutoDL host and installed models.

- [ ] **Step 1: Audit every requested filename and behavior**

Use `rg` to confirm all five diffusion model names, all three encoder names, two VAE names, and the LoRA name occur in the implementation or README. Inspect the endpoint, media list limits, duration/size/seed fields, model root, ComfyUI root, and lifecycle commands against the spec.

- [ ] **Step 2: Re-run the full local verification from Task 5**

Run the complete command block again immediately before reporting completion. Record exact test counts and any environment-limited check.

- [ ] **Step 3: Check repository state**

Run: `git status --short && git log -6 --oneline`

Expected: no uncommitted implementation files and the task commits are visible. Do not run the real GPU smoke test on the local macOS workspace; report the exact AutoDL command from the README as the remaining environment-specific verification.
